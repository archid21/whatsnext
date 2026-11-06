# Competitive review and reuse for whatsnext
Date: 2026-11-06 (UTC). Status: proposed, unverified unless a row says otherwise.

## Summary

The closest overlap is the compact side: prep-compact (MIT, Python inside bash hooks) keeps a running on-disk record from the transcript and drafts a tailored `/compact` line, and compact-hooks (MIT, shell) saves the compact summary. On the handoff side, agent-handoff (MIT, Python stdlib, Claude Code and Codex), cc-handoff (Apache-2.0) and claude-handoff (MIT) each write a handoff note, but none builds the compact text from a fixed structure and none records git facts, which is whatsnext's gap-filler. 13 of the 15 tools reviewed are MIT or Apache-2.0; Task Master (MIT plus Commons Clause) and Claude Code itself (proprietary) cannot be vendored. The most reusable code is small: prep-compact's user-message filter and tail-read loop, its atomic write with a stale-write guard, and agent-handoff's tracked-file guard. Three findings change the plan for rows 4 to 6: PreCompact stdout has no dependable size cap on Claude Code (a 2.2 MB `bd prime` hook caused compaction thrash), Codex documents PreCompact plain-text stdout as ignored, and a PreCompact hook that prints JSON can be rejected. Memory plugins (claude-mem, Mem0) and trackers (Beads, Backlog.md, Task Master) stay out of scope under ADR-0001 and the rightsize-engine framing.

## Tools reviewed

License column: read from the repo's LICENSE file or the GitHub license field (both fetched 2026-11-06). Stars are not recorded because they do not drive reuse.

