# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`merucari_agent` is a Python toolkit for querying Japan's Mercari marketplace.

Current modules:
- `mercari_api_client.py`: primary fetch client (search, top N, details)
- `mercari_scraper.py`: Playwright-based browser fallback scraper
- `scoring.py`: keyword/description scoring logic
- `webapp.py`: Flask endpoints for search/details

## Running

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Web API/UI
python webapp.py
# open http://127.0.0.1:5000

# Tests
python -m unittest discover -s tests -v
```

## Core API

`MercariApiClient` public methods:
- `search_titles(keyword, top_n)` -> `[{id, title, price, thumbnail}]`
- `fetch_details_for_ids(ids)` -> `[{id, title, description, url, price, thumbnail}]`
- `fetch_items(keyword, top_n)` -> search + all details in one go

Scoring (`scoring.py`):
- `final_score = 0.6 * length_score + 0.4 * coverage_score`
- descriptions shorter than 30 chars are penalized
