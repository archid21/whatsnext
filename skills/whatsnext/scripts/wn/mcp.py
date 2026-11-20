"""`whatsnext mcp`: a stdio MCP server for agents with no shell (P-81).

Newline-delimited JSON-RPC 2.0 on stdin/stdout. Five typed tools wrap the
existing commands: status, next, start, done and wrap_up. Each tool call runs
`whatsnext.py` with a fixed argument list built from the typed input, so the
server adds no plan logic of its own and never runs an arbitrary command:
`done` with `verify` runs only the item's own done-means command, which the
CLI enforces (no `--override-reason` is ever passed). The server exits when
stdin closes, so it ends with the agent's session.
"""

import json
import os
import re
import subprocess
import sys

PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "whatsnext.py")
ID_PATTERN = r"^[A-Za-z][A-Za-z0-9]*-[0-9]+$"
# Exit codes the CLI uses for a normal answer: 0 done, 4 a question to ask the user.
OK_EXITS = (0, 4)

TOOLS = [
    {
        "name": "status",
        "description": "What's next and where we left off: the current item, the handoff note, ready items and warnings (`status --json`).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session": {"type": "string", "description": "this session's id"},
                "limit": {"type": "integer", "minimum": 1, "description": "ready items to list (default 3)"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "next",
        "description": "The open plan items to pick from, recommended first (`plan next --json`).",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1}},
            "additionalProperties": False,
        },
    },
    {
        "name": "start",
        "description": "Claim a plan item (`plan start <id> --json`). A result with `ask` is a question: ask the user, then call again with the answer field set.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "pattern": ID_PATTERN, "description": "plan item id, e.g. P-13"},
                "agent": {"type": "string", "description": "your agent name"},
                "session": {"type": "string"},
                "takeover": {"type": "boolean"},
                "done_means": {"type": "string", "description": "done means, when the item has none"},
                "dirty": {"type": "string", "enum": ["commit", "stash", "carry-on"]},
                "current": {"type": "string", "enum": ["done", "keep", "put-back"]},
                "evidence": {"type": "string", "description": "evidence for current=done"},
                "saved": {"type": "boolean"},
                "unverified": {"type": "boolean"},
                "branch": {"type": "string", "enum": ["branch", "stay", "worktree"]},
                "concurrent": {"type": "string", "enum": ["worktree", "stay"]},
                "always": {"type": "boolean"},
            },
            "required": ["id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "done",
        "description": "Check off a plan item (`plan done <id> --json`). `verify` runs only the item's own backticked done-means command; `verify_part` picks one when there are several (exact text).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "pattern": ID_PATTERN},
                "verify": {"type": "boolean"},
                "verify_part": {"type": "string", "description": "one backticked command from the item's done means, exact text"},
                "evidence": {"type": "string", "description": "one line of evidence no command can check"},
                "unverified": {"type": "boolean"},
                "fresh": {"type": "boolean"},
            },
            "required": ["id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "wrap_up",
        "description": "The handoff instructions to follow when the user says `wrap up` (`wrap-up-instructions`).",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
]
TOOL_NAMES = {t["name"]: t for t in TOOLS}


class ToolInputError(ValueError):
    pass


def _check(args, tool):
    """Check `args` against the tool's input schema (the subset the tools use)."""
    schema = TOOL_NAMES[tool]["inputSchema"]
    if not isinstance(args, dict):
        raise ToolInputError("arguments must be an object")
    props = schema["properties"]
    for key in schema.get("required", []):
        if key not in args:
            raise ToolInputError("missing required argument: %s" % key)
    for key, value in args.items():
        if key not in props:
            raise ToolInputError("unknown argument: %s" % key)
        spec = props[key]
        kind = spec["type"]
        if kind == "boolean" and not isinstance(value, bool):
            raise ToolInputError("%s must be a boolean" % key)
        if kind == "integer" and (isinstance(value, bool) or not isinstance(value, int) or value < spec.get("minimum", value)):
            raise ToolInputError("%s must be an integer >= %s" % (key, spec.get("minimum")))
        if kind == "string":
            if not isinstance(value, str) or "\n" in value or "\x00" in value:
                raise ToolInputError("%s must be a one-line string" % key)
            if "enum" in spec and value not in spec["enum"]:
                raise ToolInputError("%s must be one of %s" % (key, ", ".join(spec["enum"])))
            if "pattern" in spec and not re.match(spec["pattern"], value):
                raise ToolInputError("%s does not match %s" % (key, spec["pattern"]))


