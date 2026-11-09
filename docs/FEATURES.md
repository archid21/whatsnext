# Features

Every whatsnext feature: what it is, how it works and what it gives you.

Current release: 0.3.0

**Since** is the release that added the feature. `Unreleased` means it is on `main` but not in a release yet.

## Update this file at each release

1. Add a row for each new feature, with **Since** set to `Unreleased`, when the feature lands.
2. At release, change every `Unreleased` to the new version (for example `0.3`), and set `Current release:` above to the version in `.claude-plugin/plugin.json`.
3. Run `python3 -m unittest tests.test_features`. It fails when `Current release:` is not the plugin version, or when no row has that version's **Since**.

## Plan

| Feature | How it works | Value | Since |
|---|---|---|---|
| Plan checklist | `PLAN.md` in the repository is a checklist of items with ids such as `P-13`. "what's next?" (`plan next`) shows the first open item that is not blocked. | Every agent and every session reads one list of work, so nobody has to re-explain what is left. | 0.1 |
| Start an item | "start P-13" (`plan start`) asks about takeover, done means, uncommitted changes, work in progress and the branch, then claims the item. | Work starts with the goal and the finish line written down. | 0.1 |
| Claims | `plan start` writes a claim file. It is created with O_EXCL and a per-item lock, so of two agents asking at once only one gets the item. A released claim stays released. | Two agents never take the same item on one machine. | 0.3 |
| Edit the plan | "add an item", "drop P-16", "move P-14 to Later" (`plan add`, `plan drop`, `plan move`). | Change the plan by asking, without hand-editing Markdown. | 0.2 |
| Import a plan | Reads any spec or task file and writes its steps as `PLAN.md` items. | Start from the plan you already have. | 0.2 |
| Permanent ids | `plan drop` records the id as retired in `PLAN.md`; `plan add` never reuses it. | An id in a commit, note or journal always means one item. | 0.3 |
| Plan check | `plan check` finds items ticked without evidence, verified items with newer commits, and blocked-by cycles. `plan next` says why nothing is ready. | Problems in the plan show up before they waste a session. | 0.1 (cycles: 0.3) |
| Status in one call | `whatsnext status` (`--json`) returns the current item, the handoff and whether to read it first, the ready items and every warning. | "What's next?" and "where did we leave off?" take one command, and the answer is the same for every agent. | 0.3 |
| Parallel sessions in one folder | When another session has an item in progress in this checkout, Start asks: new worktree (recommended) or stay with a warning. Claims and the active task belong to a session. `plan.concurrentStart` saves the answer; "always worktree" is offered after two equal answers. | Two chats in one folder no longer take over each other's item or mix commits by accident. | 0.3 |
| Run all steps | At start, choose to run every step of the item, then verify and mark it done. "run the ready plan items" approves a named set of items. | Hand over a whole item or batch and come back to a result. | 0.2 |

## Check off

| Feature | How it works | Value | Since |
|---|---|---|---|
| Mark done with proof | `plan done P-13 --verify` runs the item's saved test command from the project root. Exit 0 ticks the item; any other result leaves it open and journals the last 20 output lines. | "Done" means a command passed, not that an agent said so. | 0.1 |
| Stricter verify | A command other than the saved one needs an approved `--override-reason`, recorded with the evidence. Matching keeps shell semantics. | An agent cannot swap in an easier test. | 0.2 |
| Manual check-off | `--evidence "<text>"` ticks an item no command can check. It shows as `done*`. | Manual checks are allowed but never look like verified ones. | 0.1 |
| Code state on verify | The evidence records the commit; `plan check` flags the item after new commits. | You know when a check-off is stale. | 0.1 |

## Save and resume

| Feature | How it works | Value | Since |
|---|---|---|---|
| Wrap up | The prompt `wrap up` makes the agent write goal, next action, decisions, constraints and blockers to `docs/project/HANDOFF.md`. In Claude Code the reply ends with one line saying to run `/compact` or `/clear`. | One prompt saves where you are before you step away. | 0.1 (ending: 0.3) |
| Resume note | At session start, after `/clear` and after a compact, a note of at most 1,200 characters gives done, next, a test command and what changed since. It warns when the note is over 7 days old. | A new session starts where the last one stopped. | 0.1 |
| Session-aware handoff | A handoff is used only by the session that wrote it or the task it names; any other note is marked as another session's. | Two agents in one repository do not read each other's notes as their own. | 0.1 |
| Recent handoff steers a new session | With no active task, a handoff from the last 24 hours with `Task: none` adds its goal and next action to the resume note. | A fresh session picks up loose work, not only plan items. | 0.3 |
| Own handoff after /clear | The handoff note has a `Branch:` line. A `Task: none` note from this branch, written within `plan.staleAfter`, says "read it first" even after `/clear` gives a new session id. | After `/clear` you get your own last note back, not a "another session's note" pointer. | 0.3 |
| Repeat the latest request | After a compact, the resume note repeats your latest request; `plan next` puts work in progress in this checkout first. | The agent keeps doing what you asked, not what the summary guessed. | 0.2 |
| Smart compact | `compact-instructions` builds the `/compact` text from the handoff; `--json` gives a one-line `compact_line` for other plugins. | The compact keeps your goal and decisions. | 0.1 |
| Auto wrap-up | Opt-in. After 45 idle minutes, the handoff is saved before Claude Code's own idle compact. | No lost context when you forget to wrap up. | 0.2 |

## Progress and history

| Feature | How it works | Value | Since |
|---|---|---|---|
| Task progress files | One file per task in `docs/project/progress/`: goal, what is done, the exact next step, with a trust mark (`confirmed`, `auto`, `facts`). | Each task carries its own state; a guess never replaces a confirmed next step. | 0.1 |
| Facts journal | Stop, PreCompact and SessionEnd hooks add one line per event: time, commit, branch, dirty files, files changed. No model call. | A free, exact record of what happened in each session. | 0.1 |
| Plan capture | A plan-mode plan is stored word for word in `docs/project/plans/`, with up to 20 steps in the progress file. | The approved plan survives the session. | 0.1 |
| Session file pruning | SessionStart removes a session's state files once none has changed for 14 days. | `.whatsnext/sessions/` does not grow forever. | 0.3 |
## Setup and agents

| Feature | How it works | Value | Since |
|---|---|---|---|
| Init | `whatsnext init` creates `PLAN.md`, `.whatsnext/`, one `.gitignore` line and one marked `AGENTS.md` block. `--dry-run` and `--undo` are available. | Set up in one command, with a small, reversible footprint. | 0.1 |
| Settings | `config show` and `config set --user`, checked against a schema. | Change behavior safely; unknown keys are refused. | 0.1 |
| Codex hooks | `install-hooks` adds the hooks to Codex and links the skill. | The same plan and notes work in Codex. | 0.1 |
| Codex continuity | `wrap up`, forked chats, interruptions and session end work in Codex. | Switch agents without losing the thread. | 0.2 |
| Doctor | `doctor` shows which hooks each agent has configured and which it has actually run. | Find a broken setup in one command. | 0.2 |
| Welcome table | The first session after install shows what whatsnext does; `/whatsnext-welcome` shows it again. | New users learn the three phrases at once. | 0.2 |
| Tips | Claude Code only. A band above the prompt teaches `wrap up`, `what's next?` and `mark P-13 done`, one tip at a time. | Users learn by doing, without reading docs. | 0.2 |
