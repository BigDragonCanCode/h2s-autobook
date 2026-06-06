from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from config import AutoBookConfig, ENV_PATH, ListingFilter, load_config
from models import Listing
from notifier_email import ResendEmailNotifier
from scrapers.holland2stay import HollandStayScraper


def _print_listing(listing: Listing) -> None:
    print(f"- {listing.name}")
    print(f"  city={listing.city} status={listing.status} price={listing.price_display}")
    print(f"  available_from={listing.available_from or '-'}")
    print(f"  url={listing.url}")


def _load_listing_id_set(path: Path) -> set[str]:
    try:
        return set(json.loads(path.read_text(encoding="utf-8")))
    except FileNotFoundError:
        return set()
    except Exception:
        return set()


def _save_listing_id_set(path: Path, listing_ids: set[str]) -> None:
    path.write_text(json.dumps(sorted(listing_ids), indent=2), encoding="utf-8")
def _env_enabled(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() == "true"


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.environ.get(name)
    if raw is None:
        return list(default)
    return [part.strip() for part in raw.split("|") if part.strip()]


def _env_float(name: str, default: float | None) -> float | None:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return float(raw.strip())


def _listing_book_key(listing: Listing) -> str:
    source = (getattr(listing, "source", "") or "holland2stay").strip().lower()
    return f"{source}:{listing.id}"


def _listing_sort_key(listing: Listing) -> tuple[str, float]:
    price = listing.price_value
    available_from = listing.available_from or "9999-99-99"
    return (available_from, price if price is not None else float("inf"))


def setup_logging() -> logging.Logger:
    base_dir = Path(__file__).resolve().parent
    log_path = base_dir / "run.log"
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_path, encoding="utf-8"),
        ],
        force=True,
    )
    return logging.getLogger(__name__)


def build_autobook_config() -> AutoBookConfig:
    return AutoBookConfig(
        enabled=_env_enabled("AUTO_BOOK_ENABLED", False),
        dry_run=_env_enabled("AUTO_BOOK_DRY_RUN", True),
        email=os.environ.get("H2S_EMAIL", ""),
        password=os.environ.get("H2S_PASSWORD", ""),
        listing_filter=ListingFilter(
            max_rent=_env_float("AUTO_BOOK_MAX_RENT", 1300),
            allowed_types=_env_list("AUTO_BOOK_ALLOWED_TYPES", ["Studio"]),
            allowed_contract=_env_list("AUTO_BOOK_ALLOWED_CONTRACTS", ["Indefinite"]),
            available_from_start=os.environ.get("MONITOR_RANGE_START", "").strip(),
            available_from_end=os.environ.get("MONITOR_RANGE_END", "").strip(),
        ),
        cancel_enabled=_env_enabled("AUTO_BOOK_CANCEL_ENABLED", False),
        payment_method=os.environ.get("AUTO_BOOK_PAYMENT_METHOD", "idealcheckout_visa").strip() or "idealcheckout_visa",
    )


def run_once() -> int:
    base_dir = Path(__file__).resolve().parent
    seen_path = base_dir / "seen_filtered_listings.json"
    booked_path = base_dir / "booked_success_listing_ids.json"
    logger = logging.getLogger(__name__)
    email_notifier = ResendEmailNotifier.from_env()
    try:
        cfg = load_config()
        autobook = build_autobook_config()
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

        for listing in all_listings:
            _print_listing(listing)

        bookable = [
            listing
            for listing in all_listings
            if autobook.listing_filter.passes(listing)
        ]

        print(f"\nAvailable to book after filter: {len(bookable)}")
        logger.info("total scraped listings: %d; after filter: %d", len(all_listings), len(bookable))

        seen_listing_ids = _load_listing_id_set(seen_path)
        booked_listing_ids = _load_listing_id_set(booked_path)
        updated_seen_listing_ids = set(seen_listing_ids)
        updated_booked_listing_ids = set(booked_listing_ids)
        new_filtered_listings: list[Listing] = []
        booking_candidates: list[Listing] = []
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
                new_filtered_listings.append(listing)
                updated_seen_listing_ids.add(listing.id)
            book_key = _listing_book_key(listing)
            if book_key in booked_listing_ids:
                logger.info("skipping previously booked listing: %s", book_key)
                continue
            booking_candidates.append(listing)

        if new_filtered_listings and email_notifier is not None:
            new_filtered_listings.sort(key=_listing_sort_key)
            logger.info("sending one digest email for %d new filtered listings", len(new_filtered_listings))
            email_notifier.send_new_listing_digest(
                new_filtered_listings,
                ordered_by="available_from, then price",
                listing_type="Studio",
                range_start=autobook.listing_filter.available_from_start,
                range_end=autobook.listing_filter.available_from_end,
            )

        _save_listing_id_set(seen_path, updated_seen_listing_ids)

        if not autobook.enabled:
            print("\nAuto-book disabled. Scrape only.")
            logger.info("auto-book disabled; scrape-only run complete")
            return 0

        if autobook.dry_run:
            print("\nAuto-book enabled, but dry_run=true. Skipping booker.py entirely.")
            logger.info("auto-book enabled but dry_run=true; skipped booking")
            return 0

        if not autobook.email or not autobook.password:
            print(
                "\nAuto-book enabled, but H2S_EMAIL or H2S_PASSWORD is missing in .env.",
                file=sys.stderr,
            )
            return 1

        if not booking_candidates:
            print("\nNo eligible 'Available to book' listings left to attempt.")
            logger.info("no eligible 'Available to book' listings left after booked-skip filtering")
            return 0

        from booker import try_book

        for listing in booking_candidates:
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
            if result.success:
                updated_booked_listing_ids.add(_listing_book_key(listing))
                _save_listing_id_set(booked_path, updated_booked_listing_ids)

        return 0
    finally:
        if email_notifier is not None:
            email_notifier.close()


def main() -> int:
    load_dotenv(dotenv_path=ENV_PATH, override=True)
    setup_logging()
    return run_once()


if __name__ == "__main__":
    raise SystemExit(main())
