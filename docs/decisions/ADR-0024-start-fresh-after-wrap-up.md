# ADR-0024: After a wrap-up, offer a new session or a cleared one, seeded with the handoff

- **Date:** 2026-11-11T02:40Z
- **Status:** accepted (user), 2026-11-11; the band buttons and the desktop start_session path are superseded by [ADR-0026](ADR-0026-wrap-up-band-compact-or-paste.md)

Amends ADR-0008 (`wrap up` writes the handoff note). P-67.

## Decision

1. In Claude Code, after a `wrap up` turn writes the handoff note, the whatsnext band above the prompt shows three buttons until the person's next prompt: **New session**, **Clear and continue** and **Not now**.
2. **New session** keeps this chat as it is. In the desktop app it submits one prompt, as the person's own words, asking the agent to start a new session for this project with the app's session tool. The new session's first prompt is `Continue from the handoff note: read it first.` In the terminal no mod or agent can open a window, so the button shows the command to run in a new terminal window in the project folder: `claude "Continue from the handoff note: read it first."`
3. **Clear and continue** runs `/clear` in this session, then submits the same first prompt as the person's own words. The old chat is not deleted: `/resume` (or `claude --resume`) brings it back.
4. In both cases the new chat reads the handoff the usual way: whatsnext's session-start hook puts the resume note in the new context, and the first prompt points at the note.
5. The wrap-up reply's last line names the buttons. Codex has no band, so its reply is unchanged.

## Why

Starting fresh after a wrap-up took three steps: `/clear` (or a new window), then a prompt to read the handoff. People also want the old chat to look back at a table or an answer, so clearing must not be the only choice.

## Trade-offs

- The mod API has no call that opens a session, and a subagent cannot be moved to its own top-level chat. In the desktop app the new session is started by the agent, so it costs one short model turn, and it depends on the app's session tool being there.
- In the terminal, New session only shows a command to copy: there is no portable way to open a terminal window.
- The band shows only when the note was written during the wrap-up turn; a wrap-up that failed shows nothing.
