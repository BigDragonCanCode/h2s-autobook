from __future__ import annotations

import logging
import os
import re
from html import escape as html_escape

import curl_cffi.requests as req

from config import get_impersonate
from models import Listing

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]+$")


def get_shared_email_config() -> tuple[bool, str, str]:
    enabled = os.environ.get("SHARED_EMAIL_ENABLED", "true").lower() != "false"
    api_key = os.environ.get("RESEND_API_KEY", "").strip()
    from_addr = os.environ.get("RESEND_FROM", "").strip()
    if enabled and from_addr and not _EMAIL_RE.match(from_addr):
        logger.error("RESEND_FROM format invalid: %r", from_addr)
        enabled = False
    return (enabled and bool(api_key) and bool(from_addr), api_key, from_addr)


def get_notify_recipient() -> str:
    return os.environ.get("NOTIFY_EMAIL_TO", "").strip()


def _split_email_recipients(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"[,;\n]+", value or "") if part.strip()]


def _strip_leading_symbol(value: str) -> str:
    return re.sub(r"^[^\w\u4e00-\u9fff]+", "", value or "").strip() or value


def _format_email_subject(text: str) -> str:
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "FlatRadar notice")
    first_line = re.sub(r"\s+", " ", first_line)
    first_line = _strip_leading_symbol(first_line)
    if len(first_line) > 80:
        first_line = first_line[:77].rstrip() + "..."
    return f"[FlatRadar] {first_line}"


