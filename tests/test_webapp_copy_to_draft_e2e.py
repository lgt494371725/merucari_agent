import os
import sys
import threading
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server

import webapp


CATEGORY = "本・雑誌・漫画 > 本 > 資格・検定"


class _FakeSearchClient:
    def search_titles(self, keyword, top_n=10):
        return [
            {
                "id": "m-copy-category",
                "title": "Copy Draft Category Item",
                "price": 1200,
                "thumbnail": "",
            }
        ]


class _FakeDetailClient:
    def fetch_details_for_ids(self, ids):
        return [
            {
                "id": "m-copy-category",
                "title": "Copy Draft Category Item",
                "description": "detail description",
                "url": "https://jp.mercari.com/item/m-copy-category",
                "price": 1200,
                "thumbnail": "",
                "category": CATEGORY,
            }
        ]


class WebappCopyToDraftE2ETest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_search_client = webapp._search_client
        cls.original_detail_client = webapp._detail_client
        webapp._search_client = _FakeSearchClient()
        webapp._detail_client = _FakeDetailClient()
        webapp._details_cache.clear()
        webapp._latest_draft.clear()

        cls.server = make_server("127.0.0.1", 0, webapp.app)
        cls.port = cls.server.server_port
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

        try:
            cls.playwright = sync_playwright().start()
            cls.browser = cls.playwright.chromium.launch(headless=True)
        except PlaywrightError as exc:
            cls.server.shutdown()
            raise unittest.SkipTest(f"Playwright browser unavailable: {exc}") from exc

    @classmethod
    def tearDownClass(cls):
        browser = getattr(cls, "browser", None)
        if browser:
            browser.close()
        playwright = getattr(cls, "playwright", None)
        if playwright:
            playwright.stop()
        server = getattr(cls, "server", None)
        if server:
            server.shutdown()
        thread = getattr(cls, "thread", None)
        if thread:
            thread.join(timeout=2)
        webapp._search_client = cls.original_search_client
        webapp._detail_client = cls.original_detail_client
        webapp._details_cache.clear()
        webapp._latest_draft.clear()

    def setUp(self):
        webapp._details_cache.clear()
        webapp._latest_draft.clear()
        self.page = self.browser.new_page()

    def tearDown(self):
        self.page.close()

    def test_copy_to_draft_preserves_category_in_ui_and_saved_draft(self):
        self.page.goto(f"http://127.0.0.1:{self.port}/")
        try:
            self.page.get_by_placeholder("e.g. Nintendo Switch, Sony WH-1000XM5…").fill("book")
        except PlaywrightTimeoutError as exc:
            raise unittest.SkipTest(f"React UI did not load, likely CDN unavailable: {exc}") from exc

        self.page.get_by_role("button", name="Search").click()
        self.page.get_by_text("Copy Draft Category Item").click()
        self.page.get_by_role("button", name="Show Details").click()
        self.page.get_by_role("button", name="Copy to Draft").click()

        category_input = self.page.locator('[data-testid="draft-category"]')
        category_input.wait_for(state="visible", timeout=5000)
        self.assertEqual(category_input.input_value(), CATEGORY)

        self.page.locator('[data-testid="save-draft"]').click()
        self.page.wait_for_function(
            "() => document.body.textContent.includes('草稿已保存')",
            timeout=5000,
        )
        saved = self.page.request.get(f"http://127.0.0.1:{self.port}/api/draft").json()
        self.assertEqual(saved["draft"]["category"], CATEGORY)


if __name__ == "__main__":
    unittest.main()
