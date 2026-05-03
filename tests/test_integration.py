import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import webapp


class WebAppIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = webapp.app.test_client()
        webapp._details_cache.clear()
        webapp._latest_draft.clear()

    def test_api_search_uses_top_n_and_returns_items(self):
        fake_client = MagicMock()
        fake_client.search_titles.return_value = [{"id": "m1", "title": "t1", "price": 100}]

        with patch.object(webapp, "_search_client", fake_client):
            resp = self.client.get("/api/search?keyword=nikke&top_n=7")
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertEqual(data["items"][0]["id"], "m1")
            fake_client.search_titles.assert_called_once_with("nikke", top_n=7)

    def test_api_search_empty_keyword_returns_empty_items(self):
        resp = self.client.get("/api/search?keyword=")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"items": []})

    def test_api_details_returns_requested_items(self):
        fake_client = MagicMock()
        fake_client.fetch_details_for_ids.return_value = [
            {"id": "m1", "title": "t1", "description": "d1", "url": "u1"}
        ]
        with patch.object(webapp, "_detail_client", fake_client):
            resp = self.client.get("/api/details?ids=m1,m2")
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertEqual(len(data["items"]), 1)
            fake_client.fetch_details_for_ids.assert_called_once_with(["m1", "m2"])

    def test_api_details_uses_cache_on_repeat_click(self):
        fake_client = MagicMock()
        fake_client.fetch_details_for_ids.return_value = [
            {"id": "m1", "title": "t1", "description": "d1", "url": "u1"}
        ]
        with patch.object(webapp, "_detail_client", fake_client):
            resp1 = self.client.get("/api/details?ids=m1")
            resp2 = self.client.get("/api/details?ids=m1")
            self.assertEqual(resp1.status_code, 200)
            self.assertEqual(resp2.status_code, 200)
            fake_client.fetch_details_for_ids.assert_called_once_with(["m1"])

    def test_api_details_fetches_only_missing_ids(self):
        fake_client = MagicMock()
        fake_client.fetch_details_for_ids.side_effect = [
            [{"id": "m1", "title": "t1", "description": "d1", "url": "u1"}],
            [{"id": "m2", "title": "t2", "description": "d2", "url": "u2"}],
        ]
        with patch.object(webapp, "_detail_client", fake_client):
            self.client.get("/api/details?ids=m1")
            resp = self.client.get("/api/details?ids=m1,m2")
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(fake_client.fetch_details_for_ids.call_count, 2)
            fake_client.fetch_details_for_ids.assert_any_call(["m1"])
            fake_client.fetch_details_for_ids.assert_any_call(["m2"])

    def test_api_draft_save_and_get(self):
        payload = {
            "title": "test title",
            "description": "test description",
            "price": "1200",
            "shippingDays": "2~3日で発送",
        }
        save = self.client.post("/api/draft", json=payload)
        self.assertEqual(save.status_code, 200)
        save_body = save.get_json()
        self.assertTrue(save_body["ok"])

        read = self.client.get("/api/draft")
        self.assertEqual(read.status_code, 200)
        read_body = read.get_json()
        self.assertEqual(read_body["draft"]["title"], "test title")
        self.assertEqual(read_body["draft"]["price"], "1200")

    def test_api_auto_fill_launches_process(self):
        webapp._latest_draft.update({"title": "x"})
        with patch("webapp.subprocess.Popen") as popen_mock:
            resp = self.client.post("/api/auto-fill")
            self.assertEqual(resp.status_code, 200)
            body = resp.get_json()
            self.assertTrue(body["ok"])
            self.assertTrue(popen_mock.called)


if __name__ == "__main__":
    unittest.main()