def _format_email_html(text: str) -> str:
    raw_lines = text.splitlines()
    non_empty = [line.strip() for line in raw_lines if line.strip()]
    title = _strip_leading_symbol(non_empty[0]) if non_empty else "FlatRadar notice"
    safe_title = html_escape(title)

    paragraph_blocks: list[str] = []
    current: list[str] = []
    for line in raw_lines:
        if line.strip():
            current.append(html_escape(line.strip()))
        elif current:
            paragraph_blocks.append("<br>".join(current))
            current = []
    if current:
        paragraph_blocks.append("<br>".join(current))

    body_html = "\n".join(
        f'<p style="margin:0 0 14px;color:#374151;font-size:14px;line-height:1.7;">{block}</p>'
        for block in paragraph_blocks
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{safe_title}</title>
</head>
<body style="margin:0;padding:0;background:#f5f7fb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;color:#1f2530;">
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#f5f7fb;padding:32px 16px;">
  <tr>
    <td align="center">
      <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="560" style="max-width:560px;width:100%;background:#ffffff;border-radius:18px;box-shadow:0 8px 32px rgba(20,30,50,.08);overflow:hidden;">
        <tr>
          <td style="padding:30px 34px 12px;">
            <div style="font-size:12px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:#2f8cff;">FlatRadar</div>
            <h1 style="margin:12px 0 8px;font-size:22px;font-weight:700;line-height:1.3;color:#111827;">{safe_title}</h1>
          </td>
        </tr>
        <tr>
          <td style="padding:12px 34px 18px;">{body_html}</td>
        </tr>
      </table>
    </td>
  </tr>
</table>
</body>
</html>"""


def _source_short(source: str | None) -> str:
    value = (source or "holland2stay").strip().lower()
    return {"holland2stay": "H2S", "ourdomain": "OD"}.get(value, value.upper() or "H2S")


def format_new_listing(l: Listing) -> str:
    fm = l.feature_map()
    source = _source_short(getattr(l, "source", ""))
    lines = [
        f"[{source}] New Listing",
        "",
        l.name,
        f"Status: {l.status}",
        f"Basic rent: {l.basic_rent_display}/mo",
        f"Total monthly cost: {l.price_display}/mo",
        f"Available: {l.available_from or '?'}",
    ]
    if getattr(l, "allowance_price", None):
        lines.append(f"Allowance: {l.allowance_price}")
    lines.extend([
        "",
        f"Type: {fm.get('type', '—')}",
        f"Area: {fm.get('area', '—')}",
        f"Occupancy: {fm.get('occupancy', '—')}",
        f"Floor: {fm.get('floor', '—')}",
        f"Energy: {fm.get('energy_label', '—')}",
        "",
        l.url,
    ])
    return "\n".join(lines)


def format_new_listing_digest(
    listings: list[Listing],
    *,
    ordered_by: str,
    listing_type: str,
    range_start: str,
    range_end: str,
) -> str:
    lines = [
        f"New Listings ({len(listings)})",
        f"Ordered by: {ordered_by}",
        f"Type: {listing_type}",
        f"Monitoring time range: from {range_start} to {range_end}",
        "",
    ]
    for index, listing in enumerate(listings, start=1):
        fm = listing.feature_map()
        source = _source_short(getattr(listing, "source", ""))
        lines.extend([
            f"{index}. [{source}] {listing.name}",
            f"Status: {listing.status}",
            f"Basic rent: {listing.basic_rent_display}/mo",
            f"Total monthly cost: {listing.price_display}/mo",
            f"Available: {listing.available_from or '?'}",
        ])
        if getattr(listing, "allowance_price", None):
            lines.append(f"Allowance: {listing.allowance_price}")
        lines.extend([
            f"Type: {fm.get('type', '—')}",
            f"Area: {fm.get('area', '—')}",
            f"Floor: {fm.get('floor', '—')}",
            f"Energy: {fm.get('energy_label', '—')}",
            f"Contract: {fm.get('contract', '—')}",
            listing.url,
            "",
        ])
    return "\n".join(lines).rstrip()


def format_booking_success(
    l: Listing,
    pay_url: str = "",
    contract_start_date: str = "",
    order_id: str = "",
) -> str:
    start = contract_start_date or l.available_from or "?"
    source = _source_short(getattr(l, "source", ""))
    lines = [
        f"[{source}] Booking Successful!",
        "",
        l.name,
        f"Order ID: {order_id or '-'}",
        f"Basic rent: {l.basic_rent_display}/mo",
        f"Total monthly cost: {l.price_display}/mo",
        f"Move-in: {start}",
    ]
    if getattr(l, "allowance_price", None):
        lines.append(f"Allowance: {l.allowance_price}")
    lines.extend([
        "",
        "Pay now (expire in 1 hour):",
        "",
        pay_url or l.url,
        "",
        "Original listing:",
        "",
        l.url,
    ])
    return "\n".join(lines)


def format_booking_failed(
    l: Listing,
    *,
    reason: str = "",
    contract_start_date: str = "",
    order_id: str = "",
) -> str:
    start = contract_start_date or l.contract_start_date or l.available_from or "?"
    source = _source_short(getattr(l, "source", ""))
    lines = [
        f"[{source}] Booking Failed - Manual Action Required",
        "",
        l.name,
        f"Order ID: {order_id or '-'}",
        f"Basic rent: {l.basic_rent_display}/mo",
        f"Total monthly cost: {l.price_display}/mo",
        f"Move-in: {start}",
    ]
    if getattr(l, "allowance_price", None):
        lines.append(f"Allowance: {l.allowance_price}")
    lines.extend([
        "",
        "Booking failed automatically.",
    ])
    if reason:
        lines.extend([
            "",
            "Failure reason:",
            "",
            reason,
        ])
    lines.extend([
        "",
        "Original listing:",
        "",
        l.url,
        "",
        "Please open the original listing link above and complete the booking manually.",
    ])
    return "\n".join(lines)


class ResendEmailNotifier:
    ENDPOINT = "https://api.resend.com/emails"

    def __init__(self, api_key: str, from_addr: str, to_addrs: str) -> None:
        self._api_key = api_key.strip()
        self._from = from_addr.strip()
        self._to = to_addrs.strip()
        self._session = req.Session(impersonate=get_impersonate())

    @classmethod
    def from_env(cls) -> "ResendEmailNotifier | None":
        enabled, api_key, from_addr = get_shared_email_config()
        to_addrs = get_notify_recipient()
        if not enabled:
            return None
        if not to_addrs:
            logger.info("shared email configured but NOTIFY_EMAIL_TO is empty; email notifications disabled")
            return None
        return cls(api_key, from_addr, to_addrs)

    def send_text(self, text: str) -> bool:
        recipients = _split_email_recipients(self._to)
        if not recipients:
            logger.error("email send failed: recipient is empty")
            return False
        payload = {
            "from": self._from,
            "to": recipients,
            "subject": _format_email_subject(text),
            "text": text,
            "html": _format_email_html(text),
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            resp = self._session.post(self.ENDPOINT, json=payload, headers=headers, timeout=15)
        except Exception as e:
            logger.error("resend network error: %s", e)
            return False
        if 200 <= resp.status_code < 300:
            logger.info("email sent to %s", ", ".join(recipients))
            return True
        logger.error("resend send failed %s: %s", resp.status_code, resp.text[:300])
        return False

    def send_new_listing(self, listing: Listing) -> bool:
        return self.send_text(format_new_listing(listing))

    def send_new_listing_digest(
        self,
        listings: list[Listing],
        *,
        ordered_by: str,
        listing_type: str,
        range_start: str,
        range_end: str,
    ) -> bool:
        return self.send_text(
            format_new_listing_digest(
                listings,
                ordered_by=ordered_by,
                listing_type=listing_type,
                range_start=range_start,
                range_end=range_end,
            )
        )

    def send_booking_success(
        self,
        listing: Listing,
        pay_url: str = "",
        contract_start_date: str = "",
        order_id: str = "",
    ) -> bool:
        return self.send_text(format_booking_success(listing, pay_url, contract_start_date, order_id))

    def send_booking_failed(
        self,
        listing: Listing,
        *,
        reason: str = "",
        contract_start_date: str = "",
        order_id: str = "",
    ) -> bool:
        return self.send_text(
            format_booking_failed(
                listing,
                reason=reason,
                contract_start_date=contract_start_date,
                order_id=order_id,
            )
        )

    def close(self) -> None:
        self._session.close()
