"""Tests for the hooks (`whatsnext hook <event>`, ADR-0005) and `install-hooks`.

Run: python3 -m unittest discover -s tests
"""

import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fixtures import ROOT, STATUS, StatusBase, session_note  # noqa: E402

import whatsnext  # noqa: E402
from wn import hook as wnhook  # noqa: E402
from wn import journal as wnjournal  # noqa: E402

PLANS = "docs/project/plans"
PLAN = "## Write the form\n## Add tests\n"


class HookBase(StatusBase):
    def hook(self, event, data=None, agent="claude-code", raw=None):
        args = ["hook", event] + (["--agent", agent] if agent else [])
        r = self.gw(args, stdin=raw if raw is not None else json.dumps(data if data is not None else {}))
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        return session_note(event, agent, r.stdout)

    def plan_field(self, task="P-13"):
        for line in self.get("%s/%s.md" % (STATUS, task)).splitlines():
            if line.startswith("- **Plan:**"):
                return line
        return None


class SessionStartTests(HookBase):
    def test_prints_the_resume_note(self):
        self.task()
        out = self.hook("session-start", {"source": "startup"})
        self.assertEqual(out, self.packet()["text"])
        self.assertIn("Next: Run the login tests.", out)
        self.assertIn("Context was compacted", self.hook("session-start", {"source": "compact"}))

    def test_claude_code_gets_json_with_a_one_line_banner_the_user_sees(self):  # P-41
        self.task()
        r = self.gw(["hook", "session-start", "--agent", "claude-code"], stdin=json.dumps({"source": "clear"}))
        data = json.loads(r.stdout)
        self.assertEqual(data["hookSpecificOutput"]["hookEventName"], "SessionStart")
        self.assertEqual(data["hookSpecificOutput"]["additionalContext"] + "\n", self.packet()["text"])
        self.assertEqual(data["systemMessage"], "whatsnext: resume note loaded. Next: Run the login tests. "
                                                "Type `what's next?` for details.")
        self.assertNotIn("\n", data["systemMessage"])

    def test_banner_without_a_next_line_and_codex_stays_plain_text(self):  # P-41
        r = self.gw(["hook", "session-start", "--agent", "claude-code"], stdin=json.dumps({"source": "startup"}))
        data = json.loads(r.stdout)
        self.assertEqual(data["systemMessage"], "whatsnext: resume note loaded. Type `what's next?` to see where "
                                                "you left off.")
        codex = self.gw(["hook", "session-start", "--agent", "codex"], stdin=json.dumps({"source": "startup"}))
        self.assertFalse(codex.stdout.startswith("{"))

    def test_codex_note_names_the_command_and_claude_code_note_does_not(self):
        self.task()
        codex = self.hook("session-start", {"source": "startup"}, agent="codex")
        self.assertTrue(codex.startswith(self.packet()["text"]))
        self.assertRegex(codex, r'whatsnext command: WHATSNEXT_AGENT=codex python3 ".*whatsnext\.py" <command>')
        self.assertIn("do not tick PLAN.md by hand", codex)
        self.assertNotIn("whatsnext command:", self.hook("session-start", {"source": "startup"}))

    def test_silent_outside_a_project_and_on_bad_input(self):
        os.makedirs(os.path.join(self.tmp.name, "other"))
        r = self.gw(["hook", "session-start"], stdin="{}", cwd=os.path.join(self.tmp.name, "other"))
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        self.task()
        self.assertEqual(self.hook("session-start", raw="not json"), "")
        self.assertEqual(self.hook("session-start", raw="[1]"), "")
        r = self.gw(["hook", "no-such-event"], stdin="{}")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))


class ClaudeCodePlanTests(HookBase):
    def shown(self, text=PLAN):
        self.hook("plan-shown", {"tool_name": "ExitPlanMode", "permission_mode": "plan",
                                 "tool_input": {"plan": text, "planFilePath": "/x/plan.md"}})

    def test_shown_then_approved(self):
        self.task()
        self.shown()
        self.assertRegex(self.plan_field(), r"\(shown\)$")
        self.assertIn("- [ ] Add tests", self.get(STATUS + "/P-13.md"))
        self.hook("plan-approved", {"tool_name": "ExitPlanMode", "tool_input": {}, "permission_mode": "auto"})
        self.assertRegex(self.plan_field(), r"\(approved\)$")

    def test_plan_hooks_leave_another_branchs_item_untouched(self):
        rel = self.task("P-2", branch="other", commit="deadbee")
        before = self.get(rel)
        self.assertNotEqual(self.branch(), "other")
        self.shown()
        self.hook("plan-approved", {"tool_name": "ExitPlanMode", "tool_input": {}, "permission_mode": "auto"})
        self.hook("prompt-submit", {"prompt": "go", "permission_mode": "auto"})
        self.assertEqual(self.get(rel), before)
        self.assertFalse(self.has("docs/project/plans"))

    def test_prompt_outside_plan_mode_marks_a_shown_plan_unapproved(self):
        self.task()
        self.shown()
        self.assertEqual(self.hook("prompt-submit", {"prompt": "hm", "permission_mode": "plan"}), "")
        self.assertRegex(self.plan_field(), r"\(shown\)$")
        self.assertEqual(self.hook("prompt-submit", {"prompt": "go", "permission_mode": "auto"}), "")
        self.assertRegex(self.plan_field(), r"\(used without approval\)$")

    def test_prompt_leaves_an_approved_plan_and_codex_alone(self):
        self.task()
        self.shown()
        self.hook("prompt-submit", {"permission_mode": "default"}, agent="codex")
        self.assertRegex(self.plan_field(), r"\(shown\)$")
        self.hook("plan-approved", {"tool_input": {}})
        self.hook("prompt-submit", {"permission_mode": "auto"})
        self.assertRegex(self.plan_field(), r"\(approved\)$")

    def test_no_active_task_or_empty_plan_is_silent(self):
        self.shown()
        self.assertFalse(self.has(PLANS))
        self.task()
        self.hook("plan-shown", {"tool_input": {"plan": "  "}})
        self.hook("plan-shown", {"tool_input": "x"})
        self.assertFalse(self.has(PLANS))


