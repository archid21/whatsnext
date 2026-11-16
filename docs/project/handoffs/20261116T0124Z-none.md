# Handoff
Session: 4cfcc767-bc5b-4950-b1a9-8749aa6dd9ca
Task: none
Written: 2026-11-16T01:24Z
Branch: p-75-hook-free-mode-the-agents-md-block-and-s

## Goal

Make whatsnext work in any coding agent (ADR-0027). Now: P-75 hook-free mode, then P-76 to P-78.

## Next action

Get the P-75 live run done in an agent with no whatsnext hooks: say "what's next?" then "wrap up" in a scratch repo after `init`. Log the result in docs/project/progress/P-75.md, then `plan done P-75 --evidence "..."`.
Verify: the agent ran `status`, and its HANDOFF.md has the eight sections.
If it fails: ask the user to run it, or use Codex without hooks.

## State

State on Sun 2026-11-15 5:24 PM PST (Pacific): P-75 code, docs and tests are done but not committed, on branch p-75-hook-free-mode-the-agents-md-block-and-s. `python3 -m unittest discover -s tests` passed 690 tests. P-75 is stamped blocked: the live run has not happened.

## What changed

- f2af4e1, 780e3b0 on main: roadmap, ADR-0027, handoff files. b894e32 + merge 008d786: P-74 tier tables in README and docs/GUIDE.md; P-69 marked done.
- New `wrap-up-instructions` command (skills/whatsnext/scripts/whatsnext.py, wn/wrapup.py: HOOKLESS variant). Uncommitted.
- wn/initcmd.py block: run `whatsnext status` at start; on `wrap up` with no hook, run `wrap-up-instructions`. Uncommitted.
- skills/whatsnext/SKILL.md: both rules plus a command-table row. Uncommitted.
- tests/test_hookless.py is new (6 tests); tests/test_init.py checks the new block words. Uncommitted.

## Decisions

The hook-free wrap-up reuses wrapup.begin() with agent "none". It drops the Stop-hook promises and tells the agent to run `progress next` itself. Recorded in code only, because it follows ADR-0027 tier 2.

## Constraints

Local only: do not push. Ask before each commit and merge. Standard library only, Python 3.9+. Leave docs/project/progress/journal/P-52.md uncommitted. Show the plan steps inside the approval question. Claude Code's auto mode blocks `gemini --yolo`.

## Open questions and blockers

How to do the P-75 live run: the user runs it, or Codex without hooks? P-75 is not committed yet. For the README or P-77: Gemini CLI reads GEMINI.md, not AGENTS.md, by default. The block's `<plugin>` path needs P-76.

## Dead ends

- Gemini CLI 0.67.0 live run: `IneligibleTierError: This client is no longer supported for Gemini Code Assist for individuals`.
- `gemini --yolo`: denied by the Claude Code auto mode classifier.
