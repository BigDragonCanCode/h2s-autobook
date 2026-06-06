# Third-Party Notices

## Upstream Source

This repository includes code copied from and derived from:

- Repository: `751K/holland2stay-monitor`
- URL: <https://github.com/751K/holland2stay-monitor>

The copied files were extracted from the upstream repository and added into this repository as a starting point for further work.

## Copied or Derived Files

The following files in this repository were copied from or derived from the upstream repository:

- `booker.py`
- `scraper.py`
- `config.py`
- `models.py`
- `notifier_email.py`
- `scrapers/base.py`
- `scrapers/holland2stay.py`

In particular, `notifier_email.py` is a partial extraction and adaptation of the upstream email notification logic from:

- `notifier.py`

The local environment examples also reuse relevant configuration keys derived from the upstream example configuration file:

- `.env.example`

In addition:

- `scrapers/__init__.py` was added locally so the extracted `scrapers` directory works as a Python package in this repository.

## How The Files Were Copied

The upstream source files were fetched from the public GitHub repository and copied into this repository with their structure preserved where practical.

The extraction was based on the upstream `booker.py` file, the upstream `scrapers/holland2stay.py` file, the upstream `notifier.py` email notification implementation, the upstream `.env.example`, and the helper modules those files directly import or depend on in the upstream project.

The intent of this extraction was to preserve the original behavior and import relationships closely enough that the copied files remain understandable and workable in isolation inside this repository.

## License

The upstream repository includes a `LICENSE` file identifying the upstream code as licensed under:

- `PolyForm Noncommercial License 1.0.0`
- License URL: <https://polyformproject.org/licenses/noncommercial/1.0.0>

Upstream license file:

- <https://github.com/751K/holland2stay-monitor/blob/master/LICENSE>

These copied or derived upstream portions remain subject to that upstream license.

In practical terms, that means:

- The upstream-derived code may be copied and modified.
- The upstream-derived code is intended for noncommercial use under the upstream license terms.
- Anyone receiving a copy of the upstream-derived portions should also be given the upstream license text or license URL.

This notice is included to document the source of the copied code and to preserve the relevant upstream license reference for the derived portions of this repository.

## Modify

Local modifications made so far include:

- Added an `allowance_price` field for listing result handling.
- Extracted and adapted only the email-related notification path for:
  new filtered listings and booking success notifications.
- Added local monitor/runner entrypoints (`run.py` and `monitor.py`) around the extracted modules.
- Added local runner-specific notification state tracking for previously seen filtered listings.
- Batched newly seen filtered listings into a single email digest per run instead of sending one email per listing.
- Added local runner-side filtering and ordering rules for:
  rent, type, city, contract, and available-from date range checks.
- Added local environment-driven booking controls for:
  enable/disable, dry-run, cancel-on-conflict, and payment-method selection.
- Added local persistent skip state for successful bookings via:
  `booked_success_listing_ids.json`, so future monitor cycles do not re-attempt a listing that already booked successfully once.
- Sorted email digest listings by available-from date first, then by price.

Additional modification notes can be added here later.