def rollout(*turns):
    """A Codex session file: one task_started per (turn id, mode, plan text or None)."""
    lines = [{"type": "session_meta", "payload": {"id": "s"}}]
    for turn_id, mode, plan in turns:
        lines.append({"type": "event_msg", "payload": {"type": "task_started", "turn_id": turn_id,
                                                       "collaboration_mode_kind": mode}})
        if plan is not None:
            lines.append({"type": "event_msg", "payload": {"type": "item_completed", "turn_id": turn_id,
                                                           "item": {"type": "Plan", "id": "p", "text": plan}}})
        lines.append({"type": "event_msg", "payload": {"type": "task_complete", "turn_id": turn_id}})
    return "\n".join(json.dumps(l) for l in lines) + "\nnot json\n"


class CodexStopTests(HookBase):
    def stop(self, turn_id, *turns):
        self.put("rollout.jsonl", rollout(*turns))
        self.hook("stop", {"transcript_path": self.p("rollout.jsonl"), "turn_id": turn_id,
                           "permission_mode": "default"}, agent="codex")

    def test_plan_turn_then_default_turn(self):
        self.task()
        self.stop("t1", ("t1", "plan", PLAN))
        self.assertRegex(self.plan_field(), r"\(shown\)$")
        self.assertIn("- **Agent:** codex", self.get("%s/%s" % (PLANS, os.listdir(self.p(PLANS))[0])))
        self.stop("t2", ("t1", "plan", PLAN), ("t2", "default", None))
        self.assertRegex(self.plan_field(), r"\(approved\)$")

    def test_no_plan_unknown_format_or_claude_code_does_nothing(self):
        self.task()
        self.stop("t2", ("t1", "default", None), ("t2", "default", None))
        self.put("garbage.jsonl", "\x00\x01 nope\n")
        self.hook("stop", {"transcript_path": self.p("garbage.jsonl"), "turn_id": "t1"}, agent="codex")
        self.hook("stop", {"transcript_path": self.p("missing.jsonl"), "turn_id": "t1"}, agent="codex")
        self.put("rollout.jsonl", rollout(("t1", "plan", PLAN)))
        self.hook("stop", {"transcript_path": self.p("rollout.jsonl"), "turn_id": "t1"})
        self.assertIsNone(self.plan_field())

    def test_capture_unreadable(self):
        self.task()
        fact = ".whatsnext/sessions/capture.unreadable.json"
        self.put("garbage.jsonl", "\x00\x01 nope\n{\"type\": \"other\"}\n")
        self.hook("stop", {"transcript_path": self.p("garbage.jsonl"), "turn_id": "t1"}, agent="codex")
        state = json.loads(self.get(fact))
        self.assertEqual((state["fact"], state["count"]), ("capture.unreadable", 1))
        self.assertIn("no task_started records", state["reason"])
        since = state["since"]
        self.hook("stop", {"transcript_path": self.p("garbage.jsonl"), "turn_id": "t2"}, agent="codex")
        state = json.loads(self.get(fact))
        self.assertEqual((state["count"], state["since"]), (2, since))  # one fact: the first reason and time are kept
        out = self.gw(["doctor"]).stdout
        self.assertIn("plan capture: unreadable since %s (2 turns)" % since, out)
        self.assertIn("fix: record the plan by hand with `whatsnext progress capture`", out)
        self.stop("t1", ("t1", "default", None))  # a readable transcript clears the fact
        self.assertFalse(self.has(fact))
        self.assertNotIn("plan capture:", self.gw(["doctor"]).stdout)
        self.hook("stop", {"transcript_path": self.p("missing.jsonl"), "turn_id": "t3"}, agent="codex")
        self.assertIn("cannot read the transcript", json.loads(self.get(fact))["reason"])

    def test_capture_unreadable_never_writes_through_a_link(self):
        self.task()
        outside = os.path.join(self.tmp.name, "outside.json")
        os.makedirs(self.p(".whatsnext/sessions"), exist_ok=True)
        os.symlink(outside, self.p(".whatsnext/sessions/capture.unreadable.json"))
        self.put("garbage.jsonl", "nope\n")
        self.hook("stop", {"transcript_path": self.p("garbage.jsonl"), "turn_id": "t1"}, agent="codex")
        self.assertFalse(os.path.exists(outside))

    def test_parser_approval_looks_back_past_plan_mode_turns_without_a_plan(self):
        path = self.p("r.jsonl")
        self.put("r.jsonl", rollout(("t1", "plan", "x"), ("t2", "plan", None), ("t3", "default", None)))
        self.assertEqual(wnhook.codex_plan(path, "t3"), ("approved", None))
        self.assertIsNone(wnhook.codex_plan(path, "t2"))
        self.assertEqual(wnhook.codex_plan(path, "t1"), ("shown", "x"))
        self.assertIsNone(wnhook.codex_plan(path, "t9"))

    def test_parser_a_default_turn_between_breaks_the_chain(self):
        path = self.p("r.jsonl")
        self.put("r.jsonl", rollout(("t1", "plan", "x"), ("t2", "default", None), ("t3", "plan", None),
                                    ("t4", "default", None)))
        self.assertEqual(wnhook.codex_plan(path, "t2"), ("approved", None))
        self.assertIsNone(wnhook.codex_plan(path, "t4"))

    def test_live_sequence_typed_approve_in_plan_mode_then_switch(self):
        # The 2026-11-05 Codex live test: question, plan, "Approve the plan, but don't implement"
        # still in plan mode, then "implement" in default mode.
        self.task()
        turns = (("t1", "default", None), ("t2", "plan", PLAN), ("t3", "plan", None), ("t4", "default", None))
        self.stop("t2", *turns[:2])
        self.assertRegex(self.plan_field(), r"\(shown\)$")
        self.stop("t3", *turns[:3])
        self.assertRegex(self.plan_field(), r"\(shown\)$")
        self.stop("t4", *turns)
        self.assertRegex(self.plan_field(), r"\(approved\)$")


