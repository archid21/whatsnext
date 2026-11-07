import type { On } from 'claude-code'
import { expect, mock, test } from 'claude-code/testing'

import { DEFAULT_MIN_TOKENS, FLOOR_MIN_TOKENS, IDLE_MS, minTokens, skipReason } from './idle'

const TURN = { answer: 'ok', durationMs: 1, isAborted: false, turnId: 't', reason: 'end_turn' } as const
const MINUTE = 60 * 1000

type World = {
  tokens?: number
  idleCompaction?: unknown
  autoCompact?: boolean
  env?: Record<string, string>
  fire?: boolean // what the whatsnext check answers
}

// What sits beneath the plugin: Claude Code's settings and context size, the whatsnext check, and a record of every
// `process.run` and `prompt.submit`. The test's own `prompt.submit` hook sees what the plugin submits.
function world(on: On, { tokens = 250_000, idleCompaction, autoCompact = true, env = {}, fire = true }: World = {}) {
  const clock = mock.clock(on)
  mock.store(on)
  mock.env(on, env)
  const ran: string[][] = []
  const submitted: string[] = []
  on('session.usage', () => ({
    value: {
      startedAt: 0,
      context: { tokens, window: 1_000_000, percent: 25, breakdown: { isAutoCompactEnabled: autoCompact } },
    },
  }))
  on('turn.complete', () => ({ text: 'ok' }))
  on('settings.read', () => ({ value: { idleCompaction, autoCompactEnabled: autoCompact } }))
  on('session.id', () => ({ value: '11111111-2222-3333-4444-555555555555' }))
  on('session.cwd', () => ({ value: '/project' }))
  on('process.run', (_, e) => {
    ran.push([...e.argv])

    return { value: { exitCode: 0, stdout: JSON.stringify({ fire }), stderr: '' } }
  })
  on('prompt.submit', (_, e) => {
    submitted.push(e.text)

    return { text: 'ok' }
  })

  return { clock, ran, submitted }
}

test('the numbers: 45 minutes, a 200,000 default and a 100,000 floor', () => {
  expect(IDLE_MS).toBe(45 * MINUTE)
  expect(minTokens(undefined)).toBe(DEFAULT_MIN_TOKENS)
  expect(minTokens('300000')).toBe(300_000)
  expect(minTokens('50000')).toBe(FLOOR_MIN_TOKENS)
  expect(minTokens('nope')).toBe(DEFAULT_MIN_TOKENS)
  expect(minTokens('-5')).toBe(DEFAULT_MIN_TOKENS)
})

test('only an explicit false turns Claude Code settings off; a small context skips', () => {
  const facts = { idleCompaction: undefined, autoCompactEnabledSetting: undefined, isAutoCompactEnabled: true, tokens: 200_000, minTokens: 200_000 }
  expect(skipReason(facts)).toBeUndefined()
  expect(skipReason({ ...facts, idleCompaction: true })).toBeUndefined()
  expect(skipReason({ ...facts, idleCompaction: false })).toContain('idleCompaction')
  expect(skipReason({ ...facts, isAutoCompactEnabled: false })).toContain('autoCompactEnabled')
  expect(skipReason({ ...facts, autoCompactEnabledSetting: false })).toContain('autoCompactEnabled')
  expect(skipReason({ ...facts, isAutoCompactEnabled: undefined })).toBeUndefined()
  expect(skipReason({ ...facts, tokens: 199_999 })).toContain('minimum')
  expect(skipReason({ ...facts, tokens: undefined })).toContain('minimum')
})

test('submits wrap up once, 45 minutes after the last turn, after asking the whatsnext check', async ($, on) => {
  const w = world(on)
  await $.turn.complete(TURN)
  await w.clock.advance(45 * MINUTE - 1000)
  expect(w.submitted).toEqual([])
  await w.clock.advance(1001)
  expect(w.submitted).toEqual(['wrap up'])
  expect(w.ran).toHaveLength(1)
  expect(w.ran[0]?.slice(-4)).toEqual(['hook', 'idle-check', '--agent', 'claude-code'])
})

test('a prompt during the wait restarts it, and a turn end starts it again', async ($, on) => {
  const w = world(on)
  await $.turn.complete(TURN)
  await w.clock.advance(40 * MINUTE)
  await $.prompt.submit({ text: 'still here', asUser: true })
  await w.clock.advance(60 * MINUTE) // no turn has ended since the prompt: no timer runs
  expect(w.submitted).toEqual(['still here'])
  await $.turn.complete(TURN)
  await w.clock.advance(44 * MINUTE)
  expect(w.submitted).toEqual(['still here'])
  await w.clock.advance(MINUTE + 1)
  expect(w.submitted).toEqual(['still here', 'wrap up'])
})

test('never a second time until the person sends a prompt', async ($, on) => {
  const w = world(on)
  await $.turn.complete(TURN)
  await w.clock.advance(IDLE_MS + 1)
  expect(w.submitted).toEqual(['wrap up'])
  await $.turn.complete(TURN) // the wrap-up turn ends: no new timer
  await w.clock.advance(300 * MINUTE)
  expect(w.submitted).toEqual(['wrap up'])
  await $.prompt.submit({ text: 'back', asUser: true })
  await $.turn.complete(TURN)
  await w.clock.advance(IDLE_MS + 1)
  expect(w.submitted.filter(t => t === 'wrap up')).toHaveLength(2)
})

test('a subagent turn does not start the wait', async ($, on) => {
  const w = world(on)
  await $.turn.complete({ ...TURN, agentId: 'sub' } as never)
  await w.clock.advance(100 * MINUTE)
  expect(w.submitted).toEqual([])
})

const SKIPS = [
  ['a small context', { tokens: 150_000 }],
  ['an env minimum above the context', { tokens: 250_000, env: { CLAUDE_CODE_IDLE_COMPACT_MIN_TOKENS: '300000' } }],
  ['idleCompaction false', { idleCompaction: false }],
  ['autoCompact off', { autoCompact: false }],
  ['the whatsnext check saying no', { fire: false }],
] as const

for (const [name, opts] of SKIPS) {
  test(`skips ${name}`, async ($, on) => {
    const w = world(on, opts)
    await $.turn.complete(TURN)
    await w.clock.advance(60 * MINUTE)
    expect(w.submitted).toEqual([])
  })
}

test('the env minimum is never under the floor: 100,000 tokens fires with the variable at 1', async ($, on) => {
  const w = world(on, { tokens: 100_000, env: { CLAUDE_CODE_IDLE_COMPACT_MIN_TOKENS: '1' } })
  await $.turn.complete(TURN)
  await w.clock.advance(IDLE_MS + 1)
  expect(w.submitted).toEqual(['wrap up'])
})
