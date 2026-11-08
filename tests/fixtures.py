"""Shared fixtures for the whatsnext tests: a temp git project, a progress base, and a plan base.

Imported by the test files. `unittest discover` does not collect this module (it has no test_ prefix).
"""

import datetime
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "skills" / "whatsnext" / "scripts"
SCRIPT = SCRIPTS / "whatsnext.py"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))


class Sandbox(unittest.TestCase):
    """A temp HOME, XDG dir and git repo, so the real ~/.config is never touched."""

    git = True

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = os.path.realpath(self.tmp.name)
        self.home = os.path.join(base, "home")
        self.xdg = os.path.join(base, "home", "xdg")
        self.proj = os.path.join(base, "proj")
        os.makedirs(self.xdg)
        os.makedirs(self.proj)
        # Install is long past in a test: the first-run welcome (P-44) has been shown. Its own tests remove the marker.
        os.makedirs(os.path.join(self.xdg, "whatsnext"))
        with open(os.path.join(self.xdg, "whatsnext", "welcomed"), "w", encoding="utf-8") as f:
            f.write("shown\n")
        if self.git:
            subprocess.run(["git", "init", "-q", self.proj], check=True)
        self.env = dict(os.environ, HOME=self.home, XDG_CONFIG_HOME=self.xdg)
        # The invoking agent must not change a test's default identity.
        for key in ("WHATSNEXT_AGENT", "GROUNDWORK_AGENT"):
            self.env.pop(key, None)
        old = {k: os.environ.get(k) for k in ("HOME", "XDG_CONFIG_HOME")}
        os.environ["HOME"], os.environ["XDG_CONFIG_HOME"] = self.home, self.xdg
        self.addCleanup(self.restore, old)

    def restore(self, old):
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def write(self, where, data, raw=False):
        paths = {
            "user": os.path.join(self.xdg, "whatsnext", "config.json"),
            "project": os.path.join(self.proj, ".whatsnext", "config.json"),
            "local": os.path.join(self.proj, ".whatsnext", "config.local.json"),
        }
        path = paths[where]
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(data if raw else json.dumps(data))

    def gw(self, args, stdin="", cwd=None):
        return subprocess.run([sys.executable, str(SCRIPT)] + args, input=stdin, capture_output=True,
                              text=True, env=self.env, cwd=cwd or self.proj)


class RepoBase(Sandbox):
    def setUp(self):
        super().setUp()
        self.events = os.path.join(self.tmp.name, "events.jsonl")
        self.env["GW_TEST_EVENTS"] = self.events
        self.env["PYTHONPATH"] = os.path.dirname(os.path.abspath(__file__))
        self.write("project", {"backend": {"name": "support_backend:LogBackend"}})
        git = ["git", "-C", self.proj]
        subprocess.run(git + ["config", "user.name", "T"], check=True)
        subprocess.run(git + ["config", "user.email", "t@example.com"], check=True)
        self.clock = 1700000000

    def p(self, rel):
        return os.path.join(self.proj, *rel.split("/"))

    def put(self, rel, text):
        os.makedirs(os.path.dirname(self.p(rel)), exist_ok=True)
        with open(self.p(rel), "w", encoding="utf-8", newline="") as f:
            f.write(text)

    def get(self, rel):
        with open(self.p(rel), encoding="utf-8", newline="") as f:
            return f.read()

    def has(self, rel):
        return os.path.exists(self.p(rel))

    def commit(self, message="c", when=None):
        """Commit everything at a given unix time (later calls default to later times)."""
        if when is None:
            self.clock += 1000
            when = self.clock
        env = dict(self.env, GIT_AUTHOR_DATE="%d +0000" % when, GIT_COMMITTER_DATE="%d +0000" % when)
        subprocess.run(["git", "-C", self.proj, "add", "-A"], check=True, env=env)
        subprocess.run(["git", "-C", self.proj, "commit", "-q", "-m", message], check=True, env=env)


STATUS = "docs/project/progress"


FIRST_BLOCK = 2000


