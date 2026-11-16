"""Tests for the drift note (ADR-0028, P-73): one note when a turn changes files outside the claimed item's scope.

Run: python3 -m unittest discover -s tests
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fixtures import STATUS  # noqa: E402
from test_wrapup import HookBase  # noqa: E402

from wn import claims as wnclaims  # noqa: E402

SID = "s1"


class DriftBase(HookBase):
    def setUp(self):
        super().setUp()
        self.cfg()
        self.task()
        self.commit("task")
        wnclaims.claim(self.proj, "P-13", "claude-code", session=SID)

    def turn(self, *names, session=SID, agent="claude-code"):
        """Change files, then end the turn. Returns the Stop hook's stdout."""
        for name in names:
            self.put(name, "x %s\n" % self.clock)
            self.clock += 1
        r = self.gw(["hook", "stop", "--agent", agent],
                    stdin=json.dumps({"session_id": session, "cwd": self.proj}))
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        return r.stdout

    def learn(self):
        self.turn("src/a.py")
        self.turn("src/b.py")
        self.turn("lib/c.py")

    def state(self, session=SID):
        path = self.p(".whatsnext/sessions/%s.drift.json" % session)
        if not os.path.exists(path):
            return {}
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def pending(self, session=SID):
        return self.state(session).get("pending")

    def status(self, session=SID):
        env = dict(self.env, WHATSNEXT_SESSION=session)
        import subprocess
        import sys as _sys
        from fixtures import SCRIPT
        text = subprocess.run([_sys.executable, str(SCRIPT), "status"], capture_output=True, text=True, env=env,
                              cwd=self.proj).stdout
        data = subprocess.run([_sys.executable, str(SCRIPT), "status", "--json"], capture_output=True, text=True,
                              env=env, cwd=self.proj).stdout
        return text, json.loads(data)["warnings"]


class ScopeTests(DriftBase):
    def test_first_three_file_turns_learn_the_folders_and_never_note(self):
        self.learn()
        self.assertIsNone(self.pending())
        item = self.state()["items"]["P-13"]
        self.assertEqual(item["turns"], 3)
        self.assertEqual(sorted(item["folders"]), ["lib", "src"])

    def test_a_turn_with_no_file_change_is_not_a_learning_turn(self):
        self.turn()
        self.turn()
        self.turn("src/a.py")
        self.assertEqual(self.state()["items"]["P-13"]["turns"], 1)

    def test_folder_matching_in_a_listed_folder_or_under_it(self):
        self.learn()
        self.turn("src/deep/er/d.py", "lib/e.py")
        self.assertIsNone(self.pending())  # src and lib hold both: under a listed folder, and in one

    def test_a_file_outside_every_learned_folder_gives_the_note(self):
        self.learn()
        out = self.turn("tools/x.py")
        self.assertEqual(out, "")  # Claude Code shows it on the band, not as hook output
        pending = self.pending()
        self.assertEqual(pending["item"], "P-13")
        self.assertEqual(pending["files"], ["tools/x.py"])
        self.assertEqual(pending["text"], "1 file changed outside P-13 (tools/x.py). Add them to P-13 "
                         "(`progress stamp P-13 --files …`), or plan them as new work?")

    def test_the_note_lists_three_names_then_an_ellipsis(self):
        self.learn()
        self.turn("a1/a.py", "a2/b.py", "a3/c.py", "a4/d.py")
        text = self.pending()["text"]
        self.assertTrue(text.startswith("4 files changed outside P-13 (a1/a.py, a2/b.py, a3/c.py, …)."), text)

    def test_the_files_line_replaces_learning_and_checks_from_the_first_turn(self):
        self.task(files="src/a.py, docs/")
        self.commit("files")
        out = self.turn("src/z.py")  # in src, the folder of a listed file
        self.assertIsNone(self.pending())
        self.turn("docs/g.md")  # under a listed folder
        self.assertIsNone(self.pending())
        self.turn("other/q.py")
        self.assertEqual(self.pending()["files"], ["other/q.py"])
        self.assertEqual(out, "")

    def test_files_under_docs_project_never_count(self):
        self.learn()
        self.turn("docs/project/notes/new.md", "docs/project/handoffs/h.md")
        self.assertIsNone(self.pending())

    def test_a_root_file_does_not_put_every_folder_in_scope(self):
        self.turn("setup.py")
        self.turn("setup.cfg")
        self.turn("tox.ini")
        self.turn("src/x.py")
        self.assertEqual(self.pending()["files"], ["src/x.py"])


