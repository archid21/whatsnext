"""Tests for the session-aware handoff, the compact line and `config set --user`
(ADR-0008 and ADR-0009).

Run: python3 -m unittest discover -s tests
"""

import datetime
import hashlib
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fixtures import STATUS, Sandbox  # noqa: E402
from test_wrapup import SID, CompactBase, HookBase, entry, write_jsonl  # noqa: E402

from wn import packet as wnpacket  # noqa: E402
from wn import wrapup as wnwrapup  # noqa: E402

HANDOFF = "docs/project/HANDOFF.md"
WRITTEN = "2026-11-05T05:03Z"


def note(session="s1", task="P-13", written=WRITTEN, next_action="Run the form tests.", constraints="Do not touch auth.",
         goal="Ship the forms.", decisions="none", blockers="none", header=True, branch=None):
    head = "# Handoff\n" + ("Session: %s\nTask: %s\nWritten: %s\n" % (session, task, written) if header else "")
    if header and branch:
        head += "Branch: %s\n" % branch
    return (head + "\n## Goal\n%s\n\n## Next action\n%s\nVerify: python3 -m unittest\n\n## State\nState on x (Pacific): ok\n\n"
            "## What changed\nnone\n\n## Decisions\n%s\n\n## Constraints\n%s\n\n## Open questions and blockers\n%s\n"
            % (goal, next_action, decisions, constraints, blockers))


class HandoffBase(HookBase):
    def setUp(self):
        super().setUp()
        self.cfg()
        self.task()
        self.commit("task")

    def wrap_up(self, session, text):
        """A wrap-up in `session`: the prompt, the agent writing `text`, then Stop."""
        self.prompt("wrap up", session=session)
        self.put(HANDOFF, text)
        self.stop(session=session)

    def sidecar(self, session):
        path = os.path.join(self.proj, ".whatsnext", "sessions", session + ".handoff.json")
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def start(self, session="s1", source="startup"):
        return self.hook("session-start", {"source": source, "session_id": session, "cwd": self.proj})


class HeaderAndSidecarTests(HandoffBase):
    def test_instructions_give_the_header_lines(self):
        out = self.prompt("wrap up", session="sess-9")
        self.assertIn("\nSession: sess-9\n", out)
        self.assertIn("\nTask: P-13\n", out)
        self.assertRegex(out, r"\nWritten: \d{4}-\d\d-\d\dT\d\d:\d\dZ\n")
        self.assertLess(out.index("# Handoff"), out.index("Session: sess-9"))

    def test_no_task_says_none(self):
        os.remove(self.p("%s/P-13.md" % STATUS))
        self.assertIn("\nTask: none\n", self.prompt("wrap up"))

    def test_settle_writes_the_sidecar(self):
        text = note()
        self.wrap_up("s1", text)
        side = self.sidecar("s1")
        self.assertEqual(side["sha256"], hashlib.sha256(text.encode()).hexdigest())
        self.assertEqual(side["path"], HANDOFF)
        self.assertAlmostEqual(side["written_epoch"], os.path.getmtime(self.p(HANDOFF)), places=2)

    def test_no_sidecar_when_the_note_was_not_written(self):
        self.prompt("wrap up")
        self.stop()
        self.assertFalse(os.path.exists(os.path.join(self.proj, ".whatsnext", "sessions", "s1.handoff.json")))

    def test_parse_header(self):
        self.assertEqual(wnwrapup.parse_header(note()), {"session": "s1", "task": "P-13", "written": WRITTEN, "branch": None})
        self.assertEqual(wnwrapup.parse_header(note(header=False)), {"session": None, "task": None, "written": None, "branch": None})
        self.assertEqual(wnwrapup.parse_header("# Handoff\n" * 2 + "\n" * 20 + "Session: late\n")["session"], None)


