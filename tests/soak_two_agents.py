"""Two-agent soak test (P-12): do two agents, in two git worktrees, ever both start the same plan item?

Each run makes one plan item and starts two processes at the same instant, one in each worktree, both running
`plan start <item>`. A run is a double claim when both processes report "Started". Agent B can be put on the Codex
fallback path (its git folder refuses claim files, so it writes `.whatsnext/claims/` in its own worktree).

    python3 tests/soak_two_agents.py --runs 20            # both agents share the git claims folder
    python3 tests/soak_two_agents.py --runs 20 --fallback  # agent B on the fallback path

Exit 0 when no run had a double claim, else 1. A passing run is the evidence to drop "experimental" for multi-agent use.
"""

import argparse
import os
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "skills", "whatsnext", "scripts", "whatsnext.py")
SCRIPTS = os.path.dirname(SCRIPT)

# Run as a child: B can read the git claims folder but not write it (as in a Codex sandbox), so its claim
# goes to `.whatsnext/claims/` in its own worktree. Then the normal CLI runs.
FALLBACK_RUNNER = """
import os, sys
sys.path.insert(0, {scripts!r})
from wn import claims
real = claims.claims_dir(os.getcwd()) + os.sep
for name in ("_write_new", "_write_replace"):
    def guard(path, data, _orig=getattr(claims, name)):
        if os.path.abspath(path).startswith(real):
            raise PermissionError("read-only file system (soak test)")
        return _orig(path, data)
    setattr(claims, name, guard)
import whatsnext
sys.exit(whatsnext.main(sys.argv[1:]))
"""


def git(cwd, *args):
    subprocess.run(["git", "-C", cwd] + list(args), check=True, capture_output=True, text=True)


def make_repo(base, items):
    main = os.path.join(base, "main")
    os.makedirs(main)
    git(main, "init", "-q")
    git(main, "config", "user.name", "Soak")
    git(main, "config", "user.email", "soak@example.com")
    lines = ["# Plan", "", "## Now", ""] + ["- [ ] P-%d Job %d · done means: `true`" % (n, n) for n in range(1, items + 1)]
    os.makedirs(os.path.join(main, "docs", "project"))
    with open(os.path.join(main, "docs", "project", "PLAN.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(main, ".gitignore"), "w", encoding="utf-8") as f:
        f.write(".whatsnext/\n")
    git(main, "add", "-A")
    git(main, "commit", "-q", "-m", "plan")
    other = os.path.join(base, "other")
    git(main, "worktree", "add", "-q", "-b", "agent-b", other)
    return main, other


def command(agent, item, fallback_b, home, gate):
    args = ["plan", "start", item, "--agent", agent, "--branch", "stay", "--dirty", "carry-on", "--current", "keep"]
    if agent == "agent-b" and fallback_b:
        launch = [sys.executable, "-c", FALLBACK_RUNNER.format(scripts=SCRIPTS)] + args
    else:
        launch = [sys.executable, SCRIPT] + args
    wait = 'while [ ! -e "$1" ]; do :; done; shift; exec "$@"'
    return ["sh", "-c", wait, "sh", gate] + launch


def one_run(main, other, item, fallback_b, home, base):
    gate = os.path.join(base, "gate-" + item)
    env = dict(os.environ, HOME=home, XDG_CONFIG_HOME=os.path.join(home, "xdg"))
    procs = []
    for agent, cwd in (("agent-a", main), ("agent-b", other)):
        procs.append((agent, subprocess.Popen(command(agent, item, fallback_b, home, gate), cwd=cwd, env=env,
                                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)))
    time.sleep(0.2)  # both are waiting at the gate
    open(gate, "w").close()
    started = []
    for agent, proc in procs:
        out, _err = proc.communicate(timeout=120)
        if proc.returncode == 0 and "Started %s:" % item in out:
            started.append(agent)
    return started


def main_(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--fallback", action="store_true", help="put agent B on the Codex fallback path")
    args = parser.parse_args(argv)
    doubles, nones = [], []
    with tempfile.TemporaryDirectory() as base:
        home = os.path.join(base, "home")
        os.makedirs(os.path.join(home, "xdg"))
        main, other = make_repo(base, args.runs)
        for n in range(1, args.runs + 1):
            item = "P-%d" % n
            started = one_run(main, other, item, args.fallback, home, base)
            if len(started) > 1:
                doubles.append(item)
            elif not started:
                nones.append(item)
    mode = "agent B on the fallback path" if args.fallback else "shared git claims folder"
    print("Two-agent soak (%s): %d runs, %d double claims, %d runs where neither started" % (
        mode, args.runs, len(doubles), len(nones)))
    if doubles:
        print("Double claims: " + ", ".join(doubles))
    if nones:
        print("Neither started: " + ", ".join(nones))
    return 1 if doubles else 0


if __name__ == "__main__":
    sys.exit(main_())
