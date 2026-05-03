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
import os
import subprocess

from flask import Flask, jsonify, render_template, request

from mercari_api_client import MercariApiClient

SEARCH_TIMEOUT = 4.0
DETAIL_TIMEOUT = 8.0

app = Flask(__name__)
_search_client = MercariApiClient(timeout=SEARCH_TIMEOUT)
_detail_client = MercariApiClient(timeout=DETAIL_TIMEOUT)
_details_cache: Dict[str, Dict[str, Any]] = {}
_latest_draft: Dict[str, Any] = {}


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
        items = _fetch_details_with_cache(ids)
    except Exception as exc:
        app.logger.exception("detail fetch failed")
        return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 502

    return jsonify({"items": items})


@app.route("/api/draft", methods=["GET", "POST"])
def api_draft():
    global _latest_draft
    if request.method == "GET":
        return jsonify({"draft": _latest_draft})

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "draft json object is required"}), 400

    allowed_keys = {
        "id",
        "title",
        "category",
        "condition",
        "description",
        "url",
        "price",
        "thumbnail",
        "shippingPayer",
        "shippingMethod",
        "shippingFrom",
        "shippingDays",
        "saleType",
    }
    _latest_draft = {k: body.get(k) for k in allowed_keys if k in body}
    return jsonify({"ok": True, "draft": _latest_draft})


@app.route("/api/auto-fill", methods=["POST"])
def api_auto_fill():
    if not _latest_draft:
        return jsonify({"error": "No saved draft. Please save draft first."}), 400

    body = request.get_json(silent=True) or {}
    cdp_url = str(body.get("cdpUrl", "") or "").strip()
    script_path = os.path.join(os.path.dirname(__file__), "playwright_fill_sell.py")
    log_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "autofill.log")
    cmd = [
        sys.executable,
        script_path,
        "--base-url",
        "http://127.0.0.1:5000",
        "--log-file",
        log_file,
    ]
    if cdp_url:
        cmd.extend(["--cdp-url", cdp_url])
    try:
        subprocess.Popen(cmd, cwd=os.path.dirname(__file__))
    except Exception as exc:
        return jsonify({"error": f"failed to launch auto-fill: {exc}"}), 500
    return jsonify({"ok": True, "logFile": log_file})


def _fetch_details_with_cache(ids: List[str]) -> List[Dict[str, Any]]:
    missing_ids = [item_id for item_id in ids if item_id not in _details_cache]
    if missing_ids:
        fetched = _detail_client.fetch_details_for_ids(missing_ids)
        for item in fetched:
            item_id = item.get("id")
            if item_id:
                _details_cache[item_id] = item

    # Keep response order aligned with requested ids.
    return [_details_cache[item_id] for item_id in ids if item_id in _details_cache]


def _setup_console_encoding() -> None:
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    _setup_console_encoding()
    debug = os.getenv("FLASK_DEBUG", "1") == "1"
    app.run(host="127.0.0.1", port=5000, debug=debug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
