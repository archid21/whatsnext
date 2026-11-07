# whatsnext user guide

What you can do with whatsnext, and the words to say. Each section gives the action first.

You talk to your agent (Claude Code or Codex). The agent runs the commands. The few commands you may run yourself are marked **Run it yourself**.

Contents: [Save and resume](#save-and-resume-a-session) · [Pick work](#pick-and-start-work) · [Mark done](#mark-work-done) · [Track a task](#track-a-task) · [Compact](#compact-a-long-session) · [Several agents](#use-more-than-one-agent) · [Health check](#check-that-it-works) · [Settings](#change-a-setting) · [Tips](#tips) · [Set up a repo](#set-up-a-repository) · [Known gaps](#known-gaps)

---

## Save and resume a session

Use this when you stop work, or the context window is full.

1. Type `wrap up`. Type exactly these two words as the whole prompt.
2. Wait for the reply to end with `Handoff written: <path>`.
3. Type `/clear`.
4. In the new session, type `what's next?`.

**What happens at step 1.** The agent writes `docs/project/HANDOFF.md` and overwrites the old one. The note holds: Goal, Next action (with a `Verify:` line), State, What changed, Decisions, Constraints, Open questions and blockers. The old note is archived first.

**What you see at step 2.** A summary of the session, then three lines: the path, a one-line `/compact` text you can paste, and "or `/clear` for a fresh start".

**What you see at step 3.** A one-line banner appears at the top of the new session by itself: "whatsnext: resume note loaded. Next: …". The full resume note goes to the agent, not to your screen. The agent uses it in its first reply, and `what's next?` shows it to you. The note says what was done, what is next, which test command to run, and what changed in git since the note. It is at most 1,200 characters. In Codex there is no banner.

**What `what's next?` does at step 4.** It shows the handoff's Next action and open questions, with the file path and the time it was written. It then offers the open items from the plan checklist (`PLAN.md`). If the plan has no open items, it says so and still shows the handoff.

**Use `wrap up` before:** closing the laptop, switching agent, ending the day, or a `/clear`.

---

## Pick and start work

| You say | The agent does |
|---|---|
| `what's next?` | Shows up to 3 open items from the plan. The recommended one is first. Items idle for too long are marked stale. |
| `start P-13` | Starts that item. |
| `show the plan` or `who has what?` | Lists every item, its status and who holds it. |
| `check the plan` | Finds items with no done means or no evidence, and duplicate ids. |

**Start asks questions first.** It asks one at a time, only when needed:

1. Someone else has the item: take it over?
2. The item has no done means: what proves it done?
3. You have uncommitted changes: commit first?
4. Another item is in progress: mark it done, keep it, or put it back?
5. Branch: make a branch, stay, or make a worktree? Say "always do this" to stop being asked.

Nothing is marked in progress until every answer is in. After Start, the agent restates the goal and done means, lists 3 to 5 steps, and waits for your OK before it changes files.

**Keep or put back a stale item.** Say `keep working on P-12` to reset its idle clock. Say `put P-12 back` to release it for any agent. The agent updates its progress file first.

---

## Mark work done

Say `mark P-13 done`. The agent then picks one of two ways:

- **Proved by a command.** The agent runs your test command from the project root. Exit 0 ticks the item as **confirmed**. Any failure leaves it open and saves the last 20 lines of output.
- **Checked by a person.** For work no command can check, the agent ticks it with one line of evidence. It shows as `done*`, which means "not verified". The agent asks you which way to use.

Tip: give every plan item a done means that is a command, such as `python3 -m unittest discover -s tests`.

---

## Track a task

Use this for work that takes more than one session.

| You say | The agent does |
|---|---|
| `start a task` or `track this task` | Creates a progress file for the task with a title. |
| `the next step is now <text>` | Sets the Next action. It is marked **confirmed**. |
| `where did we leave off?` | Shows the active task's progress file. |
| `save this plan` | After a plan-mode plan is shown, stores it word for word and copies up to 20 steps into the progress file. |

The progress file has a trust mark in its header:

- `confirmed`: you or the agent set it on purpose.
- `auto`: a model's guess. It never replaces a confirmed Next action.
- `facts`: the hooks wrote it from git.

Between sessions, the hooks add one line per event to `docs/project/progress/journal/<task>.md`: time, commit, branch, files changed. This uses no model call.

---

## Compact a long session

Use this when the context window is filling but you want to keep going in the same session.

1. Say `compact`.
2. If this session has no fresh handoff, the agent runs `wrap up` first.
3. The agent then submits `/compact` with text built from your handoff: goal, next action, decisions, constraints.

A handoff written by a different session is never put into a compact. The text names its path instead.

**After a compact.** Before the compact starts, whatsnext saves your latest request (the first 250 characters, secrets removed) and any running subagents or in-progress todo, in a git-ignored file. The resume note that loads after the compact repeats them, so the model still knows what you just asked even if the summary dropped it. It does nothing when no task is active. To turn it off: `python3 skills/whatsnext/scripts/whatsnext.py config set --user note.carryAfterCompact false`.

**Run it yourself:** `compact-instructions` prints the `/compact` text. See [Commands](#commands).

**Compare with `/clear`.** `/clear` drops everything and starts over from the resume note. Compact keeps a summary of this session. Use `/clear` after `wrap up` for a clean start. Use compact to stay in flow.

---

## Use more than one agent

Claude Code and Codex read the same plain files, so one can pick up where the other stopped.

- `plan start` refuses an item another agent holds. It asks if you want to take it over.
- A claim is a note, not a lock. Two agents that ask at the same moment might both get it.
- Claims in other git worktrees are visible, except in Codex's default sandbox.
- A handoff note is read first only by the session that wrote it, or one working the same task.

This is experimental. See the README's [Known limits](../README.md#known-limits).

For Codex: run `install-hooks`, then trust the hooks in Codex's `/hooks`.

---

## Check that it works

**Run it yourself:**

```bash
python3 skills/whatsnext/scripts/whatsnext.py doctor
```

It reports whether the hooks are in place for Claude Code and Codex, and when a hook last fired. It prints the fix for each gap.

Say `check the plan` to find plan items ticked without proof.

---

## Change a setting

**Run it yourself:**

```bash
python3 skills/whatsnext/scripts/whatsnext.py config show
python3 skills/whatsnext/scripts/whatsnext.py config set --user plan.staleAfter 2h
```

`config show` lists every setting and where its value comes from. `config set --user` writes to `~/.config/whatsnext/config.json`. A project setting still wins over it.

Settings you may want:

| Key | Default | Meaning |
|---|---|---|
| `plan.staleAfter` | `4h` | How long an item can sit idle before it is stale |
| `plan.branchOnStart` | `ask` | Whether Start asks about a branch |
| `plan.tickGuard` | `warn` | Warn when a plan item is ticked by hand |
| `plan.verifyTimeout` | `30m` | How long a `--verify` command may run |
| `note.staleDays` | `7` | Age at which the resume note warns |
| `note.carryAfterCompact` | `true` | Repeat your latest request in the resume note after a compact |
| `paths.handoff` | `docs/project/HANDOFF.md` | Where the handoff note is written |

---

## Tips

A short tip band shows above the prompt in Claude Code, in the terminal and the desktop app. It does not show in Codex, VS Code or on mobile. One tip shows at a time, only when it applies:

- **`wrap up`:** after a compact, or after 20 turns in one session.
- **`what's next?`:** after your first turn, when no task is active.
- **`mark P-13 done`:** after a plan item's `--verify` command passes.

Press **Next tip** to mark the tip seen and see the next one. Press **Stop tips** to hide the band for good, in every session. Type `/whatsnext-tips` to turn the tips back on and show them all again. A tip you have seen does not return, and no tip shows twice in one session.

---

## Set up a repository

Say `set up whatsnext in this repo`. The agent first shows a dry run, then runs `init` after your OK.

`init` creates only: `PLAN.md`, `.whatsnext/`, one line in `.gitignore`, and one marked block in `AGENTS.md`. It needs a git repository. To remove the `AGENTS.md` block: `init --undo`.

It never pushes and never creates a remote. Full list of files it touches: [WHAT-IT-TOUCHES.md](WHAT-IT-TOUCHES.md).

---

## Commands

You rarely type these. The agent runs them from your words. All commands start with `python3 skills/whatsnext/scripts/whatsnext.py`.

| Command | Use |
|---|---|
| `plan list`, `plan next`, `plan check` | See the plan |
| `plan start <id>`, `plan keep <id>`, `plan put-back <id>` | Move an item |
| `plan done <id> --verify "<cmd>"` or `--evidence "<text>"` | Mark done |
| `progress new/next/stamp/show/list` | Task progress files |
| `progress capture`, `progress resume-note` | Store a plan, print the resume note |
| `handoff verify` | Run the handoff's `Verify:` line and archive the note if it passes |
| `compact-instructions` | Text for `/compact` |
| `doctor` | Check hooks |
| `config show`, `config set --user` | Settings |
| `init`, `install-hooks` | Set up |

Every command takes `--help`.

---

## Known gaps

- **After `/clear`, the resume note may call the handoff "another session's note".** The new session has a new id. The note is marked "read it first" only when its `Task:` matches the active task. With `Task: none`, it never matches. The resume note then shows only a pointer to the handoff. `what's next?` shows the handoff's Next action and open questions whoever wrote it.
- **`what's next?` shows the handoff even if it is old.** Check the written time it prints.
