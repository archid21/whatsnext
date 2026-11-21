#!/usr/bin/env python3
"""P-88 research: cut a saved Claude Code transcript (.jsonl) down to what a helper model needs.

Keeps user and assistant text and a one-line form of each tool call. Trims each tool result to
a head and a tail. Drops the oldest messages until the text fits a byte budget (the latest stay).
Standard library only, Python 3.9+.

    python3 p88_trim.py <transcript.jsonl> [--head 800] [--tail 400] [--budget 120000]
                        [--until-row N | --cut-at-wrapup] [--out FILE]

The trimmed text goes to stdout (or --out). The sizes go to stderr (or stdout with --out).
"""
import argparse
import json
import re
import sys

WRAPUP_RE = re.compile(r"^\s*wrap up[.!]?\s*$|message:\s*\n\s*wrap up\s*\n", re.I)
FIRST_USER_CAP = 3000   # the opening request is kept even when older messages drop
ASSISTANT_CAP = 6000    # assistant text is kept whole up to this many chars


def clip(text, head, tail):
    """Keep the first `head` and last `tail` chars; say how much was cut."""
    if len(text) <= head + tail + 40:
        return text
    cut = len(text) - head - tail
    return "%s\n[... %d chars cut ...]\n%s" % (text[:head], cut, text[-tail:] if tail else "")


def block_text(content):
    """Plain text of a tool_result content (string or list of blocks)."""
    if isinstance(content, str):
        return content
    parts = []
    for b in content or []:
        if isinstance(b, dict) and b.get("type") == "text":
            parts.append(b.get("text", ""))
        elif isinstance(b, dict) and b.get("type") == "image":
            parts.append("[image]")
    return "\n".join(parts)


def call_line(b):
    name, inp = b.get("name", "?"), b.get("input") or {}
    if name == "Bash":
        return "CALL Bash: " + clip(inp.get("command", ""), 400, 150)
    if name == "Write":
        c = inp.get("content", "")
        return "CALL Write %s (%d chars): %s" % (inp.get("file_path"), len(c), clip(c, 250, 0).replace("\n", " "))
    if name == "Edit":
        return "CALL Edit %s: %s -> %s" % (inp.get("file_path"), clip(inp.get("old_string", ""), 120, 0).replace("\n", " "),
                                          clip(inp.get("new_string", ""), 300, 0).replace("\n", " "))
    if name in ("Read", "Grep", "Glob"):
        return "CALL %s: %s" % (name, clip(json.dumps(inp), 250, 0))
    return "CALL %s: %s" % (name, clip(json.dumps(inp), 300, 100))


def user_text(content):
    if isinstance(content, str):
        return content
    return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")


