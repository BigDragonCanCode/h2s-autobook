from __future__ import annotations

from dotenv import load_dotenv

from config import ENV_PATH
from notifier_email import ResendEmailNotifier
from models import Listing


def _sample_listing() -> Listing:
    return Listing(
        id="test-listing-001",
        name="Kastanjelaan Sample 12",
        status="Available to book",
        price_raw="€1295",
        basic_rent_raw="€1180",
        available_from="2026-07-01",
        features=[
            "Type: Studio",
            "Area: 42 m²",
            "Occupancy: Single",
            "Floor: 3",
            "Energy: A+",
            "Contract: Indefinite",
        ],
        url="https://example.com/listings/test-listing-001",
        city="Eindhoven",
        sku="TEST-SKU-001",
        contract_id=123,
        contract_start_date="2026-07-01",
        allowance_price="€150",
        source="holland2stay",
    )


def main() -> int:
    load_dotenv(dotenv_path=ENV_PATH, override=True)
    notifier = ResendEmailNotifier.from_env()
    if notifier is None:
        print("Email notifier is not configured. Check RESEND_API_KEY, RESEND_FROM, and NOTIFY_EMAIL_TO.")
        return 1
    try:
        listing = _sample_listing()
        results = [
            ("new listing", notifier.send_new_listing(listing)),
            (
                "new listing digest",
                notifier.send_new_listing_digest(
                    [listing],
                    ordered_by="available_from, then price",
                    listing_type="Studio",
                    range_start="2026-07-01",
                    range_end="2026-07-31",
                ),
            ),
            (
                "booking success",
                notifier.send_booking_success(
                    listing,
                    pay_url="https://example.com/pay/test-order-001",
                    contract_start_date="2026-07-01",
                    order_id="TEST-ORDER-001",
                ),
            ),
            (
                "booking failed",
                notifier.send_booking_failed(
                    listing,
                    reason="Payment authorization expired during checkout.",
                    contract_start_date="2026-07-01",
                    order_id="TEST-ORDER-002",
                ),
            ),
        ]
        failed = [label for label, ok in results if not ok]
        if failed:
            print(f"Email send failed for: {', '.join(failed)}")
            return 1
        print("Sent test emails: " + ", ".join(label for label, _ in results))
        return 0
    finally:
        notifier.close()


if __name__ == "__main__":
    raise SystemExit(main())
