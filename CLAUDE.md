# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`merucari_agent` is a Python CLI tool that scrapes Japan's Mercari marketplace, scores results by description quality and keyword relevance, and returns the best-matching item.

## Running

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium  # only needed for --use-browser fallback

# Default: API client (no browser, fast)
python main.py --keyword "Nintendo Switch" [--top-n 10] [--timeout-ms 20000]

# Legacy: browser-based scraper
python main.py --keyword "Nintendo Switch" --use-browser [--headless] [--timeout-ms 20000]
```

No build step, no test suite, no linter configured.

## Architecture

Three-stage pipeline:

**1. Fetching** — two interchangeable clients with the same `fetch_items(keyword, top_n)` interface

- `mercari_api_client.py` (`MercariApiClient`) — **default, no browser**
  - Search: tries `POST api.mercari.jp/v2/entities:search` → falls back to HTML `__NEXT_DATA__` parsing → regex href extraction
  - Details: tries `GET api.mercari.jp/items/get?id=` → falls back to page HTML `__NEXT_DATA__` / json-ld / og tags
  - Fetches all details **concurrently** via `asyncio` + `httpx` (semaphore-limited to `max_concurrent`)

- `mercari_scraper.py` (`MercariScraper`) — browser fallback (`--use-browser`)
  - Playwright/Chromium with `ja-JP` locale; blocks images/fonts/media for speed
  - Two-phase: Playwright navigation for search links, fast HTTP for detail pages

**2. Scoring** — `scoring.py` (`score_items`)
- `final_score = 0.6 × length_score + 0.4 × coverage_score`
- Penalizes descriptions shorter than 30 chars
- Returns items sorted descending by score

**3. Output** — `main.py` (`main()`)
- Parses CLI args, runs stages, prints summary table + best item details with timing

## Key Implementation Details

- Windows stdout/stderr forced to UTF-8 at startup to handle Japanese characters
- Mercari API may require DPOP tokens (returns 401); both clients transparently fall back to HTML parsing
- `__NEXT_DATA__` (Next.js SSR) is the most reliable HTML data source for both search and item detail pages
