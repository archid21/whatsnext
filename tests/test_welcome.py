"""Tests for the first-run welcome (P-44): `whatsnext welcome` and the once-only SessionStart message.

Run: python3 -m unittest discover -s tests
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fixtures import PlanBase  # noqa: E402

from wn import welcome  # noqa: E402


class TableTests(unittest.TestCase):
    def setUp(self):
        self.text = welcome.render()

    def test_three_columns_with_the_five_to_learn_first_in_order_before_the_extras(self):
        head = next(line for line in self.text.split("\n") if line.startswith("Feature"))
        self.assertEqual([c.strip() for c in head.split("|")], ["Feature", "What it does", "How it works"])
        first = [n for n, _w, _h in welcome.ROWS][:5]
        self.assertEqual(first, ["Set up your plan", "Start work", "Change the plan", "Mark done with proof", "Save and resume"])
        at = [self.text.index(name.split()[0] + " " + name.split()[1][:3]) for name in first]  # a name may wrap
        self.assertEqual(at, sorted(at))
        rule = self.text.index("\n-----", self.text.index("Save and resume"))
        self.assertLess(rule, self.text.index("Smart compact"))
        self.assertLess(self.text.index("Save and resume"), rule)

    def test_short_summary_comes_before_the_table(self):
        at = self.text.index("The short version:")
        self.assertLess(at, self.text.index("Feature "))
        for phrase in ("set up whatsnext in this repo", "wrap up", "what's next?"):
            self.assertIn(phrase, self.text[at:self.text.index("Feature ")])

    def test_every_line_fits_in_a_terminal_and_rows_do_not_lose_words(self):
        for line in self.text.split("\n"):
            self.assertLessEqual(len(line), 106, line)
        flat = " ".join(self.text.split())
        for _name, what, _how in welcome.ROWS:
            self.assertTrue(all(word in flat for word in what.split()[:4]))

    def test_says_how_the_flow_fits_and_how_to_see_it_again(self):
        self.assertIn("How it fits together", self.text)
        self.assertIn('"wrap up"', self.text)
        self.assertIn("/whatsnext-welcome", self.text)
        self.assertIn("Auto-compact off", self.text)


class FirstRunTests(PlanBase):
    def setUp(self):
        super().setUp()
        os.remove(self.marker())  # a fresh install: the welcome has not been shown

    def hook(self, source="startup", agent="claude-code", cwd=None):
        data = {"session_id": "11111111-2222-3333-4444-555555555555", "cwd": cwd or self.proj, "source": source}
        r = self.gw(["hook", "session-start", "--agent", agent], stdin=json.dumps(data))
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        return r.stdout

    def marker(self):
        return os.path.join(self.xdg, "whatsnext", "welcomed")

    def test_the_command_prints_the_table(self):
        r = self.gw(["welcome"])
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout, welcome.render())

    def test_shows_once_after_install_in_a_project_with_the_banner_after_it(self):
        out = json.loads(self.hook())
        self.assertTrue(out["systemMessage"].startswith("whatsnext: one plan, one next step"))
        self.assertIn("Set up your plan", out["systemMessage"])
        self.assertTrue(os.path.exists(self.marker()))
        second = self.hook()
        self.assertNotIn("Set up your plan", second)

    def test_shows_outside_a_whatsnext_project_too(self):
        bare = os.path.join(self.home, "bare")
        os.makedirs(bare)
        out = json.loads(self.hook(cwd=bare))
        self.assertIn("Set up your plan", out["systemMessage"])
        self.assertEqual(self.hook(cwd=bare), "")

    def test_not_on_resume_clear_or_compact(self):
        for source in ("resume", "clear", "compact"):
            self.assertNotIn("Set up your plan", self.hook(source=source))
        self.assertFalse(os.path.exists(self.marker()))

    def test_codex_gets_plain_text(self):
        out = self.hook(agent="codex")
        self.assertTrue(out.startswith("whatsnext: one plan, one next step"))
        self.assertNotIn("Set up your plan", self.hook(agent="codex"))

    def test_an_unwritable_marker_says_nothing_rather_than_everything_every_time(self):
        os.chmod(os.path.join(self.xdg, "whatsnext"), 0o500)
        try:
            self.assertNotIn("Set up your plan", self.hook())
        finally:
            os.chmod(os.path.join(self.xdg, "whatsnext"), 0o700)


if __name__ == "__main__":
    unittest.main()
