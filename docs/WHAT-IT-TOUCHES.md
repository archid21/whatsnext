# What whatsnext touches

whatsnext is Python 3.9+, standard library only. It makes no network calls, runs no background process and makes no model call of its own.

## Files it writes in your repository

| Path | What | When |
|---|---|---|
| `docs/project/PLAN.md` (or `paths.plan`) | The plan checklist | `init`, `plan` commands |
| `.whatsnext/config.json` | Project settings | `init` |
| `docs/project/progress/<task>.md` | Task progress file: state, next action, trust marks | `plan start`, hooks, `wrap up` |
| `docs/project/progress/journal/<task>.md` | Facts journal, one line (at most 200 characters) per Stop, PreCompact and SessionEnd | hooks |
| `docs/project/plans/` | Plans captured from plan mode, one file per plan | plan-mode hooks |
| `docs/project/HANDOFF.md` (or `paths.handoff`) | The handoff note | the agent writes it when you type `wrap up` |
| `AGENTS.md` | One block between `<!-- whatsnext:start -->` and `<!-- whatsnext:end -->`, appended, never replacing text | `init`; `init --undo` removes it |
| `.gitignore` | The line `.whatsnext/sessions/` | `init` |
| `.whatsnext/sessions/` (git-ignored) | Per-session state, handoff sidecars, compaction carryover and per-agent hook observations | hooks |

`init --dry-run` prints every change and writes nothing. `init` never overwrites a file.

## Files it writes outside the repository

| Path | What | When |
|---|---|---|
| `<git common dir>/whatsnext/claims` | Soft claims: which session has which plan item. When `.git` cannot be written, `.whatsnext/claims/` (git-ignored) is used instead | `plan start` |
| `~/.config/whatsnext/config.json` (or `$XDG_CONFIG_HOME`) | Your user settings | `config set --user`, and only that |
| `~/.codex/hooks.json` (or `$CODEX_HOME`) | whatsnext's hook entries, next to yours | `install-hooks`, and only that; `--remove` undoes it |
| `~/.agents/skills/whatsnext` | A symlink to this plugin's skill folder, so Codex finds the commands | `install-hooks --user`; never replaces anything it did not make; `--remove` deletes only that link |

## What it reads

- Your repository and git (branch, commit, changed files).
- Claude Code's session transcripts in `~/.claude/projects/` (or `$CLAUDE_CONFIG_DIR`), only for a session's id, working folder and turn times. It does not send them anywhere.
- On Codex, `transcript_path` or a session-id lookup under `$CODEX_HOME/sessions/`: plan items, user/assistant turn times, latest request and in-progress plan steps. Known message records are read locally, never sent anywhere.

## What it runs

- `plan done <id> --verify` runs the single saved completion command. An explicit different command needs a user-approved `--override-reason`. It runs in the repository with a time limit; the agent must obtain approval of commands imported from untrusted files.
- `git`, read-only except what you commit yourself. whatsnext never commits, pushes or changes branches.

## Hooks (Claude Code)

SessionStart, PreToolUse and PostToolUse on `ExitPlanMode`, UserPromptSubmit, Stop, PreCompact and SessionEnd. Each runs `whatsnext.py hook <event>`; on any error it prints nothing and exits 0. Outside a whatsnext project every hook does nothing.

## Remove it

`whatsnext init --undo` removes the `AGENTS.md` block. `install-hooks --remove` removes the Codex entries. Uninstall the plugin to remove the Claude Code hooks. Your plan, progress and handoff files stay; they are plain Markdown.
