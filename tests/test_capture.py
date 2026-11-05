"""Tests for plan-mode capture (`progress capture`, ADR-0006) and its resume-note line.

Run: python3 -m unittest discover -s tests
"""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fixtures import STATUS, StatusBase  # noqa: E402

from wn import capture  # noqa: E402

PLANS = "docs/project/plans"
PLAN = """# Add login

Some context.

## Write the form

1. a numbered line inside a section

## Add tests
"""


class SplitTests(unittest.TestCase):
    def test_h2_headings_win_and_code_fences_are_skipped(self):
        text = "# Title\n## One\n### Not a step\n```\n## In a fence\n```\n## Two ##\n1. numbered\n"
        self.assertEqual(capture.split_steps(text), ["One", "Two"])

    def test_items_under_a_steps_heading_beat_other_headings(self):
        text = "# Add x\n## Context\nWhy.\n## Steps\n1. Create x\n   - detail\n2. Verify x\n## Verification\n- cat x\n"
        self.assertEqual(capture.split_steps(text), ["Create x", "Verify x"])
        text = "## Implementation Steps\n- one\n- two\n## Testing\n- three\n"
        self.assertEqual(capture.split_steps(text), ["one", "two"])
        self.assertEqual(capture.split_steps("## Steps\nprose only\n## Two\n"), ["Steps", "Two"])

    def test_numbered_items_at_the_least_indent(self):
        text = "Intro\n  - bullet\n1. First\n   1. nested\n2) Second\n"
        self.assertEqual(capture.split_steps(text), ["First", "Second"])

    def test_bullets_when_nothing_else_and_checkboxes_dropped(self):
        self.assertEqual(capture.split_steps("- [ ] one\n* two\n  - nested\n"), ["one", "two"])

    def test_prose_gives_its_first_line(self):
        self.assertEqual(capture.split_steps("\n# Just do   the thing\nmore prose\n"), ["Just do the thing"])
        self.assertEqual(capture.split_steps("  \n"), [])

    def test_long_step_is_clipped(self):
        step = capture.split_steps("## " + "x" * 300)[0]
        self.assertEqual(len(step), capture.MAX_STEP)
        self.assertTrue(step.endswith("…"))


