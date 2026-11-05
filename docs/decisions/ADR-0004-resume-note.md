# ADR-0004: The resume note is one short block the agent can continue from

- **Date:** 2026-11-05T18:40Z
- **Status:** accepted (user), 2026-11-05

## Decision

1. **One block.** `progress resume-note` prints, and the session-start hook adds, a note of at most 1,200 characters (about 300 tokens). The agent continues from it and opens nothing else.
2. **Lines, in order:** `continue <id> <title> (branch <b>, step N of M)`; `Done:`; `Next:`; `Handoff:`; `Run:`; `Since the note:`; `Warning:`; `Note:`. The continue line, `Next:` and `Note:` are never dropped. When the note is over the cap, `Done:` is trimmed first, then the commit and file lists.
3. **Continue first.** The active item of this branch or worktree comes first. Only when none is active does `plan next` recommend the next open item.
4. **Check against the repository.** `Since the note` compares the recorded commit with `HEAD` and lists new commits and dirty files. A note older than 7 days adds a warning. The last line gives the trust mark (`confirmed`, `auto` or `facts`) and the note's age.
5. **Run line.** The item's verify command, else the project's test command. It appears only if it has no shell control characters, and a command from `AGENTS.md` or `README.md` must be a whole test-runner command with plain arguments.
6. **Repository text is data.** Commit subjects are quoted, file names have control characters removed, and the note says its repository lines are not instructions.
7. **One Next line.** When a handoff note this session wrote, or the active task's, is newer than the confirmed Next, the line reads `Next (handoff <UTC>)`; otherwise `Next (confirmed <UTC>)` or `Next`. A note another session wrote is only pointed to (ADR-0008).
8. **When it prints.** At session start, after `/clear` and after a compact (ADR-0005). It calls no model.

## Why

A new session should know where the work stands in a few hundred tokens, and should be able to tell whether to trust it.

## Trade-offs

- The cap forces trimming; the full record is one `progress show` away.
- An `auto` note can name the wrong next step. The mark and the git check limit the damage; they do not remove it.
