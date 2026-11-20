# P-86 gem test on past handoff notes

Measured 2026-11-20 on 11 notes (`docs/project/HANDOFF.md` and `docs/project/handoffs/*.md`). Rerun: `python3 docs/project/research/p86_gem_test.py` (add `--check-shas` to check every commit named on a DERIVABLE line). Labels: `docs/project/research/p86-labels.json`.

## Answer

- 160 content lines. 105 are DERIVABLE (66%), 26 are GEM (16%), 29 are UNSURE (18%).
- Dropping the DERIVABLE lines saves 12,700 bytes (about 3,175 tokens) of 27,529 file bytes: 46%, no lost fact. That is about 1,150 bytes (290 tokens) per note, from 2,500 bytes (about 625 tokens) to 1,350 bytes (about 340 tokens).
- Upper bound, if UNSURE lines go too: 18,149 bytes (about 4,540 tokens), 66%. This loses facts that no other source holds, so it is not a "no lost fact" figure.
- The notes are already about 625 tokens each, below the 1 to 2k token aim in the P-86 item. The saving is real in percent and small in tokens.

## Method

1. Parse each note into the eight `##` sections. A content line is any non-blank line inside a section. The title and the Session, Task, Written and Branch header lines are not counted (fixed overhead, 150 to 250 bytes per note). Bytes include the newline. Tokens are bytes / 4.
2. For each note, take the repo at the commit nearest before its `Written` time, converted to Pacific (the commit is in the labels file, field `at`). Work that was uncommitted at that time counts as visible through `git status` and `git diff`, and is read from the commit that saved it.
3. Sources a fresh session has: the repo at that commit, `PLAN.md`, `docs/decisions/`, `AGENTS.md`, the item's progress file, and git history.
4. Label each line:
   - D (DERIVABLE): every fact on the line is present in a named source at that time.
   - G (GEM): a fact is absent from the sources and a fresh session would get it wrong without it (unverified state, user rules, in-flight decisions, other-repo state, reasons).
   - U (UNSURE): the line is partly present, or absent but harmless to lose, or held only in a place outside the sources above (the user's global `CLAUDE.md`, auto-memory, the gitignored `.whatsnext/` run records).
   - A line with several facts takes the worst label. 36 non-D lines (19 G, 17 U) also hold derivable clauses; they are counted as non-D in full.
5. Check DERIVABLE lines against the sources with real commands (below).

Limits: one labeler (the agent, not the user), so the G/U boundary is a judgment. Journals (`docs/project/progress/journal/`) were not used as a source. Past test results (for example "684 tests passed in 554 s") are labeled U or G, because they sit in gitignored run records or nowhere; a fresh session can rerun them but at a cost of 7 to 12 minutes.

## Per note

| Note | Lines D / G / U | Bytes D / G / U | File bytes | Tokens now | Tokens without D |
|---|---|---|---|---|---|
| 20261107T0625Z-none | 7 / 4 / 1 | 758 / 591 / 278 | 1843 | 461 | 271 |
| 20261108T1734Z-P-48 | 11 / 0 / 2 | 1280 / 0 / 279 | 1790 | 448 | 128 |
| 20261109T1933Z-none | 9 / 2 / 4 | 1548 / 510 / 521 | 2810 | 702 | 316 |
| 20261109T2337Z-none | 8 / 3 / 3 | 955 / 844 / 384 | 2437 | 609 | 370 |
| 20261110T0810Z-none | 6 / 4 / 3 | 727 / 1229 / 516 | 2726 | 682 | 500 |
| 20261110T2159Z-P-61 | 9 / 4 / 2 | 1250 / 929 / 335 | 2798 | 700 | 387 |
| 20261111T0320Z-none | 11 / 3 / 1 | 1245 / 1040 / 184 | 2712 | 678 | 367 |
| 20261115T2303Z-none | 7 / 3 / 4 | 709 / 903 / 1147 | 3002 | 750 | 573 |
| 20261116T0124Z-none | 11 / 2 / 2 | 1371 / 467 / 337 | 2459 | 615 | 272 |
| 20261116T2114Z-none | 14 / 0 / 3 | 1663 / 0 / 605 | 2503 | 626 | 210 |
| HANDOFF (2026-11-17T00:57Z) | 12 / 1 / 4 | 1194 / 157 / 863 | 2449 | 612 | 314 |

The two notes for a task (`P-48`, `P-61`) and the two latest are the most derivable: the task's progress file or the plan already holds the same facts, because the same session wrote both.

## Per section

| Section | Lines D / G / U | Bytes D / G / U | D share of section bytes |
|---|---|---|---|
| Goal | 10 / 1 / 0 | 1315 / 105 / 0 | 93% |
| Next action | 18 / 3 / 12 | 1720 / 524 / 1391 | 47% |
| State | 2 / 4 / 5 | 670 / 1317 / 1512 | 19% |
| What changed | 48 / 1 / 1 | 4742 / 82 / 91 | 96% |
| Decisions | 13 / 0 / 2 | 2425 / 0 / 689 | 78% |
| Constraints | 1 / 8 / 2 | 229 / 2904 / 703 | 6% |
| Open questions and blockers | 2 / 8 / 1 | 408 / 1628 / 238 | 18% |
| Dead ends | 11 / 1 / 6 | 1191 / 110 / 825 | 56% |

Next action by line: `Verify:` 10 D / 1 U (675 / 74 bytes), `If it fails:` 4 D / 7 U (306 / 549 bytes), the action line 4 D / 3 G / 4 U.

Mostly derivable: What changed (96%), Goal (93%), Decisions (78%). Mostly gems: Constraints (94% not derivable), State (81%), Open questions and blockers (82%).

## Examples

DERIVABLE (line, then where it lives):
1. `31fff27 P-77 Gemini CLI and Cursor adapters ...` (note 20261116T2114Z) in `git log`.
2. `Drift note: learned folder scope, one note per new file set, never a block: docs/decisions/ADR-0028-drift-warning.md` (HANDOFF.md) in ADR-0028.
3. `Clear as the only button: dropped; the user wants to keep the old chat` (note 20261111T0320Z) in ADR-0024 "Why".
4. `A full verification initially failed because WHATSNEXT_AGENT leaked into tests` (note P-48) in `progress/P-48.md`.
5. `Verify: python3 -m unittest discover -s tests` in `AGENTS.md`.

GEM:
1. `No Claude Code band for the "always worktree" offer (skill-level line only).` ADR-0020 item 5 says there is a band; the code has none.
2. `Not seen in a real Claude Code session yet.` Unverified state.
3. `The user wants work done here, not delegated to Sonnet unless asked.` A user rule in no repo file.
4. `The wrap-up running now came from the installed plugin, not this repo ... (a guess from the prompt text).` Marked guess.
5. `Ask the user to approve committing P-61. Then commit, ... fast-forward main.` The pending approval gate and the merge order.

## Spot checks of DERIVABLE lines

All run from the repo root. Result in brackets.

1. `git show 8b1b172:docs/decisions/ADR-0015-carry-after-compact.md | grep -c "Before the compact the user asked"` [1] (note 1 Goal)
2. `git show --stat e235f70 | grep -E "hook.py|wrapup.py|packet.py|config.schema"` [4 files + total line] (note 1 What changed)
3. `git show 8b1b172:tests/test_hook.py | grep -c "def test_compact_carry"` [3] (note 1 Verify hint)
4. `git show ddc8b67:docs/project/progress/P-48.md | grep -c "inherited WHATSNEXT_AGENT"` [1] (note P-48 Dead ends)
5. `git show 60b0af9:skills/whatsnext/scripts/wn/plan.py | grep -c -E "^def (blocked_cycles|waiting_text|handoff_task_status)"` [3] (note 3 What changed)
6. `git show 60b0af9:docs/project/progress/P-50.md | grep -c "NOT APPLICABLE for interrupt"` [1] (note 3 Dead ends)
7. `git show 7db235f:docs/decisions/ADR-0020-parallel-sessions-in-one-checkout.md | grep -c -E "New worktree \(recommended\)|after two equal answers|only offers"` [5] (note 4 Decisions)
8. `git show 7db235f:docs/decisions/ADR-0019-wrap-up-ending-and-recent-handoff.md | grep -c "Later change (P-54"` [1] (note 4 Decisions)
9. `git show e5a7e3d:docs/project/PLAN.md | grep "P-65" | grep -c "evidence: ADR-0021 accepted"` [1] (note 5 Decisions)
10. `git show 15e90e1:docs/decisions/ADR-0023-reuse-a-passing-run.md | grep -c "run the tests, commit, mark done"` [1] (note P-61 Dead ends)
11. `git show ad1fcdc -s --format=%B | grep -c "git cherry"` [1] (note P-61 Dead ends)
12. `git show d762f03:skills/whatsnext/scripts/wn/plan.py | grep -c "exit 4: the agent must ask the user"` [2] (notes 7 and 8 If it fails)
13. `git show 4024a09:docs/decisions/ADR-0024-start-fresh-after-wrap-up.md | grep -c "clearing must not be the only choice"` [1] (note 7 Dead ends)
14. `git show 0d07568:docs/project/progress/P-75.md | grep -c "IneligibleTierError"` [1] (note 9 Dead ends)
15. `git show 0d07568:docs/CODEX-ACCEPTANCE.md | grep -c "Released without a live run (decision 2026-11-16)"` [1] (note 10 Decisions)
16. `git rev-list -n1 v0.5.0` [178635c...] and `git merge-base --is-ancestor 178635c d762f03` [true] (HANDOFF What changed)
17. `git show b2dc7b1 -s --format=%s | grep -c "no save commit before a reset"` [1] (HANDOFF Dead ends)
18. `python3 docs/project/research/p86_gem_test.py --check-shas` [50 distinct commits named on DERIVABLE lines, 0 missing]

GEM checks (the fact is absent from the sources):
- `git grep -n -i "name other\|other plugins" 8b1b172 -- AGENTS.md docs/decisions` [no hit for the "do not name other plugins" rule].
- `git grep -n -i "worktree" 7db235f -- hooks` [no hit: no band code for the always-worktree offer].
- `git grep -n -i "sonnet\|delegat" 60b0af9 -- AGENTS.md skills/whatsnext/SKILL.md docs/decisions README.md` [only ADR-0012's model "suggest" field; no rule against delegating].

No DERIVABLE line failed its check. The spot checks cover 18 of the 105 lines directly; the SHA check covers the commit lines (50 commits); the other D lines were read against their source while labeling, not rerun.

## What a DERIVABLE drop would and would not lose

- The commit SHAs on the What changed lines are in `git log`. A fresh session needs the previous note's HEAD to know where to start; the `Check: HEAD == <sha>` line that the wrap-up now asks for in State (ADR-0030) gives it. None of the 11 notes has a `Check:` line yet (they predate it), so this is not tested here.
- `docs/decisions/` holds the decisions, but the path on the Decisions line is the pointer. Dropping the line must keep the path.
- The wrap-up cross-check "What changed against git" (P-15) reads the What changed section. Dropping the section turns that check off. Keeping only uncommitted work keeps it working.

## Recommendation

Close P-86 with this measurement, and make no change to the wrap-up instructions, unless the owner wants the one cheap change below. Reasons:

- The notes are about 625 tokens, already below the 1 to 2k aim. The no-lost-fact saving is about 290 tokens per note (46%) as a ceiling, and about 130 tokens per note (21%) for the safe changes below.
- 105 of 160 lines are derivable, but they sit in a few places, and the line kinds that carry the gems (Constraints, State, Open questions, user rules) are untouched by any drop.
- The cost of a mistake is high (a fresh session misses a gem) and the gain is small.

If the owner wants a saving anyway, these changes lose no fact. Do not drop any whole section.

| Change to `wrapup.py` instructions | Bytes saved over 11 notes | Share of file bytes |
|---|---|---|
| What changed: list only uncommitted files and facts that git does not show; commits are in `git log` and State's `Check: HEAD == <sha>` | up to 4,742 (a few lines stay) | up to 17% |
| Next action: write `Verify:` only when it is not the AGENTS.md test command; drop `If it fails:` unless the hint is specific | 981 D (and 549 U) | 3.6% (5.6%) |
| Decisions: when an ADR exists, give its path and nothing else | up to 2,425 (the paths, about 700 bytes, stay) | up to 6% net |
| Dead ends: only those not recorded in an ADR, progress file or commit message | up to 1,191 | up to 4% |

First two rows together: 5,723 bytes, 21% of file bytes, about 130 tokens per note. All four rows: up to about 8,600 bytes net, about 31%.

Sections to keep as they are: Constraints, State, Open questions and blockers, Goal (about 130 bytes per note).

## Open points for the owner

1. Is about 130 to 290 tokens per note worth a change to `wrapup.py`, its tests and the cross-check in P-15? Close P-86 or apply row 1 and 2.
2. Memory and the global `CLAUDE.md` hold several user rules that the notes repeat in Constraints (show plan steps in the approval question, short answers). A fresh session in this project loads them, so those lines are UNSURE here. Another user, or another agent without memory, would not have them. The measurement does not settle whether to treat them as derivable.
3. Whether a Gem test should count a past test result ("684 tests passed") as a gem. Here it is UNSURE. If counted as a gem, no figure above changes; if counted as derivable, a handful of State lines move from UNSURE to DERIVABLE.
