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

Real Chrome CDP mode for H2S:

- Set `H2S_USE_REAL_CHROME_CDP=true` in `.env` to make the H2S scraper run GraphQL requests inside a manually verified real Chrome session instead of direct `curl_cffi`.
- Optional: set `H2S_CDP_URL=http://127.0.0.1:9222` if you want a non-default CDP endpoint.
- When Cloudflare clearance expires, the scraper will fail with a message telling you to refresh the real Chrome session and rerun `attach_real_chrome.py`.
- Helper scripts:
  - `attach_real_chrome.py` attaches to the already-open Chrome session and confirms whether `/api/graphql` works.
  - `manual_cf_browser.py` opens a separate persistent Chromium profile and waits for manual Cloudflare verification, but the main working path is the real Chrome CDP session.

For full source, license, and adaptation details, see [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md).
