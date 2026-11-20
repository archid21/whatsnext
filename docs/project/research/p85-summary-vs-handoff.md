# P-85 step 1: compact summaries against the handoff note of the time

Measured 2026-11-20. Script: `python3 docs/project/research/p85_compare.py` (read-only; prints the tables below).
Question: if the text injected after a compact says "the handoff wins" and the PreCompact text tells the compactor not to spend space on what the handoff holds, does the summary shrink, and is a fact lost?

## Answer in four lines

- Overlap is small. 16% of the summary bytes (9,144 of 57,617) restate a handoff fact, over all 17 pairs. 81% of the summary's sentences are in no handoff note.
- Conflicts exist in 15 of 17 pairs (24 in all), and in every one the note is the stale side. The two pairs where the session wrote the note itself, just before the compact, have 0 conflicts.
- The only pairs with real overlap are those same two (28% of bytes, about 3.9 KB of 14.2 KB). Everything else is another session's note, which whatsnext already keeps out of the compact text.
- Recommendation: close P-85 as written. Details at the end.

## Method

1. Pairing (script). Each summary's time is `saved` in its `.summary.json` (the PostCompact write). Every distinct note text is collected from the git history of `docs/project/HANDOFF.md`, the working copy, and `docs/project/handoffs/*.md`, and read for its `Written:` and `Session:` header lines. A summary is paired with the latest note written at or before its compact; a note by the same session wins when there is one. All 17 pair; none is unpaired.
2. Facts (by hand). I broke each of the 4 distinct paired notes into atomic facts (goal, next action, state, tests, files, decisions, constraints, open questions and blockers, dead ends): 24, 19, 29 and 26 facts. I then read each summary and recorded which note facts it restates (overlap), which it contradicts (conflict) and which it lacks (note-only). Summary-only is counted in sentence units, not facts, because the summaries hold many small sentences.
3. Anchors. Each hand judgment is tied to a regex that must match the summary's `<summary>` block. The script exits with an error if one does not match, so the record cannot drift from the data. Facts that only appear in the `<analysis>` block do not count: Claude Code's own summary text keeps `<summary>`, and the analysis is working notes.
4. Bytes. "ov bytes (units)" is the bytes of the sentence units that contain a restated fact: an upper bound at sentence level, because a long sentence can mix facts. "matched text" is only the matched words: a lower bound. For the same-session pairs I also give a section-level estimate (whole sections that mostly restate the note). "lexical 4-gram %" is an independent mechanical check (share of the summary's word 4-grams found in the note); it undercounts because the summaries paraphrase.
5. Conflict kinds. `stale` = the note is older than the work, or about other work, and now says something else. `contra` = both current, same slot, different value.

## What the data is (read before the numbers)

- 15 of 17 summaries are compacts of throwaway test sessions. The user's only words were "hi", "ok", "reply with the single word ok", or a pasted repo dump (661478a5). They were made on 2026-11-06 and 2026-11-07 (Pacific and UTC dates differ for some) while the compact hooks were being tested (P-39). They hold no real work to lose.
- 15 of 17 notes are another session's. The summaries say so ("another session wrote it ... Read it only if it fits"). The existing code already handles this: `compact_instructions` (wn/wrapup.py) does not carry a foreign note into the PreCompact text, and the resume note labels it "another session's note" (wn/packet.py `handoff_line`).
- Only 2 summaries are real work sessions that wrote their own note minutes before the compact: a09a001d (note 4 min old, task P-61) and c917f1f8 (note 5 min old). This is the designed flow, "wrap up, then /compact", so these two are the cases P-85 targets. n = 2.
- 661478a5 (idle wrap-up test) wrote its note to `.whatsnext/sessions/idle3-HANDOFF.md`. That file is gone. I paired it with the project note of the time (foreign). Low confidence; if it is dropped, totals change by 3 overlap facts and 2 conflicts.
- The `item` column of the session file is the task at the session's last event, not at the compact (a09a001d shows P-69, but its note and summary are about P-61; c917f1f8 shows P-62 but the work was P-75 to P-82). I did not use it for pairing.
- What reaches the model after a compact: the resume note is capped at 1,200 characters (wn/packet.py `NOTE_CAP`) and holds one pointer line to the handoff ("Handoff: <path>, wrapped up <time> (read it first | another session's note)"), not the note's facts. So a fact dropped from the summary is in context only if the model opens HANDOFF.md.
- The existing PreCompact text does the opposite of P-85 for an own note: `compact_instructions` appends the note body after "Carry it into the summary". The mirrored headings of c917f1f8's summary (Goal, Next action, State, Decisions, Open questions, Dead ends) are consistent with that. The compact instructions themselves are not saved, so I could not confirm it.

## Pairing (mechanical)

17 saved summaries; 14 distinct handoff versions found.

| summary | compact (UTC) | item | note paired | note written (UTC) | age (min) | same session | rule |
|---|---|---|---|---|---|---|---|
| 55d1fcd8 | 2026-11-07T00:46Z | P-39 | HANDOFF.md@f2790a3 | 2026-11-06 22:56Z | 110 | no | latest note before the compact (written by another session) |
| 2b841192 | 2026-11-07T00:48Z | P-39 | HANDOFF.md@f2790a3 | 2026-11-06 22:56Z | 112 | no | latest note before the compact (written by another session) |
| 02cc7693 | 2026-11-07T00:50Z | P-39 | HANDOFF.md@f2790a3 | 2026-11-06 22:56Z | 114 | no | latest note before the compact (written by another session) |
| d8fb79c6 | 2026-11-07T00:53Z | P-39 | HANDOFF.md@f2790a3 | 2026-11-06 22:56Z | 117 | no | latest note before the compact (written by another session) |
| 6ffd59c4 | 2026-11-07T00:55Z | P-39 | HANDOFF.md@f2790a3 | 2026-11-06 22:56Z | 119 | no | latest note before the compact (written by another session) |
| 76d432c7 | 2026-11-07T00:57Z | P-39 | HANDOFF.md@f2790a3 | 2026-11-06 22:56Z | 121 | no | latest note before the compact (written by another session) |
| f7c22e49 | 2026-11-07T00:59Z | P-39 | HANDOFF.md@f2790a3 | 2026-11-06 22:56Z | 123 | no | latest note before the compact (written by another session) |
| b0b57b52 | 2026-11-07T01:02Z | P-39 | HANDOFF.md@f2790a3 | 2026-11-06 22:56Z | 126 | no | latest note before the compact (written by another session) |
| ba2f15bf | 2026-11-07T06:57Z | P-39 | HANDOFF.md@8b1b172 = archive/20261107T0625Z-none.md | 2026-11-07 06:25Z | 32 | no | latest note before the compact (written by another session) |
| e6fc9110 | 2026-11-07T07:02Z | P-39 | HANDOFF.md@8b1b172 = archive/20261107T0625Z-none.md | 2026-11-07 06:25Z | 37 | no | latest note before the compact (written by another session) |
| 1d1c8054 | 2026-11-07T07:06Z | P-39 | HANDOFF.md@8b1b172 = archive/20261107T0625Z-none.md | 2026-11-07 06:25Z | 41 | no | latest note before the compact (written by another session) |
| 6090a150 | 2026-11-07T07:15Z | P-39 | HANDOFF.md@8b1b172 = archive/20261107T0625Z-none.md | 2026-11-07 06:25Z | 50 | no | latest note before the compact (written by another session) |
| 0e994395 | 2026-11-07T07:21Z | P-39 | HANDOFF.md@8b1b172 = archive/20261107T0625Z-none.md | 2026-11-07 06:25Z | 56 | no | latest note before the compact (written by another session) |
| c5137415 | 2026-11-07T07:23Z | P-39 | HANDOFF.md@8b1b172 = archive/20261107T0625Z-none.md | 2026-11-07 06:25Z | 58 | no | latest note before the compact (written by another session) |
| 661478a5 | 2026-11-07T23:20Z | - | HANDOFF.md@8b1b172 = archive/20261107T0625Z-none.md | 2026-11-07 06:25Z | 1015 | no | latest note before the compact (written by another session) |
| a09a001d | 2026-11-10T22:03Z | P-69 | HANDOFF.md@0f217bf = archive/20261110T2159Z-P-61.md | 2026-11-10 21:59Z | 4 | yes | same session wrote it |
| c917f1f8 | 2026-11-16T21:19Z | P-62 | HANDOFF.md@dccf50e = archive/20261116T2114Z-none.md | 2026-11-16 21:14Z | 5 | yes | same session wrote it |

## Facts per pair (hand judgment, regex-anchored)

H = facts in the note; O = in both; C = conflict; Ho = only in the note (O+C+Ho = H). units = sentence units in the summary block; ov = units that restate note facts; So = summary-only units.

| summary | note | H | O | C | Ho | units | ov units | So | summary bytes | ov bytes (units) | ov bytes (matched text) | ov % | ov % without constraints | lexical 4-gram % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 55d1fcd8 | H1 | 24 | 3 | 2 | 19 | 42 | 4 | 36 | 2765 | 205 | 49 | 7% | 0% | 2% |
| 2b841192 | H1 | 24 | 3 | 2 | 19 | 47 | 5 | 40 | 3025 | 311 | 49 | 10% | 0% | 1% |
| 02cc7693 | H1 | 24 | 3 | 2 | 19 | 34 | 3 | 29 | 2590 | 187 | 52 | 7% | 0% | 2% |
| d8fb79c6 | H1 | 24 | 3 | 2 | 19 | 41 | 4 | 35 | 2730 | 217 | 49 | 8% | 0% | 1% |
| 6ffd59c4 | H1 | 24 | 4 | 2 | 18 | 38 | 5 | 31 | 2834 | 280 | 63 | 10% | 0% | 2% |
| 76d432c7 | H1 | 24 | 3 | 2 | 19 | 31 | 3 | 26 | 2255 | 252 | 49 | 11% | 0% | 1% |
| f7c22e49 | H1 | 24 | 3 | 2 | 19 | 37 | 5 | 30 | 2716 | 290 | 49 | 11% | 0% | 1% |
| b0b57b52 | H1 | 24 | 3 | 2 | 19 | 35 | 4 | 29 | 2334 | 223 | 49 | 10% | 0% | 1% |
| ba2f15bf | H3 | 19 | 3 | 1 | 15 | 46 | 5 | 40 | 3225 | 376 | 51 | 12% | 4% | 1% |
| e6fc9110 | H3 | 19 | 5 | 1 | 13 | 35 | 5 | 29 | 3003 | 500 | 109 | 17% | 7% | 1% |
| 1d1c8054 | H3 | 19 | 4 | 1 | 14 | 53 | 7 | 45 | 3315 | 588 | 62 | 18% | 7% | 2% |
| 6090a150 | H3 | 19 | 2 | 1 | 16 | 36 | 5 | 30 | 2953 | 393 | 30 | 13% | 6% | 2% |
| 0e994395 | H3 | 19 | 3 | 1 | 15 | 36 | 8 | 27 | 2768 | 561 | 51 | 20% | 13% | 1% |
| c5137415 | H3 | 19 | 3 | 1 | 15 | 31 | 6 | 24 | 2860 | 547 | 51 | 19% | 8% | 1% |
| 661478a5 | H3 | 19 | 3 | 2 | 14 | 56 | 4 | 50 | 4057 | 300 | 49 | 7% | 0% | 3% |
| a09a001d | H_a09 | 29 | 24 | 0 | 5 | 101 | 22 | 79 | 7998 | 2026 | 461 | 25% | 21% | 5% |
| c917f1f8 | H_c917 | 26 | 26 | 0 | 0 | 90 | 27 | 63 | 6189 | 1888 | 606 | 31% | 25% | 7% |

## Totals

- all (17 pairs): H=380, O=98, C=24, Ho=258; summary units=789, overlap units=122, summary-only units=643; summary bytes=57617, overlap bytes=9144 (16%; matched text only 3%; without constraint lines 8%)
- own fresh note (same session) (2 pairs): H=55, O=50, C=0, Ho=5; summary units=191, overlap units=49, summary-only units=142; summary bytes=14187, overlap bytes=3914 (28%; matched text only 8%; without constraint lines 23%)
- another session's note (15 pairs): H=325, O=48, C=24, Ho=253; summary units=598, overlap units=73, summary-only units=501; summary bytes=43430, overlap bytes=5230 (12%; matched text only 2%; without constraint lines 3%)

Bytes: summary block = text inside <summary>; the saved files also hold an <analysis> block (total file bytes 74668, summary-block bytes 57617).

## Conflicts (hand judgment)

- 55d1fcd8 [H1 G1]: note: ship the release, all 31 items built; summary: P-39 tips-band check is the task
- 55d1fcd8 [H1 N1]: note: try three unverified hooks, run doctor; summary: P-39 manual band check
- 2b841192 [H1 G1]: note: ship the release, all 31 items built; summary: P-39 tips-band check is the task
- 2b841192 [H1 N1]: note: try three unverified hooks, run doctor; summary: P-39 manual band check
- 02cc7693 [H1 G1]: note: ship the release, all 31 items built; summary: P-39 tips-band check is the task
- 02cc7693 [H1 N1]: note: try three unverified hooks, run doctor; summary: P-39 manual band check
- d8fb79c6 [H1 G1]: note: ship the release, all 31 items built; summary: P-39 tips-band check is the task
- d8fb79c6 [H1 N1]: note: try three unverified hooks, run doctor; summary: P-39 manual band check
- 6ffd59c4 [H1 G1]: note: ship the release, all 31 items built; summary: P-39 tips-band check is the task
- 6ffd59c4 [H1 N1]: note: try three unverified hooks, run doctor; summary: P-39 manual band check
- 76d432c7 [H1 G1]: note: ship the release, all 31 items built; summary: P-39 tips-band check is the task
- 76d432c7 [H1 N1]: note: try three unverified hooks, run doctor; summary: P-39 manual band check
- f7c22e49 [H1 G1]: note: ship the release, all 31 items built; summary: P-39 tips-band check is the task
- f7c22e49 [H1 N1]: note: try three unverified hooks, run doctor; summary: P-39 manual band check
- b0b57b52 [H1 G1]: note: ship the release, all 31 items built; summary: P-39 tips-band check is the task
- b0b57b52 [H1 N1]: note: try three unverified hooks, run doctor; summary: P-39 manual band check
- ba2f15bf [H3 N1]: note: check the resume note shows 'Before the compact the user asked'; summary (from progress file): check the tips band
- e6fc9110 [H3 N1]: note: check the resume note shows 'Before the compact the user asked'; summary (from progress file): check the tips band
- 1d1c8054 [H3 N1]: note: check the resume note shows 'Before the compact the user asked'; summary (from progress file): check the tips band
- 6090a150 [H3 N1]: note: check the resume note shows 'Before the compact the user asked'; summary (from progress file): check the tips band
- 0e994395 [H3 N1]: note: check the resume note shows 'Before the compact the user asked'; summary (from progress file): check the tips band
- c5137415 [H3 N1]: note: check the resume note shows 'Before the compact the user asked'; summary (from progress file): check the tips band
- 661478a5 [H3 G1]: note: carry the latest request after a compact; summary: idle wrap-up test
- 661478a5 [H3 N1]: note: finish P-39 band/carry check; summary: send the wrap-up closing lines

Conflict kinds: all 24 are 'stale' (the note is older than the work or about other work); 0 are 'contra' (both current, same slot, different value).

## Sections of the two same-session summaries (bytes)

- a09a001d: (before first heading) 1; Primary Request and Intent 651; Key Technical Concepts 1361; Files and Code Sections 2292; Errors and fixes 727; Problem Solving 265*; All user messages 1256; Pending Tasks 285*; Current Work 462*; Optional Next Step 492*
  sections marked * mostly restate the note: 1504 of 7998 bytes (19%), a section-level estimate
- c917f1f8: (before first heading) 1; Goal 193*; Next action 386*; State 1392*; Files 1821; Decisions 598*; Instructions 713*; Open questions 417*; Dead ends 384*; The last reply must end with exactly 162
  sections marked * mostly restate the note: 4083 of 6189 bytes (66%), a section-level estimate

## Facts by category (all pairs / same-session pairs)

| category | facts x pairs | in both | conflict | in both, same-session | facts x pairs, same-session |
|---|---|---|---|---|---|
| goal | 25 | 3 | 9 | 2 | 2 |
| next | 53 | 6 | 15 | 6 | 8 |
| state | 44 | 6 | 0 | 6 | 6 |
| tests | 25 | 2 | 0 | 2 | 2 |
| files | 70 | 10 | 0 | 10 | 10 |
| decisions | 35 | 7 | 0 | 6 | 6 |
| constraints | 87 | 50 | 0 | 10 | 11 |
| open | 37 | 10 | 0 | 4 | 6 |
| deadend | 4 | 4 | 0 | 4 | 4 |


## Conflict examples (quotes shortened; all are `stale`)

1. Goal, 8 summaries (e.g. 55d1fcd8) against the note of 2026-11-06T22:56Z: note "All 31 plan items are built" (goal: ship the release); summary "continue P-39 ... Verify in a real session".
2. Next action, same 8: note "Try the three unverified hooks in a real session"; summary "start a session with `claude --plugin-dir .` and run /compact".
3. Next action, 6 summaries against the note of 2026-11-07T06:25Z (e.g. 1d1c8054): note "check the resume note shows 'Before the compact the user asked'"; summary "check the band shows a tip with Next tip and Stop tips". Partial: both are P-39, the check target differs.
4. 661478a5 (idle wrap-up test) against the same note: note goal "repeats the user's latest request" (ADR-0015); summary goal "idle wrap-up test", next step "send the three closing lines".
5. Hidden in the `<analysis>` block, not counted: ba2f15bf and c5137415 show the compact ran and the note listed "hi" as the latest request, while the note still says "Not seen in a real Claude Code session yet". A note that says "wins" would have been wrong here too.

There is no `contra` case: in no pair were both texts current and different.

## Does it matter?

Conflicts. Yes in count (15 of 17 pairs), no in effect for P-85. In all 24 the note is the stale side: it was written before the work the summary describes, or for other work. A rule that says "the handoff wins" would send the model to a stale next action in these 15 pairs. The sentence is only safe when the note is this session's and newer than the last user turn, and that is the one case with 0 conflicts (2 of 2), so there is nothing for it to settle. The code already withholds foreign notes from the compact text and labels them in the resume note.

Shrink. In the two same-session pairs 50 of the 55 note facts are in the summary (91%), and 28% of the summary bytes (3,914 of 14,187; range 8% to 39% by method) restate the note. At about 4 characters per token that is roughly 500 tokens per compact (the section-level estimate gives up to about 1,000 for c917f1f8), against a context of hundreds of thousands of tokens at compact time (221.8k of 1M in one saved case). Over all 17 pairs the figure is 16%, and 3% for the 15 foreign pairs once constraint lines (also in AGENTS.md) are excluded. The summaries are 81% sentences that no note holds: errors and fixes, the message list, file and function detail, test-session chatter.

No fact lost. Not shown. After a trim the dropped facts live only in HANDOFF.md; the resume note holds just a pointer. The check holds only if the model reads the file ("read it first" is already in the pointer). I did not test that. A before and after test needs real compacts with the trimmed text; the 17 saved ones cannot give it, because they were made with the current text.

## Recommendation: close P-85 as written

Criteria: conflicts that matter, bytes saved, risk of a lost fact.

1. Do not build "the handoff wins". It has nothing to decide where it is safe (0 conflicts in 2 of 2 same-session pairs) and does harm where it would fire (stale note wins in 15 of 15 foreign pairs).
2. Do not build the PreCompact "do not spend space" half as written for foreign notes: it already carries nothing from them.
3. The only real saving is for an own, fresh note: change "Carry it into the summary" so the compactor refers to the file instead of restating it, about 1.5 KB to 4 KB per compact. That is a small, separate change. It needs a real before and after compact to show the model still finds the facts. I would only do it if compact size is a problem, which this data does not show.
4. Trade-off and risk of closing: the evidence is thin where it counts (2 real pairs, 15 test sessions). If more real wrap-up and compact pairs pile up in `.whatsnext/sessions/`, rerun the script; it takes seconds and the anchors catch drift.

Unsure about: (a) the pairing of 661478a5; (b) whether the own-note compacts really had the note body in their instructions; (c) the fact counts are my reading, and the same-session overlap is high enough (50 of 55) that small changes in reading do not change the conclusion; (d) whether Claude Code keeps the `<analysis>` block in context (I assumed not).
