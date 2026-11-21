"""Tests for `whatsnext handoff from-transcript` (P-88, ADR-0035). Fixtures are small synthetic chats, never real ones.

Run: python3 -m unittest tests.test_transcript
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fixtures import SCRIPTS, StatusBase  # noqa: E402

sys.path.insert(0, str(SCRIPTS))
from wn import redact  # noqa: E402

HANDOFF = "docs/project/HANDOFF.md"
SID = "abcdef12-3456-7890-abcd-ef1234567890"
FAKE_KEY = "sk-" + "A1b2C3d4" * 4  # a made-up key, shaped like one
EMAIL = "jane.doe@example.com"

GOOD = """## Goal
Ship the transcript handoff.

## Next action
Run `python3 -m unittest tests.test_transcript`.
Verify: `python3 -m unittest tests.test_transcript`
If it fails: read the first failing test.

## State
State on Fri 2026-11-20 4:00 PM PST: tests written.
Check: clean

## What changed
- tests/test_transcript.py added

## Decisions
ADR-0035.

## Constraints
Standard library only.

## Open questions and blockers
none

## Dead ends
none
"""


def text_msg(kind, text, **extra):
    row = {"type": kind, "sessionId": SID, "message": {"role": kind, "content": [{"type": "text", "text": text}]}}
    row.update(extra)
    return row


def tool_call(name, **inp):
    return {"type": "assistant", "sessionId": SID,
            "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": name, "input": inp}]}}


def tool_result(text):
    return {"type": "user", "sessionId": SID,
            "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": text}]}}


class TranscriptBase(StatusBase):
    def setUp(self):
        super().setUp()
        self.cfg()
        self.put("AGENTS.md", "# Rules\n- Run the tests first.\n")

    def chat(self, rows, name="chat.jsonl"):
        path = os.path.join(self.tmp.name, name)
        with open(path, "w", encoding="utf-8") as f:
            for row in rows:
                f.write((row if isinstance(row, str) else json.dumps(row)) + "\n")
        return path

    def prepare(self, path, *args):
        return self.gw(["handoff", "from-transcript", path, "--prepare"] + list(args))

    def prepared(self, path, *args):
        r = self.prepare(path, "--json", *args)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout)

    def write_note(self, path, answer, *args):
        return self.gw(["handoff", "from-transcript", path, "--write", "-"] + list(args), stdin=answer)

    def read(self, rel):
        with open(self.p(rel), encoding="utf-8") as f:
            return f.read()

    def snapshot(self):
        out = {}
        for base, _dirs, files in os.walk(self.proj):
            if ".git" in base.split(os.sep):
                continue
            for name in files:
                full = os.path.join(base, name)
                with open(full, "rb") as f:
                    out[os.path.relpath(full, self.proj)] = f.read()
        return out


class TrimTests(TranscriptBase):
    def test_tool_output_is_cut_to_head_and_tail(self):
        big = "HEADMARK" + "x" * 5000 + "TAILMARK"
        path = self.chat([text_msg("user", "Please build X."), tool_call("Bash", command="ls"), tool_result(big)])
        data = self.prepared(path)
        self.assertIn("HEADMARK", data["input"])
        self.assertIn("TAILMARK", data["input"])
        self.assertIn("chars cut", data["input"])
        self.assertNotIn("x" * 2000, data["input"])
        self.assertIn("CALL Bash: ls", data["input"])
        self.assertEqual(data["session"], SID)

    def test_adr_and_handoff_writes_are_kept_other_writes_are_cut(self):
        adr = "# ADR\n" + "decision line\n" * 100 + "ADR-TAIL-MARK\n"
        other = "code\n" * 200 + "OTHER-TAIL-MARK\n"
        path = self.chat([text_msg("user", "go"),
                          tool_call("Write", file_path=os.path.join(self.proj, "docs/decisions/ADR-9999-x.md"), content=adr),
                          tool_call("Write", file_path=os.path.join(self.proj, HANDOFF), content=adr.replace("ADR-TAIL", "NOTE-TAIL")),
                          tool_call("Write", file_path=os.path.join(self.proj, "src/a.py"), content=other)])
        text = self.prepared(path)["input"]
        self.assertIn("ADR-TAIL-MARK", text)
        self.assertIn("NOTE-TAIL-MARK", text)
        self.assertNotIn("OTHER-TAIL-MARK", text)

    def test_oldest_messages_drop_to_budget_and_the_opening_request_stays(self):
        rows = [text_msg("user", "OPENING REQUEST")]
        for i in range(60):
            rows.append(text_msg("assistant", "message number %03d %s" % (i, "y" * 400)))
        path = self.chat(rows)
        data = self.prepared(path, "--budget-bytes", "6000")
        self.assertGreater(data["dropped_messages"], 0)
        self.assertIn("OPENING REQUEST", data["input"])
        self.assertIn("message number 059", data["input"])
        self.assertNotIn("message number 000", data["input"])
        self.assertIn("older messages dropped", data["input"])

    def test_thinking_unknown_rows_and_bad_lines_are_skipped(self):
        think = {"type": "assistant", "sessionId": SID,
                 "message": {"role": "assistant", "content": [{"type": "thinking", "thinking": "SECRET-THOUGHT"},
                                                              {"type": "text", "text": "visible"}]}}
        path = self.chat([text_msg("user", "go"), think, {"type": "mystery", "x": 1}, "not json {", "[1,2]"])
        text = self.prepared(path)["input"]
        self.assertIn("visible", text)
        self.assertNotIn("SECRET-THOUGHT", text)

    def test_file_with_no_readable_rows_is_refused(self):
        path = self.chat(["garbage", {"type": "mystery"}])
        r = self.prepare(path)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(r.stdout, "")
        self.assertIn("no readable messages", r.stderr)

    def test_input_holds_the_repo_facts_and_the_prompt_names_the_format(self):
        self.put(HANDOFF, "# Handoff\n\nSession: old\nTask: none\nWritten: 2026-11-01T00:00Z\n\n## Goal\nOLD-NOTE-GOAL\n")
        data = self.prepared(self.chat([text_msg("user", "go")]))
        self.assertIn("Run the tests first.", data["input"])  # AGENTS.md
        self.assertIn("OLD-NOTE-GOAL", data["input"])  # the previous note
        self.assertIn("git log --oneline -10", data["input"])  # the snapshot
        self.assertIn("first", data["input"])  # a commit subject
        self.assertEqual(data["bytes"], len(data["input"].encode("utf-8")))
        for name in ("Goal", "Next action", "State", "Dead ends", "Open questions and blockers"):
            self.assertIn("`## %s`" % name, data["prompt"])
        self.assertIn("only the eight", data["prompt"])
        self.assertNotIn("http", data["prompt"])


class RedactionTests(TranscriptBase):
    def test_prepare_masks_email_key_and_private_spans(self):
        path = self.chat([text_msg("user", "mail %s now" % EMAIL), tool_result("key %s end <private>HIDDEN</private>" % FAKE_KEY)])
        data = self.prepared(path)
        self.assertNotIn(EMAIL, data["input"])
        self.assertNotIn(FAKE_KEY, data["input"])
        self.assertNotIn("HIDDEN", data["input"])
        self.assertIn("[redacted]", data["input"])
        plain = self.prepare(path)
        self.assertNotIn(EMAIL, plain.stdout)
        self.assertNotIn(FAKE_KEY, plain.stdout)

    def test_existing_callers_are_unchanged(self):
        text = "write to %s with %s" % (EMAIL, FAKE_KEY)
        self.assertIn(EMAIL, redact.mask_secrets(text))  # no email mask unless asked
        self.assertNotIn(FAKE_KEY, redact.mask_secrets(text))
        masked = redact.mask_secrets(text, emails=True)
        self.assertNotIn(EMAIL, masked)
        self.assertEqual(redact.mask_secrets("a b c"), "a b c")
        self.assertEqual(redact.mask_secrets("token=abcdefgh1234"), "token= [redacted]")
        self.assertEqual(redact.mask_secrets("x <private>y</private> z"), redact.strip_private("x <private>y</private> z"))


class PrepareReadOnlyTests(TranscriptBase):
    def test_prepare_changes_nothing(self):
        self.put(HANDOFF, "# Handoff\n\nSession: old\nTask: none\nWritten: 2026-11-01T00:00Z\n\n## Goal\nx\n")
        path = self.chat([text_msg("user", "go"), text_msg("assistant", "ok")])
        before = self.snapshot()
        r = self.prepare(path)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(before, self.snapshot())
        self.assertFalse(os.path.exists(self.p("docs/project/handoffs")))


class WriteTests(TranscriptBase):
    def setUp(self):
        super().setUp()
        self.path = self.chat([text_msg("user", "go")])

    def assert_rejected(self, answer, reason):
        self.put(HANDOFF, "# Handoff\n\nSession: old\nTask: none\nWritten: 2026-11-01T00:00Z\n\n## Goal\nKEEP-ME\n")
        before = self.snapshot()
        r = self.write_note(self.path, answer)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(reason, r.stderr)
        self.assertEqual(before, self.snapshot())  # no note, no archive: nothing written
        return r

    def test_missing_section_is_rejected(self):
        self.assert_rejected(GOOD.replace("## Dead ends\nnone\n", ""), "missing section `## Dead ends`")

    def test_extra_section_is_rejected(self):
        self.assert_rejected(GOOD + "\n## Files\na.py\n", "extra section `## Files`")

    def test_over_cap_is_rejected(self):
        self.assert_rejected(GOOD.replace("## Goal\nShip the transcript handoff.", "## Goal\n" + "g" * 201),
                             "`## Goal` is 201 characters (the cap is 200)")

    def test_missing_verify_and_check_are_rejected(self):
        self.assert_rejected(GOOD.replace("Verify: `python3 -m unittest tests.test_transcript`\n", ""), "exactly one `Verify:`")
        self.assert_rejected(GOOD.replace("Check: clean\n", ""), "at least one `Check:`")

    def test_header_lines_from_the_helper_are_rejected(self):
        self.assert_rejected("Session: fake\n" + GOOD, "text before the first `##` section")

    def test_good_note_is_written_with_the_header_and_the_old_note_archived(self):
        self.put(HANDOFF, "# Handoff\n\nSession: old\nTask: P-13\nWritten: 2026-11-01T00:00Z\n\n## Goal\nOLD\n")
        r = self.write_note(self.path, GOOD.replace("Check: clean", "Check: HEAD == %s" % self.head()))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        note = self.read(HANDOFF)
        self.assertIn("Session: %s\n" % SID, note)
        self.assertIn("Task: none\n", note)
        self.assertIn("Agent: claude-code\n", note)
        self.assertIn("Branch: %s\n" % self.branch(), note)
        self.assertIn("Source: transcript abcdef12, unverified\n", note)
        self.assertRegex(note, r"Written: \d{4}-\d\d-\d\dT\d\d:\d\dZ\n")
        self.assertTrue(note.index("Source:") < note.index("## Goal"))
        self.assertEqual(os.listdir(self.p("docs/project/handoffs")), ["20261101T0000Z-P-13.md"])
        self.assertIn("Handoff checks:", r.stdout)  # decision 7: verdicts shown
        self.assertIn("1 VERIFIED", r.stdout)

    def test_stale_check_prints_a_verdict_but_still_writes(self):
        stale = GOOD.replace("Check: clean\n", "Check: HEAD == 0000000\n")
        r = self.write_note(self.path, stale)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("1 STALE", r.stdout)
        self.assertTrue(self.has(HANDOFF))

    def test_a_run_check_is_never_run(self):
        marker = "RAN-" + "CHECK.txt"
        answer = GOOD.replace("Check: clean\n", "Check: run `touch %s`\n" % marker)
        r = self.write_note(self.path, answer)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(self.has(marker))
        self.assertIn("not run", r.stdout)

    def test_note_is_masked_before_it_is_written(self):
        answer = GOOD.replace("Standard library only.", "Ask %s, key %s." % (EMAIL, FAKE_KEY))
        r = self.write_note(self.path, answer)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        note = self.read(HANDOFF)
        self.assertNotIn(EMAIL, note)
        self.assertNotIn(FAKE_KEY, note)

    def test_write_reads_a_file_too(self):
        f = os.path.join(self.tmp.name, "answer.md")
        with open(f, "w", encoding="utf-8") as out:
            out.write(GOOD)
        r = self.gw(["handoff", "from-transcript", self.path, "--write", f])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(self.has(HANDOFF))

    def test_status_shows_the_source_line(self):
        self.assertEqual(self.write_note(self.path, GOOD).returncode, 0)
        r = self.gw(["status"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("  Source: transcript abcdef12, unverified", r.stdout)
        data = json.loads(self.gw(["status", "--json"]).stdout)
        self.assertEqual(data["handoff"]["source"], "transcript abcdef12, unverified")

    def test_status_has_no_source_line_for_a_normal_note(self):
        self.put(HANDOFF, "# Handoff\n\nSession: s\nTask: none\nWritten: 2026-11-01T00:00Z\n\n## Next action\nDo it.\n")
        r = self.gw(["status"])
        self.assertNotIn("Source:", r.stdout)


class NoNetworkTests(unittest.TestCase):
    def test_new_code_has_no_network_or_key_use(self):
        path = os.path.join(str(SCRIPTS), "wn", "transcript.py")
        with open(path, encoding="utf-8") as f:
            code = f.read()
        for word in ("import socket", "urllib", "http.client", "requests", "ANTHROPIC_API_KEY", "os.environ"):
            self.assertNotIn(word, code)



class ClipRedactsFirstTests(unittest.TestCase):
    def test_a_secret_or_private_span_cut_by_the_clip_is_still_removed(self):
        from wn import transcript as wntranscript
        key = "sk-ant-api03-" + "A" * 60
        text = "x" * 990 + key + " <private>hidden words</private>" + "y" * 2000
        out = wntranscript.clip(text, 1000, 300)
        self.assertNotIn("AAAAAAAAAA", out)
        self.assertNotIn("hidden words", out)
        mail = "z" * 1500 + "someone@example.com" + "q" * 10
        self.assertNotIn("someone@example.com", wntranscript.clip(mail, 1510, 0))


if __name__ == "__main__":
    unittest.main()
