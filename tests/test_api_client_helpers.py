"""Tests for helpers in `mercari_api_client.py` added since the GUI work:
multiline-aware text cleaning and best-effort thumbnail extraction.

Run:
    python -m unittest discover -s tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from mercari_api_client import _category_path, _clean_multiline, _first_thumbnail


class CleanMultilineTest(unittest.TestCase):
    """`_clean_multiline` must preserve `\\n` (descriptions), unlike `_clean`."""

    def test_none_and_empty(self):
        self.assertEqual(_clean_multiline(None), "")
        self.assertEqual(_clean_multiline(""), "")

    def test_normalises_crlf_and_cr(self):
        self.assertEqual(_clean_multiline("a\r\nb\rc"), "a\nb\nc")

    def test_preserves_single_newlines(self):
        # Regression: `_clean` collapsed \n to space; multiline must NOT.
        self.assertEqual(_clean_multiline("line1\nline2\nline3"), "line1\nline2\nline3")

    def test_preserves_paragraph_breaks(self):
        self.assertEqual(_clean_multiline("p1\n\np2"), "p1\n\np2")

    def test_collapses_runs_of_blank_lines_to_two(self):
        self.assertEqual(_clean_multiline("p1\n\n\n\n\np2"), "p1\n\np2")

    def test_collapses_horizontal_whitespace(self):
        self.assertEqual(_clean_multiline("a   b\t\tc"), "a b c")

    def test_strips_trailing_whitespace_per_line(self):
        self.assertEqual(_clean_multiline("a   \nb\t\n c"), "a\nb\n c")

    def test_outer_strip(self):
        self.assertEqual(_clean_multiline("\n\n  hello\n\n"), "hello")

    def test_realistic_mercari_description(self):
        raw = "サイズ: M\r\nブランド: Nike\r\n\r\n使用感あり、オフェーでよろしく"
        cleaned = _clean_multiline(raw)
        self.assertIn("\n", cleaned)
        # exact preservation of paragraph break between specs and prose
        self.assertEqual(cleaned.count("\n\n"), 1)


class FirstThumbnailTest(unittest.TestCase):
    """`_first_thumbnail` probes a handful of known Mercari shapes."""

    def test_empty_inputs(self):
        self.assertEqual(_first_thumbnail({}), "")
        self.assertEqual(_first_thumbnail(None), "")
        self.assertEqual(_first_thumbnail("not a dict"), "")

    def test_thumbnails_list_of_strings(self):
        item = {"thumbnails": ["https://x/a.jpg", "https://x/b.jpg"]}
        self.assertEqual(_first_thumbnail(item), "https://x/a.jpg")

    def test_thumbnails_list_of_dicts(self):
        item = {"thumbnails": [{"url": "https://x/a.jpg"}]}
        self.assertEqual(_first_thumbnail(item), "https://x/a.jpg")
        item2 = {"thumbnails": [{"src": "https://x/b.jpg"}]}
        self.assertEqual(_first_thumbnail(item2), "https://x/b.jpg")
        item3 = {"thumbnails": [{"uri": "https://x/c.jpg"}]}
        self.assertEqual(_first_thumbnail(item3), "https://x/c.jpg")

    def test_photos_list_used_if_thumbnails_absent(self):
        item = {"photos": ["https://x/photo.jpg"]}
        self.assertEqual(_first_thumbnail(item), "https://x/photo.jpg")

    def test_thumbnails_preferred_over_photos(self):
        item = {
            "thumbnails": ["https://x/thumb.jpg"],
            "photos": ["https://x/photo.jpg"],
        }
        self.assertEqual(_first_thumbnail(item), "https://x/thumb.jpg")

    def test_scalar_string_keys(self):
        for key in ("thumbnail", "photo", "imageUrl", "image"):
            with self.subTest(key=key):
                self.assertEqual(_first_thumbnail({key: "https://x/x.jpg"}), "https://x/x.jpg")

    def test_empty_lists_and_strings_skip(self):
        item = {"thumbnails": [], "photos": [], "thumbnail": "", "imageUrl": "https://x/final.jpg"}
        self.assertEqual(_first_thumbnail(item), "https://x/final.jpg")

    def test_first_dict_without_known_keys_falls_through(self):
        # If the first photo dict has no url/src/uri, we shouldn't return it —
        # but the helper currently keys off the *first* element. Lock the
        # behaviour we have (skip by returning ""), and fall back to scalar keys.
        item = {"photos": [{"weirdkey": "x"}], "thumbnail": "https://x/t.jpg"}
        # Behaviour: nested dict has no known sub-key, so we don't get a hit
        # from `photos`; the helper then tries scalar keys and finds `thumbnail`.
        self.assertEqual(_first_thumbnail(item), "https://x/t.jpg")


class CategoryPathTest(unittest.TestCase):
    def test_category_path_from_list_of_dicts(self):
        item = {
            "categories": [
                {"name": "本・雑誌・漫画"},
                {"name": "本"},
                {"name": "資格・検定"},
            ]
        }
        self.assertEqual(_category_path(item), "本・雑誌・漫画 > 本 > 資格・検定")

    def test_category_path_from_nested_category_path(self):
        item = {
            "category": {
                "name": "資格・検定",
                "path": [{"name": "本・雑誌・漫画"}, {"name": "本"}],
            }
        }
        self.assertEqual(_category_path(item), "本・雑誌・漫画 > 本 > 資格・検定")

    def test_category_path_from_name_fields(self):
        item = {
            "rootCategoryName": "本・雑誌・漫画",
            "parentCategoryName": "本",
            "categoryName": "資格・検定",
        }
        self.assertEqual(_category_path(item), "本・雑誌・漫画 > 本 > 資格・検定")


if __name__ == "__main__":
    unittest.main()