class NoteOnceTests(DriftBase):
    def test_the_same_file_is_noted_once_and_a_new_file_notes_again(self):
        self.learn()
        self.turn("tools/x.py")
        first = self.pending()
        self.turn("tools/x.py", "src/ok.py")  # the same out-of-scope file, edited again
        self.assertEqual(self.pending(), first)
        self.assertEqual(self.state()["items"]["P-13"]["noted"], ["tools/x.py"])
        self.turn("scripts/y.py")
        self.assertEqual(self.pending()["files"], ["scripts/y.py"])
        self.assertEqual(self.state()["items"]["P-13"]["noted"], ["tools/x.py", "scripts/y.py"])

    def test_codex_and_gemini_print_a_system_message_and_never_block(self):
        for agent in ("codex", "gemini"):
            self.setUp()
            self.learn()
            out = self.turn("tools/x.py", agent=agent)
            payload = json.loads(out)
            self.assertEqual(list(payload), ["systemMessage"])
            self.assertIn("1 file changed outside P-13 (tools/x.py)", payload["systemMessage"])
            self.assertNotIn("block", out)
            self.assertEqual(self.turn(agent=agent), "")  # nothing new: no second note

    def test_cursor_prints_nothing_but_status_shows_the_note(self):
        self.learn()
        self.assertEqual(self.turn("tools/x.py", agent="cursor"), "")
        self.assertIsNotNone(self.pending())

    def test_never_a_block_and_plan_md_untouched(self):
        self.put("docs/project/PLAN.md", "# Plan\n\n## Now\n- [ ] P-13 Add login · done means: x\n")
        self.commit("plan")
        before = self.get("docs/project/PLAN.md")
        self.learn()
        out = self.turn("tools/x.py")
        self.assertNotIn("block", out)
        self.assertEqual(self.get("docs/project/PLAN.md"), before)

    def test_driftnote_off_gives_no_note_and_no_state(self):
        self.cfg(plan={"driftNote": "off"})
        self.learn()
        self.turn("tools/x.py")
        self.assertEqual(self.state(), {})

    def test_no_claimed_item_means_no_check(self):
        wnclaims.release(self.proj, "P-13")
        self.learn()
        self.turn("tools/x.py")
        self.assertEqual(self.state(), {})

    def test_another_sessions_claim_is_not_checked(self):
        self.learn()
        self.turn("tools/x.py", session="s2")
        self.assertEqual(self.state("s2"), {})
        self.assertIsNone(self.pending())

    def test_a_broken_state_file_gives_no_note_and_no_error(self):
        self.learn()
        self.put(".whatsnext/sessions/%s.drift.json" % SID, "{not json")
        self.turn("tools/x.py")  # asserts exit 0 and empty stderr

    def test_the_session_file_is_pruned_with_its_session(self):
        from wn import journal as wnjournal
        self.assertIsNotNone(wnjournal.SESSION_FILE_RE.match("s1.drift.json"))


class AnswerTests(DriftBase):
    def drifted(self):
        self.learn()
        self.turn("tools/x.py")
        self.assertIsNotNone(self.pending())

    def test_status_shows_the_note_until_it_is_answered(self):
        self.assertEqual(self.status()[1], [])
        self.drifted()
        text, warnings = self.status()
        note = self.pending()["text"]
        self.assertIn(note, warnings)
        self.assertIn("Warning: " + note, text)
        self.assertEqual(self.status("other-session")[1], [])  # another session does not see it

    def test_stamp_with_files_clears_the_note_and_sets_the_scope(self):
        self.drifted()
        r = self.gw(["progress", "stamp", "P-13", "--files", "src/a.py,tools/x.py"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIsNone(self.pending())
        self.assertEqual(self.status()[1], [])
        self.assertIn("- **Files:** src/a.py, tools/x.py", self.get("%s/P-13.md" % STATUS))
        self.turn("tools/more.py")  # tools is now in scope
        self.assertIsNone(self.pending())
        self.turn("elsewhere/z.py")
        self.assertEqual(self.pending()["files"], ["elsewhere/z.py"])

    def test_stamp_without_files_keeps_the_note(self):
        self.drifted()
        self.gw(["progress", "stamp", "P-13"])
        self.assertIsNotNone(self.pending())

    def test_dismiss_clears_the_note_and_the_files_are_not_noted_again(self):
        self.drifted()
        r = self.gw(["progress", "drift-dismiss", "--session", SID])
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "dismissed the drift note"))
        self.assertIsNone(self.pending())
        self.assertEqual(self.status()[1], [])
        self.assertEqual(self.state()["items"]["P-13"]["dismissed"], ["tools/x.py"])
        self.turn("tools/x.py")
        self.assertIsNone(self.pending())
        self.turn("tools/y.py")
        self.assertEqual(self.pending()["files"], ["tools/y.py"])

    def test_dismiss_with_nothing_pending_is_quiet(self):
        r = self.gw(["progress", "drift-dismiss", "--session", SID])
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "no drift note to dismiss"))


if __name__ == "__main__":
    unittest.main()
