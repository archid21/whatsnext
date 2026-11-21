# ADR-0035: Handoff from a saved transcript: whatsnext prepares the input and writes the note, the caller's own model reads it

- **Date:** 2026-11-20T23:43Z
- **Status:** accepted (user), 2026-11-20

Builds on ADR-0008 (the handoff note), ADR-0027 (wrap-up instructions for hookless agents; any network call is made by the user's own tool), ADR-0030 (claim checks at resume) and ADR-0025 (rightsize decides when, whatsnext says how). For P-88. The test is in `docs/project/research/p88-transcript-handoff.md`.

## Context

`wrap up` makes the main model write the note from the live chat. When the chat has sat idle past its cache time, the prompt cache is cold. The wrap-up turn then pays to write the whole context into the cache again (128,000 to 249,000 tokens in the test), and only afterwards writes a note of about 1,200 output tokens. The chat is about to be dropped, so that rebuild buys nothing else.

Claude Code saves each chat as `~/.claude/projects/<project>/<session>.jsonl`. A cheaper model can read that file instead.

**The test (research file above, 2026-11-20).** Four real transcripts (1.8 to 4.5 MB each), each cut just before its real "wrap up" message. A Sonnet 5.5 helper wrote a note from the trimmed text only (40 to 120 KB). The author of the test played the helper, in a chat, with no repo access. The same person scored the result against the real note, fact by fact.

- 102 reference facts: 65 matched (64%), 36 missed (35%), 1 wrong (1%).
- A fresh session could continue: yes on 2 of 4, partly on 2, no failures.
- Why 36 facts were missed: 17 were repo or user rules that are not in a transcript (nearly all in Constraints), 10 were cut by the test's trimmer, 8 were in the text and the helper left them out, 1 was in a dropped old message.
- Cost, cold cache: the helper costs 12 times less (5-minute cache write) to 28 times less (1-hour cache write) than the main model's wrap-up turn.
- Cost, warm cache: about equal. The helper costs 0.5 to 1.2 times a warm wrap-up.
- Prices are API list prices cached in the `claude-api` skill on 2026-11-03, not re-checked. The user is on a Claude Team plan, so for this user the numbers are a share of plan usage limits, not a bill. The ratio is the useful number.

## Decision

1. **One command, two steps, no model call inside whatsnext.** `whatsnext handoff from-transcript <path.jsonl>` takes one of two flags:
   - `--prepare` is read-only. It prints, on stdout, the helper prompt and then the trimmed input. The prompt is the wrap-up note format of `wrap-up-instructions` (ADR-0027) with two changes: it tells the helper to return only the eight `##` sections as text, and to keep the user's rules and corrections in Constraints and every dead end seen in Dead ends. `--json` prints `{prompt, input, bytes, dropped_messages, session}` for a caller that wants fields. `--budget-bytes N` overrides the default budget (decision 3).
   - `--write <note file>` reads the helper's answer from `<note file>` (`-` reads stdin), checks it, and writes the note to `docs/project/HANDOFF.md`. whatsnext writes the header itself (`Session:` the transcript's session id, `Task:`, `Written:` now in UTC, `Branch:`, `Agent:`, and the `Source:` line of decision 4), so the helper cannot omit or alter it. Checks: the eight sections of ADR-0008 in order, none missing and none extra (no `## Files`, `## Links` or `## Skills`); one `Verify:` and one `If it fails:` line under Next action; at least one `Check:` line; each section within its size cap (the caps in `wrapup.LINE_SECTIONS`). When a check fails it prints each reason, writes nothing, and exits 1, so the caller can ask the helper again. When all pass it archives the old note as usual (`archive_handoff`) and writes the new one atomically.

   The model call belongs to the caller: rightsize (its P-71) or an agent that starts its own Sonnet subagent. whatsnext makes no network call, holds no API key, and stays Python 3.9 standard library only (ADR-0027 rule 5, ADR-0001). A caller with no model access can still use `--prepare` and hand the text to a person.
2. **The helper's input adds four repo facts that a transcript lacks:**
   - `AGENTS.md`.
   - The previous handoff note (`docs/project/HANDOFF.md`), when it exists.
   - The active item's progress file in `docs/project/progress/`, when there is one.
   - A git snapshot taken at prepare time: `git rev-parse --short HEAD`, `git branch --show-current`, `git status --short`, and `git log --oneline -10`.

   The helper writes its `Check:` lines from the snapshot, not from the chat.
