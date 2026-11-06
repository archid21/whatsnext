# ADR-0013: The handoff note has a Dead ends section, and the compact text keeps it

- **Date:** 2026-11-06T20:02Z
- **Status:** accepted (user), 2026-11-06

Amends ADR-0008 item 3 (the note's structure) and ADR-0009 item 1 (what the compact text drops).

## Decision

1. **The handoff note gets an eighth section, `## Dead ends`,** after `## Open questions and blockers`: approaches tried and dropped, one line each with the reason. `none` when nothing. At most 300 characters.
2. **The compact text keeps dead ends.** It no longer says "Drop: dead ends". It says to keep them with the reason each failed. The one-line `/compact` form carries `Dead ends: <text>`, cut at 300 characters; it is the first slot cut when the line is too long (before Blockers, Decisions and Goal). Next and Constraints are still never cut.
3. **The long form (the note body)** lists Dead ends after Decisions.

## Why

A failed approach is the costliest thing for the next session to rediscover. The reason it failed is not in the code or in git.

## Cost

About 300 more characters in the compact text. Notes written before this change have no such section; that is read as no dead ends.
