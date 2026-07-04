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


class WebappFixedTermsE2ETest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
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

    def setUp(self):
        self.page = self.browser.new_page()

    def tearDown(self):
        self.page.close()

    def _open_app(self):
        self.page.goto(f"http://127.0.0.1:{self.port}/")
        try:
            search = self.page.get_by_placeholder("e.g. Nintendo Switch, Sony WH-1000XM5…")
            search.wait_for(state="visible", timeout=5000)
        except PlaywrightTimeoutError as exc:
            raise unittest.SkipTest(f"React UI did not load, likely CDN unavailable: {exc}") from exc
        return search

    def test_fixed_terms_can_be_added_appended_persisted_and_deleted(self):
        search = self._open_app()
        self.page.evaluate("localStorage.clear()")
        self.page.reload()
        search = self._open_app()

        search.fill("原有词")
        search.focus()
        self.page.locator('[data-testid="fixed-term-input"]').fill(" A ")
        self.page.locator('[data-testid="fixed-term-add"]').click()

        chip = self.page.locator('[data-testid="fixed-term-chip"]').filter(has_text="A")
        chip.wait_for(state="visible", timeout=5000)
        chip.click()
        self.assertEqual(search.input_value(), "原有词 A")

        chip.click()
        self.assertEqual(search.input_value(), "原有词 A")

        self.page.reload()
        search = self._open_app()
        search.focus()
        chip = self.page.locator('[data-testid="fixed-term-chip"]').filter(has_text="A")
        chip.wait_for(state="visible", timeout=5000)

        search.fill("原有词 A")
        self.page.locator('[data-testid="fixed-term-delete"]').click()
        self.page.wait_for_selector('[data-testid="fixed-term-chip"]', state="detached", timeout=5000)
        self.page.locator('[data-testid="fixed-terms-section"]').wait_for(state="visible", timeout=5000)
        self.assertEqual(search.input_value(), "原有词 A")


if __name__ == "__main__":
    unittest.main()