| Tool | URL | License | Runtime | What it does | Reuse (specific) | Learn only | Candidate rows |
|---|---|---|---|---|---|---|---|
| prep-compact 3.0.3 (repo now named better-compact) | https://github.com/koenvdheide/better-compact | MIT (LICENSE read locally and GitHub field) | bash wrappers with Python 3 inside | Stop hook keeps a handoff JSON (files, todos, subagent launches, last 5 user requests). A reminder fires above 450,000 tokens. The `/prep-compact` skill emits a one-line `/compact <instructions>`. | `recent_user_requests` filter and tail-read loop (about 60 lines); atomic write with an mtime stale-write guard; single-line `/compact` rule. See the detailed section. | Session-bound lookup by `CLAUDE_CODE_SESSION_ID` plus stored `cwd`; the mini-schema field order | 5, 6, 20, 25 |
| rhuss/cc-handoff | https://github.com/rhuss/cc-handoff | Apache-2.0 (LICENSE read) | bash | `/handoff` writes a Markdown note with YAML frontmatter to `~/.claude/handoffs/<project>/`. A SessionStart hook counts pending notes. Loaded notes move to `consumed/`. | Retention shape: `max_handoffs` 5 and `max_consumed` 10, pruned when a new note is written (the numbers only, no code needed) | Notification modes (proactive, passive, quiet); project slug from git remote | 14 |
| REMvisual/claude-handoff | https://github.com/REMvisual/claude-handoff | MIT (GitHub field) | Skills (Markdown) plus a TypeScript mod | `/handoff` mines the conversation into a long note (goal, state, what was tried, decisions, next steps). `/compact-handoff` swaps the conversation for the note after checking the files exist. | Nothing to vendor (skills are prompts, the mod is Claude Code specific) | A "what we tried" section for rejected approaches; leaving the context untouched when the note fails validation | 3, 16, 24 |
| blazeboltmarketing/agent-handoff | https://github.com/blazeboltmarketing/agent-handoff | MIT (LICENSE read) | Python 3 stdlib, one hook file | SessionStart hook for Claude Code and Codex. It tells the new session to read `HANDOFF.md`. If the note's `Done when:` command exits 0, it moves the note to `.handoff-archive/`. | `hooks/handoff_hook.py` guards (about 45 lines): run the command only if the file is not tracked by git; timeout; process-group kill; archive with `os.replace` into a timestamped name | One-line status text ("updated 3h ago, read it first"); AGENTS.md snippet as a hook-free fallback | 14, 23 |
| adrrr/persistent-handoff | https://github.com/adrrr/persistent-handoff | MIT (GitHub field) | bash | One handoff file, rewritten at milestones, re-read by a SessionStart hook; deleted when empty. Stored outside the repo (`~/.local/state/`) because writes under `~/.claude` prompt. | Nothing | The six-rule contract (one file, auto-read, remove what is resolved); 300 to 500 tokens as a useful size | 3, 17 |
| hacktivist123/agent-session-resume | https://github.com/hacktivist123/agent-session-resume | MIT (GitHub field) | Python 3 stdlib scripts plus a skill | A resume skill with scripts that list and digest past sessions for Claude Code, Codex and others. | `session-events.py`: Codex row shapes (`session_meta`, `event_msg` and `response_item` with `payload.type` `user_message`) and Claude row shapes, about 60 lines; use as a map for a Codex user-message reader | Index files of Codex: `session_index.jsonl`, `sessions/YYYY/MM/DD/*.jsonl`; a sidecar digest cache | 6 (Codex part) |
| MatthewJamisonJS/compact-hooks | https://github.com/MatthewJamisonJS/compact-hooks | MIT (GitHub field, page) | bash and PowerShell | PreCompact prints a keep-list (goal, decisions, files, latest error verbatim, blockers). PostCompact saves the summary to `~/.claude/last-compact-summary.md` with a `.bak` rotation and a failure diagnostic. | Idea only: rotate the previous file and write a "do not trust" marker when extraction fails. Its transcript scan (`compact_boundary` plus `parentUuid`) is not needed, because PostCompact already gives `compact_summary` | Keep-list wording; a CLAUDE.md "check for saved summary" block (whatsnext's SessionStart hook does this better) | 4, 5, 21 |
| MarcinSufa/claude-handoff | https://github.com/MarcinSufa/claude-handoff | MIT (GitHub field, badge) | Node (JavaScript) | `/handoff` writes `HANDOFF.md` plus a single-shot marker and opens a fresh session that a SessionStart hook resumes. A PostToolUse hook watches rate-limit use. | Nothing | One-shot marker consumed at resume; refusing to hand off when no goal or next step can be named | 3 |
| claude-mem (thedotmack) | https://github.com/thedotmack/claude-mem | Apache-2.0 (LICENSE read) | TypeScript, Bun worker | Records tool use through hooks, compresses it with a model, and injects relevant memory at session start. | Nothing (needs a worker, database and model calls; ADR-0001 items 4 and 5) | SessionStart matcher `startup\|clear\|compact`; hooks as a launcher command with no shell | none (out of scope) |
| Mem0 (claude-code-plugin) | https://github.com/mem0ai/mem0 | Apache-2.0 (GitHub field) | Python 3.10+ and hosted API | Hooks capture session details; a background worker sends them to a hosted memory API and recalls them later. | Nothing (hosted key, background worker) | `transcript.py` adapter layout: one adapter per agent | none (out of scope) |
| Beads (gastownhall/beads) | https://github.com/gastownhall/beads | MIT (LICENSE read) | Go | Issue graph with `bd ready`, atomic `bd update --claim`, `bd close`. Codex and Claude hooks run `bd prime` at SessionStart and PreCompact; Codex PostCompact writes a marker and the next prompt re-injects. | Pattern only: marker file written at PostCompact, consumed once at the next UserPromptSubmit | `bd prime` output must stay small (see #101057); claim and ready queue | 10, 13, 22 |
| Backlog.md (MrLesk) | https://github.com/MrLesk/Backlog.md | MIT (LICENSE read) | TypeScript | Markdown task files with acceptance criteria, a Definition of Done checklist, dependencies; one task per agent session. | Nothing | "One task per session, one PR per task" as the unit of resume; DoD as a reusable checklist | 8, 13 |
| claude-task-master | https://github.com/eyaltoledano/claude-task-master | MIT plus Commons Clause (LICENSE read; GitHub reports NOASSERTION). Cannot vendor: the clause bars selling a product whose value comes from the software. | JavaScript | PRD to task list, `next_task`, `set_task_status`, subtasks, dependencies; MCP server. | Nothing | `next` plus `set status` as the minimal step API (whatsnext already has it) | none (planner; out of scope) |
| Claude Code built-ins | https://code.claude.com/docs/en/hooks | Proprietary: "All rights reserved" (anthropics/claude-code LICENSE.md read). Docs are not vendorable. | TypeScript (closed) | `/compact [instructions]`, PreCompact and PostCompact hooks, SessionStart `source` values, `claude --resume`, auto memory (200 lines or 25 KB). No handoff command; #11455 is still open. | Nothing (format facts only) | PreCompact stdout becomes summary instructions; PostCompact gets `compact_summary`; SessionStart `compact` matcher | 4, 5, 6, 20, 21, 26 |
| Codex built-ins | https://learn.chatgpt.com/docs/hooks (redirected from developers.openai.com/codex/hooks) | Apache-2.0 (openai/codex GitHub field; docs not read for license) | Rust | `codex resume [--last]`, `codex fork`, hooks incl. PreCompact and PostCompact. Docs say PreCompact plain-text stdout is ignored; `continue: false` stops it. SessionStart takes `source` `compact`. | Nothing | Compact cannot be shaped from a hook on Codex; the transcript format "is not a stable interface" | 4, 18, 22 |

