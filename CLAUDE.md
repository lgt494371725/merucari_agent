# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`merucari_agent` is a Python CLI tool that scrapes Japan's Mercari marketplace, scores results by description quality and keyword relevance, and returns the best-matching item.

## Running

```bash
# Install dependencies (Playwright only)
pip install -r requirements.txt
playwright install chromium

# Run
python main.py --keyword "Nintendo Switch" [--top-n 10] [--headless true] [--timeout-ms 20000]
```

No build step, no test suite, no linter configured.

## Architecture

Three-stage pipeline:

**1. Scraping** — `mercari_scraper.py` (`MercariScraper`)
- `fetch_items(keyword, top_n)` orchestrates everything
- Fast path: direct HTTP + regex parsing; fallback: Playwright browser automation
- Blocks images/fonts/media for speed; sets `ja-JP` locale for Japanese text
- Multiple fallback DOM selectors for resilient title/description extraction

**2. Scoring** — `scoring.py` (`score_items`)
- `final_score = 0.6 × length_score + 0.4 × coverage_score`
- Penalizes descriptions shorter than 30 chars
- Returns items sorted descending by score

**3. Output** — `main.py` (`main()`)
- Parses CLI args, runs stages, prints summary table + best item details with timing

## Key Implementation Details

- Windows stdout/stderr forced to UTF-8 at startup to handle Japanese characters
- Cookie dialog auto-accepted before scraping begins
- Generic Mercari template descriptions are detected and treated as empty
- Fast HTTP path is attempted first; browser automation only used as fallback
