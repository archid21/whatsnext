"""Tests for `whatsnext init` (ADR-0007, git mode).

Run: python3 -m unittest discover -s tests
"""

import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fixtures import STATUS, PLAN_PATH, RepoBase, Sandbox  # noqa: E402

START = "<!-- whatsnext:start -->"
END = "<!-- whatsnext:end -->"
CREATED = ("docs/project/PLAN.md", ".whatsnext/config.json")


class InitBase(RepoBase):
    def setUp(self):
        super().setUp()
        os.remove(self.p(".whatsnext/config.json"))  # RepoBase writes a test backend config; init starts from none
        os.rmdir(self.p(".whatsnext"))

    def init(self, *flags):
        return self.gw(["init"] + list(flags))

    def snapshot(self):
        out = {}
        for base, dirs, files in os.walk(self.proj):
            dirs[:] = [d for d in dirs if d != ".git"]
            for d in dirs:
                out[os.path.relpath(os.path.join(base, d), self.proj) + "/"] = None
            for f in files:
                path = os.path.join(base, f)
                with open(path, "rb") as fh:
                    out[os.path.relpath(path, self.proj)] = fh.read()
        return out


class InitCreateTests(InitBase):
    def test_empty_repo_gets_everything(self):
        r = self.init()
        self.assertEqual(r.returncode, 0, r.stderr)
        plan = self.get(PLAN_PATH)
        for heading in ("## Now", "## Next", "## Later", "- [ ] P-N Title · done means:"):
            self.assertIn(heading, plan)
        self.assertEqual(self.get(".whatsnext/config.json"), "{}\n")
        self.assertTrue(os.path.isdir(self.p(STATUS)))
        self.assertTrue(os.path.isdir(self.p(STATUS + "/journal")))
        agents = self.get("AGENTS.md")
        self.assertTrue(agents.startswith(START) and agents.rstrip().endswith(END), agents)
        for word in ("resume-note", "progress next", "plan done <id> --verify"):
            self.assertIn(word, agents)
        self.assertIn("hooks.json", r.stdout)
        self.assertFalse(self.has("CLAUDE.md") or self.has(".gitattributes") or self.has(".claude"))

    def test_the_created_plan_and_config_load(self):
        self.init()
        r = self.gw(["plan"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.gw(["config", "show"]).returncode, 0)

    def test_second_init_changes_nothing(self):
        self.init()
        before = self.snapshot()
        r = self.init()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.snapshot(), before)
        self.assertIn("Nothing to change", r.stdout)
        self.assertEqual(self.get("AGENTS.md").count(START), 1)

    def test_existing_files_are_never_overwritten(self):
        self.put(PLAN_PATH, "# Mine\n- [ ] P-1 Keep me\n")
        self.put(".whatsnext/config.json", '{"modules": {}}\n')
        r = self.init()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.get(PLAN_PATH), "# Mine\n- [ ] P-1 Keep me\n")
        self.assertEqual(self.get(".whatsnext/config.json"), '{"modules": {}}\n')
        self.assertIn("kept docs/project/PLAN.md", r.stdout)

    def test_plan_path_follows_config(self):
        self.put(".whatsnext/config.json", '{"paths": {"plan": "notes/ROADMAP.md", "progress": "notes/progress"}}\n')
        r = self.init()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.has("notes/ROADMAP.md"))
        self.assertTrue(os.path.isdir(self.p("notes/progress/journal")))
        self.assertFalse(self.has("docs"))
        self.assertIn("notes/ROADMAP.md", self.get("AGENTS.md"))


class InitIgnoreTests(InitBase):
    def test_init_adds_the_sessions_line_to_gitignore(self):
        had = self.get(".gitignore") if self.has(".gitignore") else None
        r = self.init()
        self.assertEqual(r.returncode, 0, r.stderr)
        text = self.get(".gitignore")
        self.assertIn(".whatsnext/sessions/\n", text)
        if had:
            self.assertTrue(text.startswith(had))

    def test_existing_text_is_kept_and_a_missing_newline_is_added(self):
        self.put(".gitignore", "node_modules/")
        self.init()
        self.assertEqual(self.get(".gitignore"), "node_modules/\n.whatsnext/sessions/\n")

    def test_a_covering_line_means_no_change(self):
        for line in (".whatsnext/sessions/", ".whatsnext/", "/.whatsnext"):
            with self.subTest(line=line):
                self.put(".gitignore", "build/\n%s\n" % line)
                r = self.init()
                self.assertEqual(self.get(".gitignore"), "build/\n%s\n" % line)
                self.assertIn("kept .gitignore", r.stdout)

    def test_dry_run_only_says_it_would_add_the_line(self):
        self.put(".gitignore", "build/\n")
        r = self.init("--dry-run")
        self.assertIn("would add .whatsnext/sessions/ to .gitignore", r.stdout)
        self.assertEqual(self.get(".gitignore"), "build/\n")

    def test_the_hook_session_folder_is_then_ignored(self):
        self.init()
        self.put(".whatsnext/sessions/abc.json", "{}")
        out = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=self.proj,
                             capture_output=True, text=True).stdout
        self.assertNotIn("sessions/abc.json", out)


