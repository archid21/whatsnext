import type { On } from 'claude-code'
import { expect, mock, test } from 'claude-code/testing'

import { CONTINUE, PASTE_INTRO, TERMINAL_INTRO, terminalCommand, writtenSince } from './newchat'

// Start fresh after a wrap-up (P-67, ADR-0024).
const PROPS = { hasSurvey: false, isWorking: false, maxRows: 6, bodyColumns: 100, scroll: { offset: 0, bodyRows: 5 }, view: {} }
const TURN = { answer: 'ok', durationMs: 1, isAborted: false, turnId: 't', reason: 'end_turn' } as const
const NOW = 1_800_000_000_000

type World = { written?: boolean; copied?: boolean }

// Beneath the plugin: the whatsnext status (the note's path), the note's file time, and a record of every prompt
// submitted and command run.
function world(on: On, { written = true, copied = true }: World = {}) {
  mock.store(on)
  mock.clock(on, { now: NOW })
  const submitted: { text: string; asUser?: boolean; context?: readonly string[] }[] = []
  const commands: { command: string; args?: string }[] = []
  const copies: string[] = []
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
    const stdout = e.argv.includes('status')
      ? JSON.stringify({ handoff: { path: 'docs/project/HANDOFF.md' } })
      : e.argv.includes('compact-instructions')
        ? JSON.stringify({ instructions: 'KEEP THE GOAL' })
        : '{}'

    return { value: { exitCode: 0, stdout, stderr: '' } }
  })
  on('prompt.submit', (_, e) => {
    submitted.push({ text: e.text, asUser: (e.origin as { asUser?: boolean } | undefined)?.asUser, context: e.context })

    return { text: 'ok' }
  })
  on('command.run', (_, e) => {
    commands.push({ command: e.command, args: e.args })

    return { text: '' }
  })
  on('ui.copy', (_, e) => {
    copies.push(e.text)

    return { value: copied ? { isCopied: true } : { isCopied: false, reason: 'no clipboard' } }
  })
  on('ui.render', ($, e) => {
    const { Text } = $.ui.resolve(e)

    return <Text dimColor>engine</Text>
  })

  return { submitted, commands, copies }
}

async function buttons($: any, surface: 'terminal' | 'desktop' = 'terminal') {
  const ui = await $.ui.mount({ plugin: 'whatsnext', component: 'AbovePrompt', surface, props: PROPS })
  const found: string[] = []
  for (const label of ['Compact here', 'New session', 'Not now']) {
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

async function wrapUp($: any, origin?: { kind: 'plugin'; name: string }) {
  await $.prompt.submit(origin ? { text: 'wrap up', origin } : { text: 'wrap up' })
  await $.turn.complete(TURN)
}

test('the helpers: the first prompt, the paste lines, the terminal command and the file time', () => {
  expect(PASTE_INTRO).toBe('Paste this in a new session in this project to continue fresh:')
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
  expect(await buttons($)).toEqual(['Compact here', 'New session', 'Not now'])
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

async function has($: any, surface: 'terminal' | 'desktop', text: string) {
  const ui = await $.ui.mount({ plugin: 'whatsnext', component: 'AbovePrompt', surface, props: PROPS })
  const found = (await ui.find({ type: 'Text', text })) !== undefined
  await ui.unmount()

  return found
}

test('New session in the desktop app sends nothing and shows the paste text with a Copy button', async ($, on) => {
  const { submitted, commands } = world(on)
  await wrapUp($)
  const count = submitted.length
  await press($, 'new-session', 'desktop')
  expect(submitted.length).toBe(count)
  expect(commands).toEqual([])
  expect(await has($, 'desktop', PASTE_INTRO)).toBe(true)
  expect(await has($, 'desktop', CONTINUE)).toBe(true)
})

test('Copy puts the continue prompt on the clipboard; a failed copy leaves the text and says so', async ($, on) => {
  const ok = world(on)
  await wrapUp($)
  await press($, 'new-session', 'desktop')
  await press($, 'copy', 'desktop')
  expect(ok.copies).toEqual([CONTINUE])
  expect(await has($, 'desktop', 'Copy did not work. Select the text above and copy it yourself.')).toBe(false)
})

test('a copy that did not work says so and keeps the text shown', async ($, on) => {
  const w = world(on, { copied: false })
  await wrapUp($)
  await press($, 'new-session', 'desktop')
  await press($, 'copy', 'desktop')
  expect(w.copies).toEqual([CONTINUE])
  expect(await has($, 'desktop', 'Copy did not work. Select the text above and copy it yourself.')).toBe(true)
  expect(await has($, 'desktop', CONTINUE)).toBe(true)
})

test('New session in the terminal shows the command to run in a new window', async ($, on) => {
  const { submitted, commands } = world(on)
  await wrapUp($)
  const count = submitted.length
  await press($, 'new-session')
  expect(submitted.length).toBe(count) // nothing is sent
  expect(commands).toEqual([])
  expect(await has($, 'terminal', TERMINAL_INTRO)).toBe(true)
  expect(await has($, 'terminal', terminalCommand())).toBe(true)
})

test('Compact here runs /compact with whatsnext text and closes the band', async ($, on) => {
  const { commands } = world(on)
  await wrapUp($)
  await press($, 'compact-here')
  expect(commands).toEqual([{ command: 'compact', args: 'KEEP THE GOAL' }])
  expect(await buttons($)).toEqual([])
})

test('a wrap up from rightsize carries the closing-line context; the person\'s own does not', async ($, on) => {
  const { submitted } = world(on)
  await wrapUp($, { kind: 'plugin', name: 'rightsize' })
  const ctx = submitted[0].context?.join('\n') ?? ''
  expect(ctx).toContain('rightsize shows the next step above the prompt: paste its text into a new session to start fresh, or press Compact now to keep going here.')
  expect(ctx).not.toContain('Compact here above the prompt')
  await wrapUp($)
  expect(submitted[1].context).toBeUndefined()
})

test('after a wrap up that rightsize submitted, whatsnext shows no band', async ($, on) => {
  world(on)
  await wrapUp($, { kind: 'plugin', name: 'rightsize' })
  expect(await buttons($)).toEqual([])
})

test('after a wrap up from another plugin, the band shows', async ($, on) => {
  world(on)
  await wrapUp($, { kind: 'plugin', name: 'other' })
  expect(await buttons($)).toEqual(['Compact here', 'New session', 'Not now'])
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
