"""Smoke tests for core formatting helpers.

Run:
    python -m unittest discover -s tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from mercari_api_client import _clean, _to_int


class ToIntTest(unittest.TestCase):
    def test_int_passthrough(self):
        self.assertEqual(_to_int(1200), 1200)

    def test_numeric_string(self):
        self.assertEqual(_to_int("1200"), 1200)

    def test_comma_grouped_string(self):
        self.assertEqual(_to_int("1,200"), 1200)

    def test_whitespace_string(self):
        self.assertEqual(_to_int("  980 "), 980)

    def test_none_and_empty(self):
        self.assertEqual(_to_int(None), 0)
        self.assertEqual(_to_int(""), 0)

    def test_garbage(self):
        self.assertEqual(_to_int("abc"), 0)
        self.assertEqual(_to_int({"price": 1}), 0)


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
