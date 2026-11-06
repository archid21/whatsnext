"""Private text and a secret check, before any write of user text (ADR-0002).

Text between `<private>` and `</private>` (any case, any number of lines) is
removed before it reaches a progress file, a decision, a ground rule or an
imported item. Tags may hold spaces or attributes (`< private >`, `<private x>`)
and may nest: a span ends at the closing tag that matches its opening tag. A tag
that is never closed removes the rest of its paragraph (up to the next blank
line): private text must not leak because a closing tag is missing, and one
missing tag must not wipe the rest of a progress file that is rewritten whole.

`secret_warnings` names the kind of each secret-looking pattern it finds. It
never returns the matched text. `clean` strips and warns on stderr; the write
still happens (warn, do not block). The patterns miss some secrets and flag
some harmless text, so a warning is a prompt to look, not a guarantee.
"""

import re
import sys

TAG_RE = re.compile(r"<\s*(/?)\s*private\b[^>]*>", re.IGNORECASE)
PARAGRAPH_END_RE = re.compile(r"\n[ \t]*\n")

# (kind named in the warning, pattern)
SECRET_PATTERNS = (
    ("AWS access key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("GitHub token", re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}")),
    ("GitHub token", re.compile(r"github_pat_[A-Za-z0-9_]{20,}")),
    ("Anthropic API key", re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}")),
    ("OpenAI-style API key", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("Slack token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{6,}")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("key, password or token assignment",
     re.compile(r"(api[_-]?key|secret|token|password)\s*[:=]\s*\S{8,}", re.IGNORECASE)),
)


def _join(kept, rest, blanks):
    """Text before a dropped span, then the rest: one space when the span sat between two words."""
    if blanks and kept and rest and rest[0] not in " \t\r\n":
        return kept + " "
    return kept


def strip_private(text):
    """`text` without its `<private>…</private>` spans (and the blanks before each)."""
    if not text or not TAG_RE.search(text):
        return text
    out = []
    pos = 0  # start of the text not yet copied
    depth = 0
    start = 0  # where the open span began (for an unclosed tag)
    blanks = False
    for tag in TAG_RE.finditer(text):
        closing = tag.group(1) == "/"
        if depth == 0:
            before = text[pos:tag.start()]
            if closing:  # a stray closing tag: drop it and the blanks before it
                out.append(before.rstrip(" \t"))
                pos = tag.end()
                continue
            kept = before.rstrip(" \t")
            blanks = len(kept) < len(before)
            out.append(kept)
            start = tag.start()
            depth = 1
        elif closing:
            depth -= 1
            if depth == 0:
                pos = tag.end()
                out[-1] = _join(out[-1], text[pos:], blanks)
        else:
            depth += 1
    if depth:  # never closed: drop to the end of the paragraph, keep what follows
        end = PARAGRAPH_END_RE.search(text, start)
        pos = end.start() if end else len(text)
        return "".join(out) + strip_private(text[pos:])
    return "".join(out) + text[pos:]


def secret_warnings(text):
    """Short reasons (kinds, once each, in pattern order) why `text` looks like it holds a secret."""
    found = []
    for kind, pattern in SECRET_PATTERNS:
        if kind not in found and pattern.search(text or ""):
            found.append(kind)
    return found


def warn(text, where):
    """Print one stderr warning when `text` looks like a secret. Never prints the text."""
    kinds = secret_warnings(text)
    if kinds:
        print("warning: %s looks like it contains a secret (%s). It was written anyway; "
              "remove it, and rotate it if it is real." % (where, ", ".join(kinds)), file=sys.stderr)
    return kinds


def clean(text, where, quiet=False):
    """`text` with private spans removed, after a secret warning on stderr (none when `quiet`)."""
    text = strip_private(text)
    if not quiet:
        warn(text, where)
    return text


def mask_secrets(text):
    """`text` with private spans removed and anything that looks like a secret replaced by `[redacted]`.
    For text that is printed or stored without a human looking first (a hook's output)."""
    text = strip_private(text or "")
    for kind, pattern in SECRET_PATTERNS:
        if kind == "key, password or token assignment":
            text = pattern.sub(lambda m: re.split(r"[:=]", m.group(0), 1)[0] + "= [redacted]", text)
        else:
            text = pattern.sub("[redacted]", text)
    return text
