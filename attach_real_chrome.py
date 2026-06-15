from __future__ import annotations

import json
import time

from playwright.sync_api import sync_playwright


DEBUG_URL = "http://127.0.0.1:9222"
TARGET_URL = "https://www.holland2stay.com/residences"


def _probe_graphql(page) -> tuple[int | None, str]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Store": "default",
        "Content-Currency": "EUR",
    }
    body = {
        "query": """
{
  products(
    filter: {
      category_uid: { eq: "Nw==" }
      city: { in: ["29"] }
      available_to_book: { in: ["179", "336"] }
    },
    pageSize: 5,
    currentPage: 1
  ) {
    total_count
    items {
      name
      url_key
    }
  }
}
""".strip(),
        "variables": {},
    }
    js = f"""
        async () => {{
            try {{
                const resp = await fetch('/api/graphql', {{
                    method: 'POST',
                    credentials: 'include',
                    mode: 'same-origin',
                    cache: 'no-store',
                    redirect: 'follow',
                    referrer: window.location.href,
                    referrerPolicy: 'strict-origin-when-cross-origin',
                    headers: {json.dumps(headers)},
                    body: {json.dumps(json.dumps(body))},
                }});
                const text = await resp.text();
                return {{ status: resp.status, text }};
            }} catch (err) {{
                return {{ status: null, text: String(err) }};
            }}
        }}
    """
    result = page.evaluate(js)
    return result.get("status"), result.get("text", "")


def main() -> int:
    print("Attach target:", DEBUG_URL)
    print("Make sure Chrome is running with remote debugging enabled.")
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(DEBUG_URL)
        context = browser.contexts[0] if browser.contexts else browser.new_context()

        page = None
        for candidate in context.pages:
            if "holland2stay.com" in candidate.url:
                page = candidate
                break
        if page is None:
            page = context.new_page()
            page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)

        print("Using page:", page.url)
        print("Solve Cloudflare in your real Chrome window if needed.")

        last_title = ""
        while True:
            title = page.title()
            if title != last_title:
                print("title=", title)
                last_title = title

            cookies = context.cookies()
            has_clearance = any(cookie.get("name") == "cf_clearance" for cookie in cookies)
            if has_clearance:
                print("cf_clearance detected")
                status, text = _probe_graphql(page)
                print("graphql_status=", status)
                print("graphql_body=", text[:500].replace("\n", " "))
                if status == 200:
                    print("GraphQL access works in the real Chrome session.")
                    while True:
                        time.sleep(60)
            time.sleep(2)


if __name__ == "__main__":
    raise SystemExit(main())