class CaptureTests(StatusBase):
    def capture(self, *args, stdin=""):
        return self.gw(["progress", "capture"] + list(args), stdin=stdin)

    def shown(self, text=PLAN, *args):
        r = self.capture("--status", "shown", "--agent", "claude-code", *args, stdin=text)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def plan_files(self):
        folder = self.p(PLANS)
        return sorted(os.listdir(folder)) if os.path.isdir(folder) else []

    def test_shown_stores_the_plan_and_writes_steps(self):
        self.task()
        r = self.shown()
        [name] = self.plan_files()
        self.assertRegex(name, r"^P-13-\d{4}-\d\d-\d\d\.md$")
        rel = "%s/%s" % (PLANS, name)
        self.assertEqual(r.stdout.strip(), "captured %s (2 steps in %s/P-13.md)" % (rel, STATUS))
        text = self.get(rel)
        self.assertRegex(text, r"^# Plan: P-13\n\n- \*\*Agent:\*\* claude-code\n- \*\*Time:\*\* \d{4}-\d\d-\d\dT\d\d:\d\dZ\n"
                               r"- \*\*Status:\*\* shown\n\n")
        self.assertTrue(text.endswith("\n" + PLAN), "the plan is copied word for word")
        progress = self.get(STATUS + "/P-13.md")
        self.assertIn("- **Plan:** %s (shown)\n" % rel, progress)
        self.assertIn("## Next action\n\nRun the login tests.\n\n## Plan steps\n\n"
                      "- [ ] Write the form\n- [ ] Add tests\n\n## Goal\n", progress)
        self.assertEqual(self.logged()[-1]["payload"], {"task": "P-13", "path": STATUS + "/P-13.md", "action": "capture"})

    def test_more_than_20_steps_keeps_20_and_counts_the_rest(self):
        self.task()
        self.shown("".join("%d. step %d\n" % (n, n) for n in range(1, 26)))
        progress = self.get(STATUS + "/P-13.md")
        self.assertEqual(len(re.findall(r"^- \[ \] step", progress, re.M)), 20)
        self.assertIn("- [ ] step 20\n… 5 more in the plan file\n", progress)

    def test_recapture_replaces_the_steps_section(self):
        self.task()
        self.shown()
        self.shown("## Only step\n")
        progress = self.get(STATUS + "/P-13.md")
        self.assertEqual(progress.count("## Plan steps"), 1)
        self.assertIn("## Plan steps\n\n- [ ] Only step\n\n## Goal", progress)
        self.assertNotIn("Write the form", progress)

    def test_last_shown_wins_but_an_approved_plan_is_kept(self):
        self.task()
        self.shown("## First\n")
        self.shown("## Second\n")
        [first] = self.plan_files()
        self.assertIn("## Second\n", self.get("%s/%s" % (PLANS, first)))
        self.assertEqual(self.capture("--status", "approved").returncode, 0)
        approved = self.get("%s/%s" % (PLANS, first))
        self.shown("## Third\n")
        self.assertEqual(self.plan_files(), sorted([first, first[:-3] + "-2.md"]))
        self.assertEqual(self.get("%s/%s" % (PLANS, first)), approved)
        self.assertIn("- **Plan:** %s/%s (shown)\n" % (PLANS, first[:-3] + "-2.md"), self.get(STATUS + "/P-13.md"))

    def test_approved_and_unapproved_change_only_a_shown_plan(self):
        for status, text in (("approved", "approved"), ("unapproved", "used without approval")):
            with self.subTest(status=status):
                self.task()
                self.shown()
                r = self.capture("--status", status)
                self.assertEqual(r.returncode, 0, r.stderr)
                [name] = self.plan_files()
                rel = "%s/%s" % (PLANS, name)
                self.assertEqual(r.stdout.strip(), "%s: %s" % (rel, text))
                self.assertIn("- **Status:** %s\n" % text, self.get(rel))
                self.assertIn("- **Plan:** %s (%s)\n" % (rel, text), self.get(STATUS + "/P-13.md"))
                before = self.get(rel)
                other = "unapproved" if status == "approved" else "approved"
                r = self.capture("--status", other)
                self.assertEqual((r.returncode, r.stdout.strip()), (0, "%s is already %s; unchanged." % (rel, text)))
                self.assertEqual(self.get(rel), before)
                os.remove(self.p(rel))

    def test_named_task_and_file_option(self):
        self.task("P-13")
        self.task("P-14", state="parked")
        self.put("plan.md", PLAN)
        r = self.capture("P-14", "--status", "shown", "--file", "plan.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("- **Agent:** unknown\n", self.get("%s/%s" % (PLANS, self.plan_files()[0])))
        self.assertIn("- [ ] Add tests", self.get(STATUS + "/P-14.md"))
        self.assertNotIn("Plan steps", self.get(STATUS + "/P-13.md"))

    def test_private_text_never_reaches_the_plan_or_the_steps(self):
        self.task()
        self.shown("## Step <private>hunter2</private> one\n")
        self.assertNotIn("hunter2", self.get("%s/%s" % (PLANS, self.plan_files()[0])))
        self.assertNotIn("hunter2", self.get(STATUS + "/P-13.md"))

    def test_plans_folder_setting(self):
        self.cfg(paths={"plans": "notes/plans"})
        self.task()
        self.shown()
        self.assertEqual(len(os.listdir(self.p("notes/plans"))), 1)
        self.assertFalse(self.has(PLANS))

    def test_refusals(self):
        r = self.capture("--status", "shown", stdin=PLAN)
        self.assertEqual(r.returncode, 1)
        self.assertIn("no active task", r.stderr)
        self.assertEqual(self.capture("P-99", "--status", "shown", stdin=PLAN).returncode, 1)
        self.assertEqual(self.capture("../x", "--status", "shown", stdin=PLAN).returncode, 1)
        self.task()
        r = self.capture("--status", "shown", stdin="  \n")
        self.assertEqual(r.returncode, 1)
        self.assertIn("the plan is empty", r.stderr)
        r = self.capture("--status", "approved")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no captured plan", r.stderr)
        self.assertEqual(self.capture("--status", "shown", "--file", "missing.md").returncode, 1)
        self.assertEqual(self.plan_files(), [])


class ResumeLineTests(StatusBase):
    """The resume note's first line carries the plan track: step N of M (and the plan's status when not approved)."""

    def note_line(self):
        return self.packet()["text"].split("\n")[0]

    def with_steps(self, steps, status="approved"):
        self.task()
        path = self.p(STATUS + "/P-13.md")
        lines = self.get(STATUS + "/P-13.md").split("\n")
        lines = capture.replace_steps(lines, ["## Plan steps", ""] + steps)
        text = "\n".join(lines).replace("- **Decisions:** none\n",
                                        "- **Decisions:** none\n- **Plan:** %s/P-13-2026-10-30.md (%s)\n" % (PLANS, status))
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def head(self):
        return "continue P-13 Add login (branch %s" % self.branch()

    def test_no_plan_no_step_text(self):
        self.task()
        self.assertEqual(self.note_line(), self.head() + ")")

    def test_first_open_step(self):
        self.with_steps(["- [x] One", "- [ ] Two", "- [ ] Three"])
        self.assertEqual(self.note_line(), self.head() + ", step 2 of 3)")

    def test_all_checked_and_more_in_the_plan_file(self):
        self.with_steps(["- [x] One", "- [x] Two"])
        self.assertEqual(self.note_line(), self.head() + ", all 2 steps checked)")
        self.with_steps(["- [x] One", "- [x] Two", "\u2026 3 more in the plan file"])
        self.assertEqual(self.note_line(), self.head() + ", step 3 of 5)")

    def test_not_approved_plan_names_its_status(self):
        self.with_steps(["- [ ] One"], status="used without approval")
        self.assertEqual(self.note_line(), self.head() + ", step 1 of 1, plan used without approval)")

    def test_line_is_first_and_next_follows(self):
        self.with_steps(["- [ ] One"])
        text = self.packet()["text"]
        self.assertTrue(text.startswith("continue P-13"))
        self.assertLess(text.index("Next: "), 400)


if __name__ == "__main__":
    unittest.main()
