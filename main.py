import argparse
import sys
import time
from typing import Dict, List

from mercari_api_client import MercariApiClient
from mercari_scraper import MercariScraper
from scoring import score_items


def setup_console_encoding() -> None:
    # Windows terminals may default to GBK and fail printing Japanese text.
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search Mercari, score item description completeness, and return the best item."
    )
    parser.add_argument(
        "--keyword",
        required=True,
        help="Search keyword, for example: 'dorothy nikke acrylic stand c106'",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=10,
        help="Number of items to fetch from search results (default: 10).",
    )
    parser.add_argument(
        "--headless",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run browser in headless mode (default: true). Only used when --use-browser is set.",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=20000,
        help="Timeout in milliseconds (default: 20000).",
    )
    parser.add_argument(
        "--use-browser",
        action="store_true",
        default=False,
        help="Use browser-based scraper instead of direct API client.",
    )
    return parser.parse_args()


def print_summary(scored_items: List[Dict]) -> None:
    print("\nTop items summary")
    print("-" * 80)
    for index, item in enumerate(scored_items, start=1):
        title = (item.get("title") or "").replace("\n", " ").strip()
        print(
            f"{index:02d}. score={item['final_score']:.4f} "
            f"length={item['description_length']} "
            f"coverage={item['coverage_score']:.4f} "
            f"title={title[:80]}"
        )
    print("-" * 80)


def print_best_item(best_item: Dict) -> None:
    print("\nBest item")
    print("=" * 80)
    print(f"URL: {best_item.get('url', '')}")
    print(f"Score: {best_item['final_score']:.4f}")
    print(f"Title: {best_item.get('title', '').strip()}")
    print("Description:")
    print(best_item.get("description", "").strip() or "(empty)")
    print("=" * 80)


def main() -> int:
    setup_console_encoding()
    total_start = time.perf_counter()
    args = parse_args()
    top_n = max(1, args.top_n)

    fetch_start = time.perf_counter()
    try:
        if args.use_browser:
            client = MercariScraper(headless=args.headless, timeout_ms=args.timeout_ms)
        else:
            client = MercariApiClient(timeout=args.timeout_ms / 1000)
        items = client.fetch_items(keyword=args.keyword, top_n=top_n)
    except Exception as exc:
        print(f"Failed to fetch Mercari items: {exc}", file=sys.stderr)
        return 1
    fetch_elapsed = time.perf_counter() - fetch_start

    if not items:
        print("No items found.")
        print(f"Total elapsed: {time.perf_counter() - total_start:.2f}s")
        return 0

    score_start = time.perf_counter()
    scored_items = score_items(items, args.keyword)
    score_elapsed = time.perf_counter() - score_start
    print_summary(scored_items)
    print_best_item(scored_items[0])
    total_elapsed = time.perf_counter() - total_start
    print("\nTiming")
    print("-" * 80)
    print(f"Fetch elapsed: {fetch_elapsed:.2f}s")
    print(f"Score elapsed: {score_elapsed:.4f}s")
    print(f"Total elapsed: {total_elapsed:.2f}s")
    print("-" * 80)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