class ForeignTests(CompactBase):
    def state(self, session=SID):
        return wnwrapup.handoff_state(self.p(HANDOFF), self.transcript, session, self.proj)

    def test_own_note_is_fresh(self):
        self.handoff(note(session=SID), iso="2026-10-25T19:00:00.000Z")
        state = self.state()
        self.assertEqual((state["foreign"], state["stale"]), (False, False))

    def test_a_note_without_a_sidecar_is_foreign(self):
        self.handoff(note(), iso="2026-10-25T19:00:00.000Z", session=None)
        state = self.state()
        self.assertEqual((state["foreign"], state["stale"]), (True, True))

    def test_a_note_another_session_wrote_is_foreign(self):
        self.handoff(note(session=SID), iso="2026-10-25T19:00:00.000Z")
        self.put(HANDOFF, note(session="other", next_action="Something else."))  # B's wrap-up: new text, A's sidecar
        self.set_mtime(self.p(HANDOFF), "2026-10-25T19:30:00.000Z")
        state = self.state()
        self.assertEqual((state["foreign"], state["stale"]), (True, True))

    def test_without_a_session_nothing_is_foreign(self):
        self.handoff(note(), iso="2026-10-25T19:00:00.000Z", session=None)
        state = wnwrapup.handoff_state(self.p(HANDOFF), self.transcript)
        self.assertEqual((state["foreign"], state["stale"]), (False, False))

    def test_a_missing_note_is_stale_not_foreign(self):
        state = self.state()
        self.assertEqual((state["exists"], state["foreign"], state["stale"]), (False, False, True))

    def test_own_note_older_than_the_last_turn_is_stale(self):
        self.handoff(note(session=SID), iso="2026-10-25T17:00:00.000Z")
        state = self.state()
        self.assertEqual((state["foreign"], state["stale"]), (False, True))

    def test_compact_instructions_omit_a_foreign_body(self):
        self.handoff(note(next_action="Secret next step."), session=None)
        text = wnwrapup.compact_instructions(self.proj, wnwrapup.gwconfig.load(self.proj), SID)
        self.assertNotIn("Secret next step.", text)
        self.assertIn("did not write it", text)
        self.assertIn(HANDOFF, text)
        mine = self.handoff(note(next_action="Own next step."))
        text = wnwrapup.compact_instructions(self.proj, wnwrapup.gwconfig.load(self.proj), SID)
        self.assertIn("Own next step.", text)

    def test_json_wrap_up_first_is_true_for_a_foreign_note(self):
        self.handoff(note(), iso="2026-10-25T19:00:00.000Z", session=None)
        data = json.loads(self.gw(["compact-instructions", "--json", "--session", SID]).stdout)
        self.assertTrue(data["wrap_up_first"])
        self.assertTrue(data["handoff_foreign"])
        self.assertNotIn("Run the form tests.", data["instructions"])
        self.assertIsNone(data["compact_line"])


class ProjectAndStateTests(CompactBase):
    def data(self):
        return json.loads(self.gw(["compact-instructions", "--json", "--session", SID]).stdout)

    def test_project_true_in_a_whatsnext_project(self):
        self.assertTrue(self.data()["project"])  # the fixture's settings file sits in .whatsnext/
        os.remove(os.path.join(self.proj, ".whatsnext", "config.json"))
        os.rmdir(os.path.join(self.proj, ".whatsnext"))
        self.assertFalse(self.data()["project"])  # no .whatsnext/ and no entry file
        os.makedirs(os.path.join(self.proj, ".whatsnext"))
        self.assertTrue(self.data()["project"])

    def test_project_true_with_the_entry_file(self):
        os.remove(os.path.join(self.proj, ".whatsnext", "config.json"))
        os.rmdir(os.path.join(self.proj, ".whatsnext"))
        self.put("docs/project/README.md", "# x\n")
        self.assertTrue(self.data()["project"])

    def test_project_false_when_the_progress_module_is_off(self):
        self.cfg(modules={"progress": False})
        self.assertFalse(self.data()["project"])

    def test_project_false_outside_a_project(self):
        other = os.path.join(self.tmp.name, "elsewhere")
        os.makedirs(other)
        r = self.gw(["compact-instructions", "--json", "--project", other])
        self.assertFalse(json.loads(r.stdout)["project"])

    def test_wrap_up_state_none_requested_written(self):
        self.assertEqual(self.data()["wrap_up_state"], "none")
        marker = wnwrapup.marker_path(self.proj, SID)
        os.makedirs(os.path.dirname(marker))
        with open(marker, "w") as f:
            f.write("{}")
        self.assertEqual(self.data()["wrap_up_state"], "requested")
        os.remove(marker)
        self.handoff(note(session=SID), iso="2026-10-25T19:00:00.000Z")
        data = self.data()
        self.assertEqual((data["wrap_up_state"], data["wrap_up_first"]), ("written", False))

    def test_wrap_up_state_is_none_once_a_later_turn_came(self):
        self.handoff(note(session=SID), iso="2026-10-25T17:00:00.000Z")
        data = self.data()
        self.assertEqual((data["wrap_up_state"], data["wrap_up_first"]), ("none", True))

    def test_wrap_up_state_without_a_session(self):
        data = json.loads(self.gw(["compact-instructions", "--json"]).stdout)
        self.assertEqual(data["wrap_up_state"], "none")


