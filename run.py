from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from config import AutoBookConfig, load_config
from models import Listing, STATUS_AVAILABLE
from scrapers.holland2stay import HollandStayScraper


def _print_listing(listing: Listing) -> None:
    print(f"- {listing.name}")
    print(f"  city={listing.city} status={listing.status} price={listing.price_display}")
    print(f"  available_from={listing.available_from or '-'}")
    print(f"  url={listing.url}")


def main() -> int:
    log_path = Path(__file__).resolve().parent / "run.log"
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_path, encoding="utf-8"),
        ],
        force=True,
    )

    cfg = load_config()
    autobook = AutoBookConfig(
        enabled=True,
        dry_run=True,
        email=os.environ.get("H2S_EMAIL", ""),
        password=os.environ.get("H2S_PASSWORD", ""),
        cancel_enabled=False,
        payment_method="idealcheckout_visa",
    )
    scraper = HollandStayScraper()

    all_listings: list[Listing] = []

    with scraper.batch_session():
        for task in cfg.scrape_tasks_v2():
            result = scraper.scrape(task)
            if result.error:
                print(f"[ERROR] {task.city_display}: {result.error}", file=sys.stderr)
            print(
                f"[SCRAPE] city={task.city_display} source={task.source} "
                f"listings={len(result.listings)} complete={result.complete}"
            )
            all_listings.extend(result.listings)

    print(f"\nTotal listings scraped: {len(all_listings)}")
    for listing in all_listings:
        _print_listing(listing)

    bookable = [
        listing
        for listing in all_listings
        if listing.status.lower() == STATUS_AVAILABLE
        and autobook.listing_filter.passes(listing)
    ]

    print(f"\nAvailable to book after filter: {len(bookable)}")
    for listing in bookable:
        print(f"- {listing.name} ({listing.url})")

    if not autobook.enabled:
        print("\nAuto-book disabled. Scrape only.")
        return 0

    if autobook.dry_run:
        print("\nAuto-book enabled, but dry_run=true. Skipping booker.py entirely.")
        return 0

    if not autobook.email or not autobook.password:
        print(
            "\nAuto-book enabled, but H2S_EMAIL or H2S_PASSWORD is missing in .env.",
            file=sys.stderr,
        )
        return 1

    if not bookable:
        print("\nNo eligible 'Available to book' listings found.")
        return 0

    from booker import try_book

    for listing in bookable:
        print(f"\n[BOOK] Attempting booking for {listing.name}")
        result = try_book(
            listing,
            autobook.email,
            autobook.password,
            dry_run=False,
            cancel_enabled=autobook.cancel_enabled,
            payment_method=autobook.payment_method,
        )
        print(result.message)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
