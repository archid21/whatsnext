// After a wrap-up (P-67, ADR-0024): compact here, or paste the first prompt in a new session.
// The texts are a copy of wn/fresh.py (ADR-0025), the one source; tests/test_fresh.py fails when they differ.

// The new chat's first prompt. The session-start hook already puts the resume note (with the handoff) in context.
export const CONTINUE = 'Continue from the handoff note: read it first.'

// The band's lines above the first prompt (ADR-0026). New session sends nothing to the model.
export const PASTE_INTRO = 'Paste this in a new session in this project to continue fresh:'
export const TERMINAL_INTRO = "In a new terminal window, in this project's folder, run:"

// The terminal: no portable way to open a window, so the person runs this in a new one.
export function terminalCommand() {
  return `claude "${CONTINUE}"`
}

// A handoff note counts as written in the wrap-up turn when it changed after the prompt (file times tick coarser
// than the clock: allow one second).
export function writtenSince(mtimeMs: number | undefined, askedAt: number) {
  return mtimeMs !== undefined && mtimeMs >= askedAt - 1000
}
