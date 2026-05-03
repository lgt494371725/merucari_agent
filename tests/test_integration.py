import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import webapp


class WebAppIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = webapp.app.test_client()

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


if __name__ == "__main__":
    unittest.main()