def task_text(task_id="P-13", title="Add login", state="active", branch="p-13-add-login", commit="1a2b3c4",
              updated="2026-10-27T14:05Z", files="none", decisions="none", next_action="Run the login tests.",
              goal="", doing="", questions="", done="", note="", steps=None):
    """A progress file. `note` is the Note field's value; `steps` a list of Plan steps checklist lines."""
    lines = ["# %s: %s" % (task_id, title), "", "- **State:** " + state, "- **Agent:** claude-code",
             "- **Branch:** " + branch, "- **Commit:** " + commit, "- **Updated:** " + updated,
             "- **Files:** " + files, "- **Decisions:** " + decisions]
    if note:
        lines.append("- **Note:** " + note)
    lines += ["", "## Next action", "", next_action, ""]
    if steps:
        lines += ["## Plan steps", ""] + list(steps) + [""]
    lines += ["## Goal", "", goal, "", "## Done", "", done, "",
             "## In progress", "", doing, "", "## Open questions", "", questions, ""]
    return "\n".join(lines)


class StatusBase(RepoBase):
    def setUp(self):
        super().setUp()
        self.put("README.md", "x\n")
        self.commit("first")

    def cfg(self, **extra):
        data = {"backend": {"name": "support_backend:LogBackend"}}
        data.update(extra)
        self.write("project", data)

    def git(self, *args):
        return subprocess.run(["git", "-C", self.proj] + list(args), check=True, capture_output=True,
                              text=True, env=self.env).stdout.strip()

    def head(self):
        return self.git("rev-parse", "--short", "HEAD")

    def branch(self):
        return self.git("symbolic-ref", "--short", "HEAD")

    def task(self, task_id="P-13", **kw):
        kw.setdefault("branch", self.branch())
        kw.setdefault("commit", self.head())
        self.put("%s/%s.md" % (STATUS, task_id), task_text(task_id, **kw))
        return "%s/%s.md" % (STATUS, task_id)

    def packet(self):
        r = self.gw(["progress", "resume-note", "--json"])
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def logged(self):
        """Backend events recorded by the test backend."""
        if not os.path.exists(self.events):
            return []
        with open(self.events, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]


PLAN_PATH = "docs/project/PLAN.md"


PLAN = """# Plan

## Now
- [ ] P-13 Add login · done means: login tests pass
- [ ] P-14 Rate-limit the API · done means: 429 after 100 requests a minute
## Next
- [ ] P-15 Password reset · done means: reset email is sent
## Later
- [ ] P-16 Audit log
"""


def ts(minutes_ago=0):
    t = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=minutes_ago)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def minute_ts(minutes_ago=0):
    """A minute-resolution stamp. It can sit up to 59 s before the real time, so use it only where a
    one-minute error does not matter (wide margins). To assert an exact age in minutes, use ts()."""
    return ts(minutes_ago)[:16] + "Z"


class PlanBase(StatusBase):
    def setUp(self):
        super().setUp()
        self.cfg()
        self.put(PLAN_PATH, PLAN)
        self.commit("plan")

    def plan(self, *args, **kw):
        return self.gw(["plan"] + list(args), **kw)

    def jplan(self, *args, **kw):
        r = self.plan(*(list(args) + ["--json"]), **kw)
        return r, (json.loads(r.stdout) if r.stdout.strip() else None)

    def start(self, item="P-13", *flags, **kw):
        return self.plan("start", item, "--agent", kw.pop("agent", "codex"), *flags, **kw)

    def claim_path(self, item_id):
        return os.path.join(self.proj, ".git", "whatsnext", "claims", item_id + ".json")

    def claim_data(self, item_id):
        with open(self.claim_path(item_id), encoding="utf-8") as f:
            return json.load(f)

    def has_claim(self, item_id):
        return os.path.exists(self.claim_path(item_id))

    def set_claim(self, item_id, agent="codex", updated=None, asked_at=None, worktree=None, since=None, branch="b"):
        os.makedirs(os.path.dirname(self.claim_path(item_id)), exist_ok=True)
        with open(self.claim_path(item_id), "w", encoding="utf-8") as f:
            json.dump({"id": item_id, "agent": agent, "session": None, "branch": branch,
                       "worktree": worktree or os.path.realpath(self.proj), "since": since or updated or ts(),
                       "updated": updated or ts(), "token": "other-token", "asked_at": asked_at}, f)

    def evs(self, name=None):
        return [e for e in self.logged() if name is None or e["event"] == name]

    def question(self, r):
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        return json.loads(r.stdout)


def session_note(event, agent, out):
    """The resume note a session-start hook printed. Claude Code gets JSON (a `systemMessage` banner and the note as
    `additionalContext`, P-41); Codex gets the note as plain text. Other events and empty output come back as given."""
    if event == "session-start" and agent != "codex" and out.startswith("{"):
        return json.loads(out)["hookSpecificOutput"]["additionalContext"] + "\n"
    return out
