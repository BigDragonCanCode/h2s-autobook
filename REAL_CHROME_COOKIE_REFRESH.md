# Real Chrome Cookie Refresh

Use this flow when Holland2Stay scraping is configured to use your real Chrome session via CDP and Cloudflare clearance expires.

## 1. Start a dedicated Chrome session with remote debugging

Run:

```bash
/usr/bin/google-chrome \
  --remote-debugging-port=9222 \
  --user-data-dir=/tmp/h2s-real-chrome
```

This opens a separate Chrome profile just for H2S scraping.

## 2. Open Holland2Stay and solve Cloudflare manually

In that Chrome window:

1. Open `https://www.holland2stay.com/residences`
2. If Cloudflare shows `Verify you are human`, click it manually
3. Wait until the page is no longer stuck on `Just a moment...`

## 3. Confirm GraphQL works in that exact Chrome session

Run:

```bash
python3 attach_real_chrome.py
```

Expected result:

- it attaches to `http://127.0.0.1:9222`
- it detects `cf_clearance`
- it probes `/api/graphql`
- it prints `GraphQL access works in the real Chrome session.`

If it still prints a blocked status, refresh the page in Chrome and solve Cloudflare again.

## 4. Use the scraper in CDP mode

Set these in `.env`:

```env
H2S_USE_REAL_CHROME_CDP=true
H2S_CDP_URL=http://127.0.0.1:9222
```

Then run your normal scripts, for example:

```bash
python3 run.py
python3 test_building_filter.py
```

## 5. When it fails later

If H2S scraping starts returning a message about missing or expired Cloudflare clearance:

1. Keep the dedicated Chrome window open
2. Go back to the H2S tab
3. Refresh and solve Cloudflare manually again
4. Rerun:

```bash
python3 attach_real_chrome.py
```

5. Retry the scraper

## Notes

- Do not close the dedicated Chrome window while scraping depends on it.
- This flow reuses a legitimate browser session after manual verification; it does not bypass Cloudflare.
- `attach_real_chrome.py` attaches to the Chrome you started manually; it does not launch a separate browser process.
