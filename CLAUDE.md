# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`merucari_agent` is a Python toolkit for querying Japan's Mercari marketplace.

Current modules:
- `mercari_api_client.py`: primary fetch client (search, top N, details)
- `mercari_scraper.py`: Playwright-based browser fallback scraper
- `scoring.py`: keyword/description scoring logic
- `webapp.py`: Flask endpoints for search/details/draft/autofill launch
- `playwright_fill_sell.py`: Playwright autofill script for Mercari sell page via CDP

## Running

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Web API/UI
python webapp.py
# open http://127.0.0.1:5000

# Tests
python -m unittest discover -s tests -v          # Python (stdlib unittest)
node --test tests/test_recent_keywords.mjs       # JS (Node 18+ built-in runner)
```

## Listing Workflow (Recommended)

1. Start webapp.
2. Start Chrome with CDP enabled (close all Chrome windows first):
```powershell
& "$env:ProgramFiles\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\tmp\chrome-debug-profile"
```
3. Verify CDP endpoint: `http://127.0.0.1:9222/json/version`.
4. In webapp:
   - search and select item
   - click `Copy to Draft`
   - edit draft fields
   - click `保存草稿（自动出品用）`
   - click `运行自动填表（连接现有浏览器）`
5. Review Mercari sell page manually, then submit.

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
