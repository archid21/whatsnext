"""Tests for private text in progress files (`progress new` and `progress stamp`).

Run: python3 -m unittest discover -s tests
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fixtures import STATUS, StatusBase  # noqa: E402


SECRETS = {
    "AWS access key": "AKIA" + "ABCDEFGHIJKLMNOP",
    "GitHub token": "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8",
    "GitHub token (fine-grained)": "github_pat_" + "11ABCDEFG0abcdefghij_klmnop",
    "Anthropic API key": "sk-ant-" + "api03-abcdefghijklmnopqrstuv",
    "OpenAI-style API key": "sk-" + "abcdefghijklmnopqrstuvwx",
    "Slack token": "xoxb-" + "123456789012-abcdef",
    "private key block": "-----BEGIN RSA " + "PRIVATE KEY-----",
    "key, password or token assignment": "API_KEY = " + "hunter2hunter2",
}


class ProgressWriteTests(StatusBase):
    def test_private_title_is_removed_from_a_new_progress_file(self):
        r = self.gw(["progress", "new", "P-1", "--title", "Fix login <private>for ACME corp</private>"])
        self.assertEqual(r.returncode, 0, r.stderr)
        text = self.get(STATUS + "/P-1.md")
        self.assertTrue(text.startswith("format: 2\n\n# P-1: Fix login\n"))
        self.assertNotIn("ACME", text)

    def test_private_text_an_agent_wrote_is_removed_at_the_next_stamp(self):
        self.task()
        path = STATUS + "/P-13.md"
        self.put(path, self.get(path).replace("Run the login tests.", "Run the tests. <private>pw is x</private>"))
        r = self.gw(["progress", "stamp", "P-13"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Run the tests.", self.get(path))
        self.assertNotIn("pw is x", self.get(path))

    def test_secret_in_a_progress_file_warns_at_stamp_without_echo(self):
        self.task()
        path = STATUS + "/P-13.md"
        secret = SECRETS["Anthropic API key"]
        self.put(path, self.get(path).replace("Run the login tests.", "Key is " + secret))
        r = self.gw(["progress", "stamp", "P-13"])
        self.assertEqual(r.returncode, 0)
        self.assertIn("Anthropic API key", r.stderr)
        self.assertIn("P-13.md", r.stderr)
        self.assertNotIn(secret, r.stderr + r.stdout)
        self.assertIn(secret, self.get(path))

    def test_harmless_stamp_is_silent(self):
        self.task()
        self.assertEqual(self.gw(["progress", "stamp", "P-13"]).stderr, "")


if __name__ == "__main__":
    unittest.main()
