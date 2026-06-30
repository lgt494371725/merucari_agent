# merucari_agent

## Project Overview

`merucari_agent` is a Python toolkit for querying Japan's Mercari marketplace.

Current modules:
- `mercari_api_client.py`: primary fetch client (search, top N, details)
- `mercari_scraper.py`: Playwright-based browser fallback scraper
- `scoring.py`: keyword/description scoring logic
- `webapp.py`: Flask endpoints for search/details/draft/autofill launch
- `playwright_fill_sell.py`: Playwright autofill script for Mercari sell page via CDP

## Running

### Daily startup on macOS

```bash
./run.sh
```

This script will:
- use the existing `.venv`
- start the webapp
- open Google Chrome with CDP enabled on `http://127.0.0.1:9222`

Press `Ctrl+C` in the terminal running `./run.sh` to stop the webapp.

### Setup

```bash
# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies inside the virtual environment
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m playwright install chromium
```

### Manual run

```bash
source .venv/bin/activate

# Web API/UI
python webapp.py
# open http://127.0.0.1:5000

# Tests
python -m unittest discover -s tests -v
```

If you see `ModuleNotFoundError: No module named 'flask'`, you are probably
using the system/Homebrew Python instead of the virtual environment. Run:

```bash
source .venv/bin/activate
python webapp.py
```

## Listing Workflow (Recommended)

1. Start everything on macOS:
```bash
./run.sh
```

Manual Chrome CDP command for macOS:
```bash
open -na "Google Chrome" --args --remote-debugging-port=9222 --user-data-dir=".pw-user-data/chrome-debug-profile"
```

2. Verify CDP endpoint: `http://127.0.0.1:9222/json/version`.
3. In webapp:
   - search and select item
   - click `Copy to Draft`
   - edit draft fields
   - click `保存草稿（自动出品用）`
   - click `运行自动填表（连接现有浏览器）`
4. Review Mercari sell page manually, then submit.

## Autofill Logs

- Autofill runtime logs are written to:
  - `logs/autofill.log`
- The script logs field-by-field fill result (`ok/skip`) and selector errors for debugging.

## Core API

`MercariApiClient` public methods:
- `search_titles(keyword, top_n)` -> `[{id, title, price, thumbnail}]`
- `fetch_details_for_ids(ids)` -> `[{id, title, description, url, price, thumbnail}]`
- `fetch_items(keyword, top_n)` -> search + all details in one go

Scoring (`scoring.py`):
- `final_score = 0.6 * length_score + 0.4 * coverage_score`
- descriptions shorter than 30 chars are penalized
