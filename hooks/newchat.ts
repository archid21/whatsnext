// After a wrap-up (P-67, ADR-0024): start a new session or clear this one, seeded with the handoff note.
// The texts are a copy of wn/fresh.py (ADR-0025), the one source; tests/test_fresh.py fails when they differ.

// The new chat's first prompt. The session-start hook already puts the resume note (with the handoff) in context.
export const CONTINUE = 'Continue from the handoff note: read it first.'

// The desktop app: the agent starts the session with the app's own session tool, as no mod call can.
export function newSessionPrompt() {
  return (
    'Start a new session for this project with the start_session tool (initiation "user_asked", context "fresh"), ' +
    `titled "Continue from the handoff". Its first prompt, word for word: "${CONTINUE}" ` +
    'Then stop: do nothing else in this session.'
  )
}

// The terminal: no portable way to open a window, so the person runs this in a new one.
export function terminalCommand() {
  return `claude "${CONTINUE}"`
}

export function terminalNotice() {
  return `In a new terminal window, in this project's folder, run: ${terminalCommand()}`
}

// A handoff note counts as written in the wrap-up turn when it changed after the prompt (file times tick coarser
// than the clock: allow one second).
export function writtenSince(mtimeMs: number | undefined, askedAt: number) {
  return mtimeMs !== undefined && mtimeMs >= askedAt - 1000
}