3. **Trimming.** The input is built from the `.jsonl` file as follows:
   - Each tool result is cut to its first 800 and last 400 characters.
   - Each tool call is one line.
   - Thinking blocks are dropped (saved files hold them empty).
   - `Write` and `Edit` inputs for files under `docs/decisions/`, and for the handoff note, are kept in full (the test used a cap of about 6 KB per input; the build sets the final cap).
   - The opening request and `AskUserQuestion` text (it holds the plan steps) get extra room.
   - Over the byte budget, the oldest messages are dropped first, and the opening request stays. The default budget is 120 KB (about 30,000 tokens). The input says how many messages were dropped.
4. **Use it only when the chat's cache is cold.** The caller decides, not whatsnext (rightsize's P-71 knows the idle time). When the cache is warm, the normal `wrap up` costs about the same and reads the live chat, so it stays the default. A note from this path carries the header line `Source: transcript <session8>, unverified` (`<session8>` is the first eight characters of the session id). The next session runs the ADR-0030 claim checks on it as for every note, and `status` shows the `Source:` line with the note so the reader treats the facts as unverified. `Check:` and `Verify:` lines stay mandatory so a wrong note fails early.
5. **Redact before anything is printed.** `--prepare` runs the existing `redact` module over the whole input: `strip_private` for `<private>` spans and `mask_secrets` for keys, tokens, key blocks and `password=` forms. The module has no email pattern today, and the test found an email address in a tool result, so the build adds one (an opt-in argument, so the hook output of existing callers does not change). `--write` masks the helper's note the same way before it writes.
6. **The transcript never leaves the machine except as the redacted, trimmed text** that `--prepare` prints and the caller sends to its own model. whatsnext reads the one file it is given, writes only the handoff note and its archive copy, and sends nothing anywhere.

7. **`--write` runs the ADR-0030 claim checks and prints their verdicts, but still writes the note** (accepted 2026-11-20). The note is already marked unverified, and the next session runs the checks again.
8. **The user's global rules file is not passed to the helper** (accepted 2026-11-20). It lives outside the project and holds personal preferences; the next session loads it anyway.

## Why

- A cold wrap-up pays for a context that is about to be thrown away. A small input read by a cheaper model does the same job for 1/12 to 1/28 of the tokens.
- The test met its bar: the note was good enough to continue on 2 of 4 transcripts and partly on 2, with one wrong fact in 102. The 10 misses that came from the trimmer, and the 17 that came from missing repo rules, are the two things decisions 2 and 3 address.
- The split keeps ADR-0027's rule that whatsnext makes no network call. It also keeps the model choice, the key and the billing with the caller, which already has them.
- `--write` validates in code, so a weak helper answer is caught by structure (sections, `Verify:`, `Check:`) before it replaces a good note.
- Reusing the wrap-up format and the ADR-0030 checks means resume code does not change. A note from a transcript is read like any other note.

## Trade-offs and risks

- **Small test.** n = 4 transcripts, one project, one pass. The scoring was done by the person who played the helper, not an independent reader. Facts are not equally important: a missed "ask before commit" matters more than a missed test count. Read 64% as a rough level, not a measure.
- **The helper in the test is not the production helper.** It was one long chat with no repo access. A `claude -p` call or a subagent will behave differently, and its thinking tokens (assumed 2,000) were not measured.
- **A transcript cannot show current git state or other sessions' edits.** It misses commits made in another terminal after the chat went cold, edits by other sessions in the same checkout, the user's answer to the last question if it was given elsewhere, and anything done outside the chat. Decision 2's git snapshot covers HEAD, branch and dirty files at prepare time, not who changed them or why. A note that says "nothing is committed" can be hours old.
- **A wrong Next action has no signal.** The test's eb5f8678 note named a real open question instead of the planned next item. The trimmer was the cause and decision 3 fixes it, but a bad note still sends the next session the wrong way until a check fails. The `Source:` line and the claim checks lower this risk. They do not remove it.
- **Rules outside the project stay missing.** The user's global rules and corrections from earlier, compacted sessions are not in the input; only `AGENTS.md` is added. Constraints matched 9 of 22 facts in the test, and this change targets the project-rule share of that.
- **Old messages can drop.** A 4.5 MB transcript lost 70 of 332 messages and one fact. A 20 MB transcript would lose more early decisions.
- **Saved transcripts hold secrets and personal data.** The redaction patterns miss some secrets and flag harmless text (see `redact.py`). Redaction lowers the risk of what the caller's model sees; it is not a guarantee.
- **Prices may differ.** The 12 to 28 times ratio uses list prices from 2026-11-03. It also holds only when the cache is cold; when warm, the helper saves nothing.
- **Build work.** `handoff` today accepts only `verify`, so the build adds the `from-transcript` action, a trimmer (about 150 lines in the test), the validator, and the email pattern. The transcript reader depends on Claude Code's `.jsonl` row format; an unknown row type is skipped, and a file with no readable rows is refused.
