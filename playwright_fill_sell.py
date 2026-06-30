import argparse
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable
from urllib.request import Request, urlopen

from playwright.sync_api import Page, sync_playwright

SELL_URL = "https://jp.mercari.com/sell/create"
VISIBLE_TIMEOUT_MS = 250
ACTION_TIMEOUT_MS = 500
NAV_TIMEOUT_MS = 2500
SHIPPING_METHOD_OPTIONS = ("らくらくメルカリ便", "ゆうゆうメルカリ便")

SET_INPUT_VALUE_JS = """
({ selectors, value }) => {
  const setValue = (el, nextValue) => {
    const proto = el instanceof HTMLTextAreaElement
      ? HTMLTextAreaElement.prototype
      : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
    if (setter) {
      setter.call(el, nextValue);
    } else {
      el.value = nextValue;
    }
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  };
  const isUsable = (el) => {
    if (!el || el.disabled || el.readOnly) return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };
  for (const selector of selectors) {
    for (const el of document.querySelectorAll(selector)) {
      if (!isUsable(el)) continue;
      setValue(el, value);
      return selector;
    }
  }
  return null;
}
"""

SELECT_OPTION_BY_LABEL_JS = """
({ value }) => {
  const wanted = String(value).trim();
  if (!wanted) return null;
  for (const select of document.querySelectorAll("select")) {
    if (select.disabled) continue;
    const option = Array.from(select.options).find((opt) => opt.textContent.trim() === wanted);
    if (!option) continue;
    select.value = option.value;
    select.dispatchEvent(new Event("input", { bubbles: true }));
    select.dispatchEvent(new Event("change", { bubbles: true }));
    return option.textContent.trim();
  }
  return null;
}
"""

CLICK_VISIBLE_TEXT_JS = """
({ texts }) => {
  const normalize = (s) => String(s || "").replace(/\\s+/g, " ").trim();
  const wanted = texts.map(normalize).filter(Boolean);
  const isVisible = (el) => {
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.visibility !== "hidden"
      && style.display !== "none"
      && rect.width > 0
      && rect.height > 0;
  };
  const clickableAncestor = (el) => {
    const selector = "button,a,label,li,[role='button'],[role='option'],[role='radio'],[tabindex]";
    const direct = el.closest(selector);
    if (direct) return direct;
    let cur = el;
    for (let i = 0; i < 5 && cur; i += 1, cur = cur.parentElement) {
      const style = window.getComputedStyle(cur);
      const role = cur.getAttribute("role") || "";
      if (role === "radio" || role === "button" || style.cursor === "pointer") return cur;
      if (cur.tagName === "DIV" && normalize(cur.textContent).length <= 400) return cur;
    }
    return el;
  };
  const candidates = Array.from(document.querySelectorAll("button,a,label,li,[role='button'],[role='option'],[role='radio'],[tabindex],div,span,p"));
  for (const text of wanted) {
    const matches = candidates
      .map((el) => [el, normalize(el.textContent)])
      .filter(([el, ownText]) => {
        if (!isVisible(el) || !ownText || !ownText.includes(text)) return false;
        return ownText.length <= Math.max(text.length + 80, text.length * 4);
      })
      .sort((a, b) => a[1].length - b[1].length);
    for (const [el] of matches) {
      if (!isVisible(el)) continue;
      clickableAncestor(el).click();
      return text;
    }
  }
  return null;
}
"""


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


def _first_visible(page: Page, selectors: Iterable[str], timeout_ms: int = VISIBLE_TIMEOUT_MS):
    for sel in selectors:
        loc = page.locator(sel).first
        try:
            if loc.is_visible(timeout=timeout_ms):
                return loc
        except Exception:
            continue
    return None


def _set_text_value_fast(page: Page, selectors: Iterable[str], value: str) -> bool:
    try:
        matched = page.evaluate(SET_INPUT_VALUE_JS, {"selectors": list(selectors), "value": value})
    except Exception as exc:
        logging.info("fast text fill failed: %s", exc)
        return False
    return bool(matched)


def _fill_text(page: Page, name: str, selectors: Iterable[str], value: str) -> bool:
    if not value:
        logging.info("skip %s: empty value", name)
        return False
    selectors = list(selectors)
    if _set_text_value_fast(page, selectors, value):
        logging.info("filled(fast) %s", name)
        return True
    loc = _first_visible(page, selectors)
    if not loc:
        logging.warning("skip %s: no selector matched", name)
        return False
    loc.fill(value, timeout=ACTION_TIMEOUT_MS)
    logging.info("filled %s", name)
    return True


