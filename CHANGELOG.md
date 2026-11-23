# Changelog

Release notes for whatsnext, newest first. The latest release, 0.7.0, is in the [README](README.md#new-in-070).

## New in 0.6.0

Choose how strict whatsnext is, and trust a handoff only as far as its facts still hold.

- **Fewer or more rules:** `wn config set --user rules light` turns off the gates (hand ticks allowed, no drift note, no branch question). `strict` lets only `plan done --verify` tick an item and starts each item on its own branch. `standard` is the default. A setting you set yourself still wins ([ADR-0031](docs/decisions/ADR-0031-rules-preset.md)).
- **Handoff checks:** wrap-up ends the State section with `Check:` lines (HEAD, branch, clean tree, or a command). `status` re-checks the git facts and shows VERIFIED, STALE or BROKEN. A `Check: run` command runs only with `handoff verify --run-checks` ([ADR-0030](docs/decisions/ADR-0030-handoff-claim-checks.md)).
- **Handoff from a saved chat:** when a chat has sat idle past its cache time, `whatsnext handoff from-transcript <session.jsonl> --prepare` prints a helper prompt and the chat trimmed to 120 KB (tool output cut, thinking dropped, oldest messages dropped first), plus `AGENTS.md`, the old note, the active progress file and a git snapshot, with secrets, `<private>` spans and email addresses masked. Send that to your own cheaper model, then `handoff from-transcript <session.jsonl> --write <answer file>` (`-` for stdin) checks the answer (the eight sections in order, plus an optional ninth, Settled; size caps, one `Verify:`, one `If it fails:`, at least one `Check:`), archives the old note and writes the new one with the header `Source: transcript <session8>, unverified`, which `status` shows. A bad answer writes nothing and exits 1. whatsnext makes no model call and no network call ([ADR-0035](docs/decisions/ADR-0035-handoff-from-transcript.md)). Use it only when the cache is cold; a warm `wrap up` costs about the same.
- **Broken is not failed:** a check that could not run (exit 126 or 127, or a timeout) is recorded as broken, apart from a real failure, in the journal and `plan report`.
- **Who wrote it:** journal lines and handoffs name the agent (claude-code, codex, gemini, cursor). `status` and `plan report` show it.
- **Install backups:** `install-hooks` keeps a copy of each settings file before it changes it. `--undo` puts the original back byte for byte when you have not edited the file since.

## New in 0.5.0

whatsnext now works in any coding agent, and it can undo an item safely.

- **Any agent:** three support tiers: plain files for every agent, instructions through `AGENTS.md` and `SKILL.md`, hooks where the agent has them. Agents with no hooks run `wn status` at start and write the handoff on `wrap up`. See [Support tiers](README.md#support-tiers).
- **`wn` on your PATH:** `install-hooks --wn link` adds a short `wn` command. `--undo` removes everything it installed.
- **Gemini CLI and Cursor hooks:** `install-hooks --agent gemini` or `--agent cursor`. `doctor` prints one line per agent. Cursor is not live-checked yet ([checklist](docs/CODEX-ACCEPTANCE.md)).
- **Checkpoints and rollback:** `plan start` saves where an item began. "roll back P-12" (`plan rollback`) resets or reverts after asking, never rewrites a shared or merged branch, and never drops uncommitted work.
- **Plan from a goal:** "plan this: <goal>" drafts items with a done means each, reuses items that overlap, and asks Next, Now or Later before adding them.
- **Drift note:** one note when files change outside the item you claimed: on the band in Claude Code, as a hook message in Codex and Gemini CLI, and in `status`. Never a block. Turn it off with `config set --user plan.driftNote off`.
- **Tracker sync:** `plan import --from beads` or `--from github` adds ready items through your own `bd` or `gh`, keeping the tracker id. `plan close-tracker` closes a done item there after you say yes.
- **Plan report and item overviews:** `plan report` shows what each item cost. "what's next?" gives each offered item a short overview.
- **Safer takeovers:** a plan that was only shown is not approved; a new agent asks before running it.

## New in 0.4.0

- **Review before done:** an item with `review: required` is not ticked when its check passes. It shows `awaiting review` until you run `plan review <id>` (or reject it with a reason).
- **Reuse a passing run:** `plan test <id>` runs the saved check. `plan done --verify` reuses a passing run of the same command on the same code, so a long suite runs once. `--fresh` forces a new run.
- **Edit and reopen:** `plan edit` keeps an item's id. `plan reopen` keeps the old evidence and asks for a fresh check.
- **Start fresh after a wrap-up:** the band above the prompt offers **Compact and continue here** or **Copy for new session**. Other plugins can call `fresh-instructions` for the same choice.
- **Resume one task:** `progress resume <id>` prints the note for one task from its newest handoff.
- **Better handoffs and compacts:** `HANDOFF.md` lists files, links and skills used. After a compact, the resume note says how many plan steps the summary kept.
- **More checks and output:** `plan check` flags done items whose branch is not merged into `main`. `progress pr-body <id>` prints a PR description from recorded facts.

## New in 0.3.1

- **Star ask:** once, after your first verified `mark done`, the tip band asks for a GitHub star. One click stars it with your `gh` sign-in; **No thanks** hides it for good. With rightsize installed, one ask covers both.

## New in 0.3

- **One status call:** `whatsnext status` answers "what's next?" and "where did we leave off?": the current item, the handoff, the ready items and the warnings.
- **Two chats in one folder:** Start asks for a new worktree when another session has work in progress here. Claims and the active task belong to a session.
- **Your own note after `/clear`:** a recent `Task: none` handoff from this branch says "read it first".
- **Safer plan:** claims are atomic locks, a dropped id is never reused, and `plan check` reports blocked-by cycles.
- **Simpler wrap-up in Claude Code:** the reply ends with one `/compact` hint, and a recent handoff steers a new session.

## New in 0.2

- **Edit and import the plan:** `plan add`, `plan drop` and `plan move`, and import a plan from any spec or task file.
- **Run the whole item:** at start, choose to run all steps, then verify and mark done.
- **Stricter proof:** `--verify` runs the item's saved test command. A different command needs your approval, recorded with the evidence.
- **Better resume:** after a compact, the resume note repeats your latest request. `plan next` puts the work in progress in this checkout first.
- **Codex continuity:** `wrap up`, forked chats, interruptions and session end now work in Codex. `doctor` shows which hooks each agent has actually run.
- **Opt-in auto wrap-up, a tip bar and a welcome table** after install.