class InstallHooksTests(HookBase):
    def install(self, *args):
        return self.gw(["install-hooks", "--project"] + list(args))

    def hooks_file(self):
        return json.loads(self.get(".codex/hooks.json"))

    def test_install_is_idempotent_and_keeps_other_hooks(self):
        other = {"type": "command", "command": "echo mine"}
        self.put(".codex/hooks.json", json.dumps({"x": 1, "hooks": {"Stop": [{"hooks": [other]}]}}))
        r = self.install("--dry-run")
        self.assertIn("Dry run: nothing written.", r.stdout)
        self.assertNotIn("SessionStart", self.get(".codex/hooks.json"))
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("trust the whatsnext hooks", r.stdout)
        data = self.hooks_file()
        self.assertEqual(data["x"], 1)
        self.assertEqual(sorted(data["hooks"]), ["PreCompact", "PreToolUse", "SessionStart", "Stop", "UserPromptSubmit"])
        self.assertEqual(data["hooks"]["Stop"][0], {"hooks": [other]})
        command = data["hooks"]["SessionStart"][0]["hooks"][0]["command"]
        self.assertRegex(command, r'^python3 ".*whatsnext\.py" hook session-start --agent codex$')
        self.assertEqual(data["hooks"]["SessionStart"][0]["matcher"], "startup|resume|clear|compact")
        before = self.get(".codex/hooks.json")
        self.assertIn("already installed", self.install().stdout)
        self.assertEqual(self.get(".codex/hooks.json"), before)
        self.install("--remove")
        self.assertEqual(self.hooks_file(), {"x": 1, "hooks": {"Stop": [{"hooks": [other]}]}})

    def test_remove_takes_away_a_file_it_alone_filled(self):
        self.install()
        self.install("--remove")
        self.assertFalse(self.has(".codex"))

    def test_bad_file_is_left_alone(self):
        self.put(".codex/hooks.json", "{nope")
        r = self.install()
        self.assertEqual(r.returncode, 1)
        self.assertIn("fix it first", r.stderr)
        self.assertEqual(self.get(".codex/hooks.json"), "{nope")


class InstallSkillLinkTests(HookBase):
    """`install-hooks --user` also links the skill into ~/.agents/skills/whatsnext for Codex."""

    def setUp(self):
        super().setUp()
        self.env["CODEX_HOME"] = os.path.join(self.home, ".codex")
        os.makedirs(self.env["CODEX_HOME"])
        self.link = os.path.join(self.home, ".agents", "skills", "whatsnext")

    def user(self, *args):
        return self.gw(["install-hooks", "--user"] + list(args))

    def test_install_links_the_skill_and_remove_takes_it_away(self):
        r = self.user("--dry-run")
        self.assertIn("would link the skill", r.stdout)
        self.assertFalse(os.path.lexists(self.link))
        r = self.user()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.islink(self.link))
        self.assertTrue(os.path.isfile(os.path.join(self.link, "SKILL.md")))
        self.assertTrue(os.path.isfile(os.path.join(self.link, "scripts", "whatsnext.py")))
        self.assertIn("already installed", self.user().stdout)
        r = self.user("--remove")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.lexists(self.link))

    def test_a_folder_that_is_not_ours_is_never_replaced(self):
        os.makedirs(self.link)
        with open(os.path.join(self.link, "mine.txt"), "w") as f:
            f.write("x")
        r = self.user()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("is not a link", r.stdout)
        self.assertTrue(os.path.isfile(os.path.join(self.link, "mine.txt")))
        self.user("--remove")
        self.assertTrue(os.path.isfile(os.path.join(self.link, "mine.txt")))

    def test_a_link_to_another_skill_is_never_replaced_or_removed(self):
        other = os.path.join(self.home, "other-skill")
        os.makedirs(other)
        os.makedirs(os.path.dirname(self.link))
        os.symlink(other, self.link)
        r = self.user()
        self.assertIn("not whatsnext's skill", r.stdout)
        self.user("--remove")
        self.assertEqual(os.readlink(self.link), other)

    def test_project_scope_makes_no_skill_link(self):
        self.gw(["install-hooks", "--project"])
        self.assertFalse(os.path.lexists(self.link))


