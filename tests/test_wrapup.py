"""Tests for `wrap up`, the compact hand-off and the compact hand-off (ADR-0008, ADR-0009).

Run: python3 -m unittest discover -s tests
"""

import json
import os
import stat
import subprocess
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fixtures import STATUS, StatusBase  # noqa: E402

from wn import sessions as wnsessions  # noqa: E402
from wn import wrapup as wnwrapup  # noqa: E402

SID = "11111111-2222-3333-4444-555555555555"
OLD = "2026-10-25T18:00:00.000Z"
NEW = "2026-10-25T19:00:00.000Z"


def dead_pid():
    """The pid of a process that has exited."""
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def entry(kind, when, content=None, **extra):
    item = {"type": kind, "timestamp": when}
    if content is not None:
        item["message"] = {"content": content}
    item.update(extra)
    return item


def write_jsonl(path, items):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item) + "\n")


class SessionFilesTests(StatusBase):
    """Session ids and transcript lookup."""

    def setUp(self):
        super().setUp()
        self.sessions = os.path.join(self.tmp.name, "sessions")
        os.makedirs(self.sessions)

    def test_session_ids_cannot_escape_the_projects_folder(self):
        for bad in ("../x", "a/b", "", ".hidden", "x" * 200, None):
            self.assertFalse(wnsessions.valid_session_id(bad), bad)
            self.assertIsNone(wnsessions.find_transcript(bad, self.sessions))


class LastTurnTests(StatusBase):
    def path(self):
        return os.path.join(self.tmp.name, "t.jsonl")

    def test_bookkeeping_lines_are_not_a_turn(self):
        write_jsonl(self.path(), [
            entry("user", OLD, "hello"), entry("assistant", OLD, [{"type": "text", "text": "hi"}]),
            entry("queue-operation", NEW), entry("system", NEW), entry("attachment", NEW)])
        self.assertEqual(wnsessions.last_turn_time(self.path()), wnsessions.parse_time(OLD))

    def test_wrap_up_turn_is_skipped_until_the_next_prompt(self):
        write_jsonl(self.path(), [
            entry("user", OLD, "work"), entry("assistant", OLD),
            entry("user", NEW, "wrap up"), entry("assistant", NEW),
            entry("user", NEW, [{"tool_use_id": "t", "type": "tool_result", "content": "ok"}])])
        self.assertEqual(wnsessions.last_turn_time(self.path(), "wrap up"), wnsessions.parse_time(OLD))
        with open(self.path(), "a", encoding="utf-8") as f:
            f.write(json.dumps(entry("user", "2026-10-25T20:00:00.000Z", "more work")) + "\n")
        self.assertEqual(wnsessions.last_turn_time(self.path(), "wrap up"), wnsessions.parse_time("2026-10-25T20:00:00.000Z"))

    def test_empty_or_unreadable_lines(self):
        os.makedirs(os.path.dirname(self.path()), exist_ok=True)
        with open(self.path(), "w", encoding="utf-8") as f:
            f.write("not json\n\n[1]\n")
        self.assertIsNone(wnsessions.last_turn_time(self.path()))


class HookBase(StatusBase):
    def hook(self, event, data=None, agent="claude-code"):
        r = self.gw(["hook", event, "--agent", agent], stdin=json.dumps(data or {}))
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        return r.stdout

    def prompt(self, text, session="s1"):
        return self.hook("prompt-submit", {"prompt": text, "session_id": session, "permission_mode": "default",
                                           "cwd": self.proj})

    def stop(self, session="s1"):
        return self.hook("stop", {"session_id": session, "cwd": self.proj})

    def wrapups(self):
        return [e for e in self.logged() if e["event"] == "session.wrapup"]

    def journal(self):
        path = "%s/journal/P-13.md" % STATUS
        return self.get(path) if self.has(path) else ""


