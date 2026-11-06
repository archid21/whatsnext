# Handoff

Session: 8eea2bfe-b59c-4f1f-8d4f-0454a895d4f4
Task: none
Written: 2026-11-06T18:08Z

## Goal

Plan the next whatsnext release: research user pain points and competitors, then fill PLAN.md with features, compact and handoff first, planning last.

## Next action

Start the first plan item: `python3 skills/whatsnext/scripts/whatsnext.py plan start P-4 --agent <name>`, then read docs/project/research/feature-list.md rows 4, 20, 26 before coding.
Verify: `python3 skills/whatsnext/scripts/whatsnext.py plan list` shows P-4 in progress.

## State

State on Fri 2026-11-06 10:08 AM PST (Pacific): research and plan are committed (7080f9d). No code written. `plan check` says the plan is fine. Tests pass (`python3 -m unittest discover -s tests`, OK). Tree is clean. No item started.

## What changed

- docs/project/PLAN.md: 27 items; Now P-4, P-20, P-26, P-6, P-5, P-8, P-24; Next 12 compact/handoff items; Later 8 planning items.
- docs/project/research/feature-candidates.md: 19 candidates with 20 sources.
- docs/project/research/competitive-reuse.md: 15 tools, licenses, reuse and leave-to-others.
- docs/project/research/feature-list.md: merged 27 rows, grouped by pillar, sorted by impact.
- Commit 7080f9d on main, not pushed.

## Decisions

No ADR written. User decisions recorded in feature-list.md header and rows: write all code fresh, no verbatim copying from MIT tools, but follow their proven approaches; whatsnext is the execution engine for rightsize, planning only tracks step completion and proven done; build compact and handoff items before planning items.

## Constraints

Standard library only, Python 3.9+. Never push or create a remote without asking. No model calls for recording (ADR-0001 item 4). Do not copy code from prep-compact, agent-handoff or others; follow their approach only. PreCompact text must be capped (P-20) and plain text, never JSON (P-26); on Codex PreCompact stdout is ignored, so Codex gets only the journal fact and resume note. Keep AGENTS.md under 30 lines. Run tests before reporting done. Done-means lines in PLAN.md name tests that do not exist yet; write them as part of each item.

## Open questions and blockers

Unverified: whether Claude Code appends PreCompact stdout to a user's own /compact text or replaces it (issue #101057 says appended; docs silent). Test before shipping P-4. Codex PreCompact behavior is from docs only.
