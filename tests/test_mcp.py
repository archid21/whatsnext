"""Tests for `whatsnext mcp`, the stdio MCP server (P-81).

Run: python3 -m unittest discover -s tests
"""

import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fixtures import SCRIPT, PlanBase  # noqa: E402

from wn import mcp  # noqa: E402


class Server(object):
    """One `whatsnext mcp` process, driven a line at a time."""

    def __init__(self, test):
        self.proc = subprocess.Popen([sys.executable, str(SCRIPT), "mcp"], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                     env=test.env, cwd=test.proj)
        test.addCleanup(self.close)
        self.next_id = 0

    def send(self, message):
        self.proc.stdin.write(json.dumps(message) + "\n")
        self.proc.stdin.flush()

    def request(self, method, params=None):
        self.next_id += 1
        message = {"jsonrpc": "2.0", "id": self.next_id, "method": method}
        if params is not None:
            message["params"] = params
        self.send(message)
        reply = json.loads(self.proc.stdout.readline())
        assert reply["id"] == self.next_id, reply
        return reply

    def call(self, name, arguments=None):
        return self.request("tools/call", {"name": name, "arguments": arguments or {}})["result"]

    def close(self):
        if self.proc.poll() is None:
            self.proc.stdin.close()
            self.proc.wait(timeout=10)
        self.proc.stdout.close()
        self.proc.stderr.close()


class McpServerTests(PlanBase):
    def setUp(self):
        super().setUp()
        self.server = Server(self)

    def init(self):
        reply = self.server.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                                   "clientInfo": {"name": "test", "version": "0"}})
        self.server.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return reply

    def test_initialize_names_the_server_and_tools_capability(self):
        result = self.init()["result"]
        self.assertEqual(result["protocolVersion"], "2025-06-18")
        self.assertEqual(result["serverInfo"]["name"], "whatsnext")
        self.assertIn("tools", result["capabilities"])

    def test_tools_list_has_the_five_typed_tools(self):
        self.init()
        tools = self.server.request("tools/list")["result"]["tools"]
        self.assertEqual([t["name"] for t in tools], ["status", "next", "start", "done", "wrap_up"])
        for tool in tools:
            self.assertEqual(tool["inputSchema"]["type"], "object")
        start = [t for t in tools if t["name"] == "start"][0]
        self.assertEqual(start["inputSchema"]["required"], ["id"])

    def test_status_and_next_return_the_command_json(self):
        self.init()
        status = self.server.call("status")
        self.assertFalse(status["isError"])
        self.assertIn("ready", status["structuredContent"])
        nxt = self.server.call("next", {"limit": 2})
        self.assertFalse(nxt["isError"])
        self.assertEqual(json.loads(nxt["content"][0]["text"]), nxt["structuredContent"])
        self.assertEqual(nxt["structuredContent"]["candidates"][0]["id"], "P-13")

    def test_start_asks_then_claims_and_done_checks_off(self):
        self.init()
        args = {"id": "P-13", "agent": "codex"}
        for _ in range(5):
            result = self.server.call("start", args)
            self.assertFalse(result["isError"], result)
            data = result["structuredContent"]
            if "ask" not in data:
                break
            # A question: answer with its recommended option, as an agent asks its user.
            args[data["answer_flag"].split()[0].lstrip("-").replace("-", "_")] = data["recommended"]
        self.assertTrue(self.has_claim("P-13"))
        done = self.server.call("done", {"id": "P-13", "evidence": "login tests pass"})
        self.assertFalse(done["isError"], done)
        self.assertIn("- [x] P-13", self.get("docs/project/PLAN.md"))

    def test_wrap_up_returns_the_handoff_instructions(self):
        self.init()
        result = self.server.call("wrap_up")
        self.assertFalse(result["isError"])
        self.assertIn("## Next action", result["content"][0]["text"])

    def test_bad_input_is_a_tool_error_and_runs_nothing(self):
        self.init()
        for args in ({"id": "--verify"}, {"id": "P-13", "verify_part": "rm -rf /\nx"}, {"id": "P-13", "shell": "x"}):
            result = self.server.call("done", args)
            self.assertTrue(result["isError"], args)
        self.assertIn("- [ ] P-13", self.get("docs/project/PLAN.md"))

    def test_unknown_tool_and_method_are_json_rpc_errors(self):
        self.init()
        self.assertEqual(self.server.request("tools/call", {"name": "exec"})["error"]["code"], -32602)
        self.assertEqual(self.server.request("resources/list")["error"]["code"], -32601)

    def test_it_exits_when_stdin_closes(self):
        self.init()
        self.server.proc.stdin.close()
        self.assertEqual(self.server.proc.wait(timeout=10), 0)


class ArgvTests(unittest.TestCase):
    """The argument lists are fixed: values never become options, verify never overrides."""

    def test_verify_runs_only_the_saved_command(self):
        self.assertEqual(mcp.build_argv("done", {"id": "P-1", "verify": True}), ["plan", "done", "P-1", "--json", "--verify"])
        argv = mcp.build_argv("done", {"id": "P-1", "verify_part": "make test"})
        self.assertEqual(argv[-1], "--verify=make test")
        self.assertNotIn("--override-reason", " ".join(argv))

    def test_start_cannot_set_the_done_means(self):
        # Setting done means here would let a tool caller pick the command `done --verify` runs.
        with self.assertRaises(mcp.ToolInputError):
            mcp.build_argv("start", {"id": "P-1", "done_means": "`rm -rf ~`"})

    def test_values_starting_with_a_dash_stay_values(self):
        argv = mcp.build_argv("start", {"id": "P-1", "agent": "--takeover"})
        self.assertIn("--agent=--takeover", argv)
        self.assertNotIn("--takeover", argv)


if __name__ == "__main__":
    unittest.main()
