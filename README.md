# h2s-autobook

Small local monitor around extracted parts of `751K/holland2stay-monitor`.

What is copied or derived:

- `booker.py`
- `scraper.py`
- `config.py`
- `models.py`
- `notifier_email.py`
- `scrapers/base.py`
- `scrapers/holland2stay.py`
- parts of the upstream `.env.example` config surface

What is changed locally:

- continuous local monitor loop in `monitor.py`
- one-shot runner in `run.py`
- shared email digest behavior for newly seen filtered listings
- local filter/date-window logic for booking candidates
- persistent `seen_filtered_listings.json` for digest dedupe
- persistent `booked_success_listing_ids.json` to skip future re-attempts after a successful booking

Autobook building-name filter:

- Set `AUTO_BOOK_ALLOWED_BUILDINGS` in `.env` as a `|`-separated list of partial matches.
- Matching is case-insensitive and checks `listing.name`.
- Example: `AUTO_BOOK_ALLOWED_BUILDINGS=Kastanjelaan|Docks`

For full source, license, and adaptation details, see [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md).
