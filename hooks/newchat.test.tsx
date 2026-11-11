import type { On } from 'claude-code'
import { expect, mock, test } from 'claude-code/testing'

import { CONTINUE, newSessionPrompt, terminalCommand, writtenSince } from './newchat'

// Start fresh after a wrap-up (P-67, ADR-0024).
const PROPS = { hasSurvey: false, isWorking: false, maxRows: 6, bodyColumns: 100, scroll: { offset: 0, bodyRows: 5 }, view: {} }
const TURN = { answer: 'ok', durationMs: 1, isAborted: false, turnId: 't', reason: 'end_turn' } as const
const NOW = 1_800_000_000_000

type World = { written?: boolean }

// Beneath the plugin: the whatsnext status (the note's path), the note's file time, and a record of every prompt
// submitted and command run.
function world(on: On, { written = true }: World = {}) {
  mock.store(on)
  mock.clock(on, { now: NOW })
  const submitted: { text: string; asUser?: boolean }[] = []
  const commands: string[] = []
  on('session.id', () => ({ value: '11111111-2222-3333-4444-555555555555' }))
  on('session.cwd', () => ({ value: '/project' }))
  on('turn.complete', () => ({ text: 'ok' }))
  on('fs.list', () => {
    throw new Error('ENOENT')
  })
  on('fs.stat', (_, e) => {
    if (e.path !== '/project/docs/project/HANDOFF.md') throw new Error('ENOENT')

    return { value: { kind: 'file', size: 10, mtimeMs: written ? NOW + 5_000 : NOW - 60_000, isLink: false } }
  })
  on('process.run', (_, e) => {
    const stdout = e.argv.includes('status') ? JSON.stringify({ handoff: { path: 'docs/project/HANDOFF.md' } }) : '{}'

    return { value: { exitCode: 0, stdout, stderr: '' } }
  })
  on('prompt.submit', (_, e) => {
    submitted.push({ text: e.text, asUser: (e.origin as { asUser?: boolean } | undefined)?.asUser })

    return { text: 'ok' }
  })
  on('command.run', (_, e) => {
    commands.push(e.command)

    return { text: '' }
  })
  on('ui.render', ($, e) => {
    const { Text } = $.ui.resolve(e)

    return <Text dimColor>engine</Text>
  })

  return { submitted, commands }
}

async function buttons($: any, surface: 'terminal' | 'desktop' = 'terminal') {
  const ui = await $.ui.mount({ plugin: 'whatsnext', component: 'AbovePrompt', surface, props: PROPS })
  const found: string[] = []
  for (const label of ['New session', 'Clear and continue', 'Not now']) {
    if (await ui.find({ type: 'Button', label })) found.push(label)
  }
  await ui.unmount()

  return found
}

// A press needs the band drawn: mount it, press, unmount.
async function press($: any, key: string, surface: 'terminal' | 'desktop' = 'terminal') {
  const ui = await $.ui.mount({ plugin: 'whatsnext', component: 'AbovePrompt', surface, props: PROPS })
  await $.ui.press({ plugin: 'whatsnext', key, surface })
  await ui.unmount()
}

async function wrapUp($: any) {
  await $.prompt.submit({ text: 'wrap up' })
  await $.turn.complete(TURN)
}

test('the helpers: the first prompt, the desktop prompt, the terminal command and the file time', () => {
  expect(newSessionPrompt()).toContain('start_session')
  expect(newSessionPrompt()).toContain(CONTINUE)
  expect(terminalCommand()).toBe(`claude "${CONTINUE}"`)
  expect(writtenSince(NOW - 500, NOW)).toBe(true) // file times tick coarser than the clock
  expect(writtenSince(NOW - 5_000, NOW)).toBe(false)
  expect(writtenSince(undefined, NOW)).toBe(false)
})

test('after a wrap-up that wrote the note, the band offers the three buttons until the next prompt', async ($, on) => {
  world(on)
  expect(await buttons($)).toEqual([])
  await $.turn.complete(TURN) // an ordinary turn offers nothing
  expect(await buttons($)).toEqual([])
  await wrapUp($)
  expect(await buttons($)).toEqual(['New session', 'Clear and continue', 'Not now'])
  await $.prompt.submit({ text: 'something else' })
  expect(await buttons($)).toEqual([])
})

test('a wrap-up that did not write the note offers nothing', async ($, on) => {
  world(on, { written: false })
  await wrapUp($)
  expect(await buttons($)).toEqual([])
})

test('the band yields to a survey and a running turn', async ($, on) => {
  world(on)
  await wrapUp($)
  for (const props of [{ ...PROPS, hasSurvey: true }, { ...PROPS, isWorking: true }]) {
    const ui = await $.ui.mount({ plugin: 'whatsnext', component: 'AbovePrompt', surface: 'terminal', props })
    expect(await ui.find({ type: 'Button', label: 'New session' })).toBeUndefined()
    await ui.unmount()
  }
})

test('New session in the desktop app asks the agent, as the person, and keeps this chat', async ($, on) => {
  const { submitted, commands } = world(on)
  await wrapUp($)
  await press($, 'new-session', 'desktop')
  expect(submitted.at(-1)).toEqual({ text: newSessionPrompt(), asUser: true })
  expect(commands).not.toContain('clear')
  expect(await buttons($, 'desktop')).toEqual([])
})

test('New session in the terminal shows the command to run in a new window', async ($, on) => {
  const { submitted, commands } = world(on)
  await wrapUp($)
  const count = submitted.length
  await press($, 'new-session')
  expect(submitted.length).toBe(count) // nothing is sent
  expect(commands).not.toContain('clear')
  const ui = await $.ui.mount({ plugin: 'whatsnext', component: 'AbovePrompt', surface: 'terminal', props: PROPS })
  expect(await ui.find({ type: 'Text', text: terminalCommand() })).toBeDefined()
  await ui.unmount()
})

test('Clear and continue runs /clear, then sends the first prompt as the person', async ($, on) => {
  const { submitted, commands } = world(on)
  await wrapUp($)
  await press($, 'clear-continue')
  expect(commands).toContain('clear')
  expect(submitted.at(-1)).toEqual({ text: CONTINUE, asUser: true })
})

test('Not now hides the band and sends nothing', async ($, on) => {
  const { submitted, commands } = world(on)
  await wrapUp($)
  const count = submitted.length
  await press($, 'not-now')
  expect(await buttons($)).toEqual([])
  expect(submitted.length).toBe(count)
  expect(commands).toEqual([])
})
