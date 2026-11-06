"""Tests for the facts-only compact text (P-5): the keep-list built from the progress file and git
when there is no fresh handoff note.

Run: python3 -m unittest discover -s tests
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fixtures import StatusBase  # noqa: E402

from wn import compact as wncompact  # noqa: E402
from wn import config as wnconfig  # noqa: E402
from wn import hook as wnhook  # noqa: E402

STEPS = ["- [x] Write the form", "- [ ] Add the tests", "- [ ] Ship it"]


class FactsOnlyTests(StatusBase):
    def setUp(self):
        super().setUp()
        self.cfg()
        self.task(steps=STEPS)
        self.commit("task")
        self.put("src/login.py", "x\n")
        self.put("README.md", "changed\n")

    def facts(self):
        effective = wnconfig.load(self.proj)
        return wncompact.facts_text(self.proj, effective, wnhook.branch_task(self.proj, effective)), effective

    def test_facts_only(self):
        text, effective = self.facts()
        self.assertNotIn("\n", text)
        self.assertLessEqual(len(text), wncompact.MAX_FACTS_CHARS)
        self.assertIn("P-13", text)
        self.assertIn("branch " + self.branch(), text)
        self.assertIn("Next: Run the login tests.", text)
        self.assertIn("Plan step 2 of 3: Add the tests.", text)
        self.assertIn("Files changed: README.md, src/login.py.", text)
        task = wnhook.branch_task(self.proj, effective)
        line = wncompact.facts_line(self.proj, effective, task)
        self.assertNotIn("\n", line)
        self.assertTrue(line.endswith(text))

    def test_facts_only_json_and_precompact_use_the_same_text(self):
        text, _effective = self.facts()
        r = self.gw(["compact-instructions", "--json"])
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(r.stdout)
        self.assertIsNone(data["compact_line"])  # no handoff note: ADR-0009 item 2 is unchanged
        self.assertTrue(data["facts_line"].endswith(text))
        out = self.gw(["hook", "pre-compact", "--agent", "claude-code"], stdin=json.dumps({"session_id": "s1"})).stdout
        self.assertIn(text, out)

    def test_facts_only_long_file_list_is_cut_and_no_task_gives_none(self):
        for i in range(12):
            self.put("src/f%02d.py" % i, "x\n")
        text, _effective = self.facts()
        self.assertIn("+6 more", text)  # 14 files, 8 shown
        self.assertNotIn("\n", text)
        self.tmp_none = self.gw(["compact-instructions", "--json", "--project", self.tmp.name])
        self.assertIsNone(json.loads(self.tmp_none.stdout)["facts_line"])


if __name__ == "__main__":
    unittest.main()
