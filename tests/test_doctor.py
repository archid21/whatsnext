"""Tests for `whatsnext doctor` (P-18).

Run: python3 -m unittest discover -s tests
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fixtures import StatusBase  # noqa: E402


class DoctorTests(StatusBase):
    def setUp(self):
        super().setUp()
        self.cfg()
        self.task()

    def doctor(self, *args):
        r = self.gw(["doctor"] + list(args))
        self.assertEqual(r.stderr, "")
        return r

    def test_codex_gap_prints_a_fix_line_and_a_status_line(self):
        r = self.doctor()
        self.assertEqual(r.returncode, 1)
        self.assertIn("Codex\n  hooks: not installed\n  fix: whatsnext install-hooks --user", r.stdout)
        self.assertIn("PreCompact text: Claude Code yes, Codex no (ignored;", r.stdout)
        self.assertIn("  hooks: all 8 events are in the plugin's hooks/hooks.json", r.stdout)
        self.assertIn("1 gap found.", r.stdout)

    def test_installed_codex_hooks_have_no_gap_and_a_changed_hook_is_named(self):
        self.assertEqual(self.gw(["install-hooks", "--project"]).returncode, 0)
        r = self.doctor()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("hooks (project, .codex/hooks.json): all 4 events installed", r.stdout)
        self.assertIn("trust: Codex skips new or changed hooks", r.stdout)
        self.assertIn("No gaps found.", r.stdout)
        path = os.path.join(self.proj, ".codex", "hooks.json")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        data["hooks"].pop("PreCompact")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        r = self.doctor()
        self.assertEqual(r.returncode, 1)
        self.assertIn("missing or changed: PreCompact", r.stdout)
        self.assertIn("fix: whatsnext install-hooks --project", r.stdout)

    def test_last_fired_comes_from_the_session_state_and_json_works(self):
        self.assertIn("none recorded yet", self.doctor().stdout)
        self.commit("task")
        self.gw(["hook", "stop"], stdin=json.dumps({"session_id": "s1"}))
        out = self.doctor().stdout
        self.assertRegex(out, r"Last hook fired \(either agent\): stop at \d{4}-\d\d-\d\dT\d\d:\d\dZ")
        data = json.loads(self.doctor("--json").stdout)
        self.assertEqual(data["last_fired"][0], "stop")
        self.assertEqual(self.gw(["doctor", "--bad"]).returncode, 2)


if __name__ == "__main__":
    unittest.main()