## prep-compact in detail

Version 3.0.3, read from `/Users/home/.claude/plugins/cache/claude-community/prep-compact/3.0.3`. License: MIT, "Copyright (c) 2026 Koen van der Heide" (LICENSE file). The GitHub repo is `koenvdheide/better-compact`; `plugin.json` still names `koenvdheide/prep-compact`, which GitHub redirects.

### Files

| File | Event or role | What it does |
|---|---|---|
| `hooks/hooks.json` | wiring | `UserPromptSubmit` runs `check-context-size.sh` (synchronous). `Stop` runs `update-handoff.sh` with `"async": true`. No PreCompact hook, no SessionStart hook. |
| `hooks/update-handoff.sh` | Stop | Bash wrapper that reads stdin, validates the session id (`^[A-Za-z0-9_-]{1,64}$`, else a SHA-1 of it), then runs one embedded Python 3 program. Writes `${CLAUDE_PLUGIN_DATA}/handoff-<sid>.json`. Always exits 0. |
| `hooks/check-context-size.sh` | UserPromptSubmit | Reads the last 256 KB of the transcript, finds the newest main-chain assistant `message.usage`, sums `input_tokens + cache_creation_input_tokens + cache_read_input_tokens`. At or above `CLAUDE_CONTEXT_WARN_TOKENS` (default 450,000) it prints one reminder naming the handoff path. A flag file `compact-warned-<sid>` makes it fire once per crossing; it clears when the count drops. |
| `skills/prep-compact/SKILL.md` | skill | Tells the model to resolve this session's handoff, read it, add an analytical pass over the last 30 turns (goal, next, decisions, constraints, blockers, tests), and print one single-line `/compact goal: ... \| next: ... \| files: ... \| decisions: ... \| state: ...`. It must check the line has no newline and starts with `/compact goal:`. |
| `skills/prep-compact/resolve-handoff.sh` | skill helper | Finds this session's JSON by `CLAUDE_CODE_SESSION_ID` in the plugin data dir, other plugin data dirs and `~/.claude/cache`, and accepts it only if the stored `cwd` equals the current one. Prints `HIT <path>`, `MISS` or `NOSID`. |
| `test/run-tests.sh`, `test/fixtures/*` | tests | Fixtures: `stop-real.json`, `ups-real.json` (real hook payloads), `handoff-prior.json`, and six transcript JSONL files (multi-turn, malformed tail, oversized line, no user text, tool blob, usage). |
| `.claude-plugin/plugin.json`, `CHANGELOG.md`, `PRIVACY.md`, `.github/workflows/test.yml` | metadata | Not code to reuse. |

