import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from playwright_fill_sell import ListingDraft, MercariSellFiller, SHIPPING_METHOD_OPTIONS


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FIXTURE_PATH = os.path.join(ROOT, "tests", "fixtures", "mercari_sell_fixture.html")


class MercariSellFillerE2ETest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.playwright = sync_playwright().start()
            cls.browser = cls.playwright.chromium.launch(headless=True)
        except PlaywrightError as exc:
            raise unittest.SkipTest(f"Playwright browser unavailable: {exc}") from exc

    @classmethod
    def tearDownClass(cls):
        browser = getattr(cls, "browser", None)
        if browser:
            browser.close()
        playwright = getattr(cls, "playwright", None)
        if playwright:
            playwright.stop()

    def setUp(self):
        self.page = self.browser.new_page()
        self.page.goto(f"file://{FIXTURE_PATH}")

    def tearDown(self):
        self.page.close()

    def _field_values(self):
        return self.page.evaluate(
            """
            () => ({
              title: document.querySelector('input[name="name"]').value,
              description: document.querySelector('textarea[name="description"]').value,
              price: document.querySelector('input[name="price"]').value,
              condition: document.querySelector('[data-testid="condition-value"]').value,
              shippingPayer: document.querySelector('[data-testid="shipping-payer"]').value,
              shippingMethod: document.querySelector('[data-testid="shipping-method-value"]').value,
              shippingDays: document.querySelector('[data-testid="shipping-days-value"]').value,
              shippingFrom: document.querySelector('[data-testid="shipping-from-value"]').value,
            })
            """
        )

    def test_fills_all_fields_end_to_end(self):
        draft = ListingDraft(
            title="Python 試験対策テキスト",
            description="きれいな状態です。\n書き込みなし。",
            price="1200",
            condition="新品、未使用",
            shipping_payer="送料込み(出品者負担)",
            shipping_method="らくらくメルカリ便",
            shipping_days="2~3日で発送",
            shipping_from="東京都",
        )

        result = MercariSellFiller(self.page).fill(draft)

        self.assertTrue(all(result.values()), result)
        self.assertEqual(
            self._field_values(),
            {
                "title": "Python 試験対策テキスト",
                "description": "きれいな状態です。\n書き込みなし。",
                "price": "1200",
                "condition": "新品、未使用",
                "shippingPayer": "送料込み(出品者負担)",
                "shippingMethod": "らくらくメルカリ便",
                "shippingDays": "2~3日で発送",
                "shippingFrom": "東京都",
            },
        )

    def test_selects_supported_shipping_methods(self):
        for shipping_method in SHIPPING_METHOD_OPTIONS:
            with self.subTest(shipping_method=shipping_method):
                self.page.goto(f"file://{FIXTURE_PATH}")
                draft = ListingDraft(
                    title="title",
                    description="description",
                    price="500",
                    condition="未使用に近い",
                    shipping_payer="送料込み(出品者負担)",
                    shipping_method=shipping_method,
                    shipping_days="1~2日で発送",
                    shipping_from="大阪府",
                )

                result = MercariSellFiller(self.page).fill(draft)

                self.assertTrue(all(result.values()), result)
                values = self._field_values()
                self.assertEqual(values["shippingMethod"], shipping_method)
                self.assertEqual(values["condition"], "未使用に近い")
                self.assertEqual(values["shippingDays"], "1~2日で発送")
                self.assertEqual(values["shippingFrom"], "大阪府")


if __name__ == "__main__":
    unittest.main()
