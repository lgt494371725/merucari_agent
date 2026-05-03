import asyncio
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from mercari_api_client import ITEM_API, SEARCH_API, MercariApiClient


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http error: {self.status_code}")


class _FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, json=None, headers=None):
        self.last_post = {"url": url, "json": json, "headers": headers}
        return _FakeResponse(
            200,
            {
                "items": [
                    {"id": "m1", "name": "title 1", "price": "1200", "thumbnails": ["u1"]},
                    {"id": "m2", "name": "title 2", "price": 2200, "thumbnails": ["u2"]},
                ]
            },
        )

    async def get(self, url, headers=None, params=None):
        self.last_get = {"url": url, "headers": headers, "params": params}
        return _FakeResponse(200, {"result": "OK", "data": {"name": "x", "description": "y"}})


class MercariApiClientUnitTests(unittest.TestCase):
    def test_build_search_payload_uses_top_n(self):
        client = MercariApiClient()
        payload = client._build_search_payload("abc", 17)
        self.assertEqual(payload["searchCondition"]["keyword"], "abc")
        self.assertEqual(payload["pageSize"], 17)

    def test_search_via_api_limits_top_n(self):
        client = MercariApiClient()

        class _Client:
            async def post(self, *args, **kwargs):
                return _FakeResponse(
                    200,
                    {"items": [{"id": "m1"}, {"id": "m2"}, {"id": "m3"}, {"id": "m4"}]},
                )

        ids = asyncio.run(client._search_via_api(_Client(), "k", 3))
        self.assertEqual(ids, ["m1", "m2", "m3"])

    def test_search_via_html_extracts_and_dedupes_ids(self):
        client = MercariApiClient()
        html = """
        <a href="/item/m111"></a>
        <a href="/item/m222"></a>
        <a href="/item/m111"></a>
        <a href="/item/m333"></a>
        """

        class _Client:
            async def get(self, *args, **kwargs):
                return _FakeResponse(200, text=html)

        ids = asyncio.run(client._search_via_html(_Client(), "k", 3))
        self.assertEqual(ids, ["m111", "m222", "m333"])

    def test_detail_via_api_unwraps_data_and_formats_fields(self):
        client = MercariApiClient()

        class _Client:
            async def get(self, url, params=None, headers=None):
                self.called = (url, params, headers)
                return _FakeResponse(
                    200,
                    {
                        "result": "OK",
                        "data": {
                            "name": "  title x  ",
                            "description": "line1\r\nline2",
                            "price": "1,200",
                            "thumbnails": ["thumb-x"],
                        },
                    },
                )

        result = asyncio.run(
            client._detail_via_api(_Client(), "m123", "https://jp.mercari.com/item/m123")
        )
        self.assertEqual(result["id"], "m123")
        self.assertEqual(result["title"], "title x")
        self.assertEqual(result["description"], "line1\nline2")
        self.assertEqual(result["price"], 1200)
        self.assertEqual(result["thumbnail"], "thumb-x")

    @patch("mercari_api_client.httpx.AsyncClient", _FakeAsyncClient)
    def test_search_titles_returns_id_title_price_thumbnail(self):
        client = MercariApiClient(timeout=1.0)
        items = client.search_titles("nikke", top_n=1)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], "m1")
        self.assertEqual(items[0]["title"], "title 1")
        self.assertEqual(items[0]["price"], 1200)
        self.assertEqual(items[0]["thumbnail"], "u1")

    def test_fetch_detail_prefers_api_then_html(self):
        client = MercariApiClient()

        async def _api_none(_client, _item_id, _url):
            return None

        async def _html_ok(_client, item_id, url):
            return {"id": item_id, "url": url, "title": "from html", "description": "d"}

        with patch.object(client, "_detail_via_api", _api_none), patch.object(
            client, "_detail_via_html", _html_ok
        ):
            out = asyncio.run(client._fetch_detail(object(), "m999"))
            self.assertEqual(out["title"], "from html")
            self.assertTrue(out["url"].endswith("/item/m999"))


if __name__ == "__main__":
    unittest.main()
