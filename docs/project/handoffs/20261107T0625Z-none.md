# Handoff

Session: 869b255f-5943-4f33-850f-2c3380b03f59
Task: none
Written: 2026-11-07T06:25Z

## Goal

After a compact, the resume note repeats the user's latest request and the open work, so the model keeps its place even when the summary drops them (ADR-0015).

## Next action

Finish P-39: run `claude --plugin-dir .`, `/compact`, and check the resume note shows "Before the compact the user asked: ...".
Verify: `python3 -m unittest discover -s tests` passes (418 tests).
If it fails: run `python3 -m unittest tests.test_hook -k compact_carry` first.

## State

State on Fri 2026-11-06 10:25 PM PST (Pacific): built and committed locally on branch p-32-next-shows-handoff, not pushed. Full suite 418 tests pass. Not seen in a real Claude Code session yet.

## What changed

- PreCompact saves a `carry` field (about 420 characters) in `.whatsnext/sessions/<session>.compact.json` (wn/hook.py `carry_text`, wn/wrapup.py `mark_compacted`, `compacted_carry`)
- The compact-source resume note appends it (wn/packet.py `compacted_text`)
- Setting `note.carryAfterCompact`, default true (schemas/config.schema.json)
- Three tests in tests/test_hook.py, one paragraph and a settings row in docs/GUIDE.md, ADR-0015 and its index row

## Decisions

ADR-0015, accepted (user) 2026-11-07, decided 2026-11-07T06:20Z. Not built: a 15-minute expiry, a 5-bullet cap and a summary-dedupe check, because the note is rebuilt from files and already capped at 1,200 characters. The carry is 420 characters, not the 2,000 first estimated.

## Constraints

Standard library only, Python 3.9+. Do not push or create a remote without asking. Do not name other plugins in code or public docs. Run the full suite before reporting done (about 11 minutes).

## Open questions and blockers

The unrelated P-39 progress edits and tsconfig.json were left uncommitted.
