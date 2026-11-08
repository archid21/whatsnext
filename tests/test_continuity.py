"""Cross-agent workflow regressions. These exercise hook/CLI contracts, not live model behavior."""

import json
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fixtures import PlanBase, PLAN_PATH, STATUS, session_note
from wn import config, hook, sessions, wrapup


def codex_message(role, text, timestamp="2099-01-01T00:00:00Z"):
    return {"type": "response_item", "timestamp": timestamp, "payload": {
        "type": "message", "role": role, "content": [{
            "type": "input_text" if role == "user" else "output_text", "text": text}]}}


class ContinuityTests(PlanBase):
    def event(self, agent, event, sid, **data):
        result = self.gw(["hook", event, "--agent", agent], stdin=json.dumps(
            dict(data, session_id=sid, cwd=self.proj)))
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        return session_note(event, agent, result.stdout)

    def saved_plan(self):
        self.put(PLAN_PATH, "## Now\n- [ ] P-13 Build · done means: `test -f result.txt`\n"
                 "- [ ] P-14 Next · done means: `true`\n")

    def begin_task(self, agent="codex"):
        result = self.start("P-13", "--dirty", "carry-on", "--branch", "stay", agent=agent)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_two_way_handoff_resume_verify_and_failure(self):
        for first, second in (("codex", "claude-code"), ("claude-code", "codex")):
            with self.subTest(first=first):
                self.saved_plan()
                self.begin_task(first)
                sid = first + "-writer"
                instructions = self.event(first, "prompt-submit", sid, prompt="wrap up")
                self.assertIn("Session: " + sid, instructions)
                self.assertIn("Task: P-13", instructions)
                self.put("docs/project/HANDOFF.md", "# Handoff\nSession: %s\nTask: P-13\n"
                         "Written: 2026-11-08T17:15Z\n\n## Next action\nCreate result.txt.\n"
                         "Verify: test -f result.txt\n\n## Goal\nBuild.\n" % sid)
                self.event(first, "stop", sid)
                self.assertTrue(self.has(".whatsnext/sessions/" + sid + ".handoff.json"))
                resume = self.event(second, "session-start", second + "-reader", source="startup")
                self.assertIn("continue P-13", resume)
                self.assertIn("read it first", resume)
                _, data = self.jplan("next")
                self.assertEqual(data["recommended"], "P-13")
                takeover = self.start("P-13", "--dirty", "carry-on", "--branch", "stay", agent=second)
                self.assertEqual(takeover.returncode, 4)  # another holder needs explicit authorization
                takeover = self.start("P-13", "--takeover", "--dirty", "carry-on", "--branch", "stay", agent=second)
                self.assertEqual(takeover.returncode, 0, takeover.stdout + takeover.stderr)
                # Failure must leave the item and its claim available to the next agent.
                self.assertEqual(self.plan("done", "P-13", "--verify").returncode, 1)
                self.assertIn("- [ ] P-13", self.get(PLAN_PATH))
                self.put("result.txt", "done\n")
                self.assertEqual(self.plan("done", "P-13", "--verify").returncode, 0)
                os.remove(self.p("result.txt"))
                self.assertIn("- [x] P-13", self.get(PLAN_PATH))

    def test_saved_command_mismatch_does_not_execute_and_override_is_recorded(self):
        self.saved_plan()
        r, data = self.jplan("done", "P-13", "--verify", "touch bypass.txt")
        self.assertEqual(r.returncode, 4)
        self.assertEqual(data["context"]["saved_command"], "test -f result.txt")
        self.assertFalse(self.has("bypass.txt"))
        self.assertIn("- [ ] P-13", self.get(PLAN_PATH))
        r = self.plan("done", "P-13", "--verify", "true", "--override-reason", "User accepted a manual replacement")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("override: User accepted a manual replacement", self.get(PLAN_PATH))

    def test_no_saved_or_ambiguous_command_requires_explicit_choice(self):
        self.assertEqual(self.plan("done", "P-13", "--verify").returncode, 1)
        self.assertEqual(self.plan("done", "P-13", "--verify", "true").returncode, 4)
        self.put(PLAN_PATH, "## Now\n- [ ] P-13 Build · done means: `true` and `false`\n")
        self.assertEqual(self.plan("done", "P-13", "--verify").returncode, 1)

    TWO_PARTS = ("## Now\n- [ ] P-13 Build · done means: `test -f result.txt` passes and the note mentions `/compact`\n")

    def test_verify_accepts_any_backticked_part_without_an_override(self):
        self.put(PLAN_PATH, self.TWO_PARTS)
        self.put("result.txt", "done\n")
        r = self.plan("done", "P-13", "--verify", "test -f result.txt")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("override", self.get(PLAN_PATH))

    def test_bare_verify_with_several_parts_fails_and_lists_them(self):
        self.put(PLAN_PATH, self.TWO_PARTS)
        r = self.plan("done", "P-13", "--verify")
        self.assertEqual(r.returncode, 1)
        self.assertIn("`test -f result.txt`", r.stderr + r.stdout)
        self.assertIn("`/compact`", r.stderr + r.stdout)
        self.assertIn("--verify CMD", r.stderr + r.stdout)
        self.assertIn("- [ ] P-13", self.get(PLAN_PATH))

    def test_verify_ignores_extra_spaces_but_runs_the_typed_command(self):
        self.saved_plan()
        self.put("result.txt", "done\n")
        r = self.plan("done", "P-13", "--verify", "  test   -f    result.txt ")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("override", self.get(PLAN_PATH))

    def test_a_command_matching_no_part_still_asks_for_an_override(self):
        self.put(PLAN_PATH, self.TWO_PARTS)
        r, data = self.jplan("done", "P-13", "--verify", "touch bypass.txt")
        self.assertEqual(r.returncode, 4)
        self.assertEqual(data["context"]["saved_commands"], ["test -f result.txt", "/compact"])
        self.assertIsNone(data["context"]["saved_command"])
        self.assertFalse(self.has("bypass.txt"))

    def test_next_resumes_step_and_flags_completed_handoff(self):
        self.saved_plan()
        self.begin_task()
        path = STATUS + "/P-13.md"
        self.put(path, self.get(path) + "\n## Plan steps\n- [x] Inspect\n- [ ] Implement\n")
        _, data = self.jplan("next")
        self.assertEqual((data["recommended"], data["current"]["step"]), ("P-13", "Implement"))
        self.put("docs/project/HANDOFF.md", "# Handoff\nTask: P-14\n\n## Next action\nFinish P-14.\n")
        self.assertEqual(self.plan("done", "P-14", "--verify").returncode, 0)
        _, data = self.jplan("next")
        self.assertIn("completed work: P-14", data["handoff"]["warnings"][0])

    def test_codex_new_turn_invalidates_old_handoff_and_carries_request(self):
        self.saved_plan()
        self.begin_task()
        self.put("docs/project/HANDOFF.md", "# Handoff\nSession: c1\nTask: P-13\n")
        path = self.p("docs/project/HANDOFF.md")
        os.utime(path, (time.time() - 3600, time.time() - 3600))
        wrapup.write_sidecar(self.proj, "c1", path)
        self.put("codex.jsonl", json.dumps(codex_message("user", "Fix the next step")) + "\n")
        state = wrapup.handoff_state(path, self.p("codex.jsonl"), "c1", self.proj)
        self.assertTrue(state["stale"])
        self.event("codex", "pre-compact", "c1", transcript_path=self.p("codex.jsonl"))
        out = self.event("codex", "prompt-submit", "c1", prompt="wrap up")
        self.assertIn("Fix the next step", out)
        self.assertIn("Write the project's handoff", out)
        self.assertNotIn("Before the compact", self.event("codex", "prompt-submit", "c1", prompt="continue"))

    def test_codex_wrap_up_turn_is_not_later_work_and_injections_are_not_requests(self):
        rows = [codex_message("user", "Build it", "2026-11-08T01:00:00Z"),
                codex_message("user", "wrap up"), codex_message("assistant", "Handoff written"),
                codex_message("user", "<environment_context>injected</environment_context>")]
        self.put("codex.jsonl", "\n".join(json.dumps(r) for r in rows))
        self.assertEqual(sessions.latest_request(self.p("codex.jsonl"), "wrap up"), "Build it")
        # Neither the wrap-up turn nor an injected context block can stale its own note.
        self.assertEqual(sessions.last_turn_time(self.p("codex.jsonl"), "wrap up"),
                         sessions.parse_time("2026-11-08T01:00:00Z"))

    def test_installer_and_runtime_evidence_are_agent_specific(self):
        self.gw(["install-hooks", "--project"])
        hooks = json.loads(self.get(".codex/hooks.json"))["hooks"]
        self.assertIn("fork", hooks["SessionStart"][0]["matcher"])
        self.assertEqual(hooks["SessionEnd"][0]["hooks"][0]["timeout"], 3)
        self.event("codex", "session-start", "c1", source="fork")
        self.event("codex", "stop", "c1")
        data = json.loads(self.gw(["doctor", "--json"]).stdout)
        self.assertEqual(data["runtime"]["codex"]["session-start"]["status"], "observed")
        self.assertEqual(data["runtime"]["codex"]["plan-capture"]["status"], "unverified")
        self.assertEqual(data["runtime"]["claude-code"], {})
        self.begin_task()
        self.event("codex", "interrupt", "c1")
        self.event("codex", "session-end", "c1")
        journal = self.get(STATUS + "/journal/P-13.md")
        self.assertIn(" interrupt ", journal)
        self.assertIn(" session-end ", journal)

    def test_turn_started_alone_is_not_plan_capture_proof(self):
        self.put("codex.jsonl", json.dumps({"type": "event_msg", "payload": {"type": "task_started"}}))
        self.assertFalse(hook.codex_format_known(self.p("codex.jsonl")))

    def test_codex_session_lookup_uses_session_id_and_payload_cwd(self):
        import tempfile
        from unittest import mock
        with tempfile.TemporaryDirectory() as home:
            folder = os.path.join(home, "sessions", "2026", "11", "08")
            os.makedirs(folder)
            path = os.path.join(folder, "rollout-2026-11-08T17-15-00-codex-test.jsonl")
            with open(path, "w") as f:
                json.dump({"type": "session_meta", "payload": {"id": "codex-test", "cwd": self.proj}}, f)
            with mock.patch.dict(os.environ, {"CODEX_HOME": home}):
                self.assertEqual(sessions.find_transcript("codex-test"), path)
                self.assertEqual(sessions.transcript_cwd(path), self.proj)
                self.assertIsNone(sessions.find_transcript("../codex-test"))


if __name__ == "__main__":
    unittest.main()
