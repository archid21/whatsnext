"""Tests for `fresh-instructions` (P-69, ADR-0025): what another plugin needs to wrap up and start fresh.

Run: python3 -m unittest discover -s tests
"""

import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_wrapup import SID, CompactBase  # noqa: E402

from wn import fresh as wnfresh  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRESH = "2026-10-25T19:00:00.000Z"  # after the transcript's last turn
STALE = "2026-10-25T17:00:00.000Z"  # before it


class FreshInstructionsTests(CompactBase):
    def data(self, *extra):
        r = self.gw(["fresh-instructions", "--json", "--session", SID, *extra])
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_fresh_note_needs_no_wrap_up(self):
        self.handoff(iso=FRESH)
        data = self.data()
        self.assertEqual((data["project"], data["wrap_up_first"], data["wrap_up_state"]), (True, False, "written"))
        self.assertEqual(data["handoff"], "docs/project/HANDOFF.md")
        self.assertTrue(data["session_found"])

    def test_stale_missing_or_foreign_note_needs_a_wrap_up_first(self):
        self.assertTrue(self.data()["wrap_up_first"])  # missing
        self.handoff(iso=STALE)
        self.assertTrue(self.data()["wrap_up_first"])  # older than the last turn
        self.handoff("# Handoff\n\n## Next action\n\nAnother session's step.\n", iso=FRESH, session=None)
        data = self.data()
        self.assertEqual((data["wrap_up_first"], data["handoff_foreign"]), (True, True))

    def test_handoff_values_match_compact_instructions(self):
        self.handoff(iso=FRESH)
        fresh = self.data()
        compact = json.loads(self.gw(["compact-instructions", "--json", "--session", SID]).stdout)
        for key in ("project", "session_found", "handoff", "handoff_exists", "handoff_foreign",
                    "wrap_up_first", "wrap_up_state", "wrap_up_prompt"):
            self.assertEqual(fresh[key], compact[key], key)

    def test_start_fresh_texts(self):
        data = self.data()
        self.assertEqual(data["wrap_up_prompt"], "wrap up")
        self.assertEqual(data["continue_prompt"], "Continue from the handoff note: read it first.")
        self.assertEqual(data["terminal_command"], 'claude "Continue from the handoff note: read it first."')
        self.assertEqual(data["clear_command"], "clear")
        self.assertIn('"%s"' % data["continue_prompt"], data["new_session_prompt"])
        self.assertIn("start_session", data["new_session_prompt"])

    def test_not_a_project(self):
        other = os.path.join(self.tmp.name, "elsewhere")
        os.makedirs(other)
        r = self.gw(["fresh-instructions", "--json", "--project", other])
        self.assertFalse(json.loads(r.stdout)["project"])

    def test_bad_session_id_is_an_error(self):
        r = self.gw(["fresh-instructions", "--json", "--session", "../x"])
        self.assertEqual(r.returncode, 1)

    def test_plain_text_says_wrap_up_first_only_when_needed(self):
        out = self.gw(["fresh-instructions", "--session", SID]).stdout
        self.assertIn("Wrap up first: submit `wrap up`.", out)
        self.assertIn(wnfresh.TERMINAL_COMMAND, out)
        self.handoff(iso=FRESH)
        out = self.gw(["fresh-instructions", "--session", SID]).stdout
        self.assertNotIn("Wrap up first", out)
        self.assertIn(wnfresh.CONTINUE, out)


class BandCopyTests(unittest.TestCase):
    """hooks/newchat.ts keeps a copy of the start-fresh texts for whatsnext's band; Python is the source (ADR-0025)."""

    def test_newchat_ts_matches_python(self):
        with open(os.path.join(REPO, "hooks", "newchat.ts"), encoding="utf-8") as f:
            ts = f.read()
        m = re.search(r"export const CONTINUE = '([^']*)'", ts)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), wnfresh.CONTINUE)
        self.assertNotIn("newSessionPrompt", ts)  # New session sends nothing to the model (ADR-0026)
        self.assertIn("return `claude \"${CONTINUE}\"`", ts)
        self.assertEqual(wnfresh.TERMINAL_COMMAND, 'claude "%s"' % wnfresh.CONTINUE)


if __name__ == "__main__":
    unittest.main()