class WrapUpHookTests(HookBase):
    def setUp(self):
        super().setUp()
        self.cfg()
        self.task()
        self.commit("task")

    def archive_dir(self):
        folder = self.p("docs/project/handoffs")
        return sorted(os.listdir(folder)) if os.path.isdir(folder) else []

    def put_note(self, task="P-13", written="2026-11-05T05:03Z", extra=""):
        self.put("docs/project/HANDOFF.md", "# Handoff\n\nSession: s0\nTask: %s\nWritten: %s\n\n## Goal\nold %s\n" % (task, written, extra))

    def test_archive_saves_the_old_note_before_the_wrap_up(self):
        self.assertEqual(self.archive_dir(), [])
        self.prompt("wrap up")  # no old note: nothing to save
        self.assertEqual(self.archive_dir(), [])
        self.put_note()
        out = self.prompt("wrap up")
        self.assertIn("docs/project/HANDOFF.md", out)  # the prompt is unchanged
        self.assertEqual(self.archive_dir(), ["20261105T0503Z-P-13.md"])
        self.assertIn("old ", self.get("docs/project/handoffs/20261105T0503Z-P-13.md"))
        self.prompt("wrap up")  # the same note again: not saved twice
        self.assertEqual(len(self.archive_dir()), 1)

    def test_archive_keeps_only_the_last_n(self):
        from wn import wrapup as wnwrapup
        for i in range(wnwrapup.ARCHIVE_KEEP + 3):
            self.put_note(written="2026-11-%02dT10:00Z" % (i + 1), extra=str(i))
            self.prompt("wrap up")
        names = self.archive_dir()
        self.assertEqual(len(names), wnwrapup.ARCHIVE_KEEP)
        self.assertEqual(names[0], "20261104T1000Z-P-13.md")  # the three oldest are gone
        self.assertEqual(names[-1], "20261113T1000Z-P-13.md")

    def test_archive_never_writes_through_a_link_or_deletes_other_files(self):
        from wn import wrapup as wnwrapup
        outside = os.path.join(self.tmp.name, "outside")
        os.makedirs(outside)
        folder = self.p("docs/project/handoffs")
        os.makedirs(folder)
        os.symlink(os.path.join(outside, "victim.md"), os.path.join(folder, "20261105T0503Z-P-13.md"))  # dangling link
        self.put_note()
        self.prompt("wrap up")
        self.assertFalse(os.path.exists(os.path.join(outside, "victim.md")))
        self.assertTrue(os.path.exists(os.path.join(folder, "20261105T0503Z-P-13-2.md")))
        for i in range(wnwrapup.ARCHIVE_KEEP + 2):  # other files in the folder are never pruned
            self.put("docs/project/handoffs/notes-%d.md" % i, "mine\n")
        self.put_note(written="2026-11-06T10:00Z", extra="again")
        self.prompt("wrap up")
        self.assertEqual(len([n for n in os.listdir(folder) if n.startswith("notes-")]), wnwrapup.ARCHIVE_KEEP + 2)
        shutil_target = self.p("docs/project/elsewhere")
        os.makedirs(shutil_target)
        os.rename(folder, folder + ".old")
        os.symlink(shutil_target, folder)  # the folder itself is a link: nothing is archived into it
        self.put_note(written="2026-11-07T10:00Z", extra="third")
        self.prompt("wrap up")
        self.assertEqual(os.listdir(shutil_target), [])

    def test_archive_stays_inside_the_project_when_a_parent_folder_is_a_link(self):
        outside = os.path.join(self.tmp.name, "elsewhere")
        os.makedirs(outside)
        with open(os.path.join(outside, "HANDOFF.md"), "w", encoding="utf-8") as f:
            f.write("# Handoff\n\nSession: s0\nTask: P-13\nWritten: 2026-11-05T05:03Z\n\n## Goal\nold\n")
        import shutil
        shutil.rmtree(self.p("docs/project"), ignore_errors=True)
        os.makedirs(self.p("docs"), exist_ok=True)
        os.symlink(outside, self.p("docs/project"))  # docs/project -> outside the project
        self.prompt("wrap up")
        self.assertEqual(sorted(os.listdir(outside)), ["HANDOFF.md"])  # no handoffs/ folder was made out there

    def test_archive_failure_does_not_stop_the_wrap_up(self):
        self.put_note()
        self.put("docs/project/handoffs", "a file where the folder should be\n")
        out = self.prompt("wrap up")
        self.assertIn("docs/project/HANDOFF.md", out)

    def test_template_exact(self):
        out = self.prompt("wrap up")
        self.assertIn("file paths, ids, versions, URLs, commands and error text as they appear", out)
        self.assertIn("for a decision with no ADR, give the reason", out)
        self.assertIn("the user's corrections to you in their own words", out)
        self.assertIn("then a line `If it fails: <what to check or try next>`", out)
        self.assertIn("work the user asked for that is not done", out)
        self.assertIn("At most 400 characters in all.", out)
        self.assertLess(out.index("`Verify:"), out.index("`If it fails:"))
        self.assertIn("Next: <next action, at most 400 characters>", out)

    def test_template_exact_the_longest_line_still_fits_and_next_is_not_cut(self):
        from wn import wrapup as wnwrapup
        body = ("# Handoff\n\n## Goal\n" + "g" * 200 + "\n\n## Next action\n" + "n" * 400 + "\n\n## Constraints\n" + "c" * 600
                + "\n\n## Decisions\n" + "d" * 400 + "\n\n## Dead ends\n" + "x" * 300 + "\n\n## Open questions and blockers\n" + "b" * 300 + "\n")
        line = wnwrapup.compact_line(body)
        self.assertLessEqual(len(line), wnwrapup.MAX_LINE_CHARS)
        self.assertIn("n" * 400, line)
        self.assertIn("c" * 600, line)
        self.assertEqual(wnwrapup.MAX_NEXT_CHARS, 400)

    def test_exact_prompt_prints_the_instructions(self):
        out = self.prompt("wrap up")
        self.assertIn("docs/project/HANDOFF.md", out)
        self.assertIn("(Pacific)", out)
        self.assertRegex(out, r"= \d{4}-\d\d-\d\dT\d\d:\d\dZ")
        for section in ("## Goal", "## Next action", "## State", "## What changed", "## Decisions", "## Constraints",
                        "## Open questions and blockers"):
            self.assertIn(section, out)
        self.assertLess(out.index("## Goal"), out.index("## Next action"))
        self.assertLess(out.index("## Constraints"), out.index("## Open questions and blockers"))
        self.assertIn("Verify:", out)
        self.assertIn("never an absolute path", out)
        self.assertIn("P-13", out)
        self.assertNotIn("progress next", out)
        self.assertEqual(self.prompt("  wrap up\n"), out)

    def test_other_prompts_print_nothing(self):
        for text in ("wrap up now", "Wrap up", "please wrap up", "wrapup", "", "/compact"):
            self.assertEqual(self.prompt(text), "", text)

    def test_silent_outside_a_project(self):
        other = os.path.join(self.tmp.name, "other")
        os.makedirs(other)
        r = self.gw(["hook", "prompt-submit"], stdin=json.dumps({"prompt": "wrap up", "session_id": "s", "cwd": other}), cwd=other)
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_the_event_is_recorded_once_the_handoff_is_written(self):
        self.prompt("wrap up")
        self.assertEqual(self.wrapups(), [])  # nothing recorded when the request is made
        self.put("docs/project/HANDOFF.md", "# Handoff\n")
        self.stop()
        events = self.wrapups()
        self.assertEqual(len(events), 1)
        payload = events[0]["payload"]
        self.assertEqual((payload["session"], payload["handoff"], payload["task"]),
                         ("s1", "docs/project/HANDOFF.md", "P-13"))
        self.assertRegex(self.journal(), r"\n- \S+ wrap-up \S+ \S+ dirty=\d+")
        self.stop()  # the marker is gone: a later Stop records nothing more
        self.assertEqual(len(self.wrapups()), 1)

    def test_the_next_action_is_copied_as_auto(self):
        self.prompt("wrap up")
        self.put("docs/project/HANDOFF.md", "# Handoff\n\n## Next action\n\nWrite the form tests.\nRun: python3 -m unittest\n\n## State\n\nok\n")
        self.stop()
        text = self.get("%s/P-13.md" % STATUS)
        self.assertIn("## Next action\n\nWrite the form tests. Run: python3 -m unittest\n", text)
        self.assertRegex(text, r"- \*\*Note:\*\* auto \(")

    def test_a_confirmed_next_action_is_kept(self):
        self.task(note="confirmed (2026-10-27T14:05Z)")
        self.prompt("wrap up")
        self.put("docs/project/HANDOFF.md", "# Handoff\n\n## Next action\n\nWrite the form tests.\n")
        self.stop()
        text = self.get("%s/P-13.md" % STATUS)
        self.assertIn("## Next action\n\nRun the login tests.\n", text)
        self.assertRegex(text, r"## Since wrap-up\n\n- \S+: Next: Write the form tests\.")

    def test_no_event_when_the_handoff_was_not_written(self):
        self.put("docs/project/HANDOFF.md", "# old\n")
        old = time.time() - 3600
        os.utime(self.p("docs/project/HANDOFF.md"), (old, old))
        self.prompt("wrap up")
        self.stop()
        self.assertEqual(self.wrapups(), [])
        self.assertNotIn("wrap-up", self.journal())

    def test_stop_without_a_request_records_nothing(self):
        self.put("docs/project/HANDOFF.md", "# Handoff\n")
        self.stop()
        self.assertEqual(self.wrapups(), [])

    def test_the_path_agents_md_names(self):
        self.put("AGENTS.md", "# x\n\n- Handoff file: `notes/NEXT.md`\n")
        self.assertIn("File: notes/NEXT.md", self.prompt("wrap up"))
        self.put("notes/NEXT.md", "# Handoff\n")
        self.stop()
        self.assertEqual(self.wrapups()[0]["payload"]["handoff"], "notes/NEXT.md")

    def test_a_setting_beats_agents_md(self):
        self.put("AGENTS.md", "Handoff: notes/NEXT.md\n")
        self.cfg(paths={"handoff": "docs/HAND.md"})
        self.assertIn("File: docs/HAND.md", self.prompt("wrap up"))

    def test_an_unsafe_path_in_agents_md_is_ignored(self):
        for bad in ("../outside.md", "/etc/x.md"):
            self.put("AGENTS.md", "Handoff: %s\n" % bad)
            self.assertIn("File: docs/project/HANDOFF.md", self.prompt("wrap up"))

    def test_pacific_time_is_named(self):
        import datetime

        winter = datetime.datetime(2026, 11, 5, 5, 3, tzinfo=datetime.timezone.utc)
        summer = datetime.datetime(2026, 7, 1, 19, 30, tzinfo=datetime.timezone.utc)
        self.assertEqual(wnwrapup.pacific_now(winter), ("Wed 2026-11-04 9:03 PM PST", "2026-11-05T05:03Z"))
        self.assertEqual(wnwrapup.pacific_now(summer), ("Wed 2026-07-01 12:30 PM PDT", "2026-07-01T19:30Z"))


