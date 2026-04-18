## Project Overview

`merucari_agent` is a Python tool that queries Japan's Mercari marketplace. Two entry points:
- **`gui.py`** — interactive Tk GUI: enter keyword → pick from a list of titles → view full details for selected items
- **`main.py`** — CLI that auto-picks the single best match using `scoring.py`

## Running

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium  # only needed for --use-browser fallback

# Interactive GUI (tkinter, bundled with Python)
python gui.py

# CLI: auto-score + print best match
python main.py --keyword "Nintendo Switch" [--top-n 10] [--timeout-ms 20000]

# CLI: force Playwright browser (legacy)
python main.py --keyword "Nintendo Switch" --use-browser [--headless]
```

No build step, no test suite, no linter configured.

## Architecture

Three-stage pipeline:

**1. Fetching** — `mercari_api_client.py` (`MercariApiClient`) is the default; `mercari_scraper.py` (`MercariScraper`) is the Playwright fallback (`--use-browser`)

`MercariApiClient` public methods:
- `search_titles(keyword, top_n)` → `[{id, title}]` — one API call, no detail fetches (used by GUI for the first step)
- `fetch_details_for_ids(ids)` → `[{id, title, description, url}]` — concurrent detail fetches (used by GUI after selection)
- `fetch_items(keyword, top_n)` → search + all details in one go (used by CLI)

Under the hood:
- Search: `POST api.mercari.jp/v2/entities:search` (falls back to HTML `__NEXT_DATA__` / regex hrefs)
- Details: `GET api.mercari.jp/items/get?id=` (falls back to item page HTML parsing)
- Concurrency: `asyncio` + `httpx.AsyncClient`, semaphore-limited to `max_concurrent` (default 8)

**2. Scoring** — `scoring.py` (`score_items`), used only by the CLI
- `final_score = 0.6 × length_score + 0.4 × coverage_score`; sub-30-char descriptions are penalized

**3. Presentation**
- `gui.py` — Tk window (listbox + multi-select + details pane). Background fetches run on a thread; results are marshalled back with `root.after(0, ...)` to stay on the Tk thread.
- `main.py` — CLI summary table + best item

## Key Implementation Details

- **DPoP authentication is mandatory** for `api.mercari.jp`. `_DpopSigner` generates an ES256-signed JWT per request (ephemeral P-256 key, `htu`/`htm`/`jti`/`iat`/`uuid` claims). Without it the API returns `401 missing auth token`.
- Item detail response is wrapped as `{"result":"OK","data":{...}}` — `_detail_via_api` unwraps `body["data"]` before reading `name`/`description`.
- Mercari JP's website is now fully CSR — the search HTML contains no `__NEXT_DATA__` and no `/item/m...` hrefs, so the HTML fallback is practically dead; the API path is the real one.
- Windows stdout/stderr is forced to UTF-8 on startup so Japanese text prints correctly.
