// After a wrap-up (P-67, ADR-0024): compact here, or paste the first prompt in a new session.
// The texts are a copy of wn/fresh.py (ADR-0025), the one source; tests/test_fresh.py fails when they differ.

// The new chat's first prompt. The session-start hook already puts the resume note (with the handoff) in context.
export const CONTINUE = 'Continue from the handoff note: read it first.'

// The band's texts (ADR-0026). Copy for new session copies at once and sends nothing to the model.
export const BAND_FIRST = 'Handoff saved. Keep going here, or start a new session from it.'
export const COPIED_TOAST = 'Copied. Open a new session in this project and paste it.'
export const COPY_FAILED = 'Copy did not work. Select the prompt above and copy it.'

export function promptLine() {
  return `New-session prompt: "${CONTINUE}"`
}

export function terminalLine() {
  return `In a new terminal window in this folder, run: ${terminalCommand()}`
}

// The terminal: no portable way to open a window, so the person runs this in a new one.
export function terminalCommand() {
  return `claude "${CONTINUE}"`
}

// A handoff note counts as written in the wrap-up turn when it changed after the prompt (file times tick coarser
// than the clock: allow one second).
export function writtenSince(mtimeMs: number | undefined, askedAt: number) {
  return mtimeMs !== undefined && mtimeMs >= askedAt - 1000
}
