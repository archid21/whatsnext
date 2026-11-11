# whatsnext

**One plan, one next step, for every coding agent.**

whatsnext is a plugin for Claude Code and Codex. It keeps a plan checklist, check-offs and a short resume note as plain files in your repository, so a new session, or a second agent, starts from where the last one stopped.

**Status: 0.3.1.** See [New in 0.3.1](#new-in-031).

MIT license · Python 3.9+, standard library only · no database, no background process

## Install

Claude Code:

```
claude plugin marketplace add archid21/whatsnext
claude plugin install whatsnext@whatsnext
```

Codex: from a checkout, run `python3 skills/whatsnext/scripts/whatsnext.py install-hooks`, then review the new hooks in Settings > Hooks (desktop) or `/hooks` (CLI).

## Key steps

1. Say **"set up whatsnext in this repo"** and make a plan.
2. Work. Say **"wrap up"** before you step away or clear the chat.
3. Come back and say **"what's next?"**. You pick up where you left off.

When an item is finished, say **"mark P-13 done"**. It is ticked only if its test command passes.

## Features

| Feature | What it does |
|---|---|
| Set up your plan | `PLAN.md`, a checklist in your repo. "what's next?" shows the first open item. |
| One status call | "what's next?" and "where did we leave off?" run `whatsnext status`: the current item, the handoff, the ready items and any warnings. |
| Start work | "start P-13" asks a few questions, then you run all steps or one at a time. Another agent or session cannot take an item you hold. |
| Two chats in one folder | When another session has work in progress here, Start asks whether to use a new worktree. Each chat resumes its own item. |
| Change the plan | "add an item", "drop P-16", "move P-14 to Later", or import a plan from any spec or task file. |
| Mark done with proof | The item is ticked only when its test command exits 0. Otherwise it stays open with the last 20 lines of output. |
| Save and resume | "wrap up" writes your goal, next step and decisions to `docs/project/HANDOFF.md`. A short resume note loads at session start, after `/clear` and after a compact. |
| Smart compact | The `/compact` text is built from your handoff, so the summary keeps your goal. |
| Auto wrap-up | Opt-in. After 45 idle minutes, your handoff is saved before Claude Code's own idle compact. |
| Task progress files | One file per task: goal, what is done, the exact next step, and a journal of commits and files changed. |
| Tips | Claude Code only. A hint bar teaches the phrases above, one at a time. |
| Claude Code and Codex | Both agents read and write the same plain files. Switching between them is experimental. |

Every feature, how it works, its value and the release that added it: [docs/FEATURES.md](docs/FEATURES.md).

## New in 0.3.1

- **Star ask:** once, after your first verified `mark done`, the tip band asks for a GitHub star. One click stars it with your `gh` sign-in; **No thanks** hides it for good. With rightsize installed, one ask covers both.

## New in 0.3

- **One status call:** `whatsnext status` answers "what's next?" and "where did we leave off?": the current item, the handoff, the ready items and the warnings.
- **Two chats in one folder:** Start asks for a new worktree when another session has work in progress here. Claims and the active task belong to a session.
- **Your own note after `/clear`:** a recent `Task: none` handoff from this branch says "read it first".
- **Safer plan:** claims are atomic locks, a dropped id is never reused, and `plan check` reports blocked-by cycles.
- **Simpler wrap-up in Claude Code:** the reply ends with one `/compact` hint, and a recent handoff steers a new session.

## New in 0.2

- **Edit and import the plan:** `plan add`, `plan drop` and `plan move`, and import a plan from any spec or task file.
- **Run the whole item:** at start, choose to run all steps, then verify and mark done.
- **Stricter proof:** `--verify` runs the item's saved test command. A different command needs your approval, recorded with the evidence.
- **Better resume:** after a compact, the resume note repeats your latest request. `plan next` puts the work in progress in this checkout first.
- **Codex continuity:** `wrap up`, forked chats, interruptions and session end now work in Codex. `doctor` shows which hooks each agent has actually run.
- **Opt-in auto wrap-up, a tip bar and a welcome table** after install.

**New here? Read the [user guide](docs/GUIDE.md):** what to say to save a session, resume it, pick work and mark it done.

---

## The problem: every session starts blank

A coding agent forgets between sessions. So you pay in one of three ways:

- **You re-explain.** What was done, what is left and which branch it lives on.
- **Two agents take the same item.** Nothing says who has it.
- **"Done" is a claim.** The agent says the tests pass; no one ran them.

A compact does not fix this. It keeps whatever the model thinks matters, which may not be your goal or your rules.

## What you get

**A plan every agent reads.** `PLAN.md` is a checklist in your repository. `plan next` shows what is next; `plan start` asks a few questions first and refuses an item another agent has checked out. A claim is a lock on one machine: of two agents requesting the same item at once, only one gets it.

**"Done" means a command passed.** `plan done P-13 --verify` runs the backticked command saved in the item (when it has exactly one); with several, pass one with `--verify CMD`. Any command that matches a backticked part (exact text, including whitespace) runs the matched saved command. Any other command requires an explicit approved `--override-reason`, recorded with the evidence. Exit 0 ticks the item. Anything else leaves it open and saves the last 20 lines of output. An item no command can check is ticked with `--evidence` and shows as `done*`, so you can tell the two apart.

**Resume where you stopped.** At session start, after `/clear` and after a compact, a note of at most 1,200 characters says what is done, what is next, which test command to run and what changed since the note was written. It warns when it is over 7 days old. With no active task, a handoff note from the last 24 hours with `Task: none` adds its goal and next action.

**A handoff on one prompt.** Type `wrap up`. The agent writes the goal, next action, decisions, constraints and open blockers to `docs/project/HANDOFF.md`. The next session reads it first, but only when the note is its own or belongs to its task, so two agents in one repository do not read each other's.

**A compact that keeps your goal.** `compact-instructions` builds the `/compact` text from that handoff, so the summary keeps what you wrote down: goal, next action, decisions, constraints.

**Works in Claude Code and Codex.** Each agent reads and writes the same plain files. *Experimental:* switching between agents on one plan, or running two at once, has not been extensively tested. See [Known limits](#known-limits).

**Nothing hidden.** Everything is a Markdown or JSON file you can read and edit. Recording a session event (time, commit, branch, files changed) uses no model call.

## Where it fits

whatsnext does plan, check-off and handoff in one repository. It does not remember facts across projects, search past conversations or write decision records. Established tools do that (memory plugins such as claude-mem and Mem0, and adr-kit for decision records), and whatsnext does not replace them. Use it next to them, or alone if a plan and a handoff are all you need.

| | Rules file only (`CLAUDE.md`, `AGENTS.md`) | Memory plugin | Handoff-only plugin | whatsnext |
|---|---|---|---|---|
| What it keeps | Rules you write | Facts and summaries from past sessions | One handoff note per session | Plan, progress per task, handoff |
| Recording needs a model call | No | Usually | Yes, the agent writes the note | Only the handoff note (the journal needs none) |
| Check-off proved by a command | No | No | No | Yes |
| Stops two agents taking one item | No | No | No | Yes, on one machine |
| Works in Claude Code and Codex | Yes | Varies | Mostly Claude Code | Yes\* |

\* Switching between agents on one plan, or running two at once, is experimental: it has not been extensively tested (see [Known limits](#known-limits)).

*Based on a market check dated 2026-11-04 ([docs/project/research/groundwork-vs-memory-plugins.md](docs/project/research/groundwork-vs-memory-plugins.md)). The rows describe each kind of tool in general; check a specific tool before you rely on a cell.*

## Better with rightsize

**whatsnext delivers more for you when used along with [rightsize](https://github.com/archid21/rightsize).** rightsize is a Claude Code plugin for the cost side of a session: it picks the model and effort for each prompt, and watches your prompt cache and usage windows. It decides *when* to wrap up or compact. whatsnext decides *what* the handoff and the compact keep, and writes the files.

Each works alone. A ★ marks where whatsnext does more because rightsize is there.

| whatsnext feature | whatsnext alone | With rightsize |
|---|---|---|
| Wrap-up handoff | You type `wrap up` when you remember it | ★ rightsize sends `wrap up` once before a big session's cache goes cold (the **save a handoff** setting), so a handoff exists without you asking |
| Compact an open session | You paste the `/compact` text from `compact-instructions` | ★ rightsize's **Compact now** button, shown at 40 to 90% of the context window and near your 5-hour limit, runs `/compact` with whatsnext's text. It compacts only when you press it |
| What a handoff or compact costs | Not shown | ★ The band and `/rightsize report` price it, in dollars on an API key or as a share of your window on a subscription |
| Plan, check-off, progress, resume note | Works | Same |

*These rightsize behaviors need rightsize 0.9.0 or later. whatsnext does not need rightsize for anything it does.*

## First run

The first time a session starts after install, whatsnext shows a table of what it does (the feature, what it does in plain words, how it works) and a short diagram of how plan, handoff, compact and resume fit together. It shows once. See it again with `/whatsnext-welcome` in Claude Code, or `whatsnext welcome`.

## Tips

In Claude Code (terminal and desktop app only), a tip band above the prompt teaches the three phrases that matter: `wrap up`, `what's next?` and `mark P-13 done`. It shows one tip at a time, only when the tip applies, and never at startup. **Next tip** moves on, **Stop tips** hides the band for good, and `/whatsnext-tips` brings it back. Once, after your first verified `mark done`, the band also asks for a GitHub star. See [the guide](docs/GUIDE.md#tips).

## Known limits

- **Using more than one agent on a plan is experimental.** Handing a plan from one agent to another works through the files, but it has not been extensively tested.
- **Claims lock one machine only.** Of two agents asking for the same item at once on one machine, only one gets it. Agents in separate clones or on other machines do not see each other's claims.
- **In Codex's default sandbox,** a claim falls back to `.whatsnext/claims/` when `.git` is read-only. Sibling worktrees can read it when accessible; separate clones cannot.
- **Agents can skip the commands.** In our Codex runs the agent sometimes edited `PLAN.md` by hand or mistyped the script path. `plan check` finds items ticked without evidence.
- **Codex support is new.** Run `install-hooks`, trust the hooks in `/hooks`, and expect some rough edges. Plan capture on Codex may stop working after a Codex update (ADR-0005).

## What it never does

- It never pushes, and never creates a remote repository.
- It starts no model call of its own. (`wrap up` uses your open session to write the note.)
- Its `init` changes only `PLAN.md`, `.whatsnext/`, one line in `.gitignore` and one marked block in `AGENTS.md`. `init --dry-run` prints the plan and writes nothing; `init --undo` removes the block.
- Outside the repository it writes only `~/.config/whatsnext/` (your settings, on `config set --user`) and, on `install-hooks`, Codex's `hooks.json` and one skill link in `~/.agents/skills/`. Full list: [What it touches](docs/WHAT-IT-TOUCHES.md). Security: [SECURITY.md](SECURITY.md).

## Try it

From a checkout, in a git repository:

```
python3 skills/whatsnext/scripts/whatsnext.py init --dry-run
python3 skills/whatsnext/scripts/whatsnext.py status --json
python3 skills/whatsnext/scripts/whatsnext.py plan next
python3 skills/whatsnext/scripts/whatsnext.py plan done P-13 --verify "python3 -m unittest discover -s tests"
```

Claude Code loads `hooks/hooks.json` with the plugin. For Codex, run `install-hooks` (it also links the skill into `~/.agents/skills/whatsnext`), then review changed hooks in Settings > Hooks (desktop) or `/hooks` (CLI).

---

## Reference: every feature


- **Plan:** list the plan items, show what is next, and start an item. Start asks a few questions first (takeover, done means, uncommitted changes, the item already in progress, and the branch). An agent does not start an item another agent has checked out.
- **Status:** `whatsnext status` (`--json` for data) answers "what's next?" and "where did we leave off?" in one call: the current item with its step, next action and blockers; the handoff note and whether to read it first; up to 3 ready items with the recommended one; and every warning from `plan check` and stale checkouts, with verify-drift warnings folded into one line. It writes nothing.
- **Check off:** `plan done <id> --verify "<cmd>"` runs the command from the project root. Exit 0 ticks the item and marks it confirmed. Any other result leaves it open and journals the last 20 output lines. `--evidence "<text>"` ticks an item that no command can check; it shows as `done*` (checked by a person, not verified).
- **Progress:** create and stamp a progress file per task, show it, and print the resume note. Every progress file starts with `format: 2`. Its header has a Note trust mark: `confirmed`, `auto` (a model's guess) or `facts` (written by the hooks from git). `progress next <id> "<text>"` sets the Next action as confirmed. With `--auto`, a guess never replaces a confirmed Next action; it goes under `## Since wrap-up`.
- **Facts journal:** the Stop, PreCompact and SessionEnd hooks add one line per event to `docs/project/progress/journal/<item>.md`: time, event, commit, branch, dirty file count and files changed. No model call. Per-session state lives in the git-ignored `.whatsnext/sessions/`; SessionStart removes a session's files once none has changed for 14 days ([ADR-0018](docs/decisions/ADR-0018-prune-session-files.md)).
- **Resume note:** `progress resume-note` prints it, and the session-start hook adds it. Its first line is `continue <id> <title> (branch …, step N of M)`. It then lists `Done:`, `Next:`, a `Run` line with a safe test command, and `Since the note` (new commits and dirty files). It warns when the note is over 7 days old, and its last line gives the Note mark and age. It stays under 1,200 characters.
- **Plan capture:** store a plan-mode plan in `docs/project/plans/` word for word, and write at most 20 of its steps into the task's progress file. The continue line says `plan shown` or `plan used without approval` when the plan is not approved. See [ADR-0006](docs/decisions/ADR-0006-plan-capture.md).
- **Wrap up:** when the open session gets the exact prompt `wrap up`, the UserPromptSubmit hook tells the agent to write the handoff note to `docs/project/HANDOFF.md`, overwriting it. A `paths.handoff` setting or a line `Handoff: <path>` in `AGENTS.md` names another path. The note starts with `Session: <id>`, `Task: <id or none>` and `Written: <UTC>` lines under `# Handoff`, then has `## Goal`, `## Next action` (ending with a `Verify:` line), `## State` (dated in Pacific time), `## What changed`, `## Decisions`, `## Constraints` and `## Open questions and blockers`. An older note with `## Open questions` is still read. In Claude Code the agent ends its reply with `Handoff written: <path>` and one line that says to run `/compact` (the handoff is added to the compact for you) or to press New session or Clear and continue: the band above the prompt shows those buttons until the next prompt ([ADR-0024](docs/decisions/ADR-0024-start-fresh-after-wrap-up.md)). Codex gets the same ending plus a one-line `/compact <text>` (the prompt shows it with a slot for each section), because Codex ignores the PreCompact hook. The person does nothing else. See [ADR-0019](docs/decisions/ADR-0019-wrap-up-ending-and-recent-handoff.md). At Stop, whatsnext records the `session.wrapup` event and a `wrap-up` journal line, writes the sidecar `.whatsnext/sessions/<session>.handoff.json` (`sha256`, `path`, `written_epoch`), and copies the note's Next action into the task's progress file as `auto` (it never replaces a confirmed one; it goes under `## Since wrap-up`). See [ADR-0008](docs/decisions/ADR-0008-wrap-up-and-handoff.md).
- **Session-aware handoff:** a note is fresh for a session only when that session's sidecar exists, its SHA-256 is the file's, and no turn came after the file was written. Any other note is *foreign* (another session wrote it, it was edited since, or it predates the sidecar). A foreign note is never carried into a compact: the text says another session wrote it and gives the path. The resume note adds `Handoff: <path> (read it first)` when the note's `Session:` is this session or its `Task:` is the active task, else `Handoff: <path> (another session's note)`. When a related note has a Next action, the `Next` line shows the newer of it and the progress file's Next, labeled `Next (confirmed <UTC>)` or `Next (handoff <UTC>)`; without one it stays `Next:`.
- **Compact:** `compact-instructions` prints the text for `/compact` in an open session, built from the handoff note. `--json` also returns a one-line `compact_line`. A note another session wrote is never carried into a compact.
- **Init:** `whatsnext init` (git repositories only) creates what is missing: `PLAN.md`, `.whatsnext/config.json`, the progress and journal folders, the `.whatsnext/sessions/` line in `.gitignore`, and a block in `AGENTS.md` between `<!-- whatsnext:start -->` and `<!-- whatsnext:end -->`. `--dry-run` prints the plan and writes nothing. `--undo` removes only the `AGENTS.md` block.
- **Hooks:** the resume note at session start, after `/clear` and after compaction; plan capture when the agent shows a plan; the facts journal. Claude Code loads `hooks/hooks.json` with the plugin. For Codex, run `install-hooks` (it also links the skill into `~/.agents/skills/whatsnext`), then review changed hooks in Settings > Hooks (desktop) or `/hooks` (CLI). See [ADR-0005](docs/decisions/ADR-0005-hooks-and-journal.md).

Commands: `status`, `plan`, `progress`, `config show`, `config set --user`, `init`, `install-hooks` and `compact-instructions`. The script is `skills/whatsnext/scripts/whatsnext.py`.

```
python3 skills/whatsnext/scripts/whatsnext.py plan next
python3 skills/whatsnext/scripts/whatsnext.py plan done P-13 --verify "python3 -m unittest discover -s tests"
python3 skills/whatsnext/scripts/whatsnext.py progress new P-13 --title "Add login"
python3 skills/whatsnext/scripts/whatsnext.py progress next P-13 "Write the login tests"
python3 skills/whatsnext/scripts/whatsnext.py progress capture --status shown --file plan.md
python3 skills/whatsnext/scripts/whatsnext.py init --dry-run
python3 skills/whatsnext/scripts/whatsnext.py install-hooks --dry-run
python3 skills/whatsnext/scripts/whatsnext.py config set --user plan.staleAfter 2h
```

**Settings.** `config show` prints every effective setting with its layer. `config set --user <key> <value>` writes one setting to the user layer (`~/.config/whatsnext/config.json`), after checking the key and value type against `skills/whatsnext/schemas/config.schema.json`. It refuses an unknown key (exit 2), never overwrites a user file that is not valid JSON, and prints the effective value after (a project setting still wins and the line says so). Values: `true` or `false` for a boolean, digits for an integer, text for a string or enum.

**Compact hand-off (for another plugin).** To compact an open session, run `python3 skills/whatsnext/scripts/whatsnext.py compact-instructions --session <id> --json`. It prints JSON with:

- `project`: true when whatsnext acts in the folder (the progress module is on and `.whatsnext/` or the entry file exists; the same test the hooks use). When it is false, `wrap up` is a plain prompt.
- `wrap_up_first`: true when this session has no fresh handoff note: it is missing, foreign, or older than the session's last turn.
- `wrap_up_state`: `requested` (the `wrap up` prompt came and Stop has not run yet), `written` (this session's note is fresh) or `none`.
- `handoff`, `handoff_exists` and `handoff_foreign` (true when another session wrote the note, or none did).
- `wrap_up_prompt` (`wrap up`), `compact_prompt` (`/compact <instructions>`) and `instructions`. A foreign note is left out of `instructions`, which names its path instead.
- `compact_line`: the finished one-line `/compact <text>` built from this session's note (Goal 200, Next 300, Constraints 600, Decisions 400, Blockers 300 characters, at most 1,800 in all), or `null` when there is no note of this session.
- `session_found`.

When `wrap_up_first` is true, submit the prompt `wrap up`, wait for that turn to end (`wrap_up_state` is then `written`), and run the command again, because the instructions include the note. Then submit `compact_prompt` (or pass `instructions` to the harness's own compact call). Without `--json` the command prints only the instruction text.

## Where it came from

whatsnext began as the planning part of Groundwork, a separate project that is now retired. whatsnext is the only plugin and owns the name. Decision records, ground rules and presets are not part of it; `CLAUDE.md`, `AGENTS.md` and adr-kit cover them. Scope: [ADR-0001](docs/decisions/ADR-0001-scope.md).

## Tests

Standard library only. From the repository root:

```
python3 -m unittest discover -s tests
```

The tests create temporary git repositories and a temporary HOME, so your own config and repositories are not touched.

## Layout

| Path | What it holds |
|---|---|
| `.claude-plugin/plugin.json` | Plugin manifest |
| `skills/whatsnext/SKILL.md` | The skill: commands and the Start flow |
| `skills/whatsnext/scripts/whatsnext.py` | The command-line entry point |
| `skills/whatsnext/scripts/wn/` | The library: plan, claims, progress files, the facts journal, the resume note, wrap up, compact, session files, `init`, config, backends and redaction |
| `hooks/hooks.json` | Claude Code hooks: session start, plan capture, `wrap up`, Stop, PreCompact and SessionEnd |
| `skills/whatsnext/schemas/config.schema.json` | The settings schema |
| `tests/` | Unit tests (`fixtures.py` holds the shared test bases) |
| `docs/decisions/` | The current decisions, [index](docs/decisions/README.md) |

## Execution and Codex continuity

`what's next?` recommends current work before a new item and flags a handoff that references completed work. The agent reports completed work, current step, next action, blockers and verification at meaningful milestones. “Run all steps” covers one task; “run the ready plan items” approves an explicit set of tasks.

Codex supports `wrap up`, request carryover after compaction, fork startup, session-end and interruption facts. `doctor` separates configured hooks from observed behavior for each agent. Automated two-way workflow coverage is in `tests/test_continuity.py`; live release validation is tracked in [the acceptance checklist](docs/CODEX-ACCEPTANCE.md). Tips, idle wrap-up and compact-summary comparison remain Claude-only.
