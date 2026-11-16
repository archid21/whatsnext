"""Tests for checkpoints and rollback (ADR-0029, P-71). Temp repos and a temp HOME only.

Run: python3 -m unittest tests.test_rollback
"""

import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fixtures import PLAN_PATH, PlanBase  # noqa: E402

REF = "refs/whatsnext/checkpoints/P-13"


class RollbackTests(PlanBase):
    def setUp(self):
        super().setUp()
        self.git("branch", "-M", "main")
        # whatsnext's own progress files stay out of git status, so the tree is clean unless a test dirties it.
        with open(os.path.join(self.proj, ".git", "info", "exclude"), "a") as f:
            f.write("docs/project/progress/\n")

    def sha(self, rev="HEAD"):
        return self.git("rev-parse", rev)

    def has_ref(self, ref=REF):
        return subprocess.run(["git", "-C", self.proj, "show-ref", "--verify", "--quiet", ref]).returncode == 0

    def begin(self, branch="branch", item="P-13"):
        """Start the item. Returns the start sha."""
        before = self.sha()
        r = self.start(item, "--branch", branch)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return before

    def work(self, name="a.txt", text="a\n"):
        self.put(name, text)
        self.commit("work " + name)

    def rollback(self, *flags):
        return self.plan("rollback", "P-13", *flags)

    def ask_q(self, *flags):
        return self.question(self.rollback(*(flags + ("--json",))))

    # ---- checkpoint

    def test_start_records_the_checkpoint_before_the_branch_switch(self):
        before = self.sha()
        self.assertEqual(self.start("P-13", "--branch", "branch").returncode, 0)
        self.assertEqual(self.sha(REF), before)
        self.assertEqual(self.branch(), "p-13-add-login")
        line = [l for l in self.get("docs/project/progress/P-13.md").split("\n") if l.startswith("- **Checkpoint:**")]
        self.assertEqual(len(line), 1)
        self.assertTrue(line[0].startswith("- **Checkpoint:** %s on main, 20" % before[:7]), line[0])

    def test_restart_keeps_the_first_checkpoint(self):
        first = self.sha()
        self.assertEqual(self.start("P-13", "--branch", "stay").returncode, 0)
        self.work()
        self.assertEqual(self.plan("put-back", "P-13", "--saved").returncode, 0)
        self.assertEqual(self.start("P-13", "--branch", "stay").returncode, 0)
        self.assertEqual(self.sha(REF), first)

    def test_no_commits_skips_the_checkpoint_silently(self):
        from wn import plan as wnplan
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["git", "init", "-q", d], check=True)

            class Ctx(object):
                root = os.path.realpath(d)
                folder = os.path.join(root, "p")
            self.assertIsNone(wnplan.record_checkpoint(Ctx, "P-13"))

    # ---- reset

    def test_reset_on_the_items_own_branch_asks_then_moves_back(self):
        start = self.begin()
        self.work()
        q = self.ask_q("--dirty", "stash")
        self.assertEqual(q["ask"], "rollback")
        self.assertEqual(q["answer_flag"], "--yes")
        self.assertIn("reset", q["question"])
        self.assertIn("a.txt", q["question"])
        self.assertTrue(any("work a.txt" in c for c in q["context"]["commits"]))
        self.assertEqual(self.sha(REF), start)
        r = self.rollback("--yes")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.sha(), start)
        self.assertFalse(self.has("a.txt"))
        self.assertTrue(self.has_ref())  # a second rollback still works
        self.assertEqual(self.sha(REF), start)

    def test_no_yes_changes_nothing(self):
        self.begin()
        self.work()
        head = self.sha()
        q = self.ask_q()
        self.assertEqual(q["ask"], "rollback")
        self.assertEqual(self.sha(), head)
        self.assertTrue(self.has("a.txt"))

    def test_nothing_to_undo_says_so(self):
        self.begin()
        r = self.rollback()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Nothing to undo", r.stdout)

    def test_reset_moves_a_branch_that_is_not_checked_out(self):
        start = self.begin()
        self.work()
        branch = self.branch()
        self.git("switch", "-q", "main")
        r = self.rollback("--yes")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.sha(branch), start)
        self.assertEqual(self.branch(), "main")

    def test_revert_of_a_done_item_releases_the_claim_and_journals_it(self):
        self.begin()
        self.work()
        self.assertEqual(self.plan("done", "P-13", "--evidence", "ok").returncode, 0)
        self.commit("done")
        self.assertIn("[x] P-13", self.get(PLAN_PATH))
        self.assertEqual(self.rollback("--method", "revert", "--yes").returncode, 0)
        plan = self.get(PLAN_PATH)
        self.assertIn("- [ ] P-13", plan)
        self.assertFalse(self.has_claim("P-13"))
        journal = self.get("docs/project/progress/journal/P-13.md")
        self.assertRegex(journal, r"rollback revert undone: [0-9a-f]{7}")

    def test_reset_releases_the_claim_and_journals_it(self):
        self.begin()
        self.work()
        self.assertTrue(self.has_claim("P-13"))
        self.assertEqual(self.rollback("--yes").returncode, 0)
        self.assertFalse(self.has_claim("P-13"))
        self.assertRegex(self.get("docs/project/progress/journal/P-13.md"), r"rollback reset undone: [0-9a-f]{7}")

    def test_checked_item_is_reopened_when_the_check_survives(self):
        # The check-off is uncommitted on a reverted branch: revert keeps it, so rollback reopens it.
        self.begin("stay")
        self.work()
        self.assertEqual(self.plan("done", "P-13", "--evidence", "ok").returncode, 0)
        self.assertIn("[x] P-13", self.get(PLAN_PATH))
        r = self.rollback("--dirty", "commit", "--yes")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("- [ ] P-13", self.get(PLAN_PATH))
        self.assertIn("rolled back", self.get("docs/project/progress/P-13.md"))
        self.assertFalse(self.has_claim("P-13"))

    # ---- revert

    def test_revert_when_the_branch_is_merged_into_main(self):
        start = self.begin()
        self.work()
        self.git("switch", "-q", "main")
        self.git("merge", "-q", "--ff-only", "p-13-add-login")
        merged = self.sha()
        q = self.ask_q()
        self.assertIn("revert", q["question"])
        self.assertIn("merged", q["context"]["why"])
        r = self.rollback("--yes")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(self.has("a.txt"))
        self.assertNotEqual(self.sha(), start)
        self.git("merge-base", "--is-ancestor", merged, "HEAD")  # history kept (raises when not an ancestor)

    def test_revert_on_a_shared_branch_when_started_with_stay(self):
        self.begin("stay")
        self.work()
        q = self.ask_q()
        self.assertEqual(q["context"]["method"], "revert")
        self.assertEqual(self.rollback("--yes").returncode, 0)
        self.assertFalse(self.has("a.txt"))
        self.assertEqual(self.branch(), "main")

    def test_revert_of_several_commits_undoes_them_newest_first(self):
        self.put("shared.txt", "one\n")
        self.commit("shared")
        self.begin("stay")
        self.work("shared.txt", "two\n")
        self.work("shared.txt", "three\n")
        r = self.rollback("--method", "revert", "--yes")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.get("shared.txt"), "one\n")

    def test_revert_conflict_stops_and_says_how_to_finish(self):
        self.begin()
        self.work("c.txt", "1\n")
        self.git("switch", "-q", "main")
        self.git("merge", "-q", "--ff-only", "p-13-add-login")
        self.put("c.txt", "2\n")
        self.commit("later change on main")
        r = self.rollback("--yes")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("git revert --continue", r.stderr)
        self.assertIn("git revert --abort", r.stderr)
        self.assertTrue(self.has_claim("P-13"))
        self.git("revert", "--abort")

    # ---- method override

    def test_method_reset_is_refused_where_unsafe(self):
        self.begin("stay")
        self.work()
        head = self.sha()
        r = self.rollback("--method", "reset", "--yes")
        self.assertEqual(r.returncode, 1)
        self.assertIn("unsafe", r.stderr)
        self.assertIn("--method revert", r.stderr)
        self.assertEqual(self.sha(), head)

    def test_method_reset_is_refused_for_a_merged_branch(self):
        self.begin()
        self.work()
        self.git("switch", "-q", "main")
        self.git("merge", "-q", "--ff-only", "p-13-add-login")
        r = self.rollback("--method", "reset", "--yes")
        self.assertEqual(r.returncode, 1)
        self.assertIn("merged", r.stderr)

    # ---- dirty tree

    def dirty_setup(self):
        start = self.begin()
        self.work()
        self.put("README.md", "changed\n")  # tracked, modified
        self.put("new.txt", "untracked\n")
        return start

    def test_dirty_tree_asks_before_anything_else(self):
        self.dirty_setup()
        head = self.sha()
        q = self.ask_q("--yes")
        self.assertEqual(q["ask"], "dirty")
        self.assertEqual(q["recommended"], "stash")
        # A reset would drop a save commit, so commit is not offered here (only for a revert).
        self.assertEqual(q["answer_flag"], "--dirty stash|cancel")
        self.assertEqual([o["value"] for o in q["options"]], ["stash", "cancel"])
        self.assertEqual(self.sha(), head)
        self.assertEqual(self.get("README.md"), "changed\n")

    def test_stash_keeps_the_work_restorable(self):
        start = self.dirty_setup()
        r = self.rollback("--dirty", "stash", "--yes")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("git stash pop", r.stdout)
        self.assertEqual(self.sha(), start)
        self.assertIn("whatsnext rollback P-13", self.git("stash", "list"))
        self.assertFalse(self.has("new.txt"))
        self.git("stash", "pop")
        self.assertEqual(self.get("new.txt"), "untracked\n")
        self.assertEqual(self.get("README.md"), "changed\n")

    def test_commit_answer_saves_the_work_in_a_commit(self):
        self.begin("stay")
        self.work()
        self.put("new.txt", "untracked\n")
        r = self.rollback("--dirty", "commit", "--yes")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("whatsnext: save work before rollback of P-13", self.git("log", "--format=%s"))
        self.assertEqual(self.get("new.txt"), "untracked\n")

    def test_commit_answer_is_refused_for_a_reset(self):
        self.dirty_setup()
        head = self.sha()
        r = self.rollback("--dirty", "commit", "--yes")
        self.assertEqual(r.returncode, 1)
        self.assertIn("would drop that commit", r.stderr)
        self.assertEqual(self.sha(), head)
        self.assertEqual(self.get("README.md"), "changed\n")

    def test_whatsnext_own_files_do_not_count_as_dirty_and_survive_a_reset(self):
        self.begin()
        self.work()
        self.put("docs/project/progress/notes-extra.md", "mine\n")
        r = self.rollback("--yes")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.get("docs/project/progress/notes-extra.md"), "mine\n")

    def test_cancel_changes_nothing(self):
        self.dirty_setup()
        head, status = self.sha(), self.git("status", "--porcelain")
        r = self.rollback("--dirty", "cancel", "--yes")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.sha(), head)
        self.assertEqual(self.git("status", "--porcelain"), status)
        self.assertEqual(self.git("stash", "list"), "")
        self.assertTrue(self.has_claim("P-13"))

    def test_dirty_answer_without_yes_asks_the_confirm_and_changes_nothing(self):
        self.dirty_setup()
        status = self.git("status", "--porcelain")
        q = self.ask_q("--dirty", "stash")
        self.assertEqual(q["ask"], "rollback")
        self.assertEqual(self.git("status", "--porcelain"), status)
        self.assertEqual(self.git("stash", "list"), "")

    def test_untracked_files_survive_without_a_stash_when_there_is_nothing_to_undo(self):
        self.begin()
        self.put("new.txt", "untracked\n")
        r = self.rollback("--yes")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.get("new.txt"), "untracked\n")

    # ---- refusals

    def test_no_checkpoint_refuses_with_manual_steps(self):
        self.assertEqual(self.start("P-13", "--branch", "stay").returncode, 0)
        self.git("update-ref", "-d", REF)
        r = self.rollback("--yes")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no checkpoint", r.stderr)
        self.assertIn("git revert", r.stderr)

    def test_missing_checkpoint_commit_refuses(self):
        self.assertEqual(self.start("P-13", "--branch", "stay").returncode, 0)
        # A ref to a blob is not a commit.
        blob = self.git("hash-object", "-w", "README.md")
        self.git("update-ref", REF, blob)
        r = self.rollback("--yes")
        self.assertEqual(r.returncode, 1)
        self.assertIn("checkpoint", r.stderr)

    def test_merge_in_progress_refuses(self):
        self.begin()
        self.work()
        head = self.sha()
        with open(os.path.join(self.proj, ".git", "MERGE_HEAD"), "w") as f:
            f.write(head + "\n")
        r = self.rollback("--yes")
        self.assertEqual(r.returncode, 1)
        self.assertIn("merge is in progress", r.stderr)
        self.assertEqual(self.sha(), head)

    def test_unknown_item_fails(self):
        r = self.plan("rollback", "P-99")
        self.assertEqual(r.returncode, 1)


if __name__ == "__main__":
    unittest.main()
