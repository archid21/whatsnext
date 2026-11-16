"""Tests for tracker sync (P-79): `plan import --from beads|github` and `plan close-tracker`.

Fake `bd` and `gh` scripts on a temp PATH stand in for the real tools: no network, no real tracker.
Run: python3 -m unittest discover -s tests
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fixtures import PLAN_PATH, PlanBase  # noqa: E402

GH_ROWS = [{"number": 12, "title": "Fix · login", "url": "https://example.invalid/12"},
           {"number": 13, "title": "Write docs", "url": "https://example.invalid/13"}]
BD_ROWS = [{"id": "wn-a1", "title": "Cache results", "status": "open"}]


@unittest.skipIf(os.name == "nt", "fake tools are shell scripts")
class TrackerTests(PlanBase):
    def setUp(self):
        super().setUp()
        self.bin = os.path.join(self.tmp.name, "bin")
        os.makedirs(self.bin)
        self.calls = os.path.join(self.tmp.name, "calls")
        self.env["PATH"] = self.bin + os.pathsep + "/usr/bin:/bin"

    def tool(self, name, rows, fail_close=False):
        data = os.path.join(self.tmp.name, name + ".json")
        with open(data, "w", encoding="utf-8") as f:
            json.dump(rows, f)
        close = "exit 1" if fail_close else "exit 0"
        script = ("#!/bin/sh\necho \"%s $*\" >> '%s'\n"
                  "case \"$1 $2\" in\n  'issue list'|'ready --json') cat '%s' ;;\n"
                  "  'issue close'|close*) %s ;;\nesac\n") % (name, self.calls, data, close)
        path = os.path.join(self.bin, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(script)
        os.chmod(path, 0o755)

    def text(self):
        with open(os.path.join(self.proj, PLAN_PATH), encoding="utf-8") as f:
            return f.read()

    def called(self):
        if not os.path.exists(self.calls):
            return []
        with open(self.calls, encoding="utf-8") as f:
            return f.read().splitlines()

    def test_github_import_asks_for_done_means_then_approval_then_adds_with_tracker_ids(self):
        self.tool("gh", GH_ROWS)
        before = self.text()
        r, q = self.jplan("import", "--from", "github")
        self.assertEqual(r.returncode, 4)
        self.assertEqual(q["ask"], "done_means")
        r, q = self.jplan("import", "--from", "github", "--done-means", "`true`")
        self.assertEqual(r.returncode, 4)
        self.assertEqual(q["ask"], "import")
        self.assertEqual(q["answer_flag"], "--yes")
        self.assertEqual([i["tracker"] for i in q["context"]["items"]], ["gh#12", "gh#13"])
        self.assertEqual(self.text(), before)
        r, out = self.jplan("import", "--from", "github", "--done-means", "`true`", "--yes")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([a["tracker"] for a in out["added"]], ["gh#12", "gh#13"])
        self.assertIn("- [ ] P-17 Fix - login · done means: `true` · tracker: gh#12\n", self.text())
        self.assertIn("· tracker: gh#13\n", self.text())
        self.assertIn("gh issue list --state open --json number,title,url", self.called())

    def test_import_skips_items_already_in_the_plan(self):
        self.tool("gh", GH_ROWS)
        self.assertEqual(self.plan("import", "--from", "github", "--done-means", "`true`", "--yes").returncode, 0)
        before = self.text()
        r, out = self.jplan("import", "--from", "github", "--done-means", "`true`", "--yes")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(out["added"], [])
        self.assertEqual(out["skipped"], 2)
        self.assertEqual(self.text(), before)

    def test_beads_import_uses_bd_ready(self):
        self.tool("bd", BD_ROWS)
        r = self.plan("import", "--from", "beads", "--done-means", "`true`", "--yes", "--section", "Now")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Cache results · done means: `true` · tracker: bd:wn-a1", self.text())
        self.assertIn("bd ready --json", self.called())

    def test_missing_tool_fails_and_writes_nothing(self):
        before = self.text()
        r = self.plan("import", "--from", "beads", "--done-means", "`true`", "--yes")
        self.assertEqual(r.returncode, 1)
        self.assertIn("`bd` is not installed", r.stderr)
        self.assertEqual(self.text(), before)

    def test_done_offers_to_close_and_close_tracker_runs_the_tool(self):
        self.tool("gh", GH_ROWS)
        self.plan("import", "--from", "github", "--done-means", "`true`", "--yes")
        r = self.plan("close-tracker", "P-17")
        self.assertEqual(r.returncode, 1)
        self.assertIn("not done", r.stderr)
        r, out = self.jplan("done", "P-17", "--verify")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(out["tracker_offer"]["answer"], "plan close-tracker P-17")
        self.assertNotIn("gh issue close 12", self.called())
        r = self.plan("close-tracker", "P-17")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("gh issue close 12", self.called())

    def test_failed_close_keeps_the_item_done(self):
        self.tool("gh", GH_ROWS, fail_close=True)
        self.plan("import", "--from", "github", "--done-means", "`true`", "--yes")
        self.plan("done", "P-17", "--evidence", "checked by hand")
        r = self.plan("close-tracker", "P-17")
        self.assertEqual(r.returncode, 1)
        self.assertIn("still done", r.stderr)
        self.assertIn("- [x] P-17", self.text())

    def test_done_without_tracker_has_no_offer(self):
        r = self.plan("done", "P-13", "--evidence", "x")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("Offer:", r.stdout)


if __name__ == "__main__":
    unittest.main()
