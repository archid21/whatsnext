# P-88 test: handoff note from a saved transcript (Sonnet helper)

Date: Fri 2026-11-20 (3:31 PM PST, 23:31 UTC). Status: research, step 1 of P-88 ("a test on a few real cold transcripts"). No ADR, no commit, no API call: the helper was played by the author of this file (Sonnet 5.5), reading the trimmed text in a chat.

**Result in one line:** the note is good enough on 2 of 4 transcripts and partly good on 2 (65 of 102 reference facts matched, 36 missed, 1 wrong). The helper costs 12 to 28 times less than a cold cache rebuild of the main model. Recommendation: build P-88, with the four changes in "Recommendation".

## Method

1. Matched sessions to real notes with the `Session:` header in `docs/project/handoffs/*.md`. Ten notes exist; 8 of the 9 sessions they name have a transcript under `~/.claude/projects/-Users-home-Projects-whatsnext/` (01a1bc1c is missing).
2. Cut each transcript just before the "wrap up" message, so the real note is not in it (0-based .jsonl rows 404, 835, 1994 and 1368 respectively).
3. Trimmed with `docs/project/research/p88_trim.py` (default budget 120 KB, tool results cut to the first 800 and last 400 chars, tool calls kept as one line, thinking blocks are empty in saved files so they are dropped, the opening request is kept when old messages drop).
4. Wrote one note per transcript from the trimmed text only, in the format of `wrap-up-instructions` (header lines, eight sections). One pass, no repo access, no git, no fixing after reading the real note. Notes: `docs/project/research/p88-notes/<session8>.md`.
5. Only then read the real note and counted facts. A fact is one checkable item in a section of the real note (a command, id, sha, decision, rule, question, dead end). Matched = the helper note states it (same meaning). Missed = absent. Wrong = stated and false or misleading. Counted by one reader, so the counts are judgments, not measurements. The `Check:` lines and `What changed` are not scored (the real notes of this era have no `Check:` lines).

Picks (4 of 8 usable pairs). Excluded: 17a7422f (I had already read its real note while looking for the format), 869b255f, 032f0fc9, a09a001d (two notes, 6.7 MB), left unused to save effort. Disclosure for c917f1f8: before writing I had seen the first lines of the later `docs/project/HANDOFF.md` of the same session (written 2026-11-17, not the note I scored); it did not name any scored item.

## Picks and sizes

Context = the tokens the main model had at its last turn before "wrap up" (input + cache read + cache write from the saved `usage`). Trimmed tokens = trimmed bytes / 4 (approximate; code-heavy text can run 20-30% higher).

| Session | Row cut | Main model | Context tokens | Raw bytes to cut | Trimmed bytes | Trimmed tokens | Old messages dropped |
|---|---|---|---|---|---|---|---|
| 5d4400f2 (roadmap, ADR-0027) | 404 | claude-fable-5-2 | 137,763 | 1,795,309 | 40,471 | 10,117 | 0 |
| 4cfcc767 (P-74, P-75) | 835 | claude-opus-5-5 | 128,326 | 2,264,934 | 63,647 | 15,911 | 0 |
| c917f1f8 (P-75 to P-78, P-82) | 1994 | claude-opus-5-5 | 208,072 | 4,478,418 | 119,859 | 29,964 | 70 of 332 |
| eb5f8678 (star ask, release 0.3.1) | 1368 | claude-opus-5-5 | 249,117 | 3,325,223 | 119,115 | 29,778 | 97 of 407 |

Trimmed text is 2.3% to 3.6% of the raw transcript bytes, and 7% to 14% of the main model's context tokens (the context also holds the system prompt, tools and the project files). The two long ones hit the 120 KB budget and lost their oldest 70 and 97 messages; the helper still got the latest work.

## Per-pick fact tables