def _select_native_by_label_fast(page: Page, label_text: str, value: str) -> bool:
    try:
        matched = page.evaluate(SELECT_OPTION_BY_LABEL_JS, {"value": value})
    except Exception as exc:
        logging.info("fast native select failed for %s: %s", label_text, exc)
        return False
    if matched:
        logging.info("selected(native-fast) %s = %s", label_text, value)
        return True
    return False


def _choice_text_variants(value: str) -> list[str]:
    value = (value or "").strip()
    if not value:
        return []
    variants = [value]
    variants.append(value.replace("、", ","))
    variants.append(value.replace(",", "、"))
    return list(dict.fromkeys(v for v in variants if v))


def _clean_price(value: Any) -> str:
    return (
        str(value or "")
        .replace(",", "")
        .replace("¥", "")
        .replace("￥", "")
        .replace("楼", "")
        .strip()
    )


def _normalize_shipping_method(value: str) -> str:
    value = (value or "").strip()
    if value in SHIPPING_METHOD_OPTIONS:
        return value
    return ""


@dataclass(frozen=True)
class ListingDraft:
    title: str = ""
    description: str = ""
    price: str = ""
    condition: str = ""
    shipping_payer: str = ""
    shipping_method: str = ""
    shipping_days: str = ""
    shipping_from: str = ""

    @classmethod
    def from_payload(cls, draft: Dict[str, Any]) -> "ListingDraft":
        return cls(
            title=str(draft.get("title", "") or ""),
            description=str(draft.get("description", "") or ""),
            price=_clean_price(draft.get("price", "")),
            condition=str(draft.get("condition", "") or ""),
            shipping_payer=str(draft.get("shippingPayer", "") or ""),
            shipping_method=_normalize_shipping_method(str(draft.get("shippingMethod", "") or "")),
            shipping_days=str(draft.get("shippingDays", "") or ""),
            shipping_from=str(draft.get("shippingFrom", "") or ""),
        )


def _click_visible_text_fast(page: Page, values: Iterable[str]) -> bool:
    texts = []
    for value in values:
        texts.extend(_choice_text_variants(str(value)))
    try:
        matched = page.evaluate(CLICK_VISIBLE_TEXT_JS, {"texts": texts})
    except Exception as exc:
        logging.info("fast text click failed: %s", exc)
        return False
    return bool(matched)


def _click_text_option(page: Page, values: Iterable[str], timeout_ms: int = NAV_TIMEOUT_MS) -> bool:
    texts = []
    for value in values:
        texts.extend(_choice_text_variants(str(value)))
    if not texts:
        return False
    deadline = time.monotonic() + (timeout_ms / 1000)
    while time.monotonic() < deadline:
        if _click_visible_text_fast(page, texts):
            return True
        for text in texts:
            candidates = [
                f'text="{text}"',
                f'li:has-text("{text}")',
                f'button:has-text("{text}")',
                f'label:has-text("{text}")',
                f'[role="button"]:has-text("{text}")',
                f'[role="option"]:has-text("{text}")',
                f'[role="radio"]:has-text("{text}")',
            ]
            option = _first_visible(page, candidates, timeout_ms=120)
            if option:
                try:
                    option.scroll_into_view_if_needed(timeout=ACTION_TIMEOUT_MS)
                    option.click(timeout=ACTION_TIMEOUT_MS)
                    return True
                except Exception as exc:
                    logging.info("text option click failed for %s: %s", text, exc)
        page.wait_for_timeout(100)
    return False


def _click_field_entry(page: Page, label_text: str, trigger_texts: Iterable[str]) -> bool:
    selectors = []
    for text in trigger_texts:
        selectors.extend(
            [
                f'text="{text}"',
                f'a:has-text("{text}")',
                f'button:has-text("{text}")',
                f'[role="button"]:has-text("{text}")',
                f'label:has-text("{text}")',
            ]
        )
    trigger = _first_visible(page, selectors, timeout_ms=500)
    if trigger:
        try:
            trigger.scroll_into_view_if_needed(timeout=ACTION_TIMEOUT_MS)
            trigger.click(timeout=ACTION_TIMEOUT_MS)
            return True
        except Exception as exc:
            logging.info("field trigger click failed for %s: %s", label_text, exc)

    # Last resort for Mercari list-style rows where only text/divs are exposed.
    return _click_text_option(page, trigger_texts, timeout_ms=800)


MAIN_FORM_SELECTOR = 'textarea, input[name="name"], input[name="price"]'


