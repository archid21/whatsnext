// whatsnext idle wrap-up (P-40, ADR-0016): the numbers and the skip rules, with no engine calls so the tests can reach them.

export const IDLE_MS = 45 * 60 * 1000 // Claude Code's own idle compact came 54 minutes after the last request, twice
export const DEFAULT_MIN_TOKENS = 200_000
export const FLOOR_MIN_TOKENS = 100_000
export const WRAP_UP = 'wrap up'

// CLAUDE_CODE_IDLE_COMPACT_MIN_TOKENS: the context size below which Claude Code's idle compact does not run.
// Unset or not a positive whole number reads as the default; a number under the floor reads as the floor.
export function minTokens(raw: string | undefined): number {
  const value = raw !== undefined && /^\s*[1-9][0-9]*\s*$/.test(raw) ? Number(raw) : DEFAULT_MIN_TOKENS

  return Math.max(value, FLOOR_MIN_TOKENS)
}

export type IdleFacts = {
  idleCompaction: unknown // Claude Code's `idleCompaction` setting
  isAutoCompactEnabled: boolean | undefined // what the session reports (the context breakdown)
  tokens: number | undefined // input tokens of the last response
  minTokens: number
}

// Why `wrap up` is not submitted, or undefined when these facts allow it. Only an explicit `false` turns a setting off.
export function skipReason(facts: IdleFacts): string | undefined {
  if (facts.idleCompaction === false) return 'idleCompaction is false'
  if (facts.isAutoCompactEnabled === false) return 'auto-compact is off'
  if (facts.tokens === undefined || facts.tokens < facts.minTokens) return 'context is under the idle compact minimum'

  return undefined
}

// Which save tip fits (P-42). `manual`: Claude Code's auto-compact is off, so nothing saves a handoff unless the person
// says `wrap up`. `idle`: auto-compact is on and the context is big enough that the idle wrap-up would run, so offer to
// turn it on. Anything else: undefined, and the plain `save` tip applies.
export function saveTipKind(facts: IdleFacts): 'manual' | 'idle' | undefined {
  if (facts.isAutoCompactEnabled === false) return 'manual'

  return skipReason(facts) === undefined ? 'idle' : undefined
}
