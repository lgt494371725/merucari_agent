import asyncio
import json
import re
import uuid
from typing import Dict, List, Optional
from urllib.parse import quote

import httpx

SEARCH_API = "https://api.mercari.jp/v2/entities:search"
ITEM_API = "https://api.mercari.jp/items/get"
SEARCH_HTML_URL = "https://jp.mercari.com/search?keyword={keyword}"
ITEM_HTML_URL = "https://jp.mercari.com/item/{item_id}"

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_BASE_HEADERS = {
    "User-Agent": _BROWSER_UA,
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}


def _clean(value: Optional[str]) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


class MercariApiClient:
    def __init__(self, timeout: float = 15.0, max_concurrent: int = 8) -> None:
        self.timeout = timeout
        self.max_concurrent = max_concurrent

    def fetch_items(self, keyword: str, top_n: int = 10) -> List[Dict[str, str]]:
        return asyncio.run(self._run(keyword, top_n))

    async def _run(self, keyword: str, top_n: int) -> List[Dict[str, str]]:
        async with httpx.AsyncClient(
            headers=_BASE_HEADERS,
            timeout=self.timeout,
            follow_redirects=True,
        ) as client:
            item_ids = await self._search(client, keyword, top_n)
            if not item_ids:
                return []
            return await self._fetch_all_details(client, item_ids)

    # ── Search ──────────────────────────────────────────────────────────────

    async def _search(
        self, client: httpx.AsyncClient, keyword: str, top_n: int
    ) -> List[str]:
        ids = await self._search_via_api(client, keyword, top_n)
        if ids:
            return ids
        return await self._search_via_html(client, keyword, top_n)

    async def _search_via_api(
        self, client: httpx.AsyncClient, keyword: str, top_n: int
    ) -> List[str]:
        payload = {
            "searchSessionId": str(uuid.uuid4()),
            "indexRouting": "INDEX_ROUTING_UNSPECIFIED",
            "thumbnailTypes": [],
            "searchCondition": {
                "keyword": keyword,
                "excludeKeyword": "",
                "sort": "SORT_SCORE",
                "order": "ORDER_DESC",
                "status": ["STATUS_ON_SALE"],
                "sizeId": [],
                "categoryId": [],
                "brandId": [],
                "sellerId": [],
                "priceMin": 0,
                "priceMax": 0,
                "itemConditionId": [],
                "shippingPayerId": [],
                "shippingFromArea": [],
                "shippingMethod": [],
                "colorId": [],
                "hasCoupon": False,
                "attributes": [],
                "itemTypes": [],
                "skuIds": [],
            },
            "defaultDatasets": ["DATASET_TYPE_MERCARI", "DATASET_TYPE_BEYOND"],
            "serviceFrom": "suruga",
            "userId": "",
            "pageSize": top_n,
            "pageToken": "",
            "withItemBrand": True,
            "withItemSize": False,
            "withItemPromotions": False,
            "withItemSizes": False,
            "useDynamicAttribute": False,
        }
        try:
            resp = await client.post(
                SEARCH_API,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/plain, */*",
                    "X-Platform": "web",
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("items", [])
                ids = [item["id"] for item in items if item.get("id")]
                return ids[:top_n]
        except Exception:
            pass
        return []

    async def _search_via_html(
        self, client: httpx.AsyncClient, keyword: str, top_n: int
    ) -> List[str]:
        url = SEARCH_HTML_URL.format(keyword=quote(keyword))
        try:
            resp = await client.get(url, headers={"Accept": "text/html,*/*"})
            html = resp.text
            ids = self._ids_from_next_data(html, top_n)
            if ids:
                return ids
            # regex fallback: extract /item/mXXX hrefs
            found = re.findall(r'href=["\']?/item/(m\w+)', html)
            deduped: Dict[str, None] = {}
            for item_id in found:
                deduped[item_id] = None
                if len(deduped) >= top_n:
                    break
            return list(deduped.keys())
        except Exception:
            return []

    def _ids_from_next_data(self, html: str, top_n: int) -> List[str]:
        match = re.search(
            r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
            html,
            re.DOTALL,
        )
        if not match:
            return []
        try:
            data = json.loads(match.group(1))
            props = data.get("props", {}).get("pageProps", {})
            for key in ("searchResult", "items", "data"):
                container = props.get(key)
                if isinstance(container, dict):
                    raw_items = container.get("items", [])
                elif isinstance(container, list):
                    raw_items = container
                else:
                    continue
                ids = [
                    item.get("id") or item.get("itemId", "")
                    for item in raw_items
                    if isinstance(item, dict)
                ]
                ids = [i for i in ids if i]
                if ids:
                    return ids[:top_n]
        except Exception:
            pass
        return []

    # ── Detail fetching ─────────────────────────────────────────────────────

    async def _fetch_all_details(
        self, client: httpx.AsyncClient, item_ids: List[str]
    ) -> List[Dict[str, str]]:
        sem = asyncio.Semaphore(self.max_concurrent)

        async def fetch_one(item_id: str) -> Optional[Dict[str, str]]:
            async with sem:
                return await self._fetch_detail(client, item_id)

        results = await asyncio.gather(*[fetch_one(iid) for iid in item_ids])
        return [r for r in results if r]

    async def _fetch_detail(
        self, client: httpx.AsyncClient, item_id: str
    ) -> Optional[Dict[str, str]]:
        url = ITEM_HTML_URL.format(item_id=item_id)
        item = await self._detail_via_api(client, item_id, url)
        if not item:
            item = await self._detail_via_html(client, item_id, url)
        return item

    async def _detail_via_api(
        self, client: httpx.AsyncClient, item_id: str, url: str
    ) -> Optional[Dict[str, str]]:
        try:
            resp = await client.get(
                ITEM_API,
                params={"id": item_id},
                headers={"Accept": "application/json", "X-Platform": "web"},
            )
            if resp.status_code == 200:
                data = resp.json()
                title = _clean(data.get("name", ""))
                description = _clean(data.get("description", ""))
                if title or description:
                    return {"url": url, "title": title, "description": description}
        except Exception:
            pass
        return None

    async def _detail_via_html(
        self, client: httpx.AsyncClient, item_id: str, url: str
    ) -> Optional[Dict[str, str]]:
        try:
            resp = await client.get(url, headers={"Accept": "text/html,*/*"})
            html = resp.text
            title = self._title_from_html(html)
            description = self._description_from_html(html)
            if not title and not description:
                return None
            return {"url": url, "title": title, "description": description}
        except Exception:
            return None

    def _title_from_html(self, html: str) -> str:
        nd = self._next_data_item(html)
        if nd:
            name = _clean(nd.get("name", ""))
            if name:
                return name
        m = re.search(
            r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', html, re.IGNORECASE
        )
        return _clean(m.group(1)) if m else ""

    def _description_from_html(self, html: str) -> str:
        nd = self._next_data_item(html)
        if nd:
            desc = _clean(nd.get("description", ""))
            if desc:
                return desc
        for raw in re.findall(
            r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>',
            html,
            re.DOTALL | re.IGNORECASE,
        ):
            try:
                data = json.loads(raw.strip())
                desc = _clean(data.get("description", ""))
                if desc:
                    return desc
            except Exception:
                continue
        m = re.search(
            r'<meta[^>]+property="og:description"[^>]+content="([^"]+)"',
            html,
            re.IGNORECASE,
        )
        return _clean(m.group(1)) if m else ""

    def _next_data_item(self, html: str) -> Optional[Dict]:
        match = re.search(
            r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
            html,
            re.DOTALL,
        )
        if not match:
            return None
        try:
            data = json.loads(match.group(1))
            item = data.get("props", {}).get("pageProps", {}).get("item")
            return item if isinstance(item, dict) else None
        except Exception:
            return None
