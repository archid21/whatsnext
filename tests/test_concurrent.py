"""Tests for parallel sessions in one checkout (ADR-0020): session-aware claims, the active task per session,
the Start question, concurrentStart, and the "always" offer.

Run: python3 -m unittest discover -s tests
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fixtures import STATUS, PlanBase, ts  # noqa: E402

from wn import claims, concurrent, hook, journal, status  # noqa: E402

WARNING = "P-13 is in progress in another session in this folder. Edits and commits will mix."


class OwnershipTests(PlanBase):
    """Point 1: a claim belongs to a session."""

    def held(self, session, agent="claude-code", item="P-13"):
        got, other = claims.claim(self.proj, item, agent, session=session)
        self.assertIsNone(other)
        return got

    def test_is_ours_needs_the_same_session_when_both_have_one(self):
        mine = self.held("A")
        self.assertTrue(claims.is_ours(mine, "claude-code", self.proj, "A"))
        self.assertFalse(claims.is_ours(mine, "claude-code", self.proj, "B"))  # another live session: a conflict
        self.assertFalse(claims.is_ours(mine, "codex", self.proj, "A"))  # the agent still has to match

    def test_no_session_id_on_either_side_keeps_the_old_rule(self):
        with_session, without = self.held("A"), dict(self.held("A"), session=None)
        self.assertTrue(claims.is_ours(with_session, "claude-code", self.proj))  # the caller has none
        self.assertTrue(claims.is_ours(without, "claude-code", self.proj, "B"))  # the claim has none
        self.assertTrue(claims.is_ours(without, "claude-code", self.proj))

    def test_a_stale_claim_of_another_session_keeps_the_old_rule(self):
        stale = dict(self.held("A"), updated=ts(5 * 60))
        self.assertTrue(claims.is_ours(stale, "claude-code", self.proj, "B", "4h"))
        live = dict(self.held("A"), updated=ts(30))
        self.assertFalse(claims.is_ours(live, "claude-code", self.proj, "B", "4h"))
        self.assertTrue(claims.is_rival(live, self.proj, "B", "4h"))
        self.assertFalse(claims.is_rival(stale, self.proj, "B", "4h"))
        self.assertFalse(claims.is_rival(live, self.proj, "A", "4h"))
        self.assertFalse(claims.is_rival(live, self.proj, None, "4h"))

    def test_claim_by_another_live_session_is_a_conflict(self):
        self.held("A")
        got, other = claims.claim(self.proj, "P-13", "claude-code", session="B")
        self.assertIsNone(got)
        self.assertEqual(other["session"], "A")
        self.assertEqual(self.claim_data("P-13")["session"], "A")  # untouched
        again, none = claims.claim(self.proj, "P-13", "claude-code", session="A")  # the owner re-runs
        self.assertEqual((again["session"], none), ("A", None))
        taken, _ = claims.claim(self.proj, "P-13", "claude-code", session="B", takeover=True)
        self.assertEqual(taken["session"], "B")

    def test_claim_without_session_is_unchanged(self):
        self.held(None)
        got, other = claims.claim(self.proj, "P-13", "claude-code")
        self.assertEqual((got["agent"], other), ("claude-code", None))
        got, other = claims.claim(self.proj, "P-13", "claude-code", session="B")  # the claim has no session
        self.assertEqual((got["session"], other), ("B", None))

    def test_claim_over_a_stale_claim_of_another_session_is_a_re_run(self):
        self.held("A")
        claims.update(self.proj, "P-13", updated=ts(5 * 60))
        got, other = claims.claim(self.proj, "P-13", "claude-code", session="B", stale_after="4h")
        self.assertEqual((got["session"], other), ("B", None))


class ActiveTaskTests(PlanBase):
    """Point 2: the active task is chosen per session."""

    def setUp(self):
        super().setUp()
        self.task("P-13", updated="2026-11-09T10:00Z")
        self.task("P-14", title="Rate limit", updated="2026-11-09T11:00Z")  # the later Updated
        claims.claim(self.proj, "P-13", "claude-code", session="A")
        claims.claim(self.proj, "P-14", "claude-code", session="B", takeover=True)

    def tasks(self):
        return status.load_tasks(self.proj, os.path.join(self.proj, STATUS))

    def test_each_session_gets_its_own_item(self):
        tasks, branch = self.tasks(), self.branch()
        self.assertEqual(status.active_task(tasks, branch, "A", self.proj).id, "P-13")
        self.assertEqual(status.active_task(tasks, branch, "B", self.proj).id, "P-14")
        self.assertEqual(status.branch_task(tasks, branch, "A", self.proj).id, "P-13")
        self.assertEqual(status.branch_task(tasks, branch, "B", self.proj).id, "P-14")

    def test_without_a_session_or_a_claim_the_branch_rule_still_decides(self):
        tasks, branch = self.tasks(), self.branch()
        for session in (None, "C"):  # no id, or an id that holds nothing (a session after /clear)
            self.assertEqual(status.active_task(tasks, branch, session, self.proj).id, "P-14")
            self.assertEqual(status.branch_task(tasks, branch, session, self.proj).id, "P-14")
        self.assertEqual(status.active_task(tasks, branch).id, "P-14")  # the old call shape
        self.assertEqual(status.branch_task(tasks, branch).id, "P-14")
        self.assertEqual(status.branch_task(tasks, branch, "A").id, "P-14")  # no root: nothing to look up

    def test_branch_task_still_never_leaves_the_branch(self):
        self.assertIsNone(status.branch_task(self.tasks(), "another-branch", "A", self.proj))

    def test_a_done_or_parked_item_of_the_session_does_not_win(self):
        self.task("P-13", state="parked", updated="2026-11-09T10:00Z")
        self.assertEqual(status.active_task(self.tasks(), self.branch(), "A", self.proj).id, "P-14")

    def test_progress_show_uses_the_session_from_the_environment(self):
        self.env["WHATSNEXT_SESSION"] = "A"
        self.assertTrue(self.gw(["progress", "show"]).stdout.startswith("# P-13"))
        self.env["WHATSNEXT_SESSION"] = "B"
        self.assertTrue(self.gw(["progress", "show"]).stdout.startswith("# P-14"))

    def stop(self, session):
        r = self.gw(["hook", "stop", "--agent", "claude-code"], stdin=json.dumps({"session_id": session, "cwd": self.proj}))
        self.assertEqual((r.returncode, r.stderr), (0, ""))

    def test_the_stop_hook_writes_only_this_sessions_item(self):
        self.put("work.txt", "x\n")
        self.stop("A")
        self.assertTrue(self.has("%s/journal/P-13.md" % STATUS))
        self.assertFalse(self.has("%s/journal/P-14.md" % STATUS))
        self.stop("B")
        self.assertTrue(self.has("%s/journal/P-14.md" % STATUS))

    def test_hook_branch_task_passes_the_session_through(self):
        from wn import config as gwconfig
        effective = gwconfig.load(self.proj)
        self.assertEqual(hook.branch_task(self.proj, effective, "A").id, "P-13")
        self.assertEqual(hook.branch_task(self.proj, effective).id, "P-14")
        self.assertEqual(hook.session_of({"session_id": "A"}), "A")
        self.assertIsNone(hook.session_of({"session_id": 5}))

    def test_journal_record_takes_the_session_from_the_hook_data(self):
        from wn import config as gwconfig
        self.put("work.txt", "x\n")
        path = journal.record(self.proj, gwconfig.load(self.proj), "stop", {"session_id": "A"})
        self.assertTrue(path.endswith("P-13.md"), path)


class StartBase(PlanBase):
    def setUp(self):
        super().setUp()
        r = self.start("P-13", "--branch", "stay", "--session", "A", agent="claude-code")  # session A holds P-13
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def b(self, *flags, item="P-14", **kw):
        return self.start(item, "--session", "B", *flags, agent=kw.pop("agent", "claude-code"), **kw)

    def local_config(self):
        path = os.path.join(self.proj, ".whatsnext", "config.local.json")
        if not os.path.isfile(path):
            return {}
        with open(path, encoding="utf-8") as f:
            return json.load(f)


class StartQuestionTests(StartBase):
    """Point 3 and 4: Start asks when another live session is here; concurrentStart decides without asking."""

    def test_asks_where_the_item_should_go(self):
        r = self.b("--json")
        q = self.question(r)
        self.assertEqual(q["ask"], "concurrent")
        self.assertEqual(q["question"], "P-13 is in progress in another session here. Where should P-14 go?")
        self.assertEqual([o["value"] for o in q["options"]], ["worktree", "stay"])
        self.assertEqual(q["options"][0]["label"], "New worktree (recommended)")
        self.assertEqual(q["options"][1]["label"], "Stay on this branch")
        self.assertEqual(q["recommended"], "worktree")
        self.assertEqual(q["context"]["other_item"], "P-13")
        self.assertIn("--concurrent worktree|stay", q["answer_flag"])
        text = self.b()
        self.assertEqual(text.returncode, 4)
        self.assertIn("Question (concurrent):", text.stdout)
        self.assertFalse(self.has_claim("P-14"))  # nothing is marked until it is answered
        self.assertFalse(self.has("%s/P-14.md" % STATUS))

    def test_the_other_sessions_uncommitted_files_are_not_asked_about(self):
        self.put("work.txt", "session A's edit\n")
        self.assertEqual(self.question(self.b("--json"))["ask"], "concurrent")
        r = self.b("--concurrent", "stay")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(self.has("work.txt"))  # never stashed away from session A

    def test_worktree_uses_the_existing_worktree_path(self):
        r, data = self.jplan("start", "P-14", "--agent", "claude-code", "--session", "B", "--concurrent", "worktree")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(data["branch_action"], "worktree")
        self.assertEqual(data["branch"], "p-14-rate-limit-the-api")
        self.assertTrue(os.path.isdir(data["worktree"]))
        self.assertEqual(self.claim_data("P-14")["session"], "B")
        self.assertEqual(self.claim_data("P-14")["worktree"], data["worktree"])
        self.assertEqual(self.claim_data("P-13")["session"], "A")
        self.assertEqual(self.branch(), self.git("symbolic-ref", "--short", "HEAD"))  # this folder did not switch
        self.assertIn("Worktree: ", self.b("--concurrent", "worktree", item="P-15").stdout)  # the text form names the folder

    def test_worktree_wins_over_a_branch_answer_that_would_switch_this_folder(self):
        r, data = self.jplan("start", "P-14", "--agent", "claude-code", "--session", "B", "--concurrent", "worktree",
                             "--branch", "branch")
        self.assertEqual((r.returncode, data["branch_action"]), (0, "worktree"), r.stdout + r.stderr)
        self.assertEqual(self.local_config(), {})

    def test_stay_warns_and_keeps_the_branch(self):
        r, data = self.jplan("start", "P-14", "--agent", "claude-code", "--session", "B", "--concurrent", "stay")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(data["branch_action"], "stay")
        self.assertIsNone(data["worktree"])
        self.assertEqual(data["concurrent"], {"answer": "stay", "other_item": "P-13", "warning": WARNING})
        self.assertEqual(self.claim_data("P-14")["session"], "B")
        self.assertEqual(self.claim_data("P-13")["session"], "A")
        self.plan("put-back", "P-14", "--saved")
        r = self.b("--concurrent", "stay")
        self.assertIn("warning: " + WARNING, r.stderr)

    def test_default_setting_is_ask_and_is_separate_from_the_branch_setting(self):
        self.assertEqual(self.gw(["config", "show", "--json"]).stdout and
                         json.loads(self.gw(["config", "show", "--json"]).stdout)["plan.concurrentStart"]["value"], "ask")
        self.cfg(plan={"branchOnStart": "stay"})  # a safe solo default does not decide the shared case
        self.assertEqual(self.question(self.b("--json"))["ask"], "concurrent")

    def test_setting_worktree_creates_the_worktree_without_asking(self):
        self.cfg(plan={"concurrentStart": "worktree"})
        r, data = self.jplan("start", "P-14", "--agent", "claude-code", "--session", "B")
        self.assertEqual((r.returncode, data["branch_action"]), (0, "worktree"), r.stdout + r.stderr)
        self.assertEqual(data["concurrent"]["answer"], "worktree")
        self.assertFalse(os.path.exists(concurrent.state_path(self.proj)))  # a setting is not an answer

    def test_setting_stay_stays_and_warns_without_asking(self):
        self.cfg(plan={"concurrentStart": "stay", "branchOnStart": "branch"})
        r = self.b()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("warning: " + WARNING, r.stderr)
        self.assertEqual(self.branch(), self.git("symbolic-ref", "--short", "HEAD"))
        self.assertEqual(self.git("branch", "--list", "p-14*"), "")  # branchOnStart did not switch this folder

    def test_the_setting_accepts_only_ask_worktree_and_stay(self):
        self.assertEqual(self.gw(["config", "set", "--user", "plan.concurrentStart", "worktree"]).returncode, 0)
        self.assertEqual(self.gw(["config", "set", "--user", "plan.concurrentStart", "maybe"]).returncode, 2)
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills", "whatsnext",
                               "schemas", "config.schema.json"), encoding="utf-8") as f:
            node = json.load(f)["properties"]["plan"]["properties"]["concurrentStart"]
        self.assertEqual((node["enum"], node["default"]), (["ask", "worktree", "stay"], "ask"))


class NoQuestionTests(StartBase):
    """Where the question must not appear: the old rules."""

    def test_no_session_id_on_either_side_asks_the_old_current_item_question(self):
        self.plan("put-back", "P-13", "--saved")
        self.assertEqual(self.start("P-13", "--branch", "stay").returncode, 0)  # no session at all
        q = self.question(self.start("P-14", "--json"))
        self.assertEqual(q["ask"], "current_item")

    def test_a_claim_without_a_session_is_not_a_live_other_session(self):
        self.plan("put-back", "P-13", "--saved")
        self.set_claim("P-13", agent="claude-code")  # a claim with no session id
        self.assertEqual(self.question(self.b("--json"))["ask"], "current_item")

    def test_the_same_session_asks_the_old_question_about_its_own_item(self):
        r = self.start("P-14", "--session", "A", "--json", agent="claude-code")
        self.assertEqual(self.question(r)["ask"], "current_item")

    def test_a_stale_claim_of_another_session_asks_the_old_question(self):
        claims.update(self.proj, "P-13", updated=ts(5 * 60))
        self.task("P-13", updated="2026-11-01T10:00Z")
        self.assertEqual(self.question(self.b("--json"))["ask"], "current_item")

    def test_the_same_item_held_by_a_live_session_is_still_a_takeover(self):
        q = self.question(self.start("P-13", "--session", "B", "--json", agent="claude-code"))
        self.assertEqual(q["ask"], "takeover")
        self.assertEqual(self.claim_data("P-13")["session"], "A")

    def test_the_session_comes_from_the_environment_when_no_flag_is_given(self):
        self.env["WHATSNEXT_SESSION"] = "B"
        r = self.start("P-14", "--json", agent="claude-code")
        self.assertEqual(self.question(r)["ask"], "concurrent")
        self.assertEqual(self.start("P-14", "--concurrent", "stay", agent="claude-code").returncode, 0)
        self.assertEqual(self.claim_data("P-14")["session"], "B")

    def test_resuming_ones_own_item_in_a_new_session_after_it_went_stale(self):
        claims.update(self.proj, "P-13", updated=ts(5 * 60))
        self.task("P-13", updated="2026-11-01T10:00Z")
        r = self.start("P-13", "--session", "C", "--branch", "stay", agent="claude-code")  # the old session is long gone
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.claim_data("P-13")["session"], "C")


class AlwaysOfferTests(StartBase):
    """Point 5: the offer after two equal worktree answers; `--always` saves concurrentStart."""

    def answer(self, item, answer, *flags):
        # A new session per start: a "stay" answer leaves the item in progress, and the same session
        # would get the current_item question for it at the next start.
        self.answers_given = getattr(self, "answers_given", 0) + 1
        r, data = self.jplan("start", item, "--agent", "claude-code", "--session", "B%d" % self.answers_given,
                             "--concurrent", answer,
                             "--done-means", "it works", *flags)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return data

    def test_offer_comes_after_two_equal_worktree_answers_only(self):
        first = self.answer("P-14", "worktree")
        self.assertNotIn("always_offer", first)
        second = self.answer("P-15", "worktree")
        offer = second["always_offer"]
        self.assertEqual((offer["setting"], offer["value"]), ("plan.concurrentStart", "worktree"))
        self.assertEqual(offer["text"], "Always use a new worktree when another session is working here?")
        self.assertEqual(offer["answer"], "plan start P-15 --concurrent worktree --always")
        self.assertNotIn("always_offer", self.answer("P-16", "worktree"))  # ignored = keep asking: the count starts again

    def test_the_text_form_has_a_one_line_offer(self):
        self.answer("P-14", "worktree")
        r = self.b("--concurrent", "worktree", "--done-means", "ok", item="P-15")
        lines = [line for line in r.stdout.splitlines() if line.startswith("Offer: ")]
        self.assertEqual(len(lines), 1, r.stdout)
        self.assertIn("Always use a new worktree when another session is working here?", lines[0])
        self.assertIn("plan start P-15 --concurrent worktree --always", lines[0])

    def test_a_different_answer_between_resets_the_count(self):
        self.answer("P-14", "worktree")
        self.answer("P-15", "stay")
        self.assertNotIn("always_offer", self.answer("P-16", "worktree"))

    def test_stay_is_never_offered_as_always(self):
        for item in ("P-14", "P-15", "P-16"):
            data = self.answer(item, "stay")
            self.assertNotIn("always_offer", data)
        self.assertEqual(concurrent.read_state(self.proj), {"last": "stay", "streak": 3})

    def test_a_setting_driven_start_is_not_counted(self):
        self.cfg(plan={"concurrentStart": "worktree"})
        self.assertEqual(self.b("--done-means", "ok").returncode, 0)
        self.assertEqual(self.b("--done-means", "ok", item="P-15").returncode, 0)
        self.assertFalse(os.path.exists(concurrent.state_path(self.proj)))

    def test_always_with_worktree_saves_concurrent_start_only(self):
        data = self.answer("P-14", "worktree", "--always")
        self.assertNotIn("always_offer", data)
        self.assertEqual(self.local_config(), {"plan": {"concurrentStart": "worktree"}})
        self.assertFalse(os.path.exists(concurrent.state_path(self.proj)))
        r, data = self.jplan("start", "P-15", "--agent", "claude-code", "--session", "B", "--done-means", "ok")
        self.assertEqual((r.returncode, data["branch_action"]), (0, "worktree"), r.stdout + r.stderr)  # no question now

    def test_saying_always_after_the_offer_saves_without_a_takeover_question(self):
        self.answer("P-14", "worktree")
        self.answer("P-15", "worktree")  # the offer
        r = self.plan("start", "P-15", "--agent", "claude-code", "--session", "B%d" % self.answers_given,
                      "--concurrent", "worktree", "--always")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Saved plan.concurrentStart = worktree", r.stdout)
        self.assertEqual(self.local_config(), {"plan": {"concurrentStart": "worktree"}})

    def test_the_answers_file_follows_the_session_prune(self):
        concurrent.record_answer(self.proj, "worktree")
        path = concurrent.state_path(self.proj)
        self.assertTrue(os.path.isfile(path))
        self.assertEqual(journal.prune_sessions(self.proj, now=os.path.getmtime(path) + 10 * 86400), 0)
        self.assertEqual(journal.prune_sessions(self.proj, now=os.path.getmtime(path) + 15 * 86400), 1)
        self.assertEqual(concurrent.read_state(self.proj), {"last": None, "streak": 0})

    def test_a_damaged_answers_file_reads_as_no_answers(self):
        os.makedirs(os.path.dirname(concurrent.state_path(self.proj)), exist_ok=True)
        for text in ("not json", "[]", '{"last": "stay", "streak": "x"}', '{"last": "maybe", "streak": 4}'):
            with open(concurrent.state_path(self.proj), "w", encoding="utf-8") as f:
                f.write(text)
            self.assertEqual(concurrent.read_state(self.proj), {"last": None, "streak": 0})
        self.assertFalse(concurrent.record_answer(self.proj, "worktree"))


class SessionIdDeliveryTests(PlanBase):
    """How a session id reaches `plan start` and the hooks."""

    def start_hook(self, agent, session, env=None):
        merged = dict(self.env, **(env or {}))
        import subprocess
        from fixtures import SCRIPT
        args = ["hook", "session-start"] + (["--agent", agent] if agent else [])
        return subprocess.run([sys.executable, str(SCRIPT)] + args, input=json.dumps({"session_id": session, "cwd": self.proj,
                              "source": "startup"}), capture_output=True, text=True, env=merged, cwd=self.proj)

    def test_claude_code_session_start_exports_the_session_for_later_commands(self):
        self.task("P-13")
        target = os.path.join(self.tmp.name, "claude-env")
        r = self.start_hook("claude-code", "abc-123", {"CLAUDE_ENV_FILE": target})
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        with open(target, encoding="utf-8") as f:
            self.assertEqual(f.read(), "export WHATSNEXT_SESSION=abc-123\n")

    def test_an_unsafe_session_id_is_never_exported(self):
        target = os.path.join(self.tmp.name, "claude-env")
        self.start_hook("claude-code", "x; rm -rf ~", {"CLAUDE_ENV_FILE": target})
        self.assertFalse(os.path.exists(target))

    def test_codex_is_told_its_session_id_for_plan_start(self):
        self.task("P-13")
        r = self.start_hook("codex", "thread-9")
        self.assertIn("pass --session thread-9 to `plan start`", r.stdout)
        self.assertRegex(r.stdout, r'whatsnext command: WHATSNEXT_AGENT=codex python3 ".*whatsnext\.py" <command>')
        self.assertNotIn("--session", self.start_hook("codex", "bad id!").stdout)


if __name__ == "__main__":
    unittest.main()
