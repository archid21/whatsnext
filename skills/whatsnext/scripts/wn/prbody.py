"""`progress pr-body <id>` (P-61): a pull request description in Markdown, built from recorded facts only.

Sources: the task's progress file (Goal, Done, Plan steps, Decisions, Open questions), its PLAN.md item (title,
evidence) and git (the commits and changed files on the task's branch since the main branch, and any ADR files the
branch adds). A section with nothing in it is left out. Nothing here calls a model, and nothing from the repository
is run: progress text is repository data, so control characters are removed before it is printed.
"""

import re
import unicodedata

from . import plan as gwplan
from . import status as gwstatus

MAX_COMMITS = 30
MAX_FILES = 40
CHECKED_RE = re.compile(r"^\s*[-*]\s+\[[xX]\]\s+(.*)$")
ADR_RE = re.compile(r"(?:^|/)(ADR-\d+[^/]*)\.md$")


def tidy(text):
    """`text` without control or format characters (line breaks and tabs stay), trailing space removed per line."""
    kept = "".join(c for c in text if c in "\n\t" or unicodedata.category(c)[0] != "C")
    return "\n".join(line.rstrip() for line in kept.split("\n")).strip()


def plain(value):
    return value if value and value.strip().lower() != gwstatus.NONE else ""


def git_lines(root, *args):
    code, out = gwstatus.git(root, *args)
    return [line for line in out.splitlines() if line.strip()] if code == 0 else []


def changes(root, branch):
    """(main, commits, files, added ADR names) for `branch` against the main branch; empty when git cannot tell."""
    if not branch or not gwstatus.in_git(root) or not gwplan.branch_exists(root, branch):
        return None, [], [], []
    main = gwplan.default_branch(root)
    if main in ("HEAD", branch):
        return None, [], [], []
    # --cherry-pick drops commits main already has by content (a cherry-pick), as `plan check` does (P-60)
    commits = git_lines(root, "log", "--no-merges", "--right-only", "--cherry-pick", "--format=%h %s",
                        "%s...%s" % (main, branch))
    if not commits:
        return main, [], [], []
    files = git_lines(root, "-c", "core.quotepath=off", "diff", "--stat=100", "%s...%s" % (main, branch))
    added = git_lines(root, "-c", "core.quotepath=off", "diff", "--name-only", "--diff-filter=A",
                      "%s...%s" % (main, branch))
    adrs = [m.group(1) for m in (ADR_RE.search(p) for p in added) if m]
    return main, commits, files, adrs


def build(root, effective, task_id, trailer=None):
    """The description as {"title", "body", "sections"}, or None when no progress file has that id."""
    task = next((t for t in gwstatus.load_tasks(root, gwstatus.status_folder(root, effective)) if t.id == task_id), None)
    if task is None:
        return None
    ctx = gwplan.Ctx(root, effective)
    item = next((it for it in ctx.items() if it.id == task_id), None) if ctx.has_plan() else None
    title = tidy(item.title if item is not None and item.title else task.title) or task_id
    sections = []

    def add(name, text):
        text = tidy(text or "")
        if text:
            sections.append((name, text))

    add("Goal", task.section("Goal"))
    done = [task.section("Done")]
    steps = [m.group(1) for m in (CHECKED_RE.match(l) for l in task.section("Plan steps").split("\n")) if m]
    if steps:
        done.append("\n".join("- " + s for s in steps))
    add("Done", "\n\n".join(t for t in done if t))

    branch = plain(task.field("branch"))
    main, commits, files, adrs = changes(root, branch)
    decisions = [plain(task.field("decisions")), task.section("Decisions")]
    if adrs:
        decisions.append("Added in this branch: " + ", ".join(adrs))
    add("Decisions", "\n\n".join(t for t in decisions if t))

    if item is not None and item.checked and item.evidence:
        verification = "- " + item.evidence
        if gwplan.is_verified(item.evidence):
            verification += " (a command run by `plan done --verify`)"
        else:
            verification += " (a person's check, not a command)"
    elif item is not None and item.evidence:
        verification = "Not done yet. Last recorded: " + item.evidence
    else:
        verification = "Not verified yet."
    if item is not None and item.done_means and item.done_means not in task.section("Goal"):
        verification = "Done means: %s\n\n%s" % (item.done_means, verification)
    add("Verification", verification)

    if commits or files:
        parts = []
        if commits:
            shown = ["- " + c for c in commits[:MAX_COMMITS]]
            if len(commits) > MAX_COMMITS:
                shown.append("- and %d more" % (len(commits) - MAX_COMMITS))
            parts.append("Commits on `%s` since `%s`:\n\n%s" % (branch, main, "\n".join(shown)))
        if files:
            body = files[:MAX_FILES] + (["... and %d more lines" % (len(files) - MAX_FILES)] if len(files) > MAX_FILES else [])
            parts.append("```\n%s\n```" % "\n".join(body))
        add("Changes", "\n\n".join(parts))
    add("Open questions", task.section("Open questions"))

    text = "\n\n".join("## %s\n\n%s" % (name, body) for name, body in sections)
    if trailer and tidy(trailer):
        text = (text + "\n\n" if text else "") + tidy(trailer)
    return {"title": "%s: %s" % (task_id, title), "body": text, "sections": [name for name, _b in sections]}
