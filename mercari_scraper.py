import json
import re
from typing import Dict, List, Optional
from urllib.parse import quote

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


BASE_URL = "https://jp.mercari.com"
SEARCH_URL = BASE_URL + "/search?keyword={keyword}"


def _clean_text(value: Optional[str]) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


class MercariScraper:
    def __init__(self, headless: bool = True, timeout_ms: int = 20000) -> None:
        self.headless = headless
        self.timeout_ms = timeout_ms

    def fetch_items(self, keyword: str, top_n: int = 10) -> List[Dict[str, str]]:
        links = self._fetch_item_links(keyword=keyword, top_n=top_n)
        if not links:
            return []

        items: List[Dict[str, str]] = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context(locale="ja-JP")
            self._set_fast_routes(context)
            try:
                detail_page = context.new_page()
                detail_page.set_default_timeout(self.timeout_ms)
                for link in links:
                    item = self._fetch_item_detail_fast(context, link)
                    if not item:
                        item = self._fetch_item_detail(detail_page, link)
                    if item:
                        items.append(item)
                detail_page.close()
            finally:
                context.close()
                browser.close()
        return items

    def _fetch_item_links(self, keyword: str, top_n: int) -> List[str]:
        encoded = quote(keyword)
        search_url = SEARCH_URL.format(keyword=encoded)
        links: List[str] = []
        seen = set()

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context(locale="ja-JP")
            self._set_fast_routes(context)
            page = context.new_page()
            page.set_default_timeout(self.timeout_ms)
            try:
                page.goto(search_url, wait_until="domcontentloaded")
                self._accept_cookie_if_present(page)
                page.wait_for_selector('a[href^="/item/m"]', timeout=self.timeout_ms)
                cards = page.locator('a[href^="/item/m"]')
                total = min(cards.count(), max(top_n * 3, top_n))
                for idx in range(total):
                    href = cards.nth(idx).get_attribute("href")
                    if not href:
                        continue
                    if href.startswith("/"):
                        href = BASE_URL + href
                    if "/item/m" not in href:
                        continue
                    if href in seen:
                        continue
                    seen.add(href)
                    links.append(href)
                    if len(links) >= top_n:
                        break
            finally:
                context.close()
                browser.close()

        return links

    def _fetch_item_detail(self, page, url: str) -> Optional[Dict[str, str]]:
        try:
            page.goto(url, wait_until="domcontentloaded")
            title = self._extract_title(page)
            description = self._extract_description(page)
            return {"url": url, "title": title, "description": description}
        except PlaywrightTimeoutError:
            return None

    def _fetch_item_detail_fast(self, context, url: str) -> Optional[Dict[str, str]]:
        try:
            response = context.request.get(url, timeout=self.timeout_ms)
            if not response.ok:
                return None
            html = response.text()
            title = self._extract_title_from_html(html)
            description = self._extract_description_from_html(html)
            if self._is_generic_mercari_description(description):
                return None
            if not title and not description:
                return None
            return {"url": url, "title": title, "description": description}
        except Exception:
            return None

    def _extract_title(self, page) -> str:
        selectors = [
            'h1[data-testid="name"]',
            "h1.merHeading",
            "h1",
            'meta[property="og:title"]',
            "title",
        ]
        for selector in selectors:
            try:
                if selector.startswith("meta"):
                    value = page.locator(selector).first.get_attribute("content")
                    text = _clean_text(value)
                else:
                    text = _clean_text(page.locator(selector).first.inner_text())
                if text:
                    return text
            except Exception:
                continue
        return ""

    def _extract_description(self, page) -> str:
        selectors = [
            'pre[data-testid="description"]',
            'div[data-testid="description"]',
            "pre.merText",
            "section pre",
        ]
        for selector in selectors:
            try:
                text = _clean_text(page.locator(selector).first.inner_text())
                if text:
                    return text
            except Exception:
                continue

        text_from_jsonld = self._extract_description_from_jsonld(page)
        if text_from_jsonld:
            return text_from_jsonld

        meta_desc = page.locator('meta[property="og:description"]').first.get_attribute(
            "content"
        )
        return _clean_text(meta_desc)

    def _extract_description_from_jsonld(self, page) -> str:
        scripts = page.locator('script[type="application/ld+json"]')
        for idx in range(scripts.count()):
            try:
                raw = scripts.nth(idx).inner_text()
                if not raw:
                    continue
                data = json.loads(raw)
                if isinstance(data, dict):
                    description = data.get("description")
                    text = _clean_text(description if isinstance(description, str) else "")
                    if text:
                        return text
            except Exception:
                continue
        return ""

    def _extract_title_from_html(self, html: str) -> str:
        patterns = [
            r'<meta\s+property="og:title"\s+content="([^"]+)"',
            r"<title>(.*?)</title>",
        ]
        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
            if match:
                return _clean_text(match.group(1))
        return ""

    def _extract_description_from_html(self, html: str) -> str:
        jsonld_matches = re.findall(
            r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>',
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        for raw in jsonld_matches:
            raw = raw.strip()
            if not raw:
                continue
            try:
                data = json.loads(raw)
                if isinstance(data, dict):
                    description = data.get("description")
                    if isinstance(description, str):
                        text = _clean_text(description)
                        if text:
                            return text
            except Exception:
                continue

        og_match = re.search(
            r'<meta\s+property="og:description"\s+content="([^"]+)"',
            html,
            re.IGNORECASE | re.DOTALL,
        )
        if og_match:
            return _clean_text(og_match.group(1))
        return ""

    def _accept_cookie_if_present(self, page) -> None:
        buttons = [
            "button:has-text('Accept all')",
            "button:has-text('同意')",
            "button:has-text('同意して続行')",
        ]
        for selector in buttons:
            try:
                locator = page.locator(selector).first
                if locator.is_visible(timeout=500):
                    locator.click()
                    return
            except Exception:
                continue

    def _set_fast_routes(self, context) -> None:
        # Keep scripts/xhr needed for content; block heavy static assets for speed.
        blocked_types = {"image", "media", "font"}
        blocked_ext = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".woff", ".woff2", ".mp4")

        def handler(route):
            request = route.request
            url_lower = request.url.lower()
            if request.resource_type in blocked_types or url_lower.endswith(blocked_ext):
                route.abort()
                return
            route.continue_()

        context.route("**/*", handler)

    def _is_generic_mercari_description(self, text: str) -> bool:
        if not text:
            return False
        generic_markers = [
            "をメルカリでお得に通販",
            "誰でも安心して簡単に売り買いが楽しめるフリマサービス",
            "支払いはクレジットカード",
        ]
        return all(marker in text for marker in generic_markers)