M = matched, X = missed, W = wrong. Cause of a miss: **R** = a repo or user rule that is not in the transcript text (AGENTS.md, the user's global rules, plan CLI knowledge) and that a helper with repo access can read; **TRIM** = it was in the transcript but my trimmer cut it (long Write/Edit/Bash inputs); **T** = it was in the trimmed text and the helper missed it; **DROP** = in an old message dropped for the budget.

### 5d4400f2 (verdict: partly)

| Section | Facts | M | X | W | Misses |
|---|---|---|---|---|---|
| Next action | 5 | 3 | 2 | 0 | commit the changes first (T); exit 4 meaning (R). Command lacks `--branch branch` (counted inside the matched start command) |
| State | 6 | 4 | 2 | 0 | `plan check` clean for P-74 to P-81 (T); P-69 still unticked though merged (R) |
| Decisions | 7 | 2 | 4 | 1 | instructions tier must stand alone, tracker sync read-first, claims on a git ref (all TRIM: ADR text was cut); MCP "one layer, not the foundation" (T). **Wrong:** the note says the MCP server still needs a decision on ADR-0001's "no background process" rule; ADR-0027 as accepted already allows a per-session server |
| Constraints | 7 | 2 | 5 | 0 | local only, stdlib only, ask before commit and merge, ADR stays proposed until accepted, answer style (all R) |
| Open questions | 3 | 1 | 2 | 0 | untracked handoff file (R); mark P-69 done? (R) |
| Dead ends | 2 | 0 | 2 | 0 | MCP-only route dropped (T); zsh `$W` word-splitting failure (T) |
| **Total** | **30** | **12** | **17** | **1** | R 9, T 5, TRIM 3 |

Could a fresh session continue? **Partly.** The state, test result and next item are right. It would not know to ask about committing first, and it carries one false claim about the MCP rule. It would re-read AGENTS.md anyway for the project rules.

### 4cfcc767 (verdict: yes)

| Section | Facts | M | X | W | Misses |
|---|---|---|---|---|---|
| Next action | 5 | 3 | 2 | 0 | the exact live-run steps in a scratch repo (TRIM: cut inside the approval question); the Verify line "agent ran status, HANDOFF.md has eight sections" (T; helper wrote a weaker check) |
| State | 4 | 4 | 0 | 0 | |
| Decisions | 2 | 1 | 1 | 0 | hook-free wrap-up reuses `begin()` with a no-hook ending (TRIM: Edit input cut) |
| Constraints | 6 | 3 | 3 | 0 | local only, stdlib only, show plan steps in the approval question (all R) |
| Open questions | 4 | 4 | 0 | 0 | |
| Dead ends | 2 | 2 | 0 | 0 | |
| **Total** | **23** | **17** | **6** | **0** | R 3, TRIM 2, T 1 |

Could a fresh session continue? **Yes.** Same next action in substance (the live run, user decides who runs it), correct branch, exact uncommitted file list, both blockers. Header `Task:` differs: the helper wrote P-75 (the transcript shows it active); the real note says `none`.

### c917f1f8 (verdict: yes)

| Section | Facts | M | X | W | Misses |
|---|---|---|---|---|---|
| Next action | 4 | 4 | 0 | 0 | |
| State | 5 | 3 | 2 | 0 | which items were verified and which done* (T for P-76, P-77; DROP for P-75) |
| Decisions | 3 | 2 | 1 | 0 | Gemini and Cursor hooks are optional in `doctor` (T) |
| Constraints | 5 | 1 | 4 | 0 | stdlib only, run the suite before "done", use plan commands, tests use a temporary HOME (all R) |
| Open questions | 3 | 3 | 0 | 0 | |
| Dead ends | 2 | 2 | 0 | 0 | |
| **Total** | **22** | **15** | **7** | **0** | R 4, T 2, DROP 1 |

Could a fresh session continue? **Yes.** `Check: HEAD == 0d07568`, branch and clean tree are right and are taken from the last merge in the transcript. The 70 dropped messages (the P-75 and P-76 work) cost one fact.

### eb5f8678 (verdict: partly)

| Section | Facts | M | X | W | Misses |
|---|---|---|---|---|---|
| Next action | 5 | 1 | 4 | 0 | start P-57 with its command, its Verify and If-it-fails lines (TRIM: the note written earlier in the same session was cut to 250 chars in my trimmer, and P-57 only appears there). The helper put the open rightsize welcome question first instead |
| State | 7 | 7 | 0 | 0 | |
| Decisions | 6 | 5 | 1 | 0 | star ask comes once after the first verified done (TRIM: ADR text cut) |
| Constraints | 4 | 3 | 1 | 0 | keep rightsize's `star.ts` in step with `hooks/star.ts` (R) |
| Open questions | 3 | 3 | 0 | 0 | |
| Dead ends | 2 | 2 | 0 | 0 | |
| **Total** | **27** | **21** | **6** | **0** | TRIM 5, R 1 |

Could a fresh session continue? **Partly.** State and decisions are right. The next action is a real open question but not the planned next item (P-57); the fresh session would have to find P-57 with `wn status`. This is a trimmer problem, not a model problem.

### Totals

| | Facts | Matched | Missed | Wrong |
|---|---|---|---|---|
| 5d4400f2 | 30 | 12 | 17 | 1 |
| 4cfcc767 | 23 | 17 | 6 | 0 |
| c917f1f8 | 22 | 15 | 7 | 0 |
| eb5f8678 | 27 | 21 | 6 | 0 |
| **All** | **102** | **65 (64%)** | **36 (35%)** | **1 (1%)** |

By section (all four): Next action 19 facts, 11 matched; State 22, 18; Decisions 18, 10 (1 wrong); Constraints 22, 9; Open questions 13, 11; Dead ends 8, 6.

Why facts were missed (36): **R 17** (47%): project rules and plan-CLI knowledge, almost all in Constraints; **TRIM 10** (28%): cut by my trimmer; **T 8** (22%): the helper had it and left it out; **DROP 1**. Constraints is the weak section (9 of 22) and is nearly all R: the transcript does not repeat AGENTS.md. The one wrong fact was a guess about a rule, in a section where the transcript was cut (ADR text).

## Cost

Sources and assumptions:
- Prices: the `claude-api` skill, section "Current Models (cached: 2026-11-03)" and `shared/prompt-caching.md` (Economics). Claude Opus 5.5: $4 input, $20 output per MTok, cache read $0.20, cache write 1.25x ($5) for a 5-minute TTL and 2x ($8) for a 1-hour TTL. Claude Fable 5.2: $8 input, $40 output, read $0.20, write $10 or $16. Claude Sonnet 5.5: $2 input, $10 output per MTok. These are API list prices; I did not check them against the live pricing page. The sessions asked for a 1-hour cache (`promptCacheRequested: 1h` in the transcript), so the 1-hour column is the likely one.
- (a) Main model, cold cache: the wrap-up turn writes the whole context as cache write (C tokens), later turns read it at the cache-read price, plus the output tokens the real session produced. Turns after "wrap up" and output tokens come from the saved usage: 2 turns / 1,600 output tokens (5d4400f2), 1 / 1,172 (4cfcc767), 1 / 1,227 (c917f1f8), 2 / 1,632 (eb5f8678). Priced at Opus 5.5 as the brief says (the sessions ran Opus 5.5, except 5d4400f2 on Fable 5.2).
- (b) Helper: Sonnet 5.5, no cache, trimmed tokens + 1,000 tokens of instructions as input, 2,000 output tokens (about 800 for the note and an assumed 1,200 for thinking; not measured).
- Real money or subscription: dollars below are what the same tokens would cost on the API. The sessions run on a Claude Team plan ("Opus 5.5 · Claude Team" in the terminal capture), so for this user it is a share of the plan's usage limits, not a bill. The ratio is the useful number; plan limits are not priced per token, so the ratio is my proxy for the share.

| Session | Main-model context tokens | Helper input tokens | Token ratio | (a) Opus 5.5 cold, 1h write | (a) Opus 5.5 cold, 5m write | (a) Fable 5.2 cold, 1h write | (b) helper, Sonnet 5.5 | Ratio (a, 1h) / (b) | Ratio (a, 5m) / (b) |
|---|---|---|---|---|---|---|---|---|---|
| 5d4400f2 | 137,763 | 11,117 | 12.4 | $1.162 | $0.748 | $2.296 | $0.042 | 27.5 | 17.7 |
| 4cfcc767 | 128,326 | 16,911 | 7.6 | $1.050 | $0.665 | $2.100 | $0.054 | 19.5 | 12.4 |
| c917f1f8 | 208,072 | 30,964 | 6.7 | $1.689 | $1.065 | $3.378 | $0.082 | 20.6 | 13.0 |
| eb5f8678 | 249,117 | 30,778 | 8.1 | $2.075 | $1.328 | $4.101 | $0.082 | 25.4 | 16.3 |

With helper tokens 30% higher than bytes/4 the helper costs $0.048 to $0.100 and the ratios fall by about 15%; they stay above 10.

**Warm cache caveat.** If the main chat's cache is still warm, the wrap-up costs only cache reads: $0.049 to $0.132 on Opus 5.5. That is the same as the helper ($0.042 to $0.082, helper is 0.5x to 1.2x of warm). The helper pays off only when the cache is cold. P-88's trigger must be "cache is cold" (rightsize's P-71 knows this), not "wrap up".

## Recommendation: build P-88

Criteria: (1) note good enough to continue; (2) cheaper than a cold rebuild; (3) long transcripts cut to fit. Result: (1) yes on 2 of 4, partly on 2, no failure, 1 wrong fact in 102; (2) 12x to 28x cheaper when cold; (3) the cut worked: 120 KB held for 4.5 MB and 3.3 MB transcripts, and the latest work survived. The done-means for the test is met.

Build it with these changes, each backed by the miss counts above:
1. **Give the helper the repo facts the transcript lacks.** Pass AGENTS.md (and the user's rules file), the old `HANDOFF.md`, the active progress file, and a snapshot of `git rev-parse --short HEAD`, `git branch --show-current`, `git status --short` and `git log -5`. This targets the 17 R misses (47%) and gives the `Check:` lines real values instead of "HEAD not known".
2. **Fix the trimmer cuts.** Keep Write and Edit inputs to `docs/decisions/` and to the handoff in full (up to about 6 KB), keep the last handoff-like Write in full, and give the opening request and any `AskUserQuestion` text (it holds the plan steps) more room. This targets the 10 TRIM misses (28%), including the wrong next action in eb5f8678.
3. **Run the helper only when the cache is cold,** and print that the note is "from a transcript, unverified": the next session already re-checks `Check:` lines (ADR-0030).
4. **Prompt the helper to keep user rules and corrections in Constraints and to list every dead end seen** (the T misses, 8 of 36).

Trade-offs: a note that is wrong in the Next action (eb5f8678 pattern) sends the next session the wrong way without a signal; item 2 fixes the cause, but keep the Verify and `Check:` lines mandatory so a bad note fails early. Cost of building: a Sonnet call per cold wrap-up (about $0.05 to $0.10 API list price) plus the transcript reader (the trimmer is about 150 lines).

## Risks and limits of this test

- n = 4 transcripts from one project, one helper pass, one reader scoring (me). Facts are not equally important; a missing "ask before commit" matters more than a missing test count. Treat 64% as a rough level, not a measure.
- The helper was me in a long chat with the tools of a coding agent but no repo access. A production helper (a `claude -p` call or a subagent) will behave differently, and its thinking tokens are an assumption (2,000).
- Facts the transcript cannot show: the current git state (HEAD, dirty files, whether the user committed in another terminal after the chat went cold), edits made by other sessions in the same checkout (the transcripts mention several), the user's answer to the last question (the chat is cold, so it may have been answered elsewhere), and anything the user did outside the chat. Notes that state "nothing is committed" from a transcript can be stale by hours.
- Rules the user wrote only in global files or in an earlier session never appear (Constraints, 9 of 22 matched). Corrections made by the user in earlier sessions that have since been compacted are lost.
- Dropped old messages: when the budget forces a drop, early decisions can vanish (one fact here). A 9 MB transcript dropped 70 of 332 messages; a 20 MB one would drop more.
- Saved transcripts contain secrets and personal data (an email address appears in a tool result in eb5f8678). The trimmer does not redact. P-88 must run redaction (wn/redact.py exists) before sending text to a helper.
- Sessions with a real rightsize cache trigger were not measured: cold time (minutes since last turn) was not checked, only the token counts.
- The cost ratio uses list prices cached in the claude-api skill on 2026-11-03, not re-checked today.