class ResumeNoteTests(HandoffBase):
    def test_own_session_note_says_read_it_first(self):
        self.wrap_up("s1", note(session="s1", task="none"))
        self.assertRegex(self.start("s1"), r"Handoff: %s, wrapped up \d{4}-\d\d-\d\dT\d\d:\d\dZ \(read it first\)" % HANDOFF)

    def test_the_active_tasks_note_says_read_it_first_in_a_new_session(self):
        self.wrap_up("s1", note(session="s1", task="P-13"))
        self.assertRegex(self.start("after-clear"), r"Handoff: %s, wrapped up \d{4}-.*\(read it first\)" % HANDOFF)

    def test_another_sessions_note_is_pointed_to(self):
        self.put(HANDOFF, note(session="s2", task="P-99"))
        out = self.start("s1")
        self.assertRegex(out, r"Handoff: %s, wrapped up \d{4}-.*\(another session's note\)" % HANDOFF)
        self.assertNotIn("read it first", out)

    def test_an_old_note_without_a_header_is_another_sessions(self):
        self.put(HANDOFF, note(header=False))
        self.assertIn("(another session's note)", self.start("s1"))

    def test_no_note_no_line(self):
        self.assertIn("Handoff: none, facts only.", self.start("s1"))

    def ago(self, hours):
        when = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)
        return when.strftime("%Y-%m-%dT%H:%MZ")

    def test_no_task_a_recent_unrelated_none_note_gives_its_goal_and_next(self):
        os.remove(self.p("%s/P-13.md" % STATUS))
        self.put(HANDOFF, note(session="s2", task="none", written=self.ago(1), goal="Ship the forms.",
                               next_action="Run the form tests."))
        out = self.start("s1")
        self.assertIn("Goal (handoff ", out)
        self.assertIn("Next (handoff ", out)
        self.assertIn("Ship the forms.", out)
        self.assertIn("Run the form tests.", out)
        self.assertIn("(another session's note)", out)
        self.assertLessEqual(len(out), 1199)

    def branch(self):
        import subprocess
        return subprocess.run(["git", "-C", self.proj, "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True,
                              text=True, check=True).stdout.strip()

    def test_p54_a_fresh_none_note_from_this_branch_says_read_it_first_after_clear(self):
        os.remove(self.p("%s/P-13.md" % STATUS))
        self.put(HANDOFF, note(session="before-clear", task="none", written=self.ago(1), branch=self.branch()))
        out = self.start("after-clear", source="clear")
        self.assertIn("(read it first)", out)
        self.assertNotIn("another session's note", out)

    def test_p54_a_none_note_from_another_branch_is_another_sessions(self):
        os.remove(self.p("%s/P-13.md" % STATUS))
        self.put(HANDOFF, note(session="before-clear", task="none", written=self.ago(1), branch="some-other-branch"))
        self.assertIn("(another session's note)", self.start("after-clear", source="clear"))

    def test_p54_a_none_note_older_than_stale_after_is_another_sessions(self):
        os.remove(self.p("%s/P-13.md" % STATUS))
        self.put(HANDOFF, note(session="before-clear", task="none", written=self.ago(5), branch=self.branch()))
        self.assertIn("(another session's note)", self.start("after-clear", source="clear"))  # default staleAfter 4h

    def test_p54_a_none_note_without_a_branch_line_is_another_sessions(self):
        os.remove(self.p("%s/P-13.md" % STATUS))
        self.put(HANDOFF, note(session="before-clear", task="none", written=self.ago(1)))
        self.assertIn("(another session's note)", self.start("after-clear", source="clear"))

    def test_p54_a_task_note_from_this_branch_keeps_the_task_rule(self):
        os.remove(self.p("%s/P-13.md" % STATUS))
        self.put(HANDOFF, note(session="before-clear", task="P-99", written=self.ago(1), branch=self.branch()))
        self.assertIn("(another session's note)", self.start("after-clear", source="clear"))

    def test_p54_the_wrap_up_prompt_asks_for_a_branch_line(self):
        out = self.prompt("wrap up", session="s1")
        self.assertIn("Branch: %s" % self.branch(), out)
        self.assertIn("four header lines", out)

    def test_no_task_an_old_none_note_gives_neither_line(self):
        os.remove(self.p("%s/P-13.md" % STATUS))
        self.put(HANDOFF, note(session="s2", task="none", written=self.ago(30)))
        out = self.start("s1")
        self.assertNotIn("Goal (handoff", out)
        self.assertNotIn("Next (handoff", out)

    def test_no_task_a_note_with_a_task_id_gives_neither_line(self):
        os.remove(self.p("%s/P-13.md" % STATUS))
        self.put(HANDOFF, note(session="s2", task="P-13", written=self.ago(1)))
        out = self.start("s1")
        self.assertNotIn("Goal (handoff", out)
        self.assertNotIn("Next (handoff", out)

    def test_the_note_stays_within_its_cap(self):
        self.task(next_action="word " * 200, note="confirmed (2026-10-27T14:05Z)")
        self.put(HANDOFF, note(session="s1", next_action="x " * 300))
        out = self.start("s1")
        self.assertLessEqual(len(out), wnpacket.NOTE_CAP)
        self.assertIn("Next", out)


class NextLineTests(HandoffBase):
    def next_text(self):
        out = self.start("s1")
        return [line for line in out.splitlines() if line.startswith("Next")][0]

    def test_a_newer_handoff_wins(self):
        self.task(note="confirmed (2026-11-05T01:00Z)")
        self.put(HANDOFF, note(session="s1", written="2026-11-05T05:03Z"))
        self.assertEqual(self.next_text(), "Next (handoff 2026-11-05T05:03Z): Run the form tests. Verify: python3 -m unittest")

    def test_a_newer_confirmed_next_wins(self):
        self.task(note="confirmed (2026-11-05T06:00Z)")
        self.put(HANDOFF, note(session="s1", written="2026-11-05T05:03Z"))
        self.assertEqual(self.next_text(), "Next (confirmed 2026-11-05T06:00Z): Run the login tests.")

    def test_a_handoff_of_another_task_and_session_never_replaces_the_next(self):
        self.task(note="confirmed (2026-11-05T01:00Z)")
        self.put(HANDOFF, note(session="s2", task="P-99", written="2026-11-05T09:00Z"))
        self.assertEqual(self.next_text(), "Next: Run the login tests.")

    def test_without_a_handoff_the_line_is_plain(self):
        self.assertEqual(self.next_text(), "Next: Run the login tests.")

    def test_a_long_next_is_cut_inside_the_cap(self):
        self.task(note="confirmed (2026-11-05T01:00Z)")
        self.put(HANDOFF, note(session="s1", next_action="long " * 400))
        out = self.start("s1")
        self.assertLessEqual(len(out), wnpacket.NOTE_CAP)
        self.assertIn("Next (handoff 2026-11-05T05:03Z): long", out)
        self.assertIn("(full: ", out)


class CompactLineTests(unittest.TestCase):
    def test_line_has_the_sections_in_order(self):
        line = wnwrapup.compact_line(note(decisions="ADR-0007 chose X."))
        self.assertTrue(line.startswith("/compact Keep:"))
        self.assertNotIn("\n", line)
        order = [line.index(label + ":") for label in ("Goal", "Next", "Constraints", "Decisions")]
        self.assertEqual(order, sorted(order))
        self.assertIn("Next: Run the form tests. Verify: python3 -m unittest", line)
        self.assertIn("Constraints: Do not touch auth.", line)
        self.assertNotIn("Blockers:", line)  # `none` is left out

    def test_caps_per_section(self):
        line = wnwrapup.compact_line(note(goal="g" * 500, decisions="d" * 900, blockers="b" * 700,
                                          next_action="n" * 100, constraints="c" * 100))
        self.assertIn("g" * 199 + "\u2026", line)
        self.assertNotIn("g" * 201, line)
        self.assertIn("d" * 399 + "\u2026", line)
        self.assertIn("b" * 299 + "\u2026", line)

    def test_next_and_constraints_keep_their_caps_and_the_total_fits(self):
        line = wnwrapup.compact_line(note(goal="g" * 500, decisions="d" * 900, blockers="b" * 700,
                                          next_action="n" * 290, constraints="c" * 590))
        self.assertLessEqual(len(line), wnwrapup.MAX_LINE_CHARS)
        self.assertIn("n" * 290, line)
        self.assertIn("c" * 590, line)
        self.assertIn("Goal:", line)

    def test_next_and_constraints_are_cut_only_at_their_own_caps(self):
        line = wnwrapup.compact_line(note(next_action="n" * 1000, constraints="c" * 2000))
        self.assertIn("Next: " + "n" * 399 + "\u2026", line)
        self.assertIn("c" * 599 + "\u2026", line)
        self.assertLessEqual(len(line), wnwrapup.MAX_LINE_CHARS)

    def test_the_old_open_questions_heading_is_read(self):
        text = "# Handoff\n\n## Next action\nGo.\n\n## Open questions\nWhich database?\n"
        self.assertIn("Blockers: Which database?", wnwrapup.compact_line(text))

    def test_line_fits_on_one_line_with_a_multi_line_note(self):
        text = "# Handoff\n\n## Next action\nline one\nline two\n\n## Constraints\na\n\nb\n"
        line = wnwrapup.compact_line(text)
        self.assertNotIn("\n", line)
        self.assertIn("Next: line one line two", line)

    def test_fit_body_keeps_the_important_sections_whole(self):
        body = note(next_action="Do the thing.", constraints="Keep X.") + "\n## Extra\n" + "z" * 5000
        body = body.replace("State on x (Pacific): ok", "s" * 4000)
        fitted = wnwrapup.fit_body(body, 600, "docs/project/HANDOFF.md")
        self.assertIn("Do the thing.", fitted)
        self.assertIn("Keep X.", fitted)
        self.assertIn("Session: s1", fitted)
        self.assertIn("handoff cut here", fitted)
        self.assertLess(len(fitted), 750)
        self.assertEqual(wnwrapup.fit_body("short", 600, "x"), "short")

    def test_the_prompt_tells_the_agent_to_end_with_the_line(self):
        import tempfile, subprocess
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["git", "init", "-q", tmp], check=True)
            effective = wnwrapup.gwconfig.load(tmp)
            out = wnwrapup.instructions(tmp, effective, session_id="abc", agent="codex")
        self.assertIn("/compact Keep:", out)
        self.assertIn("Goal: <goal, at most 200 characters>", out)
        self.assertIn("Next: <next action, at most 400 characters>", out)
        self.assertIn("Constraints: <constraints, at most 600 characters>", out)
        self.assertIn("Decisions: <decisions, at most 400 characters>", out)
        self.assertIn("Blockers: <open questions and blockers, at most 300 characters>", out)
        self.assertIn("1800", out)
        template = [l for l in out.splitlines() if l.startswith("/compact ")]
        self.assertEqual(len(template), 1)
        self.assertEqual(out.splitlines()[-1], "or `/clear` for a fresh start")
        self.assertEqual(out.splitlines()[-2], template[0])

    def test_the_claude_code_prompt_ends_with_the_compact_hint_not_a_template(self):
        import tempfile, subprocess
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["git", "init", "-q", tmp], check=True)
            effective = wnwrapup.gwconfig.load(tmp)
            out = wnwrapup.instructions(tmp, effective, session_id="abc")
        lines = out.splitlines()
        self.assertFalse([l for l in lines if l.startswith("/compact ")])
        self.assertNotIn("MAX_LINE_CHARS", out)
        self.assertTrue(lines[-2].startswith("Handoff written: docs/project/HANDOFF.md"), lines[-2])
        self.assertEqual(lines[-1], "Press Compact here above the prompt to keep going in this session (the handoff "
                                    "is added to the compact for you), or New session to start fresh with it.")  # the band's buttons (ADR-0026)