class InitAgentsTests(InitBase):
    ORIGINAL = "# Rules\n\nBe kind.\n\n## More\n\n- one\n- two\n"

    def test_existing_text_is_kept_byte_for_byte_before_the_block(self):
        self.put("AGENTS.md", self.ORIGINAL)
        self.init()
        agents = self.get("AGENTS.md")
        self.assertTrue(agents.startswith(self.ORIGINAL + "\n" + START), agents)
        self.assertEqual(agents.count(START), 1)

    def test_text_without_final_newline_still_gets_a_blank_line(self):
        self.put("AGENTS.md", "# Rules\nBe kind.")
        self.init()
        self.assertTrue(self.get("AGENTS.md").startswith("# Rules\nBe kind.\n\n" + START))

    def test_crlf_file_gets_crlf_block(self):
        self.put("AGENTS.md", "# Rules\r\n\r\nBe kind.\r\n")
        self.init()
        agents = self.get("AGENTS.md")
        self.assertTrue(agents.startswith("# Rules\r\n\r\nBe kind.\r\n\r\n" + START + "\r\n"))
        self.assertNotRegex(agents.replace("\r\n", ""), "\n")
        self.init("--undo")
        self.assertEqual(self.get("AGENTS.md"), "# Rules\r\n\r\nBe kind.\r\n")

    def test_existing_block_is_left_unchanged(self):
        mine = "# Rules\n\n%s\nmy own words\n%s\n\ntail\n" % (START, END)
        self.put("AGENTS.md", mine)
        r = self.init()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.get("AGENTS.md"), mine)

    def test_broken_markers_refuse_and_change_nothing(self):
        self.put("AGENTS.md", "# Rules\n%s\nno end\n" % START)
        before = self.snapshot()
        r = self.init()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn(END, r.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_other_agent_files_are_not_touched(self):
        self.put("CLAUDE.md", "mine\n")
        self.put(".gitattributes", "* text=auto\n")
        self.init()
        self.assertEqual(self.get("CLAUDE.md"), "mine\n")
        self.assertEqual(self.get(".gitattributes"), "* text=auto\n")


class InitDryRunTests(InitBase):
    def test_dry_run_writes_nothing_and_says_what_it_would_do(self):
        self.put("AGENTS.md", "# Rules\n")
        before = self.snapshot()
        r = self.init("--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.snapshot(), before)
        for line in ("would create docs/project/PLAN.md", "would create .whatsnext/config.json",
                     "would create docs/project/progress/", "would create docs/project/progress/journal/",
                     "would append the whatsnext block to AGENTS.md"):
            self.assertIn(line, r.stdout)
        self.assertIn("Dry run: nothing written.", r.stdout)

    def test_dry_run_on_a_set_up_repo_only_adds_the_block(self):
        self.init()
        self.put("AGENTS.md", "# Rules\n")
        r = self.init("--dry-run")
        self.assertIn("kept docs/project/PLAN.md", r.stdout)
        self.assertIn("would append the whatsnext block to AGENTS.md", r.stdout)
        self.assertNotIn("would create", r.stdout)


class InitUndoTests(InitBase):
    def test_undo_removes_only_the_block(self):
        original = "# Rules\n\nBe kind.\n"
        self.put("AGENTS.md", original)
        self.init()
        r = self.init("--undo")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.get("AGENTS.md"), original)
        for rel in CREATED:
            self.assertTrue(self.has(rel), rel)
        self.assertTrue(os.path.isdir(self.p(STATUS + "/journal")))
        self.assertIn("Left in place", r.stdout)

    def test_undo_deletes_an_agents_file_that_only_held_the_block(self):
        self.init()
        self.assertTrue(self.has("AGENTS.md"))
        r = self.init("--undo")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(self.has("AGENTS.md"))
        self.assertIn("deleted", r.stdout)

    def test_undo_keeps_text_the_user_wrote_after_the_block(self):
        self.put("AGENTS.md", "# Rules\n\nBe kind.\n")
        self.init()
        with open(self.p("AGENTS.md"), "a", encoding="utf-8", newline="") as f:
            f.write("\n## Later notes\n\nmore\n")
        self.init("--undo")
        self.assertEqual(self.get("AGENTS.md"), "# Rules\n\nBe kind.\n\n## Later notes\n\nmore\n")

    def test_undo_then_init_again_works(self):
        self.put("AGENTS.md", "# Rules\n")
        self.init()
        first = self.get("AGENTS.md")
        self.init("--undo")
        self.init()
        self.assertEqual(self.get("AGENTS.md"), first)

    def test_undo_with_dry_run_writes_nothing(self):
        self.init()
        before = self.snapshot()
        r = self.init("--undo", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.snapshot(), before)
        self.assertIn("would remove the whatsnext block", r.stdout)

    def test_undo_without_a_block_changes_nothing(self):
        self.put("AGENTS.md", "# Rules\n")
        r = self.init("--undo")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.get("AGENTS.md"), "# Rules\n")
        self.assertIn("Nothing to remove", r.stdout)


class InitRefusalTests(InitBase):
    def test_format_3_progress_file_refuses_and_changes_nothing(self):
        self.put(STATUS + "/P-1.md", "format: 3\n\n# P-1: Future\n\n- **State:** active\n")
        before = self.snapshot()
        for flags in ((), ("--dry-run",)):
            r = self.init(*flags)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("format 3", r.stderr)
            self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.has("AGENTS.md"))

    def test_format_2_progress_file_is_fine(self):
        self.put(STATUS + "/P-1.md", "format: 2\n\n# P-1: Now\n\n- **State:** active\n")
        self.assertEqual(self.init().returncode, 0)


class InitOutsideGitTests(Sandbox):
    git = False

    def test_outside_git_exits_non_zero_and_writes_nothing(self):
        for flags in ([], ["--dry-run"], ["--undo"]):
            r = self.gw(["init"] + flags)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("git repository", r.stderr)
        self.assertEqual(os.listdir(self.proj), [])


if __name__ == "__main__":
    unittest.main()
