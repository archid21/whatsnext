"""Tests for the Gemini CLI and Cursor hook adapters (ADR-0027, P-77): `install-hooks --agent`, and
`hook <event> --agent gemini|cursor` on payloads shaped as the official docs show them.

Docs: https://geminicli.com/docs/hooks/reference/ and https://cursor.com/docs/hooks (see
docs/project/progress/P-77.md, "Hook events (from official docs)").

Run: python3 -m unittest discover -s tests
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fixtures import SCRIPT, STATUS, StatusBase  # noqa: E402

JOURNAL = STATUS + "/journal/P-13.md"

GEMINI_EVENTS = {"SessionStart": "session-start", "BeforeAgent": "prompt-submit", "AfterAgent": "stop",
                 "PreCompress": "pre-compact", "SessionEnd": "session-end"}
CURSOR_EVENTS = {"sessionStart": "session-start", "stop": "stop", "preCompact": "pre-compact",
                 "sessionEnd": "session-end"}  # no prompt event: beforeSubmitPrompt cannot add context
FILES = {"gemini": (".gemini", "settings.json", GEMINI_EVENTS), "cursor": (".cursor", "hooks.json", CURSOR_EVENTS)}


def own(handler, agent):
    return isinstance(handler.get("command"), str) and bool(
        re.search(r'whatsnext\.py"\s+hook\s+\S+\s+--agent\s+%s$' % agent, handler["command"]))


def handlers(data, agent):
    """Every handler under data['hooks'], for both shapes: Gemini's matcher groups and Cursor's flat lists."""
    out = []
    for event, items in data.get("hooks", {}).items():
        for item in items:
            out += [(event, h) for h in item["hooks"]] if "hooks" in item else [(event, item)]
    return out


class InstallBase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = os.path.realpath(tmp.name)
        self.home = os.path.join(base, "home")
        self.proj = os.path.join(base, "proj")
        os.makedirs(self.home)
        os.makedirs(os.path.join(self.proj, ".git"))  # find_root: a folder with .git is a project root
        self.env = dict(os.environ, HOME=self.home, XDG_CONFIG_HOME=os.path.join(base, "xdg"))
        for key in ("CODEX_HOME", "WHATSNEXT_AGENT", "GROUNDWORK_AGENT"):
            self.env.pop(key, None)

    def run_hooks(self, *args, cwd=None):
        return subprocess.run([sys.executable, str(SCRIPT), "install-hooks", "--wn", "skip"] + list(args), env=self.env,
                              cwd=cwd or self.proj, capture_output=True, text=True)

    def user_file(self, agent):
        folder, name, _events = FILES[agent]
        return os.path.join(self.home, folder, name)

    def read(self, path):
        return json.loads(self.text(path))

    def text(self, path):
        with open(path, encoding="utf-8") as f:
            return f.read()

    def put(self, path, data):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")


class InstallTests(InstallBase):
    def each(self):
        for agent in FILES:
            with self.subTest(agent=agent):
                self.setUp()  # a fresh sandbox per agent
                yield agent

    def test_dry_run_prints_the_diff_and_writes_nothing(self):
        for agent in self.each():
            os.makedirs(os.path.join(self.home, FILES[agent][0]))
            r = self.run_hooks("--agent", agent, "--dry-run")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("--agent %s" % agent, r.stdout)
            self.assertIn("Dry run: nothing written.", r.stdout)
            self.assertFalse(os.path.exists(self.user_file(agent)))
            self.assertFalse(os.path.lexists(os.path.join(self.home, ".agents")))

    def test_install_writes_the_documented_file_with_one_entry_per_mapped_event(self):
        for agent in self.each():
            os.makedirs(os.path.join(self.home, FILES[agent][0]))
            r = self.run_hooks("--agent", agent)
            self.assertEqual(r.returncode, 0, r.stderr)
            data = self.read(self.user_file(agent))
            events = FILES[agent][2]
            self.assertEqual(sorted(data["hooks"]), sorted(events))
            found = handlers(data, agent)
            self.assertEqual(len(found), len(events))
            for event, handler in found:
                self.assertTrue(own(handler, agent), handler)
                self.assertEqual(handler["type"], "command")
                self.assertTrue(handler["command"].startswith("python3 "))
                self.assertTrue(handler["command"].endswith("hook %s --agent %s" % (events[event], agent)))

    def test_gemini_shape_is_matcher_groups_with_millisecond_timeouts(self):
        os.makedirs(os.path.join(self.home, ".gemini"))
        self.run_hooks("--agent", "gemini")
        data = self.read(self.user_file("gemini"))
        group = data["hooks"]["BeforeAgent"][0]
        self.assertEqual(group["matcher"], "*")
        handler = group["hooks"][0]
        self.assertEqual((handler["name"], handler["timeout"]), ("whatsnext-prompt-submit", 10000))
        self.assertEqual(data["hooks"]["SessionEnd"][0]["hooks"][0]["timeout"], 3000)
        self.assertNotIn("version", data)

    def test_cursor_shape_is_version_one_and_flat_handler_lists_with_second_timeouts(self):
        os.makedirs(os.path.join(self.home, ".cursor"))
        self.run_hooks("--agent", "cursor")
        data = self.read(self.user_file("cursor"))
        self.assertEqual(list(data)[0], "version")
        self.assertEqual(data["version"], 1)
        self.assertEqual(data["hooks"]["stop"][0]["timeout"], 10)
        self.assertEqual(data["hooks"]["sessionEnd"][0]["timeout"], 3)
        self.assertNotIn("beforeSubmitPrompt", data["hooks"])  # a documented gap: it cannot add context

    def test_reinstall_changes_nothing(self):
        for agent in self.each():
            os.makedirs(os.path.join(self.home, FILES[agent][0]))
            self.run_hooks("--agent", agent)
            first = self.text(self.user_file(agent))
            r = self.run_hooks("--agent", agent)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("already installed", r.stdout)
            self.assertEqual(self.text(self.user_file(agent)), first)

    def test_a_moved_checkout_replaces_its_own_entries_not_adds_more(self):
        for agent in self.each():
            os.makedirs(os.path.join(self.home, FILES[agent][0]))
            self.run_hooks("--agent", agent)
            path = self.user_file(agent)
            data = self.read(path)
            for _event, handler in handlers(data, agent):
                handler["command"] = handler["command"].replace('python3 "', 'python3 "/old/place/..', 1)
            self.put(path, data)
            self.run_hooks("--agent", agent)
            found = handlers(self.read(path), agent)
            self.assertEqual(len(found), len(FILES[agent][2]))
            self.assertTrue(all("/old/place" not in h["command"] for _e, h in found))

    def test_foreign_entries_and_keys_are_kept_and_undo_removes_only_ours(self):
        foreign_gemini = {"theme": "dark", "hooks": {
            "AfterTool": [{"matcher": "write_file", "hooks": [{"type": "command", "command": "./audit.sh"}]}],
            "SessionStart": [{"matcher": "startup", "hooks": [{"type": "command", "command": "./mine.sh"}]}]}}
        foreign_cursor = {"version": 1, "hooks": {
            "beforeShellExecution": [{"command": "./audit.sh"}],
            "sessionStart": [{"command": "./mine.sh"}],
            "stop": [{"command": "python3 other.py hook stop --agent codex"}]}}  # another agent's name is not ours
        for agent, original in (("gemini", foreign_gemini), ("cursor", foreign_cursor)):
            with self.subTest(agent=agent):
                self.setUp()
                self.put(self.user_file(agent), original)
                r = self.run_hooks("--agent", agent)
                self.assertEqual(r.returncode, 0, r.stderr)
                data = self.read(self.user_file(agent))
                self.assertEqual(len(handlers(data, agent)), len(handlers(original, agent)) + len(FILES[agent][2]))
                self.assertIn("./mine.sh", json.dumps(data))
                self.assertIn("./audit.sh", json.dumps(data))
                r = self.run_hooks("--agent", agent, "--undo")
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(self.read(self.user_file(agent)), original)

    def test_remove_is_the_same_as_undo_and_a_dry_run_undo_writes_nothing(self):
        for agent in self.each():
            os.makedirs(os.path.join(self.home, FILES[agent][0]))
            self.run_hooks("--agent", agent)
            before = self.text(self.user_file(agent))
            r = self.run_hooks("--agent", agent, "--undo", "--dry-run")
            self.assertIn("Remove whatsnext hooks", r.stdout)
            self.assertEqual(self.text(self.user_file(agent)), before)
            self.run_hooks("--agent", agent, "--remove")
            self.assertFalse(os.path.exists(self.user_file(agent)))  # nothing else was in it
            self.assertTrue(os.path.isdir(os.path.join(self.home, FILES[agent][0])))  # the user's folder stays

    def test_project_scope_writes_in_the_repo_and_undo_removes_the_empty_folder(self):
        for agent in self.each():
            folder, name, events = FILES[agent]
            r = self.run_hooks("--agent", agent, "--project")
            self.assertEqual(r.returncode, 0, r.stderr)
            path = os.path.join(self.proj, folder, name)
            self.assertEqual(len(handlers(self.read(path), agent)), len(events))
            self.assertFalse(os.path.exists(os.path.join(self.home, folder)))
            self.run_hooks("--agent", agent, "--project", "--undo")
            self.assertFalse(os.path.exists(os.path.join(self.proj, folder)))

    def test_a_missing_agent_folder_is_a_note_not_a_file(self):
        for agent in self.each():
            r = self.run_hooks("--agent", agent)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("folder not found", r.stdout)
            self.assertFalse(os.path.exists(os.path.join(self.home, FILES[agent][0])))
            self.assertFalse(os.path.lexists(os.path.join(self.home, ".agents")))

    def test_the_wn_link_is_still_offered_without_the_agent_folder(self):
        for agent in self.each():
            r = subprocess.run([sys.executable, str(SCRIPT), "install-hooks", "--agent", agent, "--wn", "link"],
                               env=self.env, cwd=self.proj, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(os.path.islink(os.path.join(self.home, ".local", "bin", "wn")))

    def test_invalid_json_is_reported_and_left_alone(self):
        for agent in self.each():
            path = self.user_file(agent)
            os.makedirs(os.path.dirname(path))
            with open(path, "w", encoding="utf-8") as f:
                f.write("{ // a comment\n}\n")
            r = self.run_hooks("--agent", agent)
            self.assertEqual(r.returncode, 1)
            self.assertIn("not valid JSON", r.stderr)
            self.assertEqual(self.text(path), "{ // a comment\n}\n")

    def test_codex_stays_the_default_and_its_file_is_unchanged_by_the_other_agents(self):
        os.makedirs(os.path.join(self.home, ".codex"))
        os.makedirs(os.path.join(self.home, ".gemini"))
        self.run_hooks()
        default = self.text(os.path.join(self.home, ".codex", "hooks.json"))
        self.run_hooks("--agent", "gemini")
        self.run_hooks("--agent", "gemini", "--undo")
        self.assertEqual(self.text(os.path.join(self.home, ".codex", "hooks.json")), default)
        self.run_hooks("--agent", "codex")
        self.assertEqual(self.text(os.path.join(self.home, ".codex", "hooks.json")), default)
        self.assertEqual(len(handlers(json.loads(default), "codex")), 7)
        self.assertFalse(os.path.exists(os.path.join(self.home, ".gemini", "settings.json")))

    def test_an_unknown_agent_is_refused(self):
        r = self.run_hooks("--agent", "emacs")
        self.assertEqual(r.returncode, 2)


# ---- hook payloads, shaped as the docs show them -----------------------------------------------------


def gemini_payload(event, **extra):
    """The base fields every Gemini CLI hook gets (https://geminicli.com/docs/hooks/reference/) plus the event's own."""
    return dict({"session_id": "gem-1", "transcript_path": "/nonexistent/chats/session-gem-1.json", "cwd": None,
                 "hook_event_name": event, "timestamp": "2026-11-16T19:04:05.000Z"}, **extra)


def cursor_payload(event, **extra):
    """The common fields every Cursor hook gets (https://cursor.com/docs/hooks): no `cwd`, `conversation_id` as the id."""
    return dict({"conversation_id": "cur-1", "generation_id": "gen-1", "model": "default", "hook_event_name": event,
                 "cursor_version": "2.0.0", "workspace_roots": [], "user_email": None, "transcript_path": None}, **extra)


class AdapterBase(StatusBase):
    def run_hook(self, event, agent, data, cwd=None):
        r = self.gw(["hook", event, "--agent", agent], stdin=json.dumps(data), cwd=cwd)
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        return r.stdout

    def journal_events(self):
        if not self.has(JOURNAL):
            return []
        return [line.split()[2] for line in self.get(JOURNAL).splitlines() if line.startswith("- ")]

    def gemini(self, event, wn_event, **extra):
        return self.run_hook(wn_event, "gemini", gemini_payload(event, cwd=self.proj, **extra))

    def cursor(self, event, wn_event, **extra):
        return self.run_hook(wn_event, "cursor", cursor_payload(event, workspace_roots=[self.proj], **extra))


class GeminiHookTests(AdapterBase):
    def setUp(self):
        super().setUp()
        self.task()
        self.commit("add task")

    def test_session_start_returns_json_with_the_note_as_additional_context(self):
        out = json.loads(self.gemini("SessionStart", "session-start", source="startup"))
        body = out["hookSpecificOutput"]
        self.assertEqual(body["hookEventName"], "SessionStart")
        self.assertTrue(body["additionalContext"].startswith(self.packet()["text"].rstrip("\n")))
        self.assertIn("whatsnext command: WHATSNEXT_AGENT=gemini python3", body["additionalContext"])
        self.assertIn("--session gem-1", body["additionalContext"])
        self.assertIn("Next: Run the login tests.", out["systemMessage"])

    def test_session_start_after_clear_and_resume_give_the_same_shape(self):
        for source in ("resume", "clear"):
            out = json.loads(self.gemini("SessionStart", "session-start", source=source))
            self.assertIn("additionalContext", out["hookSpecificOutput"])

    def test_prompt_adds_nothing_for_an_ordinary_prompt(self):
        self.assertEqual(self.gemini("BeforeAgent", "prompt-submit", prompt="Refactor the auth module."), "")

    def test_prompt_wrap_up_returns_the_handoff_instructions_as_additional_context(self):
        out = json.loads(self.gemini("BeforeAgent", "prompt-submit", prompt="wrap up"))
        body = out["hookSpecificOutput"]
        self.assertEqual(body["hookEventName"], "BeforeAgent")
        text = body["additionalContext"]
        self.assertIn("the user typed `wrap up`", text)
        self.assertIn("## Next action", text)
        self.assertIn("Session: gem-1", text)
        self.assertIn("Handoff written: ", text)
        self.assertNotIn("Choose above the prompt", text)  # a Claude Code UI line
        self.assertNotIn("/compact", text)  # Gemini's command is /compress; no hook carries a handoff into it
        self.assertTrue(any(n.startswith("gem-1") for n in os.listdir(self.p(".whatsnext/sessions"))))  # the request marker

    def test_turn_end_prints_nothing_and_writes_the_facts(self):
        out = self.gemini("AfterAgent", "stop", prompt="Summarize the changelog.", prompt_response="Done.",
                          stop_hook_active=False)
        self.assertEqual(out, "")
        self.assertEqual(self.journal_events(), ["stop"])
        self.assertTrue(self.has(".whatsnext/sessions/gem-1.json"))

    def test_before_compact_prints_nothing_records_the_fact_and_the_next_prompt_shows_the_note_once(self):
        self.assertEqual(self.gemini("PreCompress", "pre-compact", trigger="auto"), "")
        self.assertEqual(self.journal_events(), ["pre-compact"])
        self.assertTrue(self.has(".whatsnext/sessions/gem-1.resume.json"))
        first = json.loads(self.gemini("BeforeAgent", "prompt-submit", prompt="go on"))
        text = first["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Context was compacted", text)
        self.assertIn("WHATSNEXT_AGENT=gemini", text)
        self.assertFalse(self.has(".whatsnext/sessions/gem-1.resume.json"))
        self.assertEqual(self.gemini("BeforeAgent", "prompt-submit", prompt="and then"), "")

    def test_session_end_prints_nothing_and_writes_the_facts(self):
        self.assertEqual(self.gemini("SessionEnd", "session-end", reason="exit"), "")
        self.assertEqual(self.journal_events(), ["session-end"])

    def test_an_unreadable_transcript_still_gives_facts(self):
        self.assertEqual(self.gemini("PreCompress", "pre-compact", trigger="manual",
                                     transcript_path="/nonexistent/x.json"), "")
        self.assertEqual(self.gemini("AfterAgent", "stop", prompt="p", prompt_response="r", stop_hook_active=False), "")
        self.assertEqual(self.journal_events(), ["pre-compact", "stop"])

    def test_silent_outside_a_project_and_on_bad_input(self):
        other = os.path.join(self.tmp.name, "other")
        os.makedirs(other)
        out = self.run_hook("session-start", "gemini", gemini_payload("SessionStart", cwd=other, source="startup"),
                            cwd=other)
        self.assertEqual(out, "")
        r = self.gw(["hook", "session-start", "--agent", "gemini"], stdin="not json")
        self.assertEqual((r.returncode, r.stdout), (0, ""))


class CursorHookTests(AdapterBase):
    def setUp(self):
        super().setUp()
        self.task()
        self.commit("add task")

    def test_session_start_returns_additional_context_json_and_nothing_else(self):
        out = json.loads(self.cursor("sessionStart", "session-start", session_id="cur-1", is_background_agent=False,
                                     composer_mode="agent"))
        self.assertEqual(list(out), ["additional_context"])
        self.assertTrue(out["additional_context"].startswith(self.packet()["text"].rstrip("\n")))
        self.assertIn("whatsnext command: WHATSNEXT_AGENT=cursor python3", out["additional_context"])
        self.assertIn("--session cur-1", out["additional_context"])

    def test_the_first_run_welcome_is_not_spent_on_cursor(self):
        marker = os.path.join(self.xdg, "whatsnext", "welcomed")
        os.remove(marker)
        out = json.loads(self.cursor("sessionStart", "session-start", session_id="cur-1", is_background_agent=False))
        self.assertEqual(list(out), ["additional_context"])
        self.assertFalse(os.path.exists(marker))

    def test_project_is_found_from_workspace_roots_when_the_hook_runs_elsewhere(self):
        other = os.path.join(self.tmp.name, "elsewhere")
        os.makedirs(other)
        data = cursor_payload("sessionStart", workspace_roots=[other, self.proj], session_id="cur-1",
                              is_background_agent=False)
        out = json.loads(self.run_hook("session-start", "cursor", data, cwd=other))
        self.assertIn("Next: Run the login tests.", out["additional_context"])

    def test_prompt_is_a_documented_gap_no_output_and_no_marker_even_for_wrap_up(self):
        out = self.cursor("beforeSubmitPrompt", "prompt-submit", prompt="wrap up", attachments=[])
        self.assertEqual(out, "")
        sessions = self.p(".whatsnext/sessions")
        self.assertEqual([n for n in os.listdir(sessions) if n.startswith("cur-1")] if os.path.isdir(sessions) else [], [])

    def test_turn_end_prints_nothing_and_writes_the_facts_under_the_conversation_id(self):
        self.assertEqual(self.cursor("stop", "stop", status="completed", loop_count=0), "")
        self.assertEqual(self.journal_events(), ["stop"])
        self.assertTrue(self.has(".whatsnext/sessions/cur-1.json"))

    def test_an_aborted_turn_is_still_recorded(self):
        self.assertEqual(self.cursor("stop", "stop", status="aborted", loop_count=0), "")
        self.assertEqual(self.journal_events(), ["stop"])

    def test_before_compact_prints_nothing_and_leaves_no_resume_marker(self):
        out = self.cursor("preCompact", "pre-compact", trigger="auto", context_usage_percent=85, context_tokens=120000,
                          context_window_size=128000, message_count=45, messages_to_compact=30,
                          is_first_compaction=True)
        self.assertEqual(out, "")
        self.assertEqual(self.journal_events(), ["pre-compact"])
        self.assertFalse(self.has(".whatsnext/sessions/cur-1.resume.json"))

    def test_session_end_prints_nothing_and_writes_the_facts(self):
        out = self.cursor("sessionEnd", "session-end", session_id="cur-1", reason="user_close", duration_ms=45000,
                          is_background_agent=False, final_status="completed")
        self.assertEqual(out, "")
        self.assertEqual(self.journal_events(), ["session-end"])

    def test_a_null_transcript_path_does_not_break_pre_compact(self):
        self.assertEqual(self.cursor("preCompact", "pre-compact", trigger="manual", transcript_path=None), "")

    def test_silent_outside_a_project(self):
        other = os.path.join(self.tmp.name, "other")
        os.makedirs(other)
        data = cursor_payload("sessionStart", workspace_roots=[other], session_id="c", is_background_agent=False)
        self.assertEqual(self.run_hook("session-start", "cursor", data, cwd=other), "")


class UnchangedTests(AdapterBase):
    """The existing agents keep their output shape."""

    def setUp(self):
        super().setUp()
        self.task()

    def test_codex_session_start_is_still_plain_text_naming_codex(self):
        out = self.run_hook("session-start", "codex", {"source": "startup", "cwd": self.proj, "session_id": "s1"})
        self.assertFalse(out.startswith("{"))
        self.assertIn("WHATSNEXT_AGENT=codex python3", out)

    def test_claude_code_session_start_is_still_json_without_a_command_line(self):
        out = json.loads(self.run_hook("session-start", "claude-code", {"source": "startup", "cwd": self.proj}))
        self.assertNotIn("whatsnext command:", out["hookSpecificOutput"]["additionalContext"])


if __name__ == "__main__":
    unittest.main()