def _flags(args, names):
    """`--name=value` for strings and integers, `--name` for true booleans.

    The `=` form keeps a value that starts with `-` from being read as an option.
    """
    out = []
    for key in names:
        if key not in args:
            continue
        flag = "--" + key.replace("_", "-")
        value = args[key]
        if isinstance(value, bool):
            if value:
                out.append(flag)
        else:
            out.append("%s=%s" % (flag, value))
    return out


def build_argv(tool, args):
    """The whatsnext argument list for one tool call. Raises ToolInputError."""
    if tool not in TOOL_NAMES:
        raise ToolInputError("unknown tool: %s" % tool)
    args = {} if args is None else args
    _check(args, tool)
    if tool == "status":
        return ["status", "--json"] + _flags(args, ["session", "limit"])
    if tool == "next":
        return ["plan", "next", "--json"] + _flags(args, ["limit"])
    if tool == "start":
        names = ["agent", "session", "takeover", "done_means", "dirty", "current", "evidence", "saved", "unverified", "branch", "concurrent", "always"]
        return ["plan", "start", args["id"], "--json"] + _flags(args, names)
    if tool == "done":
        if args.get("verify") and "verify_part" in args:
            raise ToolInputError("use verify or verify_part, not both")
        argv = ["plan", "done", args["id"], "--json"] + _flags(args, ["evidence", "unverified", "fresh"])
        if args.get("verify"):
            argv.append("--verify")
        elif "verify_part" in args:
            argv.append("--verify=" + args["verify_part"])
        return argv
    return ["wrap-up-instructions", "--project", os.getcwd()]


def call_tool(tool, args):
    """Run one tool and return an MCP `CallToolResult`."""
    try:
        argv = build_argv(tool, args)
    except ToolInputError as e:
        return {"content": [{"type": "text", "text": str(e)}], "isError": True}
    proc = subprocess.run(
        [sys.executable, SCRIPT] + argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    text = proc.stdout.strip()
    if proc.returncode not in OK_EXITS and proc.stderr.strip():
        text = (text + "\n" + proc.stderr.strip()).strip()
    result = {"content": [{"type": "text", "text": text}], "isError": proc.returncode not in OK_EXITS}
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        data = None
    if isinstance(data, dict):
        result["structuredContent"] = data
    return result


def _reply(msg_id, result=None, error=None):
    out = {"jsonrpc": "2.0", "id": msg_id}
    if error is not None:
        out["error"] = error
    else:
        out["result"] = result
    return out


def handle(message):
    """Answer one JSON-RPC message; returns the reply, or None for a notification."""
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
        return _reply(message.get("id") if isinstance(message, dict) else None, error={"code": -32600, "message": "Invalid Request"})
    method = message["method"]
    if "id" not in message:
        return None  # notifications (notifications/initialized, cancelled) need no answer
    msg_id = message["id"]
    params = message.get("params") or {}
    if method == "initialize":
        asked = params.get("protocolVersion") if isinstance(params, dict) else None
        version = asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
        from whatsnext import VERSION  # noqa: E402 (the entry script is on sys.path)

        return _reply(msg_id, {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "whatsnext", "version": VERSION},
            "instructions": "Shared plan, claims and handoff notes. Call status first. A result with `ask` is a question for the user: ask it, then call the same tool again with the answer.",
        })
    if method == "ping":
        return _reply(msg_id, {})
    if method == "tools/list":
        return _reply(msg_id, {"tools": TOOLS})
    if method == "tools/call":
        if not isinstance(params, dict) or not isinstance(params.get("name"), str):
            return _reply(msg_id, error={"code": -32602, "message": "tools/call needs a name"})
        if params["name"] not in TOOL_NAMES:
            return _reply(msg_id, error={"code": -32602, "message": "unknown tool: %s" % params["name"]})
        return _reply(msg_id, call_tool(params["name"], params.get("arguments")))
    return _reply(msg_id, error={"code": -32601, "message": "Method not found: %s" % method})


def serve(stdin=None, stdout=None):
    """Read one JSON message per line until stdin closes."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            reply = _reply(None, error={"code": -32700, "message": "Parse error"})
        else:
            if isinstance(message, list):
                replies = [r for r in (handle(m) for m in message) if r is not None]
                reply = replies or None
            else:
                reply = handle(message)
        if reply is not None:
            stdout.write(json.dumps(reply) + "\n")
            stdout.flush()
    return 0


def run(args):
    if args and args[0] in ("-h", "--help"):
        print("usage: whatsnext mcp\n\nServe status, next, start, done and wrap_up as MCP tools over stdio; exits when stdin closes.")
        return 0
    if args:
        print("usage: whatsnext mcp", file=sys.stderr)
        return 2
    return serve()
