"""Tests for `progress pr-body <id>` (P-61): a PR description from recorded facts, no model call.

Run: python3 -m unittest discover -s tests
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fixtures import PLAN_PATH, PlanBase, task_text  # noqa: E402

PLAN = """# Plan

## Now
- [x] P-13 Add login · done means: `true` · evidence: verified: true passed in 1 s (2026-11-01T10:00Z) at abc1234 t:deadbeef
- [ ] P-14 Rate-limit the API · done means: `true`
- [x] P-15 Copy review · done means: the copy reads well · evidence: looked fine (2026-11-02T10:00Z)
"""
STEPS = ["- [x] Write the form.", "- [ ] Style it.", "- [x] Add tests."]


class PrBodyTests(PlanBase):
    def setUp(self):
        super().setUp()
        self.git("branch", "-M", "main")
        self.put(PLAN_PATH, PLAN)
        self.commit("plan")

    def body(self, task_id="P-13", *extra):
        r = self.gw(["progress", "pr-body", task_id] + list(extra))
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def full_task(self, task_id="P-13", branch="p-13-add-login"):
        self.put("docs/project/progress/%s.md" % task_id, task_text(
            task_id, title="Add login", state="done", branch=branch, decisions="ADR-0009",
            goal="Users can sign in.\nDone means: `true`", done="Login form and session cookie.",
            questions="Should we add SSO?", steps=STEPS))

    def test_full_description(self):
        self.git("switch", "-q", "-c", "p-13-add-login")
        self.put("src/login.py", "x = 1\n")
        self.put("docs/decisions/ADR-0009-login.md", "# ADR-0009\n")
        self.commit("Add the login form")
        self.git("switch", "-q", "main")
        self.full_task()
        out = self.body()
        self.assertTrue(out.startswith("# P-13: Add login\n\n## Goal\n\nUsers can sign in.\nDone means: `true`\n"), out)
        self.assertIn("## Done\n\nLogin form and session cookie.\n\n- Write the form.\n- Add tests.\n", out)
        self.assertNotIn("Style it.", out)  # unchecked steps are not done
        self.assertIn("## Decisions\n\nADR-0009\n\nAdded in this branch: ADR-0009-login\n", out)
        self.assertIn("## Verification\n\n- verified: true passed in 1 s (2026-11-01T10:00Z) at abc1234 t:deadbeef "
                      "(a command run by `plan done --verify`)", out)
        self.assertNotIn("Done means: `true`\n\n- verified", out)  # the Goal already says it
        self.assertIn("Commits on `p-13-add-login` since `main`:", out)
        self.assertRegex(out, r"- [0-9a-f]{7,} Add the login form")
        self.assertIn("src/login.py", out)
        self.assertTrue(out.rstrip().endswith("## Open questions\n\nShould we add SSO?"), out)

    def test_sparse_file_leaves_empty_sections_out(self):
        self.task("P-14", title="Rate-limit the API", branch="main", goal="", done="", questions="")
        out = self.body("P-14")
        self.assertNotIn("## Done", out)
        self.assertNotIn("## Changes", out)
        self.assertNotIn("## Open questions", out)
        self.assertIn("## Verification\n\nDone means: `true`\n\nNot verified yet.", out)

    def test_person_evidence_is_marked(self):
        self.task("P-15", title="Copy review", branch="main")
        self.assertIn("looked fine (2026-11-02T10:00Z) (a person's check, not a command)", self.body("P-15"))

    def test_cherry_picked_branch_has_no_changes_section(self):
        self.git("switch", "-q", "-c", "p-13-add-login")
        self.put("src/login.py", "x = 1\n")
        self.commit("Add the login form")
        sha = self.git("rev-parse", "HEAD")
        self.git("switch", "-q", "main")
        self.git("cherry-pick", sha)
        self.full_task()
        self.assertNotIn("## Changes", self.body())

    def test_deleted_branch_has_no_changes_section(self):
        self.full_task(branch="gone")
        self.assertNotIn("## Changes", self.body())

    def test_trailer(self):
        self.full_task()
        out = self.body("P-13", "--trailer", "Generated with a tool")
        self.assertTrue(out.rstrip().endswith("Should we add SSO?\n\nGenerated with a tool"), out)
        self.assertNotIn("Generated", self.body())

    def test_json(self):
        self.full_task()
        data = json.loads(self.body("P-13", "--json"))
        self.assertEqual(data["title"], "P-13: Add login")
        self.assertEqual(data["sections"], ["Goal", "Done", "Decisions", "Verification", "Open questions"])
        self.assertTrue(data["body"].startswith("## Goal"))

    def test_control_characters_are_removed(self):
        self.put("docs/project/progress/P-13.md", task_text("P-13", title="Add login", state="done", branch="main",
                                                          done="Done\x1b[31m red\x07 bell"))
        out = self.body()
        self.assertIn("Done[31m red bell", out)
        self.assertNotIn("\x1b", out)
        self.assertNotIn("\x07", out)

    def test_unknown_id_exits_1(self):
        r = self.gw(["progress", "pr-body", "P-99"])
        self.assertEqual(r.returncode, 1)
        self.assertIn("no progress file for P-99", r.stderr)

    def test_writes_nothing(self):
        self.full_task()
        self.commit("progress")
        self.body()
        self.assertEqual(self.git("status", "--porcelain"), "")


class PrBodyNoGitTests(PlanBase):
    def test_outside_git_the_file_is_enough(self):
        self.put(PLAN_PATH, PLAN)
        self.task("P-14", title="Rate-limit the API", branch="p-14", goal="Limit it.")
        env = dict(self.env, GIT_DIR=os.path.join(self.tmp.name, "nowhere"))
        import subprocess
        r = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                                         "skills", "whatsnext", "scripts", "whatsnext.py"),
                            "progress", "pr-body", "P-14"], capture_output=True, text=True, env=env, cwd=self.proj)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("## Goal\n\nLimit it.", r.stdout)
        self.assertNotIn("## Changes", r.stdout)


if __name__ == "__main__":
    unittest.main()
