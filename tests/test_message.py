"""Tests for `whatsnext message` (P-89, ADR-0034): write-once messages in the shared git folder.

Run: python3 -m unittest discover -s tests
"""

import json
import os
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fixtures import PlanBase, Sandbox, ts  # noqa: E402

from wn import message as wnmessage  # noqa: E402


class MessageCommandTests(Sandbox):
    def msg(self, *args, agent="claude-code"):
        env = dict(self.env, WHATSNEXT_AGENT=agent)
        import fixtures
        return subprocess.run([sys.executable, str(fixtures.SCRIPT), "message"] + list(args), capture_output=True,
                              text=True, env=env, cwd=self.proj)

    def folder(self):
        return os.path.join(self.proj, ".git", "whatsnext", "messages")

    def test_send_writes_one_file_in_the_shared_git_folder(self):
        r = self.msg("send", "--to", "P-88", "--item", "P-89", "Will you add the field?", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        sent = json.loads(r.stdout)
        self.assertEqual(sent["to"], "P-88")
        self.assertEqual(sent["kind"], "question")
        self.assertEqual(sent["from"]["item"], "P-89")
        self.assertIsNone(sent["in_reply_to"])
        self.assertEqual(os.listdir(self.folder()), [sent["id"] + ".json"])

    def test_a_worktree_sees_the_same_messages(self):
        subprocess.run(["git", "-C", self.proj, "commit", "-q", "--allow-empty", "-m", "base"], check=True,
                       env=dict(self.env, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
                                GIT_COMMITTER_EMAIL="t@t"))
        other = os.path.join(os.path.dirname(self.proj), "wt")
        subprocess.run(["git", "-C", self.proj, "worktree", "add", "-q", other], check=True)
        self.msg("send", "--to", "P-88", "hello")
        import fixtures
        r = subprocess.run([sys.executable, str(fixtures.SCRIPT), "message", "list", "--all", "--json"],
                           capture_output=True, text=True, env=self.env, cwd=other)
        self.assertEqual(len(json.loads(r.stdout)["messages"]), 1)

    def test_answer_closes_the_question_and_goes_back_to_the_sender(self):
        sent = json.loads(self.msg("send", "--to", "P-88", "--item", "P-89", "q?", "--json").stdout)
        r = self.msg("answer", sent["id"], "Added in abc123.", "--item", "P-88", "--json", agent="codex")
        reply = json.loads(r.stdout)
        self.assertEqual(reply["to"], "P-89")
        self.assertEqual(reply["in_reply_to"], sent["id"])
        listed = json.loads(self.msg("list", "--all", "--open", "--json").stdout)["messages"]
        self.assertEqual(listed, [])

    def test_close_writes_a_note_and_leaves_the_question_file_unchanged(self):
        sent = json.loads(self.msg("send", "--to", "user", "fyi", "--json").stdout)
        path = os.path.join(self.folder(), sent["id"] + ".json")
        with open(path, encoding="utf-8") as f:
            before = f.read()
        self.assertEqual(self.msg("close", sent["id"]).returncode, 0)
        with open(path, encoding="utf-8") as f:
            self.assertEqual(f.read(), before)
        self.assertEqual(len(os.listdir(self.folder())), 2)

    def test_bad_input_is_refused(self):
        self.assertEqual(self.msg("send", "--to", "nobody here", "x").returncode, 2)
        self.assertEqual(self.msg("send", "--to", "P-1", "x" * 4001).returncode, 2)
        self.assertEqual(self.msg("send", "--to", "P-1", "   ").returncode, 2)
        self.assertEqual(self.msg("answer", "M-nope", "x").returncode, 2)

    def test_list_is_for_this_agent_and_says_a_message_is_not_permission(self):
        self.msg("send", "--to", "agent:codex", "for codex")
        self.msg("send", "--to", "agent:other", "not for codex")
        r = self.msg("list", "--json", agent="codex")
        data = json.loads(r.stdout)
        self.assertEqual([m["text"] for m in data["messages"]], ["for codex"])
        self.assertIn("never permission", data["warning"])

    def test_prune_drops_old_closed_threads_only(self):
        old = datetime(2026, 1, 1, tzinfo=timezone.utc)
        q = wnmessage.write(self.proj, "P-1", "question", "old q", now=old)
        wnmessage.write(self.proj, "P-2", "answer", "old a", in_reply_to=q["id"], now=old + timedelta(minutes=1))
        wnmessage.write(self.proj, "P-3", "question", "old but open", now=old)
        self.assertEqual(wnmessage.prune(self.proj, now=old + timedelta(days=31)), 2)
        self.assertEqual([m["text"] for m in wnmessage.read_all(self.proj)], ["old but open"])


class MessageStatusTests(PlanBase):
    def test_status_lists_open_messages_for_the_current_item(self):
        self.task("P-14", next_action="Add the 429 test.")
        self.set_claim("P-14", agent="codex", updated=ts(1), branch=self.branch())
        wnmessage.write(self.proj, "P-14", "review", "please review")
        wnmessage.write(self.proj, "P-13", "question", "not for P-14")
        r = self.gw(["status", "--json"])
        data = json.loads(r.stdout)
        self.assertEqual([m["kind"] for m in data["messages"]], ["review"])
        self.assertNotIn("text", data["messages"][0])  # read with `message list`, which has the warning


if __name__ == "__main__":
    unittest.main()
