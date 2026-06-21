from __future__ import annotations

import atexit
import json
import logging
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from scrapers.base import BlockedError


logger = logging.getLogger(__name__)

_H2S_MAIN_PAGE = "https://www.holland2stay.com/residences"
_H2S_GQL_PATH = "/api/graphql"
_H2S_GQL_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Store": "default",
    "Content-Currency": "EUR",
}
_CLOUDFLARE_TITLE_SNIPPETS = (
    "just a moment",
    "verify you are human",
    "attention required",
)
_CHALLENGE_WAIT_SECONDS = 15.0
_DEBUG_ARTIFACTS_DIR = Path(__file__).resolve().parent / "debug_artifacts"
_SHARED_SB = None
_SHARED_ENDPOINT_URL = ""


def _shutdown_shared_sb() -> None:
    global _SHARED_SB, _SHARED_ENDPOINT_URL
    if _SHARED_SB is not None:
        try:
            _SHARED_SB.quit()
        except Exception:
            pass
    _SHARED_SB = None
    _SHARED_ENDPOINT_URL = ""


atexit.register(_shutdown_shared_sb)


class SeleniumBaseCdpFetcher:
    """
    Launch a SeleniumBase CDP browser, attach Playwright to it, and run H2S
    GraphQL fetches inside that session.
    """

    def __init__(self) -> None:
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None
        self._sb = None

    def __enter__(self) -> "SeleniumBaseCdpFetcher":
        from scrapers.base import ScrapeNetworkError  # noqa: E402
        global _SHARED_ENDPOINT_URL, _SHARED_SB

        try:
            from seleniumbase import sb_cdp
        except Exception as e:
            raise ScrapeNetworkError(
                f"SeleniumBase CDP mode is unavailable: {e}. Install seleniumbase to use H2S SeleniumBase CDP mode."
            ) from e

        if _SHARED_SB is None:
            try:
                _SHARED_SB = sb_cdp.Chrome(guest=True, incognito=True, locale="en")
                _SHARED_ENDPOINT_URL = _SHARED_SB.get_endpoint_url()
                logger.info("started shared SeleniumBase CDP browser")
            except Exception as e:
                _shutdown_shared_sb()
                raise ScrapeNetworkError(f"Failed to start SeleniumBase CDP browser: {e}") from e

        self._sb = _SHARED_SB

        try:
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.connect_over_cdp(_SHARED_ENDPOINT_URL)
        except Exception as e:
            self.close()
            raise ScrapeNetworkError(f"Failed to attach Playwright to SeleniumBase CDP browser: {e}") from e

        self._context = self._browser.contexts[0] if self._browser.contexts else self._browser.new_context()
        self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
        if "holland2stay.com" not in (self._page.url or ""):
            self._page.goto(_H2S_MAIN_PAGE, wait_until="domcontentloaded", timeout=60000)
        self._maybe_solve_captcha("initial page load")
        return self

    def __exit__(self, *args):
        self.close()

    def close(self) -> None:
        if self._pw is not None:
            try:
                self._pw.stop()
            except Exception:
                pass
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None
        self._sb = None

    def _page_title(self) -> str:
        try:
            return (self._page.title() or "").strip()
        except Exception:
            return ""

    def _page_is_cloudflare_interstitial(self) -> bool:
        title = self._page_title().lower()
        return any(snippet in title for snippet in _CLOUDFLARE_TITLE_SNIPPETS)

    def _manual_refresh_message(self) -> str:
        return (
            "H2S SeleniumBase CDP session is still on a Cloudflare challenge page. "
            "Please inspect the saved screenshot/HTML artifacts and confirm whether the challenge can be solved automatically."
        )

    def _challenge_message(self, detail: str = "") -> str:
        title = self._page_title()
        suffix = f" Current page title: {title}." if title else ""
        if detail:
            suffix = f" {detail}{suffix}"
        return f"{self._manual_refresh_message()}{suffix}"

    def _save_debug_artifacts(self, label: str, body: str = "") -> str:
        safe_label = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in label).strip("_") or "state"
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        _DEBUG_ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        png_path = _DEBUG_ARTIFACTS_DIR / f"h2s-sb-{timestamp}-{safe_label}.png"
        html_path = _DEBUG_ARTIFACTS_DIR / f"h2s-sb-{timestamp}-{safe_label}.html"
        try:
            self._page.screenshot(path=str(png_path), full_page=True)
            logger.warning("saved SeleniumBase CDP screenshot: %s", png_path)
        except Exception as e:
            logger.warning("failed to save SeleniumBase CDP screenshot for %s: %s", label, e)
        if body:
            try:
                html_path.write_text(body, encoding="utf-8")
                logger.warning("saved SeleniumBase CDP response body: %s", html_path)
            except Exception as e:
                logger.warning("failed to save SeleniumBase CDP response body for %s: %s", label, e)
        return str(png_path)

    def _raise_blocked(self, detail: str = "", *, screenshot_label: str = "blocked", body: str = "") -> None:
        screenshot_path = self._save_debug_artifacts(screenshot_label, body=body)
        if screenshot_path:
            detail = f"{detail} Screenshot: {screenshot_path}.".strip()
        raise BlockedError(self._challenge_message(detail.strip()))

    def _maybe_solve_captcha(self, reason: str) -> None:
        if not self._page_is_cloudflare_interstitial():
            return
        logger.info("SeleniumBase CDP saw Cloudflare challenge during %s; trying solve_captcha()", reason)
        try:
            if hasattr(self._sb, "solve_captcha"):
                self._sb.solve_captcha()
                time.sleep(5)
                logger.info("post-solve title=%r", self._page_title())
        except Exception as e:
            logger.warning("SeleniumBase solve_captcha() failed during %s: %s", reason, e)

    def _evaluate_gql_fetch(self, query: str) -> dict:
        body = {"query": query, "variables": {}}
        js = f"""
            async () => {{
                try {{
                    const resp = await fetch('{_H2S_GQL_PATH}', {{
                        method: 'POST',
                        credentials: 'include',
                        mode: 'same-origin',
                        cache: 'no-store',
                        redirect: 'follow',
                        referrer: window.location.href,
                        referrerPolicy: 'strict-origin-when-cross-origin',
                        headers: {json.dumps(_H2S_GQL_HEADERS)},
                        body: {json.dumps(json.dumps(body))},
                    }});
                    const text = await resp.text();
                    return {{ status: resp.status, ok: resp.ok, text }};
                }} catch (err) {{
                    return {{ status: null, ok: false, text: String(err) }};
                }}
            }}
        """
        return self._page.evaluate(js)

    def _parse_gql_result(self, result: dict) -> dict:
        from scrapers.base import ScrapeNetworkError  # noqa: E402

        status = result.get("status")
        text = result.get("text", "")
        if status is None:
            raise ScrapeNetworkError(f"SeleniumBase CDP browser fetch failed: {text}")
        if not result.get("ok") and status >= 400:
            raise ScrapeNetworkError(f"H2S GraphQL via SeleniumBase CDP returned HTTP {status}: {text[:300]}")
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise ScrapeNetworkError(f"H2S GraphQL via SeleniumBase CDP returned non-JSON: {e}") from e

    def fetch_gql(self, query: str) -> dict:
        first_result = self._evaluate_gql_fetch(query)
        first_status = first_result.get("status")
        first_text = first_result.get("text", "")
        if first_status != 403:
            return self._parse_gql_result(first_result)

        logger.warning("SeleniumBase CDP GraphQL returned 403 attempt=1 body=%s", first_text[:300])
        self._page.goto(_H2S_MAIN_PAGE, wait_until="domcontentloaded", timeout=60000)
        self._maybe_solve_captcha("post-403 refresh")
        logger.info("GraphQL returned 403 in SeleniumBase CDP; waiting %.0fs before one retry", _CHALLENGE_WAIT_SECONDS)
        time.sleep(_CHALLENGE_WAIT_SECONDS)

        retry_result = self._evaluate_gql_fetch(query)
        retry_status = retry_result.get("status")
        retry_text = retry_result.get("text", "")
        if retry_status != 403:
            return self._parse_gql_result(retry_result)

        self._raise_blocked(
            "GraphQL returned Cloudflare challenge after SeleniumBase captcha solve attempt and one refresh.",
            screenshot_label="gql-403-retry",
            body=retry_text,
        )
