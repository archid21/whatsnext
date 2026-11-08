# whatsnext user guide

What you can do with whatsnext, and the words to say. Each section gives the action first.

You talk to your agent (Claude Code or Codex). The agent runs the commands. The few commands you may run yourself are marked **Run it yourself**.

Contents: [First run](#first-run) · [Save and resume](#save-and-resume-a-session) · [Pick work](#pick-and-start-work) · [Change the plan](#change-the-plan) · [Bring a plan](#bring-a-plan-from-another-tool) · [Mark done](#mark-work-done) · [Track a task](#track-a-task) · [Compact](#compact-a-long-session) · [Several agents](#use-more-than-one-agent) · [Health check](#check-that-it-works) · [Settings](#change-a-setting) · [Tips](#tips) · [Set up a repo](#set-up-a-repository) · [Known gaps](#known-gaps)

---

## First run

The first time a session starts after install, whatsnext shows a table of what it does: the feature, what it does in plain words, and how it works. The five rows to learn first (set up your plan, start work, change the plan, mark done with proof, save and resume) come first, then a short diagram of how they fit together. It shows once, in any folder, and never again: it writes a marker file, `welcomed`, next to your user settings (`~/.config/whatsnext/`).

To see it again: type `/whatsnext-welcome` in Claude Code, or run `python3 skills/whatsnext/scripts/whatsnext.py welcome`.

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

**What `what's next?` does at step 4.** It shows the handoff's Next action and open questions, with the file path and the time it was written. It flags references to completed tasks and prefers current plan/progress over a conflicting handoff. Current work comes first; otherwise it offers ready items from the plan checklist (`PLAN.md`). If the plan has no open items, it says so and still shows the handoff.

**Use `wrap up` before:** closing the laptop, switching agent, ending the day, or a `/clear`.

---

## Pick and start work

| You say | The agent does |
|---|---|
| `what's next?` | Shows current work and its unfinished step first, then ready alternatives. The recommended one is first. Items idle for too long are marked stale. |
| `start P-13` | Starts that item. |
| `show the plan` or `who has what?` | Lists every item, its status and who holds it. |
| `check the plan` | Finds items with no done means or no evidence, and duplicate ids. |

**Start asks questions first.** It asks one at a time, only when needed:

1. Someone else has the item: take it over?
2. The item has no done means: what proves it done?
3. You have uncommitted changes: commit first?
4. Another item is in progress: mark it done, keep it, or put it back?
5. Branch: make a branch, stay, or make a worktree? Say "always do this" to stop being asked.

Nothing is marked in progress until every answer is in. After Start, the agent restates the goal and done means, lists 3 to 5 steps, and asks once how to go on:

- **Run all steps, then verify and mark done** (recommended). You approve once. The agent works the steps in order, then runs the item's done means command. If it passes, the item is confirmed done. If it fails, the agent stops, shows you the last 20 lines of output, and leaves the item open.
- **Go step by step.** The agent does one step, shows it, and waits for your OK.
- **Change the steps.** You edit the list first.

A run also stops when a step needs a permission you have not given, a decision only you can make, or a failure the agent cannot fix. It tells you which step and why. It never skips the verify step.

**Status updates.** After a meaningful step, the agent reports completed work, current step, next action, blockers and verification. It saves these in the progress file for the next chat. A blocked task stays visible until it can resume.

**Run the plan.** “Run all steps” covers one item. To work through several items, say “run the ready plan items.” The agent shows the item IDs and completion commands, obtains approval once (or uses approval you already gave), and executes only that set. It stops at failed verification, blockers, changed checks, missing permission or a decision. New items are outside that approval.

**Keep or put back a stale item.** Say `keep working on P-12` to reset its idle clock. Say `put P-12 back` to release it for any agent. The agent updates its progress file first.

---

## Change the plan

| You say | The agent does |
|---|---|
| `add an item: <what>` | Asks what proves it done (a command is best), then adds it with the next free id. Say which section: Now, Next or Later. The default is Next. |
| `drop P-16` | Removes it. It refuses an item in progress, or one another open item waits for. |
| `move P-14 to Later` | Moves it to the end of that section. You can also say "before P-13" or "after P-15". |

The agent asks you before it changes the plan, and uses these commands instead of editing `PLAN.md` by hand, so the line is always in the right format and an id is never reused. Run it yourself: `python3 skills/whatsnext/scripts/whatsnext.py plan add "Export CSV" --done-means "python3 -m unittest" --section Next`.

---

## Bring a plan from another tool

Say `import the plan from <path>`. The path can be a file or a folder: a spec, a task list, a folder of ticket files, a design plan. Plans from Superpowers, Matt Pocock's skills (`.scratch/` tickets), Spec Kit, OpenSpec and BMAD are all examples; the agent reads whatever you point at, so any other tool works the same way.

The agent turns each task, ticket or story into a plan item, with:

- the next free `P-` id (it never reuses one);
- a done means, taken from a command in the source. If the source has none, the agent asks you once for the whole batch. It does not make one up;
- `blocked by:` for anything the source says depends on another task;
- anything already checked in the source marked as done but not verified.

Before it adds anything, the agent shows you every item with its `blocked by` and its done means command, and waits for your OK, however few items there are. A command in a file from outside is untrusted text, and a verify run executes it as a shell command, so the agent points out any command that is not a plain test or check (it deletes, installs, downloads, uses the network or writes outside the project) and asks whether to keep it. After the import it runs `plan check` and shows you the result.

---

## Mark work done

Say `mark P-13 done`. The agent then picks one of two ways:

- **Proved by a command.** The agent runs `plan done P-13 --verify`, which runs the command saved in backticks in the item's done means. If done means has several backticked parts, the agent passes one with `--verify "<cmd>"`; a command that matches any backticked part (spacing ignored) needs no approval. Any other command requires your approval and `--override-reason`, which is saved with the evidence. A passing command proves only the check it performs; separate manual acceptance criteria must also be completed. The command runs from the project root. Exit 0 ticks the item as **confirmed**. Any failure leaves it open and saves the last 20 lines of output.
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
- Claims in sibling git worktrees are read when those folders are accessible, including Codex fallback claims. Separate clones and machines do not share claims.
- A handoff note is read first only by the session that wrote it, or one working the same task.

This is experimental. See the README's [Known limits](../README.md#known-limits).

For Codex: run `install-hooks`, then review changed hooks in **Settings > Hooks** (desktop) or `/hooks` (CLI). Startup includes forked chats; session-end and interruption also record facts.

---

## Check that it works

**Run it yourself:**

```bash
python3 skills/whatsnext/scripts/whatsnext.py doctor
```

It reports installed hooks separately from runtime observations for each agent in this checkout. Each event is observed or unverified, with its time. A configured hook is not proof that it ran; an observed hook is not proof of an end-to-end handoff. It prints a fix for configuration gaps.

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
| `wrapup.autoIdle` | `false` | Claude Code only: say `wrap up` for you once, 45 minutes after your last turn, before Claude Code's own idle compact (see below) |
| `paths.handoff` | `docs/project/HANDOFF.md` | Where the handoff note is written |

**Auto wrap-up when you step away.** Set `wrapup.autoIdle` to `true` and, in Claude Code, the plugin sends `wrap up` once when a session has been idle 45 minutes. Claude Code's own idle compact (it runs when you have been away about an hour, so the prompt cache does not expire) came 54 minutes after the last request in both of our tests, so the wrap-up goes first and the handoff note exists before the compact. It sends `wrap up` only when all of these hold:

- the folder is a whatsnext project and this session has no fresh wrap-up;
- the context is at or above `CLAUDE_CODE_IDLE_COMPACT_MIN_TOKENS` (default 200,000, never under 100,000);
- Claude Code's auto-compact is on for the session (the `/config` Auto-compact toggle), and its `idleCompaction` setting is not `false`.

The plugin also lets the agent write the handoff note without asking you, but only while a `wrap up` is open and only for that one file (a permission hook; it changes none of your settings), so a wrap-up you are not there to answer does not stall on a prompt.

It sends it once. It does not send it again until you send a prompt yourself. When you come back, you will see one extra turn that wrote the handoff note.

---

## Tips

A short tip band shows above the prompt in Claude Code, in the terminal and the desktop app. It does not show in Codex, VS Code or on mobile. One tip shows at a time, only when it applies:

- **`wrap up`:** after a compact, or after 20 turns in one session.
- **`what's next?`:** after your first turn, when no task is active.
- **`mark P-13 done`:** after a plan item's `--verify` command passes.
- **Turn on auto wrap-up:** at the same moments as `wrap up`, when Claude's auto-compact is on, the context is big, and `wrapup.autoIdle` is off. The tip says Claude's auto-compact keeps what it thinks matters, not your goal, so a handoff saved first keeps your goal and next step. **Turn on** sets `wrapup.autoIdle` for you (in your user settings, `~/.config/whatsnext/config.json`) and says so. **No thanks** hides this tip for good.
- **`wrap up` before `/clear` or `/compact`:** the same moments, when Claude's auto-compact is off. Nothing saves your goal for you then, so the tip says to type `wrap up` first. It has no setting to turn on.

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
| `plan add`, `plan drop <id>`, `plan move <id>` | Change the plan |
| `plan done <id> --verify "<cmd>"` or `--evidence "<text>"` | Mark done |
| `progress new/next/stamp/show/list` | Task progress files |
| `progress capture`, `progress resume-note` | Store a plan, print the resume note |
| `handoff verify` | Run the handoff's `Verify:` line and archive the note if it passes |
| `compact-instructions` | Text for `/compact` |
| `doctor` | Check hooks |
| `welcome` | Print the table of what whatsnext does |
| `config show`, `config set --user` | Settings |
| `init`, `install-hooks` | Set up |

Every command takes `--help`.

---

## Known gaps

- **After `/clear`, the resume note may call the handoff "another session's note".** The new session has a new id. The note is marked "read it first" only when its `Task:` matches the active task. With `Task: none`, it never matches. The resume note then shows only a pointer to the handoff. `what's next?` shows the handoff's Next action and open questions whoever wrote it.
- **`what's next?` shows the handoff even if it is old.** Check the written time it prints.

## Compatibility checks

Automated workflow tests exercise both Codex → Claude Code and Claude Code → Codex: start, wrap up, reload the same task, fail verification without completing it, then pass the saved check. They also cover compaction carryover, fork startup, interruption and session-end recording. These are hook/command tests, not a claim that a live model always follows the skill. Before a release, run the [live acceptance checklist](CODEX-ACCEPTANCE.md) on the installed versions.

Codex now supports manually installed plugins with lifecycle hooks ([official packaging documentation](https://developers.openai.com/plugins/build/plugins#bundled-mcp-servers-and-lifecycle-hooks)). This repository's documented checkout install uses `install-hooks` and a skill link; it does not rely on native plugin discovery. Do not load the Claude hook file unchanged in Codex: its handlers explicitly identify Claude Code. Avoid installing both hook sources, which would run bookkeeping twice.
