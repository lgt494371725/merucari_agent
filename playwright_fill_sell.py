import argparse
import json
import logging
from typing import Any, Dict, Iterable
from urllib.request import Request, urlopen

from playwright.sync_api import Page, sync_playwright

SELL_URL = "https://jp.mercari.com/sell/create"


def setup_logging(log_file: str) -> None:
    handlers = [logging.StreamHandler()]
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=handlers,
    )


def _http_get_json(url: str) -> Dict[str, Any]:
    req = Request(url, method="GET")
    with urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _first_visible(page: Page, selectors: Iterable[str]):
    for sel in selectors:
        loc = page.locator(sel).first
        try:
            if loc.is_visible(timeout=800):
                return loc
        except Exception:
            continue
    return None


def _fill_text(page: Page, name: str, selectors: Iterable[str], value: str) -> bool:
    if not value:
        logging.info("skip %s: empty value", name)
        return False
    loc = _first_visible(page, selectors)
    if not loc:
        logging.warning("skip %s: no selector matched", name)
        return False
    loc.fill(value)
    logging.info("filled %s", name)
    return True


def _pick_select_or_combobox(page: Page, label_text: str, value: str) -> bool:
    if not value:
        logging.info("skip select %s: empty value", label_text)
        return False
    # 1) Native <select> path: robust and does not need visible option clicks.
    try:
        selects = page.locator("select")
        for i in range(selects.count()):
            sel = selects.nth(i)
            options = sel.locator("option")
            texts = []
            for j in range(options.count()):
                txt = (options.nth(j).inner_text() or "").strip()
                texts.append(txt)
            if value in texts:
                sel.select_option(label=value)
                logging.info("selected(native) %s = %s", label_text, value)
                return True
    except Exception as exc:
        logging.info("native select path failed for %s: %s", label_text, exc)

    # 2) Combobox/button path near label.
    try:
        block = page.locator(f"text={label_text}").first
        if not block.is_visible(timeout=1200):
            logging.warning("skip select %s: label not visible", label_text)
            return False
        container = block.locator("xpath=ancestor::*[self::div or self::section][1]")
        combo = container.locator('[role="combobox"], button').first
        combo.click(timeout=1200)
        # Option can be role=option/listitem/button depending on frontend impl.
        candidates = [
            f'[role="option"]:has-text("{value}")',
            f'[role="listbox"] *:has-text("{value}")',
            f'li:has-text("{value}")',
            f'button:has-text("{value}")',
            f'text="{value}"',
        ]
        for sel_text in candidates:
            opt = page.locator(sel_text).first
            if opt.is_visible(timeout=800):
                opt.click(timeout=1000)
                logging.info("selected(combo) %s = %s", label_text, value)
                return True
        logging.warning("skip select %s: option not found %s", label_text, value)
        return False
    except Exception as exc:
        logging.warning("skip select %s: %s", label_text, exc)
        return False


def _fill_listing(page: Page, draft: Dict[str, Any]) -> Dict[str, bool]:
    result = {
        "title": False,
        "description": False,
        "price": False,
        "condition": False,
        "shipping_payer": False,
        "shipping_days": False,
        "shipping_from": False,
    }

    result["title"] = _fill_text(
        page,
        "title",
        ['input[name="name"]', 'input[placeholder*="商品名"]', 'input[maxlength="40"]'],
        str(draft.get("title", "") or ""),
    )
    result["description"] = _fill_text(
        page,
        "description",
        ['textarea[name="description"]', 'textarea[placeholder*="商品の説明"]', "textarea"],
        str(draft.get("description", "") or ""),
    )
    price_value = str(draft.get("price", "") or "")
    price_value = (
        price_value.replace(",", "")
        .replace("¥", "")
        .replace("￥", "")
        .replace("楼", "")
        .strip()
    )
    result["price"] = _fill_text(
        page,
        "price",
        ['input[name="price"]', 'input[inputmode="numeric"]', 'input[placeholder*="価格"]'],
        price_value,
    )

    result["condition"] = _pick_select_or_combobox(
        page, "商品の状態", str(draft.get("condition", "") or "")
    )
    result["shipping_payer"] = _pick_select_or_combobox(
        page, "配送料の負担", str(draft.get("shippingPayer", "") or "")
    )
    result["shipping_days"] = _pick_select_or_combobox(
        page, "発送までの日数", str(draft.get("shippingDays", "") or "")
    )
    result["shipping_from"] = _pick_select_or_combobox(
        page, "発送元の地域", str(draft.get("shippingFrom", "") or "")
    )
    return result


def load_draft_from_webapp(base_url: str) -> Dict[str, Any]:
    payload = _http_get_json(f"{base_url.rstrip('/')}/api/draft")
    draft = payload.get("draft")
    if not isinstance(draft, dict) or not draft:
        raise RuntimeError("No saved draft found. Please save draft in webapp first.")
    logging.info("loaded draft keys: %s", ", ".join(sorted(draft.keys())))
    return draft


def run_via_cdp(base_url: str, cdp_url: str) -> None:
    draft = load_draft_from_webapp(base_url)
    with sync_playwright() as p:
        logging.info("connecting to CDP: %s", cdp_url)
        browser = p.chromium.connect_over_cdp(cdp_url)
        context = browser.contexts[0] if browser.contexts else browser.new_context(locale="ja-JP")
        page = context.new_page()
        page.goto(SELL_URL, wait_until="domcontentloaded")
        # Wait for form core fields to render.
        try:
            page.wait_for_selector("textarea, input", timeout=8000)
        except Exception:
            logging.warning("form selector wait timed out; continue best-effort")
        page.wait_for_timeout(1500)
        result = _fill_listing(page, draft)
        logging.info("auto-fill result: %s", result)
        logging.info("please review fields manually before submitting")
        page.bring_to_front()
        page.wait_for_timeout(3000)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fill Mercari sell/create form from saved webapp draft via Playwright."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:5000")
    parser.add_argument("--cdp-url", default="http://127.0.0.1:9222")
    parser.add_argument("--log-file", default="")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.log_file)
    run_via_cdp(base_url=args.base_url, cdp_url=args.cdp_url)
