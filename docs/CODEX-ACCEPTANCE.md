# Cross-agent release acceptance

Run in a disposable git repository with the installed versions. Keep production plans untouched. Review changed hooks in Codex Settings > Hooks (desktop) or `/hooks` (CLI). For local Claude testing, load this checkout with `claude --plugin-dir /path/to/whatsnext`.

## Automated coverage

`python3 -m unittest discover -s tests -p test_continuity.py` exercises the actual command/hook entry points with temporary repositories and representative conversation records. It covers both directions, verification failure followed by success, active-task selection, handoff conflicts, Codex freshness, compaction request carryover, fork registration, interruption, session end and per-agent diagnostics. It does not run live models.

## Live checklist

For each direction (Codex → Claude Code, then Claude Code → Codex):

1. Create an item whose done means is `test -f result.txt`, approve the displayed work, and start it in the first agent. Complete a preparatory step without creating the file.
2. Confirm the milestone update says completed work, current step, next action, blockers and verification. Type exactly `wrap up`. Confirm HANDOFF.md has the writer's session and task, and Stop records the handoff sidecar.
3. Open the second agent in the same checkout. Ask “what's next?” Confirm the same item and unfinished step come first. Check that the agent reads the related handoff, and asks before taking over another holder's claim.
4. Run the saved verification while the file is absent. Confirm the task stays open, the failed check is recorded, and execution stops.
5. Authorize continuing, create the file and run the saved verification. Confirm the task is done, its claim is released, and the next ready item is offered.
6. On a separate active item, compact after a specific user request. Confirm that the request and current step survive. Fork a Codex chat and confirm startup context loads. Interrupt work and end a session; inspect the corresponding facts and per-agent observations in `doctor`.
7. Import one small approved source plan in Codex. Confirm its exact command and dependencies are retained. Approve a bounded set of ready items and confirm new or blocked items do not run implicitly.

## Evidence

Record agent versions, direction, task IDs, observed outcomes and failures in the release task's progress file. A passing unit suite or an installed-hook report does not complete this live checklist. Hook trust remains a user-controlled setting; this project never silently trusts new hooks.