### What the Stop hook extracts and how

Method: no jq, no grep, no node. The bash wrapper starts Python 3 once; Python reads the last 1,048,576 bytes of `transcript_path`, splits lines, and calls `json.loads` on each (lines over 1 MiB and bad JSON are skipped). It then walks the parsed entries newest first and skips `isSidechain` entries.

- **Files touched.** Tier A: `tool_use` blocks named `Read`, `Edit`, `Write`, `NotebookEdit`, fields `file_path` and `notebook_path`. Tier B: `Glob` and `Grep` input fields (`path`, `file_path`) plus path-shaped tokens from the first 2,000 characters of their `tool_result` text (token before the first `:`, must contain a separator and a dotted last segment, rejects `" $ < > | * ?` and backtick). Noise filter drops `.git/` and `.claude/plugins/{data,cache}/`. A cumulative list is merged with the previous JSON and capped at 200.
- **Recent user requests.** For `message.role == "user"` entries, join the `text` blocks (a string `content` is treated as one text block); skip entries that only hold `tool_result` blocks; skip text that starts with `<task-notification>`, `[SYSTEM NOTIFICATION` or `Base directory for this skill:`. Keep at most 5 messages and 20,000 characters in total, newest first; a message that does not fit is skipped, not clipped. Merged with the prior JSON, de-duplicated. `PREP_COMPACT_NO_USER_QUOTES` turns it off and clears old quotes.
- **In-progress todos.** The newest `TodoWrite` `tool_use`: items with `status == "in_progress"`; `in_progress_status` is `known` or `unknown`.
- **Subagent launches.** Every `tool_use` named `Task`: `<subagent_type>: <description>`. The hook never knows whether an agent finished.
- **Not extracted:** decisions, constraints, blockers, test results. The skill asks the model for those at `/prep-compact` time.

Observed on this machine (2026-11-06, 15 newest transcripts under `~/.claude/projects`): subagent launches appear as `tool_use` named `Agent`, not `Task`, and no `TodoWrite` was seen. So on current Claude Code the subagent field is probably empty and the todo field may be. This is a local sample, not a proof for every version.

### JSON schema it writes (version "3.0")

`version`, `session_id`, `cwd`, `transcript_path`, `transcript_mtime_at_write`, `written_at` (UTC `...Z`), `cumulative_files[]`, `recent_files[]`, `in_progress_status`, `in_progress[]`, `recent_task_launches[]`, `recent_user_requests[]`. Write path: `tempfile.mkstemp` in the same folder, then `os.replace` (one retry on `PermissionError`); before replacing it reads the existing file and skips the write if that file's `transcript_mtime_at_write` is newer (guards against two async Stop runs).

### Can whatsnext read or write that JSON?

- **Read it: no, by design.** It sits in the other plugin's data folder (`${CLAUDE_PLUGIN_DATA}`, or `~/.claude/cache`), outside the repository. ADR-0005 item 5 says whatsnext does not rely on another plugin's hooks, and ADR-0010 item 6 keeps plugin links to the command line. Reading it would also break when prep-compact is not installed.
- **Write it: no need.** Nothing consumes the file except prep-compact's own skill.
- **Mirror the idea in whatsnext's own files:** `recent_user_requests` becomes a git-ignored `last_request` field in `.whatsnext/sessions/<session>.*`, or is computed at PreCompact and never stored (see row 6 below).

### Directly portable to Python stdlib (all of it is already Python)

1. Tail-read plus per-line `json.loads` loop (`TAIL_BYTES`, skip bad lines), about 20 lines.
2. User-message extraction: join text blocks, skip tool-result-only entries, skip injected prefixes, skip sidechains. Change on port: also skip `isMeta` entries (3 appear in the local sample) and clip an oversized message instead of skipping it, because the latest request is the one that must survive.
3. Atomic write with a stale-write guard (mkstemp, `os.replace`, compare mtime).
4. Session id sanitizer (`^[A-Za-z0-9_-]{1,64}$` or SHA-1). whatsnext's `sessions.py` likely has its own; compare before adding.
5. Single-line `/compact` rule: a newline right after `/compact` fires the bare command and drops the text (README and SKILL.md of prep-compact). Add a test that whatsnext's `compact_line` has no newline.