JOURNAL = STATUS + "/journal/P-13.md"
LINE = re.compile(r"^- (\d{4}-\d\d-\d\dT\d\d:\d\dZ) (\S+) (\S+) (\S+) dirty=(\d+)(?: set=[0-9a-f]{6})?(?: files: (.*))?$")


class FactsTests(HookBase):
    """The facts layer: one journal line per stop, pre-compact and session-end (ADR-0005)."""

    def settled(self, **kw):
        """A progress file recorded at HEAD, committed, with a clean tree except the progress file itself."""
        self.task(**kw)
        self.commit("add task")
        return self.task(**kw)

    def lines(self):
        text = self.get(JOURNAL)
        out = []
        for line in text.splitlines()[2:]:
            m = LINE.match(line)
            self.assertIsNotNone(m, line)
            out.append(m.groups())
        return text, out

    def test_stop_appends_a_line_with_commit_branch_dirty_count_and_files(self):
        rel = self.settled()
        head = self.head()
        self.put("src/a.py", "a\n")
        self.put("src/b.py", "b\n")
        self.put("README.md", "changed\n")
        self.assertEqual(self.hook("stop", {"session_id": "s1"}), "")
        text, lines = self.lines()
        self.assertTrue(text.startswith("# Journal: P-13\n\n"))
        self.assertEqual(len(lines), 1)
        _time, event, commit, branch, dirty, files = lines[0]
        self.assertEqual((event, commit, branch, dirty), ("stop", head, self.branch(), "3"))
        self.assertEqual(files, "README.md, src/a.py, src/b.py")
        self.assertLessEqual(len(text.splitlines()[-1]), wnjournal.MAX_LINE)
        self.assertIn("- **Commit:** " + head, self.get(rel))
        self.assertRegex(self.get(rel), r"- \*\*Note:\*\* facts \(\d{4}-")
        self.assertNotIn("journal", lines[0][5])  # the journal never lists itself

    def test_second_line_is_relative_to_the_first_lines_commit(self):
        self.settled()
        first = self.head()
        self.put("src/a.py", "a\n")
        self.hook("stop", {"session_id": "s1"})
        self.commit("feat: a")
        second_head = self.head()
        self.put("src/c.py", "c\n")
        self.hook("stop", {"session_id": "s1"})
        _text, lines = self.lines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0][2], first)
        self.assertEqual(lines[0][5], "src/a.py")
        self.assertEqual((lines[1][2], lines[1][4]), (second_head, "1"))
        self.assertEqual(lines[1][5], "src/a.py, src/c.py")  # a.py is committed since the first line, c.py is new
        self.assertEqual(self.get(JOURNAL).count("# Journal"), 1)

    def test_a_clean_turn_writes_a_line_without_files(self):
        self.settled()
        self.hook("stop")
        _text, lines = self.lines()
        self.assertEqual(lines[0][4:], ("0", None))

    def test_pre_compact_and_session_end_write_a_line_each(self):
        self.settled()
        self.hook("pre-compact", {"session_id": "s1"})
        self.hook("session-end", {"session_id": "s1", "reason": "other"})
        self.hook("stop", {"session_id": "s1"}, agent="codex")
        _text, lines = self.lines()
        self.assertEqual([l[1] for l in lines], ["pre-compact", "session-end", "stop"])

    def test_no_active_task_writes_nothing(self):
        for event in ("stop", "pre-compact", "session-end"):
            self.hook(event, {"session_id": "s1"})
        self.assertFalse(self.has(STATUS + "/journal"))
        self.assertFalse(self.has(".whatsnext/sessions"))
        self.task(state="parked")  # a parked task is not the active one
        self.hook("stop", {"session_id": "s1"})
        self.assertFalse(self.has(JOURNAL))

    def test_an_active_item_on_another_branch_is_left_untouched(self):
        rel = self.task("P-2", branch="other", commit="deadbee")
        self.commit("add P-2")
        before = self.get(rel)
        self.assertNotEqual(self.branch(), "other")
        for event in ("stop", "pre-compact", "session-end"):
            self.assertEqual(self.hook(event, {"session_id": "s1"}), "")
        self.assertFalse(self.has(STATUS + "/journal"))
        self.assertFalse(self.has(STATUS + "/journal/P-2.md"))
        self.assertFalse(self.has(".whatsnext/sessions"))
        self.assertEqual(self.get(rel), before)
        with open(self.p(rel), "rb") as f:
            self.assertIn(b"- **Branch:** other\n", f.read())
        self.assertIn("continue P-2", self.packet()["text"])  # the resume note still falls back to it
        self.assertIn("branch is now %s (note says other)" % self.branch(), self.packet()["text"])

    def test_a_branch_none_item_is_not_journaled(self):
        rel = self.task("P-2", branch="none", commit="none")
        before = self.get(rel)
        self.hook("stop", {"session_id": "s1"})
        self.assertFalse(self.has(STATUS + "/journal"))
        self.assertEqual(self.get(rel), before)

    def test_only_the_current_branchs_item_is_journaled_when_others_are_active(self):
        self.task("P-2", branch="other", commit="deadbee", updated="2026-11-03T10:00Z")
        other = self.get(STATUS + "/P-2.md")
        self.task("P-13", updated="2026-10-01T10:00Z")
        self.hook("stop", {"session_id": "s1"})
        self.assertTrue(self.has(JOURNAL))
        self.assertFalse(self.has(STATUS + "/journal/P-2.md"))
        self.assertEqual(self.get(STATUS + "/P-2.md"), other)
        self.assertIn("- **Branch:** " + self.branch(), self.get(STATUS + "/P-13.md"))

    def test_outside_git_writes_nothing(self):
        outside = os.path.join(self.tmp.name, "nogit")
        os.makedirs(outside)
        self.assertIsNone(wnjournal.record(outside, None, "stop", {"session_id": "s1"}))
        self.assertEqual(os.listdir(outside), [])

    def test_a_confirmed_note_survives_the_header_refresh(self):
        rel = self.settled()
        text = self.get(rel).replace("- **Updated:**", "- **Note:** confirmed (2026-11-04T10:00Z)\n- **Updated:**")
        self.put(rel, text)
        self.put("src/a.py", "a\n")
        self.hook("stop")
        after = self.get(rel)
        self.assertIn("- **Note:** confirmed (2026-11-04T10:00Z)", after)
        self.assertIn("- **Commit:** " + self.head(), after)
        self.assertIn("Run the login tests.", after)
        self.assertNotRegex(after, r"Updated:\*\* 2026-10-27")

    def test_session_state_is_written_under_whatsnext_sessions(self):
        self.settled()
        self.hook("stop", {"session_id": "abc-123"})
        state = json.loads(self.get(".whatsnext/sessions/abc-123.json"))
        self.assertEqual((state["session_id"], state["last_event"], state["item"], state["branch"]),
                         ("abc-123", "stop", "P-13", self.branch()))
        self.assertEqual(state["commit"], self.head())
        self.hook("session-end", {"session_id": "abc-123"})
        self.assertEqual(json.loads(self.get(".whatsnext/sessions/abc-123.json"))["last_event"], "session-end")
        self.assertEqual(os.listdir(self.p(".whatsnext/sessions")), ["abc-123.json"])
        _text, lines = self.lines()
        self.assertEqual([l[5] for l in lines], [None, None])  # the state file is not counted as work

    def test_session_id_is_made_safe_for_a_file_name(self):
        self.assertEqual(wnjournal.safe_session_id("../../evil"), "_.._evil")
        self.assertEqual(wnjournal.safe_session_id("a b/c"), "a_b_c")
        self.assertIsNone(wnjournal.safe_session_id("..."))
        self.assertIsNone(wnjournal.safe_session_id(7))
        self.settled()
        self.hook("stop", {"session_id": "../../evil"})
        self.assertEqual(os.listdir(self.p(".whatsnext/sessions")), ["_.._evil.json"])
        self.hook("stop")  # no session id: the journal still gets its line
        self.assertEqual(len(self.lines()[1]), 2)

    def test_a_progress_commit_that_is_an_option_is_not_passed_to_git(self):
        rel = self.settled(commit="--output=evil")
        self.put("src/a.py", "a\n")
        self.hook("stop")
        self.assertFalse(self.has("evil"))
        self.assertEqual(self.lines()[1][0][5], "src/a.py")
        self.assertIn("- **Commit:** " + self.head(), self.get(rel))

    def test_long_file_lists_are_cut_to_the_line_limit(self):
        self.settled()
        for i in range(40):
            self.put("src/module_number_%02d.py" % i, "x\n")
        self.hook("stop")
        line = self.get(JOURNAL).splitlines()[-1]
        self.assertLessEqual(len(line), wnjournal.MAX_LINE)
        self.assertRegex(line, r"\+\d+ more$")
        self.assertIn("dirty=40", line)

    def test_a_hook_never_fails_on_a_bad_progress_file(self):
        rel = self.settled()
        self.put(rel, "format: 9\n\n" + self.get(rel))  # written by a newer whatsnext
        self.hook("stop")  # exit 0 and empty stderr are asserted by the helper

    def test_sessions_folder_is_git_ignored(self):
        with open(os.path.join(str(ROOT), ".gitignore"), encoding="utf-8") as f:
            self.assertIn(".whatsnext/sessions/", f.read().splitlines())


