import os
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class TemplateContractTests(unittest.TestCase):
    def test_copy_to_draft_preserves_category(self):
        with open(os.path.join(ROOT, "templates", "index.html"), encoding="utf-8") as f:
            html = f.read()
        self.assertIn("category: item.category || \"\"", html)

    def test_shipping_method_is_select_control(self):
        with open(os.path.join(ROOT, "templates", "index.html"), encoding="utf-8") as f:
            html = f.read()
        label = '<div style={{ fontSize:12, color:"#999", marginBottom:6 }}>配送の方法</div>'
        self.assertIn(label, html)
        after_label = html.split(label, 1)[1]
        self.assertLess(after_label.find("<select"), after_label.find("</select>"))
        self.assertIn("<option>らくらくメルカリ便</option>", after_label)
        self.assertIn("<option>ゆうゆうメルカリ便</option>", after_label)
        select_body = after_label.split("<select", 1)[1].split("</select>", 1)[0]
        self.assertNotIn("普通郵便", select_body)
        self.assertNotIn("クロネコヤマト", select_body)


if __name__ == "__main__":
    unittest.main()
