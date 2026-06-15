from __future__ import annotations

import json
import logging
import os

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

    def fetch_gql(self, query: str) -> dict:
        from scrapers.base import BlockedError, ScrapeNetworkError  # noqa: E402

        if not self._has_clearance():
            raise BlockedError(self._manual_refresh_message())

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
        result = self._page.evaluate(js)
        status = result.get("status")
        text = result.get("text", "")

        if status is None:
            raise ScrapeNetworkError(f"Chrome CDP browser fetch failed: {text}")
        if status == 403:
            logger.warning("real Chrome session GraphQL returned 403 body=%s", text[:300])
            raise BlockedError(self._manual_refresh_message())
        if not result.get("ok") and status >= 400:
            raise ScrapeNetworkError(f"H2S GraphQL via real Chrome returned HTTP {status}: {text[:300]}")
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise ScrapeNetworkError(f"H2S GraphQL via real Chrome returned non-JSON: {e}") from e