def _wait_for_main_form(page: Page) -> None:
    try:
        page.wait_for_selector(MAIN_FORM_SELECTOR, timeout=NAV_TIMEOUT_MS)
    except Exception:
        logging.info("main form wait timed out; continue best-effort")


def _return_to_main_form_if_needed(page: Page) -> None:
    try:
        page.wait_for_timeout(150)
        if page.locator(MAIN_FORM_SELECTOR).first.is_visible(timeout=200):
            return
        page.go_back(wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
    except Exception as exc:
        logging.info("return to main form skipped: %s", exc)
    _wait_for_main_form(page)


def _pick_select_or_combobox(page: Page, label_text: str, value: str) -> bool:
    if not value:
        logging.info("skip select %s: empty value", label_text)
        return False
    if _select_native_by_label_fast(page, label_text, value):
        return True

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
                sel.select_option(label=value, timeout=ACTION_TIMEOUT_MS)
                logging.info("selected(native) %s = %s", label_text, value)
                return True
    except Exception as exc:
        logging.info("native select path failed for %s: %s", label_text, exc)

    # 2) Mercari mobile-style/list-page path: click field row, then click list item.
    trigger_texts = [f"{label_text}を選択する", label_text]
    if _click_field_entry(page, label_text, trigger_texts):
        if _click_text_option(page, [value]):
            _return_to_main_form_if_needed(page)
            logging.info("selected(list-page) %s = %s", label_text, value)
            return True
        logging.warning("skip select %s: list option not found %s", label_text, value)
        return False

    # 3) Combobox/button path near label.
    try:
        block = page.locator(f"text={label_text}").first
        if not block.is_visible(timeout=VISIBLE_TIMEOUT_MS):
            logging.warning("skip select %s: label not visible", label_text)
        else:
            container = block.locator("xpath=ancestor::*[self::div or self::section][1]")
            combo = container.locator('[role="combobox"], button').first
            combo.click(timeout=ACTION_TIMEOUT_MS)
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
                if opt.is_visible(timeout=VISIBLE_TIMEOUT_MS):
                    opt.click(timeout=ACTION_TIMEOUT_MS)
                    logging.info("selected(combo) %s = %s", label_text, value)
                    return True
            logging.warning("skip select %s: combo option not found %s", label_text, value)
    except Exception as exc:
        logging.warning("skip select %s: %s", label_text, exc)

    logging.warning("skip select %s: trigger not found", label_text)
    return False


def _pick_condition(page: Page, value: str) -> bool:
    """商品の状態 is sometimes not a native select; handle modal/list flows."""
    if not value or value == "未設定":
        logging.info("skip condition: empty or default value")
        return False

    # Try generic strategy first.
    if _pick_select_or_combobox(page, "商品の状態", value):
        return True

    trigger_texts = ["商品の状態を選択する", "商品の状態"]
    if not _click_field_entry(page, "商品の状態", trigger_texts):
        logging.warning("skip condition: trigger not found")
        return False

    if not _click_text_option(page, [value]):
        logging.warning("skip condition: option not found %s", value)
        return False

    confirm = _first_visible(
        page,
        ['button:has-text("決定")', 'button:has-text("完了")', 'button:has-text("保存")'],
        timeout_ms=200,
    )
    if confirm:
        try:
            confirm.click(timeout=ACTION_TIMEOUT_MS)
        except Exception as exc:
            logging.info("condition confirm click skipped: %s", exc)
    _return_to_main_form_if_needed(page)
    logging.info("selected(condition) = %s", value)
    return True


def _pick_shipping_method(page: Page, value: str) -> bool:
    value = _normalize_shipping_method(value)
    if not value:
        logging.info("skip shipping method: empty value")
        return False

    # Some Mercari builds expose this as a hidden/native select. Do not run the
    # generic combobox path here: it can enter the shipping page and leave us in
    # an ambiguous state before the card/radio strategy runs.
    if _select_native_by_label_fast(page, "配送の方法", value):
        return True

    trigger_texts = ["配送の方法を選択する", "配送方法を選択する", "配送の方法"]
    if not _click_field_entry(page, "配送の方法", trigger_texts):
        logging.warning("skip shipping method: trigger not found")
        return False

    if not _click_text_option(page, [value]):
        logging.warning("skip shipping method: option not found %s", value)
        return False

    confirm = _first_visible(
        page,
        [
            'button:has-text("更新する")',
            '[role="button"]:has-text("更新する")',
            'text="更新する"',
            'button:has-text("決定")',
            'button:has-text("完了")',
            'button:has-text("保存")',
        ],
        timeout_ms=800,
    )
    if confirm:
        try:
            confirm.scroll_into_view_if_needed(timeout=ACTION_TIMEOUT_MS)
            confirm.click(timeout=ACTION_TIMEOUT_MS)
            logging.info("confirmed(shipping method)")
        except Exception as exc:
            logging.info("shipping method confirm click skipped: %s", exc)

    # Shipping method pages often keep the selected radio highlighted. Returning
    # to the create form preserves the selection and lets the remaining fields fill.
    _return_to_main_form_if_needed(page)
    logging.info("selected(shipping method) = %s", value)
    return True


class MercariSellFiller:
    def __init__(self, page: Page) -> None:
        self.page = page

    def fill(self, draft: ListingDraft) -> Dict[str, bool]:
        result = {
            "title": False,
            "description": False,
            "price": False,
            "condition": False,
            "shipping_payer": False,
            "shipping_method": False,
            "shipping_days": False,
            "shipping_from": False,
        }

        result["title"] = _fill_text(
            self.page,
            "title",
            ['input[name="name"]', 'input[placeholder*="商品名"]', 'input[maxlength="40"]'],
            draft.title,
        )
        result["description"] = _fill_text(
            self.page,
            "description",
            ['textarea[name="description"]', 'textarea[placeholder*="商品の説明"]', "textarea"],
            draft.description,
        )
        result["price"] = _fill_text(
            self.page,
            "price",
            ['input[name="price"]', 'input[inputmode="numeric"]', 'input[placeholder*="価格"]'],
            draft.price,
        )

        result["condition"] = _pick_condition(self.page, draft.condition)
        result["shipping_payer"] = _pick_select_or_combobox(
            self.page, "配送料の負担", draft.shipping_payer
        )
        result["shipping_method"] = _pick_shipping_method(self.page, draft.shipping_method)
        result["shipping_days"] = _pick_select_or_combobox(
            self.page, "発送までの日数", draft.shipping_days
        )
        result["shipping_from"] = _pick_select_or_combobox(
            self.page, "発送元の地域", draft.shipping_from
        )
        return result


def _fill_listing(page: Page, draft: Dict[str, Any]) -> Dict[str, bool]:
    return MercariSellFiller(page).fill(ListingDraft.from_payload(draft))


def load_draft_from_webapp(base_url: str) -> Dict[str, Any]:
    payload = _http_get_json(f"{base_url.rstrip('/')}/api/draft")
    draft = payload.get("draft")
    if not isinstance(draft, dict) or not draft:
        raise RuntimeError("No saved draft found. Please save draft in webapp first.")
    logging.info("loaded draft keys: %s", ", ".join(sorted(draft.keys())))
    return draft


def run_via_cdp(
    base_url: str,
    cdp_url: str,
    review_delay_ms: int = 0,
    sell_url: str = SELL_URL,
) -> None:
    draft = load_draft_from_webapp(base_url)
    with sync_playwright() as p:
        started = time.perf_counter()
        logging.info("connecting to CDP: %s", cdp_url)
        browser = p.chromium.connect_over_cdp(cdp_url)
        context = browser.contexts[0] if browser.contexts else browser.new_context(locale="ja-JP")
        context.set_default_timeout(ACTION_TIMEOUT_MS)
        page = context.new_page()
        page.goto(sell_url, wait_until="domcontentloaded")
        # Wait for form core fields to render.
        try:
            page.wait_for_selector("textarea, input", timeout=8000)
        except Exception:
            logging.warning("form selector wait timed out; continue best-effort")
        result = _fill_listing(page, draft)
        logging.info("auto-fill result: %s", result)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logging.info("auto-fill elapsed: %sms", elapsed_ms)
        logging.info("please review fields manually before submitting")
        page.bring_to_front()
        if review_delay_ms > 0:
            page.wait_for_timeout(review_delay_ms)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fill Mercari sell/create form from saved webapp draft via Playwright."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:5000")
    parser.add_argument("--cdp-url", default="http://127.0.0.1:9222")
    parser.add_argument("--sell-url", default=SELL_URL)
    parser.add_argument("--log-file", default="")
    parser.add_argument(
        "--review-delay-ms",
        type=int,
        default=0,
        help="Optional delay after filling. Defaults to 0 so control returns immediately.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.log_file)
    run_via_cdp(
        base_url=args.base_url,
        cdp_url=args.cdp_url,
        review_delay_ms=max(0, args.review_delay_ms),
        sell_url=args.sell_url,
    )