class PreCompactTests(HookBase):
    """P-4, P-20, P-26: the auto-compact safety net."""

    def handoff(self, session="s1"):
        """A fresh handoff note this session wrote (header and sidecar)."""
        from wn import config as wnconfig
        from wn import wrapup as wnwrapup
        path = wnwrapup.handoff_path(self.proj, wnconfig.load(self.proj))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("# Handoff\n\nSession: %s\nTask: P-13\nWritten: 2026-11-06T18:08Z\n\n## Next action\n\nRun it.\n" % session)
        wnwrapup.write_sidecar(self.proj, session, path)

    def test_compacted_without_wrapup(self):
        self.task()
        out = self.hook("pre-compact", {"session_id": "s1"})
        self.assertRegex(out, r"Compacted without wrap-up at \d{4}-\d\d-\d\dT\d\d:\d\dZ\.")
        note = self.hook("session-start", {"source": "compact", "session_id": "s1"})
        self.assertRegex(note, r"Context was compacted without wrap-up at \d{4}-")
        plain = self.hook("session-start", {"source": "startup", "session_id": "s1"})
        self.assertNotIn("without wrap-up", plain)

    def test_a_fresh_handoff_records_no_fact_and_clears_an_old_one(self):
        self.task()
        self.hook("pre-compact", {"session_id": "s1"})
        self.handoff()
        out = self.hook("pre-compact", {"session_id": "s1"})
        self.assertNotIn("without wrap-up", out)
        self.assertNotIn("without wrap-up", self.hook("session-start", {"source": "compact", "session_id": "s1"}))

    def test_precompact_cap(self):
        self.task()
        self.handoff()
        from wn import config as wnconfig
        from wn import wrapup as wnwrapup
        path = wnwrapup.handoff_path(self.proj, wnconfig.load(self.proj))
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n## Goal\n\n" + "long text. " * 1000 + "\n")
        wnwrapup.write_sidecar(self.proj, "s1", path)
        out = self.hook("pre-compact", {"session_id": "s1"})
        self.assertLessEqual(len(out), 3000)
        self.assertIn("whatsnext facts:", out)
        self.assertIn("Run it", out)
        custom = self.hook("pre-compact", {"session_id": "s1", "custom_instructions": "keep the login bug"})
        self.assertTrue(custom.startswith("whatsnext facts:"))
        self.assertNotIn("long text", custom)
        self.assertNotIn("handoff note", custom)
        self.assertLessEqual(len(custom), 3000)

    def transcript(self, entries):
        path = os.path.join(self.tmp.name, "t.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")
        return path

    @staticmethod
    def user(text, **extra):
        return dict({"type": "user", "message": {"role": "user", "content": text}}, **extra)

    def test_latest_request(self):
        self.task()
        long_text = "Please do the login work. " + "x" * 3000
        path = self.transcript([
            self.user("older request"),
            self.user(long_text),
            {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": "TOOLRESULT-1"}]}},
            self.user("meta note", isMeta=True),
            self.user("sidechain note", isSidechain=True),
            self.user("wrap up"),
            self.user("<command-name>/compact</command-name>"),
            self.user("summary text", isCompactSummary=True),
            {"type": "assistant", "message": {"role": "assistant", "content": "an answer"}},
        ])
        out = self.hook("pre-compact", {"session_id": "s1", "transcript_path": path})
        self.assertIn("Keep verbatim (the user's latest request):\nPlease do the login work.", out)
        block = out.split("Keep verbatim (the user's latest request):\n")[1].split("\n\n")[0]
        self.assertLessEqual(len(block), 2000)
        self.assertTrue(block.endswith("\u2026"))
        for skipped in ("older request", "TOOLRESULT-1", "meta note", "sidechain note", "summary text", "<command-name>"):
            self.assertNotIn(skipped, out)
        self.assertLessEqual(len(out), 3000)
        self.assertIn("whatsnext facts:", out)

    def test_latest_request_is_redacted_and_kept_with_custom_instructions(self):
        self.task()
        key = "sk-ant-" + "a" * 30
        path = self.transcript([self.user("use key %s and <private>my secret plan</private> now" % key)])
        out = self.hook("pre-compact", {"session_id": "s1", "transcript_path": path, "custom_instructions": "mine"})
        self.assertIn("use key [redacted] and now", out)
        self.assertNotIn(key, out)
        self.assertNotIn("secret plan", out)

    def test_latest_request_masks_whole_key_blocks_and_filters_per_block(self):
        self.task()
        pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIEPEMBODY\n-----END RSA PRIVATE KEY-----"
        mixed = {"type": "user", "message": {"role": "user", "content": [
            {"type": "text", "text": "<system-reminder>INJECTED</system-reminder>"},
            {"type": "text", "text": "fix it. Authorization: Bearer abcdef123456 and passwd=hunter2hunter2\n" + pem},
            {"type": "text", "text": "<command-name>/x</command-name>"}]}}
        path = self.transcript([mixed])
        out = self.hook("pre-compact", {"session_id": "s1", "transcript_path": path})
        self.assertIn("fix it.", out)
        out2 = self.hook("pre-compact", {"session_id": "s1", "transcript_path": self.transcript(
            [self.user("a -----BEGIN PRIVATE KEY-----\nUNTERMINATEDBODY")])})
        self.assertNotIn("UNTERMINATEDBODY", out2)
        for leaked in ("MIIEPEMBODY", "abcdef123456", "hunter2hunter2", "INJECTED", "<command-name>"):
            self.assertNotIn(leaked, out)

    def test_latest_request_missing_or_unreadable_is_silent(self):
        self.task()
        for path in (None, os.path.join(self.tmp.name, "absent.jsonl"), self.transcript([{"type": "system"}])):
            out = self.hook("pre-compact", {"session_id": "s1", "transcript_path": path})
            self.assertNotIn("Keep verbatim", out)
            self.assertIn("whatsnext facts:", out)

    def test_output_contract(self):
        self.task()
        out = self.hook("pre-compact", {"session_id": "s1"})
        self.assertTrue(out.strip())
        self.assertFalse(out.lstrip().startswith(("{", "[")))  # plain text, never JSON
        self.assertNotIn("hookSpecificOutput", out)
        for event in ("stop", "session-end", "plan-shown", "plan-approved", "prompt-submit"):
            self.assertEqual(self.hook(event, {"session_id": "s1"}), "")
        start = self.hook("session-start", {"source": "startup"})
        self.assertFalse(start.lstrip().startswith("{"))

    def test_postcompact_bak(self):
        self.task(steps=["- [x] Write the form", "- [ ] Add the tests", "- [ ] Ship it"])
        first = "Summary: we wrote the form and will add the tests. key=sk-ant-" + "b" * 30
        self.assertEqual(self.hook("post-compact", {"session_id": "s1", "compact_summary": first}), "")
        path = ".whatsnext/sessions/s1.summary.md"
        self.assertIn("we wrote the form", self.get(path))
        self.assertNotIn("sk-ant-", self.get(path))
        self.assertFalse(self.has(path + ".bak"))
        second = "Second summary: nothing about the steps."
        self.hook("post-compact", {"session_id": "s1", "compact_summary": second})
        self.assertIn("Second summary", self.get(path))
        self.assertIn("we wrote the form", self.get(path + ".bak"))  # the previous one is kept
        note = self.hook("session-start", {"source": "compact", "session_id": "s1"})
        self.assertIn("Summary kept 0 of 3 plan steps.", note)
        self.hook("post-compact", {"session_id": "s1", "compact_summary": "Write the form. Add the tests."})
        self.assertIn("Summary kept 2 of 3 plan steps.", self.hook("session-start", {"source": "compact", "session_id": "s1"}))
        self.assertNotIn("Summary kept", self.hook("session-start", {"source": "startup", "session_id": "s1"}))

    def test_postcompact_empty_summary_says_do_not_trust_and_bad_input_is_silent(self):
        self.task()
        self.hook("post-compact", {"session_id": "s1", "compact_summary": "  "})
        self.assertIn("do not trust", self.hook("session-start", {"source": "compact", "session_id": "s1"}))
        self.assertEqual(self.hook("post-compact", {"compact_summary": "x"}), "")  # no session id: nothing written
        self.assertEqual(self.hook("post-compact", raw="not json"), "")

    def test_compact_marker_once(self):
        self.task()
        self.assertEqual(self.hook("pre-compact", {"session_id": "s1"}, agent="codex"), "")
        marker = ".whatsnext/sessions/s1.resume.json"
        self.assertTrue(self.has(marker))
        first = self.hook("prompt-submit", {"session_id": "s1", "prompt": "go on"}, agent="codex")
        self.assertIn("Context was compacted", first)
        self.assertIn("whatsnext command:", first)  # the Codex form of the note
        self.assertFalse(self.has(marker))
        self.assertEqual(self.hook("prompt-submit", {"session_id": "s1", "prompt": "next"}, agent="codex"), "")

    def test_compact_marker_is_dropped_when_session_start_already_said_so(self):
        self.task()
        self.hook("pre-compact", {"session_id": "s1"}, agent="codex")
        self.assertIn("Context was compacted", self.hook("session-start", {"source": "compact", "session_id": "s1"}, agent="codex"))
        self.assertFalse(self.has(".whatsnext/sessions/s1.resume.json"))
        self.assertEqual(self.hook("prompt-submit", {"session_id": "s1", "prompt": "go"}, agent="codex"), "")

    def test_compact_marker_claude_code_keeps_its_own_prompt_behavior(self):
        self.task()
        self.hook("pre-compact", {"session_id": "s1"})  # Claude Code: SessionStart passes source=compact; no marker
        self.assertFalse(self.has(".whatsnext/sessions/s1.resume.json"))
        self.assertEqual(self.hook("prompt-submit", {"session_id": "s1", "prompt": "go"}), "")

    def test_codex_gets_no_text_but_the_fact_and_the_note(self):
        self.task()
        self.assertEqual(self.hook("pre-compact", {"session_id": "s1"}, agent="codex"), "")
        self.assertIn("without wrap-up", self.hook("session-start", {"source": "compact", "session_id": "s1"}, agent="codex"))

    def test_outside_a_project_and_without_a_task_stay_quiet_and_safe(self):
        self.assertEqual(self.hook("pre-compact", {"session_id": "s1"}), "")  # no active task: nothing printed or written
        self.assertFalse(self.has(".whatsnext/sessions"))
        self.assertEqual(self.hook("pre-compact", raw="not json"), "")


PLAN_FILE = "docs/project/PLAN.md"
TICK_PLAN = "# Plan\n\n## Now\n\n- [ ] P-13 Add login · done means: x\n- [ ] P-14 Other · done means: y\n"


class TickGuardTests(HookBase):
    def setUp(self):
        super().setUp()
        self.cfg()
        self.put(PLAN_FILE, TICK_PLAN)

    def guard(self, tool, tool_input, agent="claude-code", cfg=None):
        if cfg:
            self.cfg(plan={"tickGuard": cfg})
        out = self.hook("pre-edit", {"tool_name": tool, "tool_input": tool_input, "cwd": self.proj}, agent=agent)
        return json.loads(out)["hookSpecificOutput"] if out else None

    def test_plan_tick_guard_warns_on_an_edit_that_ticks_an_item(self):
        out = self.guard("Edit", {"file_path": self.p(PLAN_FILE), "old_string": "- [ ] P-13 Add login", "new_string": "- [x] P-13 Add login"})
        self.assertEqual(out["hookEventName"], "PreToolUse")
        self.assertIn("Use `plan done P-13 --verify", out["additionalContext"])
        self.assertIn("plan done P-13 --verify", out["additionalContext"])
        self.assertNotIn("permissionDecision", out)

    def test_plan_tick_guard_write_multiedit_and_codex_patch(self):
        out = self.guard("Write", {"file_path": self.p(PLAN_FILE), "content": TICK_PLAN.replace("[ ] P-14", "[x] P-14")})
        self.assertIn("plan done P-14 --verify", out["additionalContext"])
        out = self.guard("MultiEdit", {"file_path": self.p(PLAN_FILE), "edits": [
            {"old_string": "- [ ] P-13", "new_string": "- [x] P-13"}]})
        self.assertIn("P-13", out["additionalContext"])
        patch = "*** Begin Patch\n*** Update File: docs/project/PLAN.md\n@@\n-- [ ] P-13 Add login\n+- [x] P-13 Add login\n*** End Patch\n"
        out = self.guard("apply_patch", {"command": patch}, agent="codex")
        self.assertIn("plan done P-13 --verify", out["additionalContext"])

    def test_plan_tick_guard_other_edits_stay_quiet(self):
        plan = self.p(PLAN_FILE)
        self.assertIsNone(self.guard("Edit", {"file_path": plan, "old_string": "Add login", "new_string": "Add sign-in"}))
        self.assertIsNone(self.guard("Edit", {"file_path": self.p("src/a.py"), "old_string": "- [ ] P-13", "new_string": "- [x] P-13"}))
        self.assertIsNone(self.guard("Write", {"file_path": plan, "content": TICK_PLAN}))  # nothing ticked
        self.assertIsNone(self.guard("Edit", {"file_path": plan, "old_string": "- [x] P-13", "new_string": "- [ ] P-13"}))  # un-ticking
        self.assertIsNone(self.guard("apply_patch", {"command": "*** Update File: src/a.py\n-- [ ] P-1\n+- [x] P-1\n"}, agent="codex"))
        self.assertEqual(self.hook("pre-edit", {"tool_name": "Edit", "tool_input": "bad"}), "")

    def test_plan_tick_guard_deny_and_off_by_setting(self):
        tick = {"file_path": self.p(PLAN_FILE), "old_string": "- [ ] P-13", "new_string": "- [x] P-13"}
        out = self.guard("Edit", tick, cfg="deny")
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertIn("plan done P-13 --verify", out["permissionDecisionReason"])
        self.assertIsNone(self.guard("Edit", tick, cfg="off"))


class ClaudeCodeConfigTests(unittest.TestCase):
    def test_hooks_json_calls_known_events(self):
        with open(os.path.join(str(ROOT), "hooks", "hooks.json"), encoding="utf-8") as f:
            data = json.load(f)["hooks"]
        self.assertEqual(sorted(data), ["PostCompact", "PostToolUse", "PreCompact", "PreToolUse", "SessionEnd",
                                        "SessionStart", "Stop", "UserPromptSubmit"])
        for name, event in (("PreCompact", "pre-compact"), ("PostCompact", "post-compact"), ("SessionEnd", "session-end"), ("Stop", "stop")):
            self.assertEqual(len(data[name]), 1)
            self.assertIn(" hook %s --agent claude-code" % event, data[name][0]["hooks"][0]["command"])
        self.assertEqual([g["matcher"] for g in data["PreToolUse"]], ["ExitPlanMode", "Edit|Write|MultiEdit"])
        self.assertEqual(data["PostToolUse"][0]["matcher"], "ExitPlanMode")
        for groups in data.values():
            for handler in groups[0]["hooks"]:
                words = handler["command"].split()
                self.assertEqual(words[2:3], ["hook"])
                self.assertIn(words[3], whatsnext.HOOK_EVENTS)
                self.assertIn(words[3], wnhook.EVENTS)
                self.assertEqual(words[4:], ["--agent", "claude-code"])


if __name__ == "__main__":
    unittest.main()
