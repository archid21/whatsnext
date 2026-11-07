import type { On } from 'claude-code'
import { expect, mock, test } from 'claude-code/testing'

import { saveTipKind } from './idle'

const BAND = {
  plugin: 'whatsnext',
  component: 'AbovePrompt',
  surface: 'terminal',
  props: { hasSurvey: false, isWorking: false, maxRows: 6, bodyColumns: 100, scroll: { offset: 0, bodyRows: 5 }, view: {} },
} as const

const COMPACT = { command: 'compact', args: '' } as const
const TURN = { answer: 'ok', durationMs: 1, isAborted: false, turnId: 't', reason: 'end_turn' } as const

type World = { tokens?: number; autoCompact?: boolean; offer?: boolean; stored?: Record<string, unknown>; setExit?: number }

// What sits beneath the plugin: the engine's band, Claude Code's settings and context size, and the whatsnext commands
// (`idle-offer` answers `offer`; `config set` is recorded and answers `setExit`).
function world(on: On, { tokens = 250_000, autoCompact = true, offer = true, stored, setExit = 0 }: World = {}) {
  mock.store(on, stored)
  mock.env(on, {})
  const ran: string[][] = []
  on('command.run', () => ({ text: 'Compacted.' }))
  on('turn.complete', () => ({ text: 'ok' }))
  on('session.usage', () => ({
    value: { startedAt: 0, context: { tokens, window: 1_000_000, percent: 25, breakdown: { isAutoCompactEnabled: autoCompact } } },
  }))
  on('settings.read', () => ({ value: { idleCompaction: undefined, autoCompactEnabled: autoCompact } }))
  on('session.id', () => ({ value: '11111111-2222-3333-4444-555555555555' }))
  on('session.cwd', () => ({ value: '/project' }))
  on('fs.list', () => {
    throw new Error('ENOENT')
  })
  on('process.run', (_, e) => {
    ran.push([...e.argv])
    const isOffer = e.argv.includes('idle-offer')

    return { value: { exitCode: isOffer ? 0 : setExit, stdout: isOffer ? JSON.stringify({ offer }) : '', stderr: '' } }
  })
  on('ui.render', ($, e) => {
    const { Text } = $.ui.resolve(e)

    return <Text dimColor>engine</Text>
  })

  return { ran }
}

async function look($: any) {
  const ui = await $.ui.mount(BAND)
  const has = async (spec: object) => (await ui.find(spec)) !== undefined
  const seen = {
    optIn: await has({ type: 'Text', text: /Claude auto-compact is on/ }),
    manual: await has({ type: 'Text', text: /Claude auto-compact is off/ }),
    save: await has({ type: 'Text', text: /save this session/ }),
    turnOn: await has({ type: 'Button', key: 'turn-on' }),
    noThanks: await has({ type: 'Button', key: 'no-thanks' }),
    nextTip: await has({ type: 'Button', key: 'next' }),
    notice: await has({ type: 'Text', text: /Auto wrap-up is on/ }),
    failed: await has({ type: 'Text', text: /Could not turn on/ }),
  }
  await ui.unmount()

  return seen
}

// A person pressing a button: the band is drawn first, because only a drawn button can be pressed.
async function press($: any, key: string) {
  const ui = await $.ui.mount(BAND)
  await $.ui.press({ plugin: 'whatsnext', key, surface: 'terminal' })
  await ui.unmount()
}

test('saveTipKind: manual when auto-compact is off, idle when the idle wrap-up would run, else none', () => {
  const facts = { idleCompaction: undefined, autoCompactEnabledSetting: undefined, isAutoCompactEnabled: true, tokens: 250_000, minTokens: 200_000 }
  expect(saveTipKind(facts)).toBe('idle')
  expect(saveTipKind({ ...facts, isAutoCompactEnabled: false })).toBe('manual')
  expect(saveTipKind({ ...facts, autoCompactEnabledSetting: false })).toBe('manual')
  expect(saveTipKind({ ...facts, tokens: 150_000 })).toBeUndefined()
  expect(saveTipKind({ ...facts, idleCompaction: false })).toBeUndefined()
})

test('auto-compact on, auto wrap-up off: the tip offers Turn on and No thanks, and says why a handoff helps', async ($, on) => {
  world(on)
  await $.command.run(COMPACT)
  const seen = await look($)
  expect(seen).toMatchObject({ optIn: true, turnOn: true, noThanks: true, nextTip: false, save: false })
})

test('Turn on sets wrapup.autoIdle for the user, says so, and the tip never comes back', async ($, on) => {
  const w = world(on)
  await $.command.run(COMPACT)
  await press($, 'turn-on')
  expect(w.ran.some(a => a.join(' ').endsWith('config set --user wrapup.autoIdle true'))).toBe(true)
  expect(await look($)).toMatchObject({ optIn: false, notice: true })
  await $.command.run(COMPACT)
  expect(await look($)).toMatchObject({ optIn: false })
})

test('Turn on that fails says so and gives the command', async ($, on) => {
  world(on, { setExit: 1 })
  await $.command.run(COMPACT)
  await press($, 'turn-on')
  expect(await look($)).toMatchObject({ notice: false, failed: true })
})

test('No thanks hides it for good, in this session and the next', async ($, on) => {
  world(on)
  await $.command.run(COMPACT)
  await press($, 'no-thanks')
  expect(await look($)).toMatchObject({ optIn: false, turnOn: false })
  await $.command.run(COMPACT)
  expect(await look($)).toMatchObject({ optIn: false })
})

test('it is not offered when auto wrap-up is already on', async ($, on) => {
  world(on, { offer: false })
  await $.command.run(COMPACT)
  expect(await look($)).toMatchObject({ optIn: false, turnOn: false, save: true })
})

test('auto-compact off: the manual tip says to wrap up before /clear or /compact, with no setting to turn on', async ($, on) => {
  world(on, { autoCompact: false })
  await $.command.run(COMPACT)
  expect(await look($)).toMatchObject({ manual: true, turnOn: false, optIn: false, nextTip: true })
})

test('a small context gets the plain save tip, not the opt-in', async ($, on) => {
  world(on, { tokens: 120_000 })
  await $.command.run(COMPACT)
  expect(await look($)).toMatchObject({ optIn: false, save: true })
})

test('it is offered after a long session as well as after a compact', async ($, on) => {
  world(on)
  for (let i = 0; i < 20; i++) await $.turn.complete(TURN)
  expect(await look($)).toMatchObject({ optIn: true })
})

test('Stop tips still stops it', async ($, on) => {
  world(on, { stored: { tips: { tipsOff: true, seen: [] } } })
  await $.command.run(COMPACT)
  expect(await look($)).toMatchObject({ optIn: false, manual: false, save: false })
})
