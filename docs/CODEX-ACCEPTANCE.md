# Cross-agent release acceptance

Run in a disposable git repository with the installed versions. Keep production plans untouched. For local Claude testing, load this checkout with `claude --plugin-dir /path/to/whatsnext`. `wn doctor` prints one status line per agent before you start.

## Status per agent

| Agent | Hooks | Live checklist |
|---|---|---|
| Claude Code | plugin `hooks/hooks.json` | passed (both directions with Codex) |
| Codex | `wn install-hooks --agent codex` | passed (both directions with Claude Code) |
| Gemini CLI | `wn install-hooks --agent gemini` | partial (2026-11-16): hooks load and session start fires; steps 1 to 5 blocked by Google sign-in. Antigravity with AGENTS.md only passed steps 1 to 3 and 5. See the P-78 progress file |
| Cursor | `wn install-hooks --agent cursor` | **not done yet.** Released without a live run (decision 2026-11-16). The adapter is tested only on payloads shaped like Cursor's docs. Open: whether Cursor's `session_id` equals `conversation_id`. Cursor has no prompt hook that adds context, so `wrap up` uses `wn wrap-up-instructions`. |

## Automated coverage

`python3 -m unittest discover -s tests -p test_continuity.py` exercises the command and hook entry points with temporary repositories and representative conversation records for Claude Code and Codex. `tests/test_hook_adapters.py` covers Gemini CLI and Cursor install and hook payloads. Neither runs a live model.

## Before you start, per agent

- **Codex:** review changed hooks in Codex Settings > Hooks (desktop) or `/hooks` (CLI).
- **Gemini CLI:** run `/hooks panel` and confirm the five whatsnext hooks are listed. Hooks run only while `hooksConfig.enabled` is true (the default).
- **Cursor:** save `hooks.json` and restart Cursor if the hooks do not load. Project hooks run only in a trusted workspace.

## Live checklist (steps 1 to 5 for every agent)

Run each step in the agent under test (A). For a handoff step, B is a second agent that already passed (Claude Code or Codex).

1. Create an item whose done means is `test -f result.txt`, approve the displayed work, and start it in A. Complete a preparatory step without creating the file.
2. Confirm the milestone update says completed work, current step, next action, blockers and verification. Type exactly `wrap up`. Confirm HANDOFF.md has the writer's session and task and the eight sections.
3. Open B in the same checkout. Ask "what's next?" Confirm the same item and unfinished step come first, B reads the handoff, and asks before taking over A's claim.
4. Run the saved verification while the file is absent. Confirm the task stays open, the failed check is recorded, and execution stops.
5. Authorize continuing, create the file and run the saved verification. Confirm the task is done, its claim is released, and the next ready item is offered.

Claude Code and Codex only:

6. On a separate active item, compact after a specific user request. Confirm that the request and current step survive. Fork a Codex chat and confirm startup context loads. Interrupt work and end a session; inspect the facts and per-agent observations in `wn doctor`.
7. Import one small approved source plan in Codex. Confirm its exact command and dependencies are retained. Approve a bounded set of ready items and confirm new or blocked items do not run implicitly.

## Evidence

Record agent versions, direction, task IDs, observed outcomes and failures in the release task's progress file. A passing unit suite or an installed-hook report does not complete this live checklist. Hook trust remains a user-controlled setting; this project never silently trusts new hooks.
