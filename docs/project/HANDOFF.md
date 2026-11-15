# Handoff
Session: 5d4400f2-b3fc-4601-8665-243a059f171c
Task: none
Written: 2026-11-15T23:03Z
Branch: main

## Goal

Make whatsnext work in any coding agent (ADR-0027), then build the 0.6 items. Roadmap: Now = P-74 to P-78, Next = P-79, P-72, P-73, P-71, P-70, P-62, Later = P-63, P-80, P-81.

## Next action

Ask the user to commit the plan and ADR changes, then `python3 skills/whatsnext/scripts/whatsnext.py plan start P-74 --agent claude-code --branch branch` (P-76 is also ready, no blocker).
Verify: the output says `Started P-74` and a new branch from main.
If it fails: exit 4 means ask the user the question it prints.

## State

State on Sun 2026-11-15 3:03 PM PST (Pacific): the roadmap is in docs/project/PLAN.md and ADR-0027 is accepted; nothing is committed or pushed. Last check: `python3 -m unittest discover -s tests` passed 684 tests in 554 s; `tests.test_docs` and `tests.test_features` passed again after the ADR status edit; `plan check` shows no problem with P-74 to P-81 (only old "code has changed since" warnings). P-69 is still unticked in Later although its commits are merged (87f3451, a980bb2).

## What changed

- docs/project/PLAN.md: added P-74 to P-78 (Now), P-79 (Next), P-80 and P-81 (Later); moved P-72, P-73, P-71, P-70, P-62 from Later to Next. Uncommitted.
- docs/decisions/ADR-0027-any-agent-support.md: new, accepted. Uncommitted.
- docs/decisions/README.md: row 0027. Uncommitted.
- Commits since the last note: P-69 work and 576ce68 (README and FEATURES for 0.4.0, version 0.4.0), from other sessions.

## Decisions

docs/decisions/ADR-0027-any-agent-support.md, accepted by the user 2026-11-15: three support tiers (files, instructions, hooks); the instructions tier must be enough alone; tracker sync is read-first; claims on a git ref; a per-session MCP server is allowed. Tracker sync moved to 0.6 (P-79) at the user's request. MCP is one layer, not the foundation: a server cannot run at session start or before a compact.

## Constraints

Local only: do not push or create a remote without asking. Standard library only, Python 3.9+. Ask before each commit and merge. Leave docs/project/progress/journal/P-52.md uncommitted. An ADR stays proposed until the user accepts it. P-77: check Gemini CLI and Cursor hook events against official docs first; the Cursor facts (`.cursor/hooks.json`: sessionStart, beforeSubmitPrompt, stop, sessionEnd) are from one GitHub issue, unverified. Copilot CLI hooks: unknown. Answers: short, answer first, lists of 5 or fewer.

## Open questions and blockers

The user has not said whether to commit PLAN.md, ADR-0027 and the index. docs/project/handoffs/20261111T0320Z-none.md is untracked. P-69 open in the plan but merged: ask whether to mark it done.

## Dead ends

- MCP as the only route to every agent: dropped; it is pull-only, so no resume note unasked, no compact safety net, no journal.
- `W="python3 ... plan"; $W add` in zsh: fails with "no such file or directory" (no word splitting); use a shell function.
