# Handoff
Session: c917f1f8-19b0-45f1-9836-930860cc4452
Task: none
Written: 2026-11-16T21:14Z
Branch: main

## Goal
Make whatsnext work in any coding agent (ADR-0027): hook-free mode, `wn` on the PATH, Gemini CLI and Cursor adapters, per-agent doctor and checklist.

## Next action
Pick the next item: run `wn status` and start the recommended one (P-79 tracker sync; also P-72, P-73 in Next) with `wn plan start <id> --agent <name>`.
Verify: `wn plan list` shows the item in progress on a new branch.
If it fails: run `wn plan check` and fix what it reports.

## State
State on Mon 2026-11-16 1:14 PM PST (Pacific): P-75, P-76, P-77, P-78 and P-82 are done and merged into main (last merge 0d07568). P-76, P-77, P-82 verified with `plan done --verify`; P-75 and P-78 are done* (evidence, live runs). Last full suite: OK (P-82 verify, 448 s). Nothing pushed.

## What changed
- 584d5e4 P-75 hook-free mode; 7e05a25 P-76 `wn` link (install-hooks --wn link|skip, --undo); merged 520b16d
- 31fff27 P-77 Gemini CLI and Cursor adapters (install-hooks --agent, hook --agent); merged 189d21e
- 8c42b82 P-78 doctor one line per agent; docs/CODEX-ACCEPTANCE.md per-agent; merged a0a54b9
- d680621 added P-82; 3c1bd76 P-82 plan_status and ask-first line; merged 0d07568
- Live results: docs/project/progress/P-75.md, P-77.md (event map), P-78.md

## Decisions
- Ship without a Cursor live check (user, 2026-11-16); recorded in docs/CODEX-ACCEPTANCE.md and `wn doctor`.
- Cursor has no prompt hook mapped (beforeSubmitPrompt cannot add context); `wrap up` there uses `wn wrap-up-instructions`.
- Gemini/Cursor hooks are optional in doctor: not installed is not a gap.

## Constraints
Standard library only, Python 3.9+. Do not push or create a remote without asking. Run `python3 -m unittest discover -s tests` before reporting done (about 7 to 12 minutes). Use plan commands, not hand edits to PLAN.md. Tests must use temp HOME, never the real ~/.codex, ~/.gemini, ~/.cursor or ~/.local/bin.

## Open questions and blockers
Gemini CLI steps 1 to 5 not run: Google sign-in refused (needs an API key). Cursor: live check not done; unknown whether `session_id` equals `conversation_id`. Gemini transcript format undocumented, so handoff sections may be thin there.

## Dead ends
- Gemini CLI with Google sign-in: "client is no longer supported ... migrate to Antigravity".
- Antigravity as a Gemini adapter test: it reads `.agents/hooks.json`, not `.gemini/settings.json`; used it as an AGENTS.md-only test instead.
