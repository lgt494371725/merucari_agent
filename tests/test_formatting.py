"""Smoke tests for price/field formatting helpers.

Run:
    python -m unittest discover -s tests -v
"""

import os
import sys
import unittest

# Allow running from repo root without installing the package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from gui import _format_price
from mercari_api_client import _clean, _to_int


class ToIntTest(unittest.TestCase):
    def test_int_passthrough(self):
        self.assertEqual(_to_int(1200), 1200)

    def test_numeric_string(self):
        self.assertEqual(_to_int("1200"), 1200)

    def test_comma_grouped_string(self):
        # Mercari occasionally returns "1,200"-style strings
        self.assertEqual(_to_int("1,200"), 1200)

    def test_whitespace_string(self):
        self.assertEqual(_to_int("  980 "), 980)

    def test_none_and_empty(self):
        self.assertEqual(_to_int(None), 0)
        self.assertEqual(_to_int(""), 0)

    def test_garbage(self):
        self.assertEqual(_to_int("abc"), 0)
        self.assertEqual(_to_int({"price": 1}), 0)


class FormatPriceTest(unittest.TestCase):
    def test_int(self):
        self.assertEqual(_format_price(1200), "¥1,200")

    def test_large_int(self):
        self.assertEqual(_format_price(1234567), "¥1,234,567")

    def test_numeric_string(self):
        # This is the case that reproduced the original crash:
        # `f"¥{price:,}"` blew up when price was a str.
        self.assertEqual(_format_price("1200"), "¥1,200")

    def test_comma_string(self):
        self.assertEqual(_format_price("1,200"), "¥1,200")

    def test_none_zero_empty(self):
        self.assertEqual(_format_price(None), "¥?")
        self.assertEqual(_format_price(0), "¥?")
        self.assertEqual(_format_price("0"), "¥?")
        self.assertEqual(_format_price(""), "¥?")

    def test_non_numeric_falls_back(self):
        # Shouldn't raise — degrade gracefully
        self.assertEqual(_format_price("free"), "¥free")


class CleanTest(unittest.TestCase):
    def test_collapses_whitespace(self):
        self.assertEqual(_clean("  hello   world  "), "hello world")

    def test_none_and_empty(self):
        self.assertEqual(_clean(None), "")
        self.assertEqual(_clean(""), "")

    def test_newlines_and_tabs(self):
        self.assertEqual(_clean("a\n\tb\r\nc"), "a b c")


if __name__ == "__main__":
    unittest.main()
