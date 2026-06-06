from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

from config import AutoBookConfig, ListingFilter, load_config
from models import Listing, STATUS_AVAILABLE
from notifier_email import ResendEmailNotifier
from scrapers.holland2stay import HollandStayScraper


def _print_listing(listing: Listing) -> None:
    print(f"- {listing.name}")
    print(f"  city={listing.city} status={listing.status} price={listing.price_display}")
    print(f"  available_from={listing.available_from or '-'}")
    print(f"  url={listing.url}")


def _load_seen_listing_ids(path: Path) -> set[str]:
    try:
        return set(json.loads(path.read_text(encoding="utf-8")))
    except FileNotFoundError:
        return set()
    except Exception:
        return set()


def _save_seen_listing_ids(path: Path, listing_ids: set[str]) -> None:
    path.write_text(json.dumps(sorted(listing_ids), indent=2), encoding="utf-8")


def main() -> int:
    base_dir = Path(__file__).resolve().parent
    log_path = base_dir / "run.log"
    seen_path = base_dir / "seen_filtered_listings.json"
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_path, encoding="utf-8"),
        ],
        force=True,
    )
    logger = logging.getLogger(__name__)
    email_notifier = ResendEmailNotifier.from_env()

    cfg = load_config()
    autobook = AutoBookConfig(
        enabled=True,
        dry_run=True,
        email=os.environ.get("H2S_EMAIL", ""),
        password=os.environ.get("H2S_PASSWORD", ""),
        listing_filter=ListingFilter(
            max_rent=1300,
            allowed_types=["Studio"],
            allowed_cities=["Rotterdam"],
            allowed_contract=["Indefinite"],
        ),
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
    seen_listing_ids = _load_seen_listing_ids(seen_path)
    updated_seen_listing_ids = set(seen_listing_ids)
    for listing in bookable:
        print(f"- {listing.name} ({listing.url})")
        logger.info(
            "passed filter: name=%s city=%s status=%s price=%s available_from=%s url=%s",
            listing.name,
            listing.city,
            listing.status,
            listing.price_display,
            listing.available_from or "-",
            listing.url,
        )
        if listing.id not in seen_listing_ids:
            logger.info("new filtered listing detected: %s", listing.id)
            if email_notifier is not None:
                email_notifier.send_new_listing(listing)
            updated_seen_listing_ids.add(listing.id)

    _save_seen_listing_ids(seen_path, updated_seen_listing_ids)

    if not autobook.enabled:
        print("\nAuto-book disabled. Scrape only.")
        logger.info("auto-book disabled; scrape-only run complete")
        if email_notifier is not None:
            email_notifier.close()
        return 0

    if autobook.dry_run:
        print("\nAuto-book enabled, but dry_run=true. Skipping booker.py entirely.")
        logger.info("auto-book enabled but dry_run=true; skipped booking")
        if email_notifier is not None:
            email_notifier.close()
        return 0

    if not autobook.email or not autobook.password:
        print(
            "\nAuto-book enabled, but H2S_EMAIL or H2S_PASSWORD is missing in .env.",
            file=sys.stderr,
        )
        if email_notifier is not None:
            email_notifier.close()
        return 1

    if not bookable:
        print("\nNo eligible 'Available to book' listings found.")
        logger.info("no eligible 'Available to book' listings found after filter")
        if email_notifier is not None:
            email_notifier.close()
        return 0

    from booker import try_book

    for listing in bookable:
        print(f"\n[BOOK] Attempting booking for {listing.name}")
        logger.info("attempting booking for %s", listing.name)
        result = try_book(
            listing,
            autobook.email,
            autobook.password,
            dry_run=False,
            cancel_enabled=autobook.cancel_enabled,
            payment_method=autobook.payment_method,
        )
        print(result.message)
        logger.info("booking result for %s: success=%s phase=%s", listing.name, result.success, result.phase)
        if result.success and email_notifier is not None:
            email_notifier.send_booking_success(
                listing,
                pay_url=result.pay_url,
                contract_start_date=result.contract_start_date,
            )

    if email_notifier is not None:
        email_notifier.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
