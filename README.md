# whatsnext

**One plan, one next step, for every coding agent.**

whatsnext is a plugin for Claude Code and Codex. It keeps a plan checklist, check-offs and a short resume note as plain files in your repository, so a new session, or a second agent, starts from where the last one stopped.

**Status: 0.1.0, the first public release.**

MIT license · Python 3.9+, standard library only · no database, no background process

---

## The problem: every session starts blank

A coding agent forgets between sessions. So you pay in one of three ways:

- **You re-explain.** What was done, what is left and which branch it lives on.
- **Two agents take the same item.** Nothing says who has it.
- **"Done" is a claim.** The agent says the tests pass; no one ran them.

A compact does not fix this. It keeps whatever the model thinks matters, which may not be your goal or your rules.

## What you get

**A plan every agent reads.** `PLAN.md` is a checklist in your repository. `plan next` shows what is next; `plan start` asks a few questions first and refuses an item another agent has checked out. A claim is a note, not a lock: two agents requesting the same item around the same time might both claim it.

**"Done" means a command passed.** `plan done P-13 --verify "<cmd>"` runs your command. Exit 0 ticks the item. Anything else leaves it open and saves the last 20 lines of output. An item no command can check is ticked with `--evidence` and shows as `done*`, so you can tell the two apart.

**Resume where you stopped.** At session start, after `/clear` and after a compact, a note of at most 1,200 characters says what is done, what is next, which test command to run and what changed since the note was written. It warns when it is over 7 days old.

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
| Stops two agents taking one item | No | No | No | Yes, except when both ask around the same time |
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

## Known limits

- **Using more than one agent on a plan is experimental.** Handing a plan from one agent to another works through the files, but it has not been extensively tested.
- **Claims are notes, not locks.** Two agents requesting the same item around the same time might both claim it.
- **In Codex's default sandbox,** a claim is written to `.whatsnext/claims/` because `.git` is read-only there, so another worktree does not see it.
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
python3 skills/whatsnext/scripts/whatsnext.py plan next
python3 skills/whatsnext/scripts/whatsnext.py plan done P-13 --verify "python3 -m unittest discover -s tests"
```

Claude Code loads `hooks/hooks.json` with the plugin. For Codex, run `install-hooks` (it also links the skill into `~/.agents/skills/whatsnext`), then trust the hooks in Codex's `/hooks`.

---

## Reference: every feature


- **Plan:** list the plan items, show what is next, and start an item. Start asks a few questions first (takeover, done means, uncommitted changes, the item already in progress, and the branch). An agent does not start an item another agent has checked out.
- **Check off:** `plan done <id> --verify "<cmd>"` runs the command from the project root. Exit 0 ticks the item and marks it confirmed. Any other result leaves it open and journals the last 20 output lines. `--evidence "<text>"` ticks an item that no command can check; it shows as `done*` (checked by a person, not verified).
- **Progress:** create and stamp a progress file per task, show it, and print the resume note. Every progress file starts with `format: 2`. Its header has a Note trust mark: `confirmed`, `auto` (a model's guess) or `facts` (written by the hooks from git). `progress next <id> "<text>"` sets the Next action as confirmed. With `--auto`, a guess never replaces a confirmed Next action; it goes under `## Since wrap-up`.
- **Facts journal:** the Stop, PreCompact and SessionEnd hooks add one line per event to `docs/project/progress/journal/<item>.md`: time, event, commit, branch, dirty file count and files changed. No model call. Per-session state lives in the git-ignored `.whatsnext/sessions/`.
- **Resume note:** `progress resume-note` prints it, and the session-start hook adds it. Its first line is `continue <id> <title> (branch …, step N of M)`. It then lists `Done:`, `Next:`, a `Run` line with a safe test command, and `Since the note` (new commits and dirty files). It warns when the note is over 7 days old, and its last line gives the Note mark and age. It stays under 1,200 characters.
- **Plan capture:** store a plan-mode plan in `docs/project/plans/` word for word, and write at most 20 of its steps into the task's progress file. The continue line says `plan shown` or `plan used without approval` when the plan is not approved. See [ADR-0006](docs/decisions/ADR-0006-plan-capture.md).
- **Wrap up:** when the open session gets the exact prompt `wrap up`, the UserPromptSubmit hook tells the agent to write the handoff note to `docs/project/HANDOFF.md`, overwriting it. A `paths.handoff` setting or a line `Handoff: <path>` in `AGENTS.md` names another path. The note starts with `Session: <id>`, `Task: <id or none>` and `Written: <UTC>` lines under `# Handoff`, then has `## Goal`, `## Next action` (ending with a `Verify:` line), `## State` (dated in Pacific time), `## What changed`, `## Decisions`, `## Constraints` and `## Open questions and blockers`. An older note with `## Open questions` is still read. The agent ends its reply with `Handoff written: <path>`, one line `/compact <text>` (the prompt shows it with a slot for each section) and "or `/clear` for a fresh start". The person does nothing else. At Stop, whatsnext records the `session.wrapup` event and a `wrap-up` journal line, writes the sidecar `.whatsnext/sessions/<session>.handoff.json` (`sha256`, `path`, `written_epoch`), and copies the note's Next action into the task's progress file as `auto` (it never replaces a confirmed one; it goes under `## Since wrap-up`). See [ADR-0008](docs/decisions/ADR-0008-wrap-up-and-handoff.md).
- **Session-aware handoff:** a note is fresh for a session only when that session's sidecar exists, its SHA-256 is the file's, and no turn came after the file was written. Any other note is *foreign* (another session wrote it, it was edited since, or it predates the sidecar). A foreign note is never carried into a compact: the text says another session wrote it and gives the path. The resume note adds `Handoff: <path> (read it first)` when the note's `Session:` is this session or its `Task:` is the active task, else `Handoff: <path> (another session's note)`. When a related note has a Next action, the `Next` line shows the newer of it and the progress file's Next, labeled `Next (confirmed <UTC>)` or `Next (handoff <UTC>)`; without one it stays `Next:`.
- **Compact:** `compact-instructions` prints the text for `/compact` in an open session, built from the handoff note. `--json` also returns a one-line `compact_line`. A note another session wrote is never carried into a compact.
- **Init:** `whatsnext init` (git repositories only) creates what is missing: `PLAN.md`, `.whatsnext/config.json`, the progress and journal folders, the `.whatsnext/sessions/` line in `.gitignore`, and a block in `AGENTS.md` between `<!-- whatsnext:start -->` and `<!-- whatsnext:end -->`. `--dry-run` prints the plan and writes nothing. `--undo` removes only the `AGENTS.md` block.
- **Hooks:** the resume note at session start, after `/clear` and after compaction; plan capture when the agent shows a plan; the facts journal. Claude Code loads `hooks/hooks.json` with the plugin. For Codex, run `install-hooks` (it also links the skill into `~/.agents/skills/whatsnext`), then trust the hooks in Codex's `/hooks`. See [ADR-0005](docs/decisions/ADR-0005-hooks-and-journal.md).

Commands: `plan`, `progress`, `config show`, `config set --user`, `init`, `install-hooks` and `compact-instructions`. The script is `skills/whatsnext/scripts/whatsnext.py`.

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
| `docs/decisions/` | The ten current decisions, [index](docs/decisions/README.md) |
