"""Tests for the idle wrap-up check (P-40, ADR-0016): `whatsnext hook idle-check`.

The timer, the context size and Claude Code's own settings are the hooks module's side (hooks/idle.test.ts).

Run: python3 -m unittest discover -s tests
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_wrapup import NEW, OLD, SID, CompactBase, entry, write_jsonl  # noqa: E402


class IdleCheckTests(CompactBase):
    def setUp(self):
        super().setUp()
        self.task()
        self.cfg(wrapup={"autoIdle": True})

    def check(self, session=SID, **extra):
        data = {"session_id": session, "transcript_path": self.transcript, "cwd": self.proj}
        data.update(extra)
        r = self.gw(["hook", "idle-check", "--agent", "claude-code"], stdin=json.dumps(data))
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        return json.loads(r.stdout) if r.stdout.strip() else None

    def asked_file(self, session=SID):
        return os.path.join(self.proj, ".whatsnext", "sessions", session + ".idle.json")

    def test_off_by_default(self):
        self.cfg()
        self.assertEqual(self.check(), {"fire": False, "reason": "wrapup.autoIdle is off"})
        self.assertFalse(os.path.exists(self.asked_file()))

    def test_fires_with_no_wrap_up_and_records_when_it_asked(self):
        self.assertEqual(self.check(), {"fire": True})
        with open(self.asked_file(), encoding="utf-8") as f:
            asked = json.load(f)["asked"]
        self.assertRegex(asked, r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")

    def test_a_fresh_wrap_up_for_this_session_does_not_fire(self):
        self.handoff(iso=NEW)  # written after the session's last turn (OLD), and this session's sidecar says so
        result = self.check()
        self.assertEqual(result, {"fire": False, "reason": "this session already has a fresh wrap-up"})
        self.assertFalse(os.path.exists(self.asked_file()))

    def test_a_wrap_up_with_a_later_turn_is_stale_and_fires(self):
        self.handoff(iso=OLD)
        write_jsonl(self.transcript, [entry("user", OLD, "work"), entry("user", NEW, "more work")])
        self.assertEqual(self.check(), {"fire": True})

    def test_another_sessions_wrap_up_is_not_this_sessions(self):
        self.handoff(iso=NEW, session="99999999-2222-3333-4444-555555555555")
        self.assertEqual(self.check(), {"fire": True})

    def test_finds_the_transcript_itself_when_none_is_given(self):
        self.handoff(iso=OLD)
        write_jsonl(self.transcript, [entry("user", OLD, "work"), entry("user", NEW, "more work")])
        self.assertEqual(self.check(transcript_path=None), {"fire": True})

    def test_silent_outside_a_project_and_without_a_session_id(self):
        outside = os.path.join(self.tmp.name, "elsewhere")
        os.makedirs(outside)
        r = self.gw(["hook", "idle-check", "--agent", "claude-code"], stdin=json.dumps({"session_id": SID, "cwd": outside}), cwd=outside)
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        self.assertEqual(self.check(session="../x"), {"fire": False, "reason": "no session id"})

    def test_schema_default_is_off_and_the_setting_is_documented(self):
        r = self.gw(["config", "show"])
        self.assertIn("wrapup.autoIdle = true", r.stdout)  # the project layer set it
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "GUIDE.md"), encoding="utf-8") as f:
            self.assertIn("`wrapup.autoIdle`", f.read())


if __name__ == "__main__":
    unittest.main()
