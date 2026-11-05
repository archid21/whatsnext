# ADR-0005: Hooks do the bookkeeping, record facts only, and never break a session

- **Date:** 2026-11-05T18:40Z
- **Status:** accepted (user), 2026-11-05

## Decision

1. **One hook command.** `whatsnext.py hook <event> [--agent claude-code|codex]` reads the agent's hook JSON on stdin. On any error or bad argument it prints nothing and exits 0. Outside a whatsnext project (ADR-0007) every event does nothing.
2. **Events.** `session-start` prints the resume note (at start, after `/clear`, after a compact). For Codex it adds one line naming the command to run (`python3 <script> <command>`), because Codex has no plugin folder to resolve `whatsnext` against; the line is injected, never written to a file. `plan-shown` and `plan-approved` (Claude Code, before and after `ExitPlanMode`) and `prompt-submit` capture plans (ADR-0006). `prompt-submit` also answers the exact prompt `wrap up` (ADR-0008). `stop`, `pre-compact` and `session-end` write the facts journal.
3. **Facts journal.** Each Stop, PreCompact and SessionEnd adds one line (at most 200 characters) to `docs/project/progress/journal/<id>.md`: UTC time, event, short commit, branch, dirty file count and files changed since the last line. It refreshes the progress file header with the `facts` mark. No model call, no transcript reading. It does nothing outside git or without an active task. Per-session state lives in the git-ignored `.whatsnext/sessions/`.
4. **Install.** Claude Code loads `hooks/hooks.json` with the plugin. For Codex, `install-hooks [--user|--project] [--dry-run] [--remove]` merges whatsnext's entries next to existing hooks, changes only entries whose command is `whatsnext.py hook <event> --agent codex`, and needs the person to trust them in Codex's `/hooks`. With `--user` it also links the skill folder into `~/.agents/skills/whatsnext` so Codex can find the commands (Codex has no plugin loader); it never replaces a file, folder or link it did not make, and `--remove` deletes only its own link.
5. **Order is not assumed.** whatsnext never relies on running before or after another plugin's hook. Its Stop hook reads only its own files and git.
6. **Codex plans.** At Stop the hook reads the `Plan` item from `transcript_path`: a plan for this turn is `shown`; a plan followed by a turn in default mode is `approved`. An unreadable format is skipped without a message.

## Why

Facts the hooks can read from git are always true, cost nothing and never go stale, so "walking away is safe" does not depend on a model or on the person typing anything.

## Trade-offs

- The journal says what changed, not why.
- Codex's transcript format has no stability promise; plan capture on Codex may stop working after an update.
- Journal lines are committed, so everyone with the repository can read them.