Not portable: the token-threshold reminder (rightsize's job), the skill's model pass (ADR-0001 item 4, no model call), `cygpath` handling (whatsnext does not target Git Bash).

### License and attribution

MIT requires the copyright and permission notice in "all copies or substantial portions". A 20 to 60 line port with changed structure is a rewrite of an idea; copying lines verbatim needs a short header comment ("Adapted from prep-compact 3.0.3, MIT, (c) 2026 Koen van der Heide, https://github.com/koenvdheide/better-compact") and the MIT text in a `THIRD_PARTY_NOTICES` entry. Unverified: whether the project wants a notices file; ADR needed if so (suggest a short ADR-0011).

### Fragility to record

- The transcript JSONL is undocumented in the hooks reference (prep-compact's own README says so; Codex docs say the same for Codex).
- Claude Code writes a `last-prompt` entry (`{"type":"last-prompt","lastPrompt":"...","leafUuid":...}`) in this machine's transcript. It is undocumented and seen in one local file; use only as a cross-check, never as the source.

## Enriched candidates

New rows continue the numbering of `feature-candidates.md`. Effort and value follow that file's scale. "Already in code?" was checked against `skills/whatsnext/scripts/wn/` on 2026-11-06 (hook.py events list, plan.py verify timeout, redact.py).

| # | Pillar | Feature | What it means (1-2 sentences, plain language) | Effort | Value | Pain point / evidence | Already in code? | Source tool / reuse |
|---|---|---|---|---|---|---|---|---|
| 20 | Compacts | Cap the PreCompact text and read `custom_instructions` | PreCompact prints at most about 3,000 characters. If `custom_instructions` is not empty (the user typed `/compact <text>`, or ran prep-compact), print only the verbatim request and the facts block, not the full keep-list. | S: one length cap, one branch | High: prevents a bad failure of row 4 | Claude Code appends every PreCompact stdout to the compaction instructions; one `bd prime` hook printed about 2.2 MB and caused "Autocompact is thrashing" (#101057, v2.1.296, open) [15]. The hooks page says 10,000 characters in one place and exempts PreCompact from the cap in another [14]. | No. `compact.py` caps the handoff text at 3,000 (ADR-0009) but the PreCompact hook prints nothing yet. | Claude Code hooks reference [14], #101057 [15]. Reuse: none; commenters' workaround is to print the first 8,000 bytes plus a path. |
| 21 | Compacts | Keep the compact summary and check it | PostCompact saves `compact_summary` to git-ignored session state (previous one kept as `.bak`). The next resume note adds one line: "summary kept 2 of 5 plan steps". | M: new event, new file, a step-ID match | Med: makes silent loss visible; rightsize can show it | Compaction is invisible to the user (anthropics/claude-code #96422, cited in `feature-candidates.md`); a feature request asks to export the summary [22] | No. PostCompact is not an event in hook.py (EVENTS line 31). | compact-hooks [7]: `.bak` rotation and a "do not trust" marker on failure. PostCompact input has `compact_summary` directly, so skip its transcript scan [14]. |
| 22 | Compacts | Codex marker fallback after compact | PostCompact writes a marker; the next UserPromptSubmit prints the resume note once and removes the marker. Used only if SessionStart did not run with `source: compact`. | S to M: one marker, one check | Med: Codex-only safety net | Beads ships this exact pattern for Codex [10]; one user saw a plugin hook miss the compact start reason (#96422). Codex docs list SessionStart `compact` as valid [18], so this may be unneeded: test first. | No. `compacted=True` comes from SessionStart only (hook.py:132). | Beads `codex_hook.go` (MIT): pattern only, no code. |
| 23 | Handoffs | Handoff done-when check | A command, `handoff verify`, runs the note's `Verify:` line (the user starts it), and on exit 0 archives the note. It refuses to run a command from a note that git tracks unless the person passes a flag. | M: new command, tracked-file guard, archive step | Med: proof for a handoff, not only for a plan item | agent-handoff runs `Done when:` only for untracked files so a cloned repo cannot make an agent run its command [4]. | Partly. ADR-0008 item 3 puts a `Verify:` line in the note; plan.py already has `verify_timeout` and a process-group kill (plan.py:509-549). Nothing runs the handoff's line. | agent-handoff `handoff_hook.py` (MIT): the `git ls-files --error-unmatch` guard and the archive step. The timeout code already exists in plan.py. |
| 24 | Handoffs | "Dead ends" line in the note and the compact text | The handoff gets one short section: approaches tried and rejected, one line each with the reason. The compact keeps it (cap about 300 characters). | S: one section, one cap, ADR-0008 and ADR-0009 text change | Med to High: stops a repeat of work already ruled out | claude-handoff calls failed approaches "the most expensive thing to rediscover" (author claim, from an A/B test the author ran, not independent) [3]; agent-handoff has a `Dead ends:` field [4]; prep-compact keeps dead ends that underpin a blocker [1]. | No. ADR-0009 item 1 says the compact text drops dead ends; the ADR-0008 structure has no such section. | claude-handoff, agent-handoff: learn only. Needs an amendment of ADR-0009 item 1. |
| 25 | Compacts | Open subagents and in-progress todo in the keep-list | The PreCompact text adds "agents launched this session" and the agent's own in-progress todo, read from the transcript tail. | M: two transcript shapes, tool names changed | Low to Med: the plan step already says what is in progress | prep-compact exists because compaction forgets running subagents [1] | No. | prep-compact [1]: tool-use walk. Port with tool names `Agent` and `Task`, and `TodoWrite`, because locally only `Agent` appears. Do after rows 4 to 6. |
| 26 | Compacts | Hook output contract test | A test asserts that PreCompact prints plain text only (never JSON), and SessionStart prints JSON with `hookEventName` (or plain text). A failing format is reported by Claude Code as a failed hook and none of its text reaches the model. | S: one test per event | High: guards rows 4, 5 and 6 | Dev10x printed `hookSpecificOutput` without `hookEventName` for PreCompact; Claude Code rejected it (closed 2026-11-02, fix format not stated) [16]; docs: PreCompact `systemMessage` and `continue` are discarded [14] | No test covers stdout shape per event (not checked in tests/; verify before building). | Dev10x issue [16]: learn only. |

### Existing rows whose effort or value changes

- **Row 6 (latest request verbatim): effort M to S, value stays High.** Port prep-compact's user-message extraction and run it at PreCompact time against `transcript_path`, so nothing is stored on disk and no new privacy rule is needed. Keep the `prompt-submit` copy only as a fallback for Codex. Changes on port: skip `isMeta`, `wrap up`, `/compact` and tool-result-only entries; clip, never skip, a long message (suggest 2,000 characters plus "(clipped)"); run `redact.clean` on it. Codex has a different row shape (`event_msg` with `payload.type` `user_message`), shown in agent-session-resume [6]; its docs warn the format is unstable [18]. Amends ADR-0005 item 3 ("no transcript reading") for PreCompact only.
- **Row 5 (facts-only keep-list): effort S stays, value High stays; wording source found.** The ADR-0008 sections (Goal, Next action, State, Decisions, Constraints, Blockers) map one to one to prep-compact's mini-schema (goal, next, files, decisions, constraints, blockers, state), so the same code path can feed both the handoff version and the facts version. Add the single-line and no-newline test (portable item 5 above) for rightsize's `compact_line`.
- **Row 4 (auto-compact safety net): effort M stays, scope splits.** On Claude Code the stdout is appended (per #101057; docs silent) and needs row 20's cap. On Codex, PreCompact plain-text stdout is ignored [18], so only the journal fact "compacted without wrap-up" and the SessionStart `compact` resume note can ship there. This answers the open "added or replaces" question in `feature-candidates.md` for Claude Code only, from a bug report, not from the docs.
- **Row 14 (archive before overwrite): effort S stays, value High to Med.** It helps two-agent use, not the rightsize pairing. Reuse the retention numbers from cc-handoff (5 pending, 10 consumed) and `os.replace` into a timestamped name from agent-handoff.
- **Row 18 (`doctor`): value rises.** It can print a per-agent capability line: "PreCompact text: Claude Code yes, Codex no (ignored)".
- **Rows 8 and 9: no reuse needed.** plan.py already has a timeout and process-group kill, so agent-handoff's code adds nothing there.

## Re-ranked first five under the rightsize-engine framing

Handoff and compact rows first. Planning rows appear only where they serve "which step is done, which is next, is it proven".

1. **Rows 4 + 20 + 26 together (Claude Code PreCompact text).** Auto-compact is the top reported loss, and the text is the one lever whatsnext has. Rows 20 and 26 are what keeps it from failing or flooding. Codex gets only the fact line and the resume note.
2. **Row 6 (latest request verbatim, computed at PreCompact).** The most named loss at compaction; now S effort by porting prep-compact's filter; no stored text.
3. **Row 5 (facts-only keep-list).** Guides every compact when no `wrap up` happened, which is the usual case for auto-compact.
4. **Row 8 (verify records the code state).** The only planning row that serves "is it proven": it stops a stale pass from counting as done. Small, and the data already exists in git.
5. **Row 24 (dead ends line).** Cheap handoff and compact quality gain; needs an ADR amendment. Row 14 (archive) is the next pick if two-agent use matters more than quality.

Moved down: row 7 (hand-tick guard) and row 13 (`blocked by:`) leave the first five because they extend planning beyond step completion; row 7 stays useful if agents keep ticking boxes by hand.

## Leave to other tools

| Feature found in competitors | Seen in | Why whatsnext should not build it |
|---|---|---|
| Cross-session memory, fact extraction, semantic recall, hosted or vector store | claude-mem [8], Mem0 [9] | ADR-0001 items 2, 4, 5: no memory, no model call, no database or background process |
| Issue graph, atomic claim, ready queue, dependency types, Dolt storage | Beads [10], Task Master [12] | Framing: whatsnext tracks step completion only. ADR-0001 "Not in this release" (tracker adapters, cross-machine claims). Row 13 stays low. |
| PRD parsing, task expansion into subtasks, complexity analysis | Task Master [12] | Planning tool; also Commons Clause license, cannot vendor |
| Acceptance criteria, Definition of Done boards, review checkpoints, web UI | Backlog.md [11] | Planning and review UI; whatsnext's proven-done is one command per step |
| Context-size reminder at a token threshold | prep-compact [1], agent-handoff statusline [4] | rightsize decides when (ADR-0010 item 1) |
| Model pass that writes decisions, constraints, blockers at compact time | prep-compact skill [1] | ADR-0001 item 4: no model call; whatsnext's note is written by the agent on `wrap up` |
| Spawning a fresh session or tab and waking it | claude-handoff (MarcinSufa) [13], REMvisual mod [3] | A hook cannot start a model turn; editor-specific; ADR-0009 item 1 says whatsnext never submits into another process |
| Replacing the conversation with the handoff (no summarizer call) | REMvisual `/compact-handoff` [3] | Needs a mod and Claude Code internals; the compact stays the person's or rightsize's action |
| Handoffs stored outside the repo, per user | cc-handoff [2], persistent-handoff [5] | ADR-0001 item 6 and 7: files in the repository are the source of truth |
| Search over past sessions and transcript digests | agent-session-resume [6] | ADR-0001 item 2: no search over past conversations |

## Sources

Each URL was fetched, read through the GitHub API, or returned by a search on 2026-11-06. "Search result only" means the page was not opened.

1. prep-compact 3.0.3, local install (README, hooks, skill, fixtures, LICENSE, CHANGELOG read): `/Users/home/.claude/plugins/cache/claude-community/prep-compact/3.0.3`; upstream repo metadata via GitHub API: https://github.com/koenvdheide/better-compact
2. cc-handoff (README, LICENSE read via GitHub API): https://github.com/rhuss/cc-handoff
3. claude-handoff, REMvisual (README read via GitHub API; license from GitHub field): https://github.com/REMvisual/claude-handoff
4. agent-handoff (README, `hooks/handoff_hook.py`, `hooks/hooks.json`, LICENSE read via GitHub API): https://github.com/blazeboltmarketing/agent-handoff
5. persistent-handoff (README read via GitHub API; license from GitHub field): https://github.com/adrrr/persistent-handoff
6. agent-session-resume (README, `references/codex.md`, `scripts/session-events.py` read via GitHub API; license from GitHub field): https://github.com/hacktivist123/agent-session-resume
7. compact-hooks (page fetched; `scripts/post-compact-capture.sh` read via GitHub API; license from GitHub field and page): https://github.com/MatthewJamisonJS/compact-hooks
8. claude-mem (README, `plugin/hooks/hooks.json`, LICENSE read via GitHub API): https://github.com/thedotmack/claude-mem
9. Mem0 and its Claude Code plugin (README and tree read via GitHub API; license from GitHub field): https://github.com/mem0ai/mem0
10. Beads (README, `cmd/bd/codex_hook.go`, `cmd/bd/agent_hook.go`, LICENSE read via GitHub API): https://github.com/gastownhall/beads
11. Backlog.md (README, LICENSE read via GitHub API): https://github.com/MrLesk/Backlog.md
12. claude-task-master (README, LICENSE read via GitHub API): https://github.com/eyaltoledano/claude-task-master
13. claude-handoff, MarcinSufa (README read via GitHub API; license from GitHub field and badge): https://github.com/MarcinSufa/claude-handoff
14. Claude Code hooks reference (fetched in full as Markdown; PreCompact, PostCompact, SessionStart sections): https://code.claude.com/docs/en/hooks.md
15. anthropics/claude-code #101057, "PreCompact hook output is added to the compaction instructions with no size limit" (open, v2.1.296): https://github.com/anthropics/claude-code/issues/101057
16. Dev10x-Guru/Dev10x-Claude #1788, "Restore post-compaction context the PreCompact hook drops" (closed 2026-11-02): https://github.com/Dev10x-Guru/Dev10x-Claude/issues/1788
17. anthropics/claude-code #11455, "Feature Request: Session Handoff / Continuity Support" (open, no maintainer reply seen; fetched): https://github.com/anthropics/claude-code/issues/11455
18. Codex hooks documentation (fetched via redirect from developers.openai.com/codex/hooks): https://learn.chatgpt.com/docs/hooks
19. Claude Code memory documentation (fetched; only the first part was used: CLAUDE.md and auto memory, no handoff feature): https://code.claude.com/docs/en/memory
20. anthropics/claude-code repository LICENSE.md (GitHub API): https://github.com/anthropics/claude-code
21. openai/codex repository, license field only (GitHub API): https://github.com/openai/codex
22. Feature request, "pre-compact hook or include last N interactions in compact summary" (search result only): https://claudeissues.com/issue/21190-feature-request-pre-compact-hook-or-include-last-n-interactions-in-compact-summa
23. Feature request, "Command to view/export context compaction summary" (search result only): https://claudeissues.com/issue/21788-feature-request-command-to-view-export-context-compaction-summary
24. DEV Community, "Claude Code Compaction Kept Destroying My Work. I Built Hooks That Fixed It" (search result only): https://dev.to/mikeadolan/claude-code-compaction-kept-destroying-my-work-i-built-hooks-that-fixed-it-2dgp
25. Codex CLI session lifecycle (resume, fork, compact; search result only, third party): https://codex.danielvaughan.com/2026/06/05/codex-cli-session-lifecycle-archive-resume-fork-compact-management/
26. EhsanMo/claude-session-handoff, 392fyc/claude-handoff, apurvbazari handoff (SessionEnd-summary and pointer-injection variants; search result only, not in the table): https://github.com/EhsanMo/claude-session-handoff
