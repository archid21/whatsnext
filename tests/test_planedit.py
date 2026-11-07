"""Tests for editing the plan from the command line (P-45): `plan add`, `plan drop`, `plan move`.

Run: python3 -m unittest discover -s tests
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fixtures import PLAN_PATH, PlanBase  # noqa: E402

from wn import plan  # noqa: E402


class PlanEditTests(PlanBase):
    def text(self):
        with open(os.path.join(self.proj, PLAN_PATH), encoding="utf-8") as f:
            return f.read()

    def ids(self, section=None):
        _lines, items = plan.parse_text(self.text())
        return [i.id for i in items if section is None or i.section == section]

    def check_clean(self):
        r = self.plan("check")
        self.assertNotIn("duplicate", r.stdout + r.stderr)
        self.assertNotIn("not in the plan", r.stdout + r.stderr)

    # ---- add

    def test_add_uses_the_next_free_id_and_goes_last_in_its_section(self):
        r = self.plan("add", "Export CSV", "--done-means", "`python3 -m unittest`", "--section", "now")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.ids("Now"), ["P-13", "P-14", "P-17"])
        self.assertIn("- [ ] P-17 Export CSV · done means: `python3 -m unittest`\n", self.text())
        self.check_clean()

    def test_add_defaults_to_next_and_keeps_every_other_line(self):
        before = self.text()
        self.assertEqual(self.plan("add", "Billing", "--done-means", "`true`").returncode, 0)
        after = self.text().split("\n")
        self.assertEqual(self.ids("Next"), ["P-15", "P-17"])
        self.assertEqual([l for l in after if "P-17" not in l], before.split("\n"))

    def test_add_without_a_done_means_asks_and_writes_nothing(self):
        before = self.text()
        r, _ = self.jplan("add", "Billing")
        q = self.question(r)
        self.assertEqual(q.get("ask"), "done_means")
        self.assertEqual(q.get("answer_flag"), '--done-means "<text>"')
        self.assertEqual(self.text(), before)

    def test_add_refuses_a_duplicate_id_and_a_bad_id(self):
        before = self.text()
        r = self.plan("add", "X", "--done-means", "y", "--id", "P-13")
        self.assertEqual(r.returncode, 1)
        self.assertIn("already in", r.stderr)
        r = self.plan("add", "X", "--done-means", "y", "--id", "nope")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.text(), before)

    def test_add_with_an_explicit_id_and_blocked_by(self):
        r = self.plan("add", "Report", "--done-means", "`true`", "--id", "P-40", "--blocked-by", "P-13,P-14")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("P-40 Report · done means: `true` · blocked by: P-13, P-14", self.text())
        self.assertEqual(self.plan("add", "Z", "--done-means", "y", "--blocked-by", "P-99").returncode, 1)

    def test_add_refuses_an_id_or_prefix_with_a_line_break_or_bad_shape(self):
        before = self.text()
        for flag, value in (("--id", "P-50\n"), ("--id", "P-50\n- [ ] P-51 x"), ("--prefix", "SK\n- [ ] P-9"), ("--prefix", "sk"), ("--prefix", "")):
            args = ["add", "X", "--done-means", "`true`", flag, value]
            r = self.plan(*args)
            if flag == "--prefix" and value == "":
                self.assertEqual(r.returncode, 0)  # an empty prefix means the default
                before = self.text()
                continue
            self.assertEqual(r.returncode, 1, (flag, value, r.stdout))
            self.assertEqual(self.text(), before)

    def test_add_with_a_prefix_starts_its_own_numbers(self):
        self.plan("add", "From a spec", "--done-means", "`true`", "--prefix", "SK")
        self.plan("add", "Another", "--done-means", "`true`", "--prefix", "SK")
        self.assertEqual([i for i in self.ids() if i.startswith("SK-")], ["SK-1", "SK-2"])

    def test_add_keeps_a_title_free_of_the_field_separator(self):
        self.plan("add", "One · two", "--done-means", "`true`")
        _lines, items = plan.parse_text(self.text())
        added = [i for i in items if i.id == "P-17"][0]
        self.assertEqual((added.title, added.done_means), ("One - two", "`true`"))

    def test_add_creates_a_missing_section(self):
        with open(os.path.join(self.proj, PLAN_PATH), "w", encoding="utf-8") as f:
            f.write("# Plan\n\n## Now\n- [ ] P-1 A · done means: `true`\n")
        self.assertEqual(self.plan("add", "B", "--done-means", "`true`", "--section", "Later").returncode, 0)
        self.assertEqual(self.ids("Later"), ["P-2"])
        self.assertEqual(self.ids("Now"), ["P-1"])

    def test_add_to_an_empty_section(self):
        with open(os.path.join(self.proj, PLAN_PATH), "w", encoding="utf-8") as f:
            f.write("# Plan\n\n## Now\n\n## Next\n\n## Later\n")
        self.plan("add", "First", "--done-means", "`true`", "--section", "Next")
        self.assertEqual(self.ids("Next"), ["P-1"])
        self.assertEqual(self.ids("Now"), [])

    def test_add_json(self):
        r, data = self.jplan("add", "J", "--done-means", "`true`")
        self.assertEqual((r.returncode, data["id"], data["section"]), (0, "P-17", "Next"))

    # ---- drop

    def test_drop_removes_one_line(self):
        before = self.text().split("\n")
        self.assertEqual(self.plan("drop", "P-16").returncode, 0)
        self.assertEqual(self.text().split("\n"), [l for l in before if "P-16" not in l])

    def test_drop_refuses_an_item_in_progress(self):
        self.set_claim("P-14")
        r = self.plan("drop", "P-14")
        self.assertEqual(r.returncode, 1)
        self.assertIn("in progress", r.stderr)
        self.assertIn("P-14", self.ids())

    def test_drop_refuses_an_item_held_in_another_worktree(self):
        self.set_claim("P-14", worktree="/elsewhere/worktree")
        r = self.plan("drop", "P-14")
        self.assertEqual(r.returncode, 1)
        self.assertIn("in progress", r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertIn("P-14", self.ids())

    def test_drop_refuses_an_item_another_open_item_waits_for(self):
        self.plan("add", "Report", "--done-means", "`true`", "--blocked-by", "P-13")
        r = self.plan("drop", "P-13")
        self.assertEqual(r.returncode, 1)
        self.assertIn("P-17", r.stderr)
        self.assertIn("P-13", self.ids())

    def test_drop_unknown_item(self):
        self.assertEqual(self.plan("drop", "P-99").returncode, 1)

    # ---- move

    def test_move_to_a_section_goes_last(self):
        self.assertEqual(self.plan("move", "P-13", "--to", "later").returncode, 0)
        self.assertEqual(self.ids("Now"), ["P-14"])
        self.assertEqual(self.ids("Later"), ["P-16", "P-13"])
        self.check_clean()

    def test_move_into_an_empty_section(self):
        with open(os.path.join(self.proj, PLAN_PATH), "w", encoding="utf-8") as f:
            f.write("# Plan\n\n## Now\n- [ ] P-1 A · done means: `true`\n\n## Next\n\n## Later\n")
        self.assertEqual(self.plan("move", "P-1", "--to", "Next").returncode, 0)
        self.assertEqual((self.ids("Now"), self.ids("Next")), ([], ["P-1"]))

    def test_move_before_and_after_another_item(self):
        self.assertEqual(self.plan("move", "P-14", "--before", "P-13").returncode, 0)
        self.assertEqual(self.ids("Now"), ["P-14", "P-13"])
        self.assertEqual(self.plan("move", "P-14", "--after", "P-15").returncode, 0)
        self.assertEqual(self.ids("Now"), ["P-13"])
        self.assertEqual(self.ids("Next"), ["P-15", "P-14"])

    def test_move_needs_exactly_one_target_and_a_real_item(self):
        before = self.text()
        self.assertEqual(self.plan("move", "P-13").returncode, 1)
        self.assertEqual(self.plan("move", "P-13", "--to", "Next", "--before", "P-15").returncode, 1)
        self.assertEqual(self.plan("move", "P-13", "--to", "Soon").returncode, 1)
        self.assertEqual(self.plan("move", "P-13", "--before", "P-13").returncode, 1)
        self.assertEqual(self.plan("move", "P-13", "--before", "P-99").returncode, 1)
        self.assertEqual(self.plan("move", "P-99", "--to", "Now").returncode, 1)
        self.assertEqual(self.text(), before)


if __name__ == "__main__":
    unittest.main()
