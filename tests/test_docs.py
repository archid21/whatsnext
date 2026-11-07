"""The Tips section (P-38): the README and the guide each say where the band shows and how to stop and restart it.

Run: python3 -m unittest discover -s tests
"""

import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TipsDocsTests(unittest.TestCase):
    def section(self, name):
        with open(os.path.join(ROOT, name), encoding="utf-8") as f:
            text = f.read()
        self.assertIn("\n## Tips\n", text, name)
        return text.split("\n## Tips\n", 1)[1].split("\n## ", 1)[0]

    def test_readme_and_guide_have_a_tips_section_with_stop_and_restart(self):
        for name in ("README.md", os.path.join("docs", "GUIDE.md")):
            body = self.section(name)
            self.assertIn("terminal", body, name)
            self.assertIn("desktop", body, name)
            self.assertIn("Stop tips", body, name)
            self.assertIn("/whatsnext-tips", body, name)


if __name__ == "__main__":
    unittest.main()
