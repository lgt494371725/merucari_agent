import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import playwright_fill_sell as fill_sell


class ListingDraftTest(unittest.TestCase):
    def test_from_payload_normalizes_price_and_shipping_method(self):
        draft = fill_sell.ListingDraft.from_payload(
            {
                "title": "title",
                "price": "¥1,200",
                "shippingMethod": "らくらくメルカリ便",
            }
        )
        self.assertEqual(draft.price, "1200")
        self.assertEqual(draft.shipping_method, "らくらくメルカリ便")

    def test_from_payload_rejects_unsupported_shipping_method(self):
        draft = fill_sell.ListingDraft.from_payload({"shippingMethod": "普通郵便(定形、定形外)"})
        self.assertEqual(draft.shipping_method, "")


class SelectionFlowTest(unittest.TestCase):
    def setUp(self):
        self.page = MagicMock()

    @patch("playwright_fill_sell._return_to_main_form_if_needed")
    @patch("playwright_fill_sell._click_text_option")
    @patch("playwright_fill_sell._click_field_entry")
    @patch("playwright_fill_sell._pick_select_or_combobox")
    def test_condition_uses_list_page_fallback(
        self, generic_mock, field_mock, option_mock, return_mock
    ):
        generic_mock.return_value = False
        field_mock.return_value = True
        option_mock.return_value = True

        ok = fill_sell._pick_condition(self.page, "新品、未使用")

        self.assertTrue(ok)
        field_mock.assert_called_once_with(
            self.page, "商品の状態", ["商品の状態を選択する", "商品の状態"]
        )
        option_mock.assert_called_once_with(self.page, ["新品、未使用"])
        return_mock.assert_called_once_with(self.page)

    @patch("playwright_fill_sell._return_to_main_form_if_needed")
    @patch("playwright_fill_sell._first_visible")
    @patch("playwright_fill_sell._click_text_option")
    @patch("playwright_fill_sell._click_field_entry")
    @patch("playwright_fill_sell._select_native_by_label_fast")
    def test_shipping_method_uses_card_page_for_supported_values(
        self, native_mock, field_mock, option_mock, visible_mock, return_mock
    ):
        for method in fill_sell.SHIPPING_METHOD_OPTIONS:
            with self.subTest(method=method):
                native_mock.reset_mock()
                field_mock.reset_mock()
                option_mock.reset_mock()
                visible_mock.reset_mock()
                return_mock.reset_mock()
                native_mock.return_value = False
                field_mock.return_value = True
                option_mock.return_value = True
                confirm = MagicMock()
                visible_mock.return_value = confirm

                ok = fill_sell._pick_shipping_method(self.page, method)

                self.assertTrue(ok)
                native_mock.assert_called_once_with(self.page, "配送の方法", method)
                field_mock.assert_called_once_with(
                    self.page,
                    "配送の方法",
                    ["配送の方法を選択する", "配送方法を選択する", "配送の方法"],
                )
                option_mock.assert_called_once_with(self.page, [method])
                confirm.scroll_into_view_if_needed.assert_called_once()
                confirm.click.assert_called_once()
                return_mock.assert_called_once_with(self.page)

    @patch("playwright_fill_sell._click_field_entry")
    @patch("playwright_fill_sell._select_native_by_label_fast")
    def test_shipping_method_rejects_unsupported_values(self, native_mock, field_mock):
        self.assertFalse(fill_sell._pick_shipping_method(self.page, "普通郵便(定形、定形外)"))
        native_mock.assert_not_called()
        field_mock.assert_not_called()

    @patch("playwright_fill_sell._return_to_main_form_if_needed")
    @patch("playwright_fill_sell._click_text_option")
    @patch("playwright_fill_sell._click_field_entry")
    @patch("playwright_fill_sell._first_visible")
    @patch("playwright_fill_sell._select_native_by_label_fast")
    def test_generic_select_falls_back_to_list_page_for_shipping_from(
        self, native_mock, visible_mock, field_mock, option_mock, return_mock
    ):
        native_mock.return_value = False
        self.page.locator.side_effect = RuntimeError("no native select or combobox")
        visible_mock.return_value = None
        field_mock.return_value = True
        option_mock.return_value = True

        ok = fill_sell._pick_select_or_combobox(self.page, "発送元の地域", "東京都")

        self.assertTrue(ok)
        field_mock.assert_called_once_with(
            self.page, "発送元の地域", ["発送元の地域を選択する", "発送元の地域"]
        )
        option_mock.assert_called_once_with(self.page, ["東京都"])
        return_mock.assert_called_once_with(self.page)

    @patch("playwright_fill_sell._pick_shipping_method")
    @patch("playwright_fill_sell._pick_select_or_combobox")
    @patch("playwright_fill_sell._pick_condition")
    @patch("playwright_fill_sell._fill_text")
    def test_fill_listing_does_not_attempt_category_autofill(
        self, fill_text_mock, condition_mock, select_mock, shipping_mock
    ):
        fill_text_mock.return_value = True
        condition_mock.return_value = True
        select_mock.return_value = True
        shipping_mock.return_value = True

        result = fill_sell._fill_listing(
            self.page,
            {
                "title": "title",
                "description": "desc",
                "price": "1,200",
                "condition": "新品、未使用",
                "shippingPayer": "送料込み(出品者負担)",
                "shippingMethod": "らくらくメルカリ便",
                "shippingDays": "2~3日で発送",
                "shippingFrom": "東京都",
            },
        )

        self.assertNotIn("category", result)

    @patch("playwright_fill_sell.MercariSellFiller.fill")
    def test_fill_listing_delegates_to_filler_with_normalized_draft(self, fill_mock):
        fill_mock.return_value = {"price": True}

        result = fill_sell._fill_listing(self.page, {"price": "¥1,200"})

        self.assertEqual(result, {"price": True})
        passed_draft = fill_mock.call_args.args[0]
        self.assertIsInstance(passed_draft, fill_sell.ListingDraft)
        self.assertEqual(passed_draft.price, "1200")


if __name__ == "__main__":
    unittest.main()