def load_rows(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    rows.append({})
    return rows


def find_wrapup_row(rows):
    """Index of the last human message that asks to wrap up, or None."""
    for i in range(len(rows) - 1, -1, -1):
        d = rows[i]
        if d.get("type") == "user" and not d.get("isSidechain"):
            c = (d.get("message") or {}).get("content")
            if c is not None and WRAPUP_RE.search(user_text(c)):
                return i
    return None


def render(rows, head, tail):
    """One text block per message part, oldest first."""
    out = []
    for d in rows:
        if d.get("type") not in ("user", "assistant") or d.get("isSidechain"):
            continue
        msg = d.get("message") or {}
        c = msg.get("content")
        if d["type"] == "user":
            if isinstance(c, str):
                out.append("USER: " + clip(c, 3000, 500))
                continue
            for b in c or []:
                if b.get("type") == "text" and b.get("text", "").strip():
                    out.append("USER: " + clip(b["text"], 3000, 500))
                elif b.get("type") == "tool_result":
                    t = block_text(b.get("content")).strip()
                    tag = "RESULT(error)" if b.get("is_error") else "RESULT"
                    out.append("%s: %s" % (tag, clip(t, head, tail) if t else "(empty)"))
        else:
            for b in c or []:
                if b.get("type") == "text" and b.get("text", "").strip():
                    out.append("ASSISTANT: " + clip(b["text"], ASSISTANT_CAP, 1000))
                elif b.get("type") == "tool_use":
                    out.append(call_line(b))
                # thinking blocks are empty in saved transcripts: skipped
    return out


def fit(blocks, budget):
    """Keep the latest blocks that fit; keep the opening request too. Returns (text, kept, dropped)."""
    sizes = [len(b.encode("utf-8")) + 2 for b in blocks]
    first = None
    if blocks and blocks[0].startswith("USER:"):
        first = clip(blocks[0], FIRST_USER_CAP, 0)
    reserve = (len(first.encode("utf-8")) + 120) if first else 0
    total, start = reserve, len(blocks)
    for i in range(len(blocks) - 1, -1, -1):
        if total + sizes[i] > budget:
            break
        total += sizes[i]
        start = i
    dropped = start - (1 if first and start > 0 else 0)
    kept = blocks[start:]
    if start > 0 and first:
        head = [first, "[... %d older messages dropped to fit the budget ...]" % max(dropped, 0)]
        kept = head + (kept if start > 0 else [])
    return "\n\n".join(kept), len(blocks) - max(start, 0), max(start, 0)


def header(rows):
    """Session id, branch and times from the row metadata (the helper cannot see git)."""
    meta = [d for d in rows if d.get("sessionId")]
    if not meta:
        return ""
    last = meta[-1]
    branch = next((d["gitBranch"] for d in reversed(meta) if d.get("gitBranch")), None)
    cwd = next((d["cwd"] for d in reversed(meta) if d.get("cwd")), None)
    return "TRANSCRIPT session=%s branch=%s cwd=%s first=%s last=%s\n\n" % (
        last.get("sessionId"), branch, cwd,
        meta[0].get("timestamp"), last.get("timestamp"))


def context_tokens(rows):
    """Context size the main model had at its last turn: input + cache read + cache write."""
    for d in reversed(rows):
        if d.get("type") == "assistant":
            u = (d.get("message") or {}).get("usage") or {}
            if "input_tokens" in u:
                return (u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0)
                        + u.get("cache_creation_input_tokens", 0)), (d["message"].get("model"))
    return None, None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("transcript")
    ap.add_argument("--head", type=int, default=800, help="chars kept from the start of each tool result")
    ap.add_argument("--tail", type=int, default=400, help="chars kept from the end of each tool result")
    ap.add_argument("--budget", type=int, default=120000, help="byte budget for the trimmed text")
    ap.add_argument("--until-row", type=int, help="use only rows before this 0-based row of the file")
    ap.add_argument("--cut-at-wrapup", action="store_true", help="stop before the last 'wrap up' message")
    ap.add_argument("--out", help="write the trimmed text here instead of stdout")
    a = ap.parse_args(argv)

    raw_bytes = 0
    with open(a.transcript, "rb") as f:
        raw_bytes = len(f.read())
    rows = load_rows(a.transcript)
    cut = a.until_row
    if cut is None and a.cut_at_wrapup:
        cut = find_wrapup_row(rows)
    if cut is not None:
        rows = rows[:cut]
    raw_used = sum(len(json.dumps(r)) for r in rows)
    blocks = render(rows, a.head, a.tail)
    full_text = "\n\n".join(blocks)
    text, kept, dropped = fit(blocks, a.budget)
    text = header(rows) + text
    tb = len(text.encode("utf-8"))
    ctx, model = context_tokens(rows)
    info = ("rows=%d cut_row=%s raw_file_bytes=%d raw_rows_bytes=%d "
            "trimmed_before_budget_bytes=%d trimmed_bytes=%d approx_tokens=%d "
            "blocks_kept=%d blocks_dropped=%d context_tokens_at_cut=%s model=%s"
            % (len(rows), cut, raw_bytes, raw_used, len(full_text.encode("utf-8")), tb, tb // 4,
               kept, dropped, ctx, model))
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print(info)
    else:
        sys.stdout.write(text + "\n")
        sys.stderr.write(info + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
