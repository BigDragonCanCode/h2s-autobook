from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from scrapers.base import BlockedError  # noqa: E402
from playwright.sync_api import sync_playwright


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
_CHALLENGE_WAIT_SECONDS = 60.0*10
_DEBUG_ARTIFACTS_DIR = Path(__file__).resolve().parent / "debug_artifacts"


class CdpBrowserFetcher:
    """
    Attach to a manually verified real Chrome session over CDP and run
    GraphQL fetches inside that trusted browser context.
    """

    def __init__(self, debug_url: str = "") -> None:
        self._debug_url = (debug_url or os.environ.get("H2S_CDP_URL", "http://127.0.0.1:9222")).strip()
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None

    def __enter__(self) -> "CdpBrowserFetcher":
        from scrapers.base import ScrapeNetworkError  # noqa: E402

        try:
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.connect_over_cdp(self._debug_url)
        except Exception as e:
            raise ScrapeNetworkError(
                f"无法连接到已打开的 Chrome CDP 会话 {self._debug_url}：{e}。"
                "请先启动带 --remote-debugging-port=9222 的 Chrome。"
            ) from e

        self._context = self._browser.contexts[0] if self._browser.contexts else self._browser.new_context()
        self._page = None
        for candidate in self._context.pages:
            if "holland2stay.com" in candidate.url:
                self._page = candidate
                break
        if self._page is None:
            self._page = self._context.new_page()
            self._page.goto(_H2S_MAIN_PAGE, wait_until="domcontentloaded", timeout=60000)
        return self

    def __exit__(self, *args):
        self.close()

    def close(self) -> None:
        # Do not close the real Chrome browser; only drop the Playwright attachment.
        if self._pw is not None:
            try:
                self._pw.stop()
            except Exception:
                pass
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None

    def _has_clearance(self) -> bool:
        try:
            return any(cookie.get("name") == "cf_clearance" for cookie in self._context.cookies())
        except Exception:
            return False

    def _manual_refresh_message(self) -> str:
        return (
            "H2S real Chrome session has no valid Cloudflare clearance. "
            "Please open or refresh holland2stay.com in your real Chrome window, solve Cloudflare manually, "
            "then rerun attach_real_chrome.py to confirm GraphQL works before retrying the scraper."
        )

    def _page_title(self) -> str:
        try:
            return (self._page.title() or "").strip()
        except Exception:
            return ""

    def _page_is_cloudflare_interstitial(self) -> bool:
        title = self._page_title().lower()
        return any(snippet in title for snippet in _CLOUDFLARE_TITLE_SNIPPETS)

    def _refresh_h2s_page(self, reason: str) -> None:
        logger.info("refreshing H2S page in real Chrome session: %s", reason)
        try:
            self._page.goto(_H2S_MAIN_PAGE, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            logger.warning("failed to refresh H2S page in real Chrome session: %s", e)

    def _challenge_message(self, detail: str = "") -> str:
        title = self._page_title()
        suffix = f" Current page title: {title}." if title else ""
        if detail:
            suffix = f" {detail}{suffix}"
        return f"{self._manual_refresh_message()}{suffix}"

    def _save_debug_screenshot(self, label: str) -> str:
        safe_label = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in label).strip("_") or "state"
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        _DEBUG_ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        path = _DEBUG_ARTIFACTS_DIR / f"h2s-{timestamp}-{safe_label}.png"
        try:
            self._page.screenshot(path=str(path), full_page=True)
            logger.warning("saved real Chrome debug screenshot: %s", path)
            return str(path)
        except Exception as e:
            logger.warning("failed to save real Chrome debug screenshot for %s: %s", label, e)
            return ""

    def _raise_blocked(self, detail: str = "", *, screenshot_label: str = "blocked") -> None:
        screenshot_path = self._save_debug_screenshot(screenshot_label)
        if screenshot_path:
            detail = f"{detail} Screenshot: {screenshot_path}.".strip()
        raise BlockedError(self._challenge_message(detail.strip()))

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
            raise ScrapeNetworkError(f"Chrome CDP browser fetch failed: {text}")
        if not result.get("ok") and status >= 400:
            raise ScrapeNetworkError(f"H2S GraphQL via real Chrome returned HTTP {status}: {text[:300]}")
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise ScrapeNetworkError(f"H2S GraphQL via real Chrome returned non-JSON: {e}") from e

    def fetch_gql(self, query: str) -> dict:

        if self._page_is_cloudflare_interstitial():
            logger.info("attached Chrome page is already on Cloudflare interstitial before GraphQL fetch")

        if not self._has_clearance():
            self._raise_blocked("cf_clearance cookie missing in attached Chrome session.", screenshot_label="missing-clearance")

        first_result = self._evaluate_gql_fetch(query)
        first_status = first_result.get("status")
        first_text = first_result.get("text", "")
        if first_status != 403:
            return self._parse_gql_result(first_result)

        logger.warning("real Chrome session GraphQL returned 403 attempt=1 body=%s", first_text[:300])

        self._refresh_h2s_page("GraphQL challenge did not clear within wait window")
        logger.info("GraphQL returned 403 while cf_clearance exists; waiting %.0fs before one retry", _CHALLENGE_WAIT_SECONDS)
        time.sleep(_CHALLENGE_WAIT_SECONDS)
        self._save_debug_screenshot("gql-403-attempt-1")
        logger.info("challenge wait finished; page title=%r", self._page_title())
        
        retry_result = self._evaluate_gql_fetch(query)
        retry_status = retry_result.get("status")
        retry_text = retry_result.get("text", "")
        if retry_status != 403:
            return self._parse_gql_result(retry_result)

        self._raise_blocked("GraphQL returned Cloudflare challenge after 30s polling and one refresh.", screenshot_label="gql-403-retry")