class CompactBase(HookBase):
    def setUp(self):
        super().setUp()
        self.cfg()
        self.claude = os.path.join(self.home, ".claude")
        self.sessions = os.path.join(self.claude, "sessions")
        self.transcript = os.path.join(self.claude, "projects", "-proj", SID + ".jsonl")
        os.makedirs(self.sessions)
        write_jsonl(self.transcript, [
            entry("system", OLD, cwd=self.proj), entry("user", OLD, "work", cwd=self.proj),
            entry("assistant", OLD, [{"type": "text", "text": "done"}], cwd=self.proj)])
        self.set_mtime(self.transcript, OLD)

    @staticmethod
    def set_mtime(path, iso):
        t = wnsessions.parse_time(iso)
        os.utime(path, (t, t))

    def handoff(self, text="# Handoff\n\n## Next action\n\nRun the login tests.\n", iso=None, session=SID):
        """Write the note. `session`: the session whose sidecar says it wrote this text (None: no sidecar)."""
        self.put("docs/project/HANDOFF.md", text)
        if iso:
            self.set_mtime(self.p("docs/project/HANDOFF.md"), iso)
        if session:
            wnwrapup.write_sidecar(self.proj, session, self.p("docs/project/HANDOFF.md"))

class CompactInstructionsTests(CompactBase):
    def test_text_has_the_keep_and_drop_rules_and_the_handoff(self):
        self.handoff()
        r = self.gw(["compact-instructions"])
        self.assertEqual(r.returncode, 0, r.stderr)
        for word in ("Keep:", "Drop:", "decisions", "open questions", "file paths", "next steps", "tool output", "dead ends"):
            self.assertIn(word, r.stdout)
        self.assertIn("Run the login tests.", r.stdout)
        self.assertIn("docs/project/HANDOFF.md", r.stdout)

    def test_without_a_handoff_it_is_the_general_text(self):
        r = self.gw(["compact-instructions"])
        self.assertNotIn("handoff note", r.stdout)
        self.assertIn("Keep:", r.stdout)

    def test_a_long_handoff_is_cut(self):
        self.handoff("# Handoff\n" + "x" * 10000)
        r = self.gw(["compact-instructions"])
        self.assertLess(len(r.stdout), 4000)
        self.assertIn("handoff cut here", r.stdout)

    def test_json_steps(self):
        self.handoff(iso=NEW)
        data = json.loads(self.gw(["compact-instructions", "--json", "--session", SID]).stdout)
        self.assertEqual(data["compact_prompt"], "/compact " + data["instructions"])
        self.assertEqual((data["wrap_up_prompt"], data["handoff"], data["handoff_exists"], data["session_found"]),
                         ("wrap up", "docs/project/HANDOFF.md", True, True))
        self.assertFalse(data["wrap_up_first"])  # the handoff is newer than the last turn

    def test_wrap_up_first_when_the_handoff_is_missing_or_older(self):
        data = json.loads(self.gw(["compact-instructions", "--json", "--session", SID]).stdout)
        self.assertTrue(data["wrap_up_first"])
        self.handoff(iso="2026-10-25T17:00:00.000Z")
        data = json.loads(self.gw(["compact-instructions", "--json", "--session", SID]).stdout)
        self.assertTrue(data["wrap_up_first"])

    def test_a_handoff_written_in_the_wrap_up_turn_is_not_stale(self):
        self.handoff(iso="2026-10-25T18:00:30.000Z")  # written inside the wrap-up turn below
        with open(self.transcript, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry("user", "2026-10-25T18:00:10.000Z", "wrap up")) + "\n")
            f.write(json.dumps(entry("assistant", "2026-10-25T18:01:00.000Z", [{"type": "text", "text": "ok"}])) + "\n")
        data = json.loads(self.gw(["compact-instructions", "--json", "--session", SID]).stdout)
        self.assertFalse(data["wrap_up_first"])

    def test_bad_session_id(self):
        r = self.gw(["compact-instructions", "--session", "../x"])
        self.assertEqual(r.returncode, 1)
