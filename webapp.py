"""Flask web UI for the Mercari agent.

Run:
    pip install -r requirements.txt
    python webapp.py
    # then open http://127.0.0.1:5000

Mirrors `gui.py` but in the browser. The frontend is the design from
`Mercari Agent.html` (React via CDN + Babel-in-the-browser), wired to
two JSON endpoints backed by `MercariApiClient`:

    GET /api/search?keyword=...&top_n=10  -> {"items": [{id, title, price}]}
    GET /api/details?ids=a,b,c            -> {"items": [{id, title, price, url, description}]}
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List

from flask import Flask, jsonify, render_template, request

from mercari_api_client import MercariApiClient

SEARCH_TIMEOUT = 4.0
DETAIL_TIMEOUT = 8.0

app = Flask(__name__)
_search_client = MercariApiClient(timeout=SEARCH_TIMEOUT)
_detail_client = MercariApiClient(timeout=DETAIL_TIMEOUT)


@app.route("/")
def index() -> str:
    return render_template("index.html")


@app.route("/api/search")
def api_search():
    keyword = (request.args.get("keyword") or "").strip()
    if not keyword:
        return jsonify({"items": []})
    try:
        top_n = max(1, min(50, int(request.args.get("top_n", 10))))
    except (TypeError, ValueError):
        top_n = 10

    try:
        items: List[Dict[str, Any]] = _search_client.search_titles(keyword, top_n=top_n)
    except Exception as exc:  # surface to the UI
        app.logger.exception("search failed")
        return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 502

    return jsonify({"items": items})


@app.route("/api/details")
def api_details():
    raw = request.args.get("ids") or ""
    ids = [s for s in (p.strip() for p in raw.split(",")) if s]
    if not ids:
        return jsonify({"items": []})

    try:
        items = _detail_client.fetch_details_for_ids(ids)
    except Exception as exc:
        app.logger.exception("detail fetch failed")
        return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 502

    return jsonify({"items": items})


def _setup_console_encoding() -> None:
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    _setup_console_encoding()
    app.run(host="127.0.0.1", port=5000, debug=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