class CompactJsonLineTests(CompactBase):
    def test_json_returns_the_finished_line(self):
        self.handoff(note(session=SID), iso="2026-10-25T19:00:00.000Z")
        data = json.loads(self.gw(["compact-instructions", "--json", "--session", SID]).stdout)
        self.assertTrue(data["compact_line"].startswith("/compact Keep:"))
        self.assertIn("Next: Run the form tests.", data["compact_line"])


class ConfigSetTests(Sandbox):
    def user_file(self):
        with open(os.path.join(self.xdg, "whatsnext", "config.json"), encoding="utf-8") as f:
            return json.load(f)

    def shown(self):
        return json.loads(self.gw(["config", "show", "--json"]).stdout)

    def test_set_writes_the_user_layer_and_prints_the_effective_value(self):
        r = self.gw(["config", "set", "--user", "plan.staleAfter", "2h"])
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        self.assertIn('plan.staleAfter = "2h"  (user: ', r.stdout)
        self.assertEqual(self.user_file(), {"plan": {"staleAfter": "2h"}})
        self.assertEqual(self.shown()["plan.staleAfter"]["source"], "user")
        self.assertEqual(self.shown()["plan.staleAfter"]["value"], "2h")

    def test_set_keeps_other_keys_and_types_the_value(self):
        self.write("user", {"plan": {"branchOnStart": "stay"}})
        self.assertEqual(self.gw(["config", "set", "--user", "plan.staleAfter", "2h"]).returncode, 0)
        self.assertEqual(self.gw(["config", "set", "--user", "plan.verifyTimeout", "10m"]).returncode, 0)
        self.assertEqual(self.user_file(), {"plan": {"branchOnStart": "stay", "staleAfter": "2h", "verifyTimeout": "10m"}})

    def test_unknown_keys_are_refused_and_nothing_is_written(self):
        for key in ("plan.nope", "plan", "nothing", "$schema", "modules.plan.x", ""):
            r = self.gw(["config", "set", "--user", key, "1"])
            self.assertEqual(r.returncode, 2, key)
            self.assertIn("unknown setting", r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.xdg, "whatsnext", "config.json")))

    def test_bad_values_are_refused(self):
        for key, value in (("plan.staleAfter", "soon"), ("plan.verifyTimeout", "soon"), ("plan.branchOnStart", "maybe"),
                           ("paths.handoff", "../x"), ("modules.plan", "maybe")):
            r = self.gw(["config", "set", "--user", key, value])
            self.assertEqual(r.returncode, 2, (key, value))
            self.assertNotEqual(r.stderr, "")
        self.assertFalse(os.path.exists(os.path.join(self.xdg, "whatsnext", "config.json")))

    def test_a_string_setting_and_a_path_setting(self):
        self.assertEqual(self.gw(["config", "set", "--user", "paths.handoff", "notes/HANDOFF.md"]).returncode, 0)
        self.assertEqual(self.user_file(), {"paths": {"handoff": "notes/HANDOFF.md"}})

    def test_user_flag_is_required_and_arguments_are_counted(self):
        for args in (["config", "set", "plan.staleAfter", "2h"], ["config", "set", "--user", "plan.staleAfter"],
                     ["config", "set"]):
            self.assertEqual(self.gw(args).returncode, 2, args)

    def test_a_broken_user_file_is_not_overwritten(self):
        self.write("user", "{not json", raw=True)
        r = self.gw(["config", "set", "--user", "plan.staleAfter", "2h"])
        self.assertEqual(r.returncode, 2)
        with open(os.path.join(self.xdg, "whatsnext", "config.json"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "{not json")

    def test_a_project_setting_still_wins_and_the_output_says_so(self):
        self.write("project", {"plan": {"staleAfter": "1h"}})
        r = self.gw(["config", "set", "--user", "plan.staleAfter", "2h"])
        self.assertEqual(r.returncode, 0)
        self.assertIn('plan.staleAfter = "1h"  (project: ', r.stdout)


if __name__ == "__main__":
    unittest.main()
