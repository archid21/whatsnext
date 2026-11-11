import type { On } from 'claude-code'
import { expect, mock, test } from 'claude-code/testing'

import { BAND_FIRST, CONTINUE, COPIED_TOAST, COPY_FAILED, promptLine, terminalCommand, terminalLine, writtenSince } from './newchat'

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
  const toasts: string[] = []
  on('ui.toast', (_, e) => {
    toasts.push(e.text)

    return { value: undefined }
  })
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

  return { submitted, commands, copies, toasts }
}

const ALL = ['Compact and continue here', 'Copy for new session', 'Not now']

async function buttons($: any, surface: 'terminal' | 'desktop' = 'terminal') {
  const ui = await $.ui.mount({ plugin: 'whatsnext', component: 'AbovePrompt', surface, props: PROPS })
  const found: string[] = []
  for (const label of ALL) {
    if (await ui.find({ type: 'Button', text: label })) found.push(label)
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
  expect(BAND_FIRST).toBe('Handoff saved. Keep going here, or start a new session from it.')
  expect(promptLine()).toBe(`New-session prompt: "${CONTINUE}"`)
  expect(terminalLine()).toBe(`In a new terminal window in this folder, run: claude "${CONTINUE}"`)
  expect(terminalCommand()).toBe(`claude "${CONTINUE}"`)
  expect(writtenSince(NOW - 500, NOW)).toBe(true) // file times tick coarser than the clock
  expect(writtenSince(NOW - 5_000, NOW)).toBe(false)
  expect(writtenSince(undefined, NOW)).toBe(false)
})

test('after a wrap-up that wrote the note, the band offers the buttons until the next prompt', async ($, on) => {
  world(on)
  expect(await buttons($)).toEqual([])
  await $.turn.complete(TURN) // an ordinary turn offers nothing
  expect(await buttons($)).toEqual([])
  await wrapUp($)
  expect(await buttons($)).toEqual(['Compact and continue here', 'Not now']) // the terminal has no copy button
  expect(await buttons($, 'desktop')).toEqual(ALL)
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
    const ui = await $.ui.mount({ plugin: 'whatsnext', component: 'AbovePrompt', surface: 'desktop', props })
    expect(await ui.find({ type: 'Button', text: 'Copy for new session' })).toBeUndefined()
    await ui.unmount()
  }
})

async function has($: any, surface: 'terminal' | 'desktop', text: string) {
  const ui = await $.ui.mount({ plugin: 'whatsnext', component: 'AbovePrompt', surface, props: PROPS })
  const found = (await ui.find({ type: 'Text', text })) !== undefined
  await ui.unmount()

  return found
}

test('the desktop band shows both lines at once', async ($, on) => {
  world(on)
  await wrapUp($)
  expect(await has($, 'desktop', BAND_FIRST)).toBe(true)
  expect(await has($, 'desktop', promptLine())).toBe(true)
})

test('Copy for new session copies at once, sends nothing, toasts and closes the band', async ($, on) => {
  const w = world(on)
  await wrapUp($)
  const count = w.submitted.length
  await press($, 'copy', 'desktop')
  expect(w.copies).toEqual([CONTINUE])
  expect(w.toasts).toEqual([COPIED_TOAST])
  expect(w.submitted.length).toBe(count)
  expect(w.commands).toEqual([])
  expect(await buttons($, 'desktop')).toEqual([])
})

test('a copy that did not work keeps the band and says so', async ($, on) => {
  const w = world(on, { copied: false })
  await wrapUp($)
  await press($, 'copy', 'desktop')
  expect(w.copies).toEqual([CONTINUE])
  expect(w.toasts).toEqual([])
  expect(await has($, 'desktop', COPY_FAILED)).toBe(true)
  expect(await has($, 'desktop', promptLine())).toBe(true)
  expect(await buttons($, 'desktop')).toEqual(ALL)
})

test('the terminal band shows the command to run in a new window', async ($, on) => {
  world(on)
  await wrapUp($)
  expect(await has($, 'terminal', BAND_FIRST)).toBe(true)
  expect(await has($, 'terminal', terminalLine())).toBe(true)
})

test('Compact and continue here runs /compact with whatsnext text and closes the band', async ($, on) => {
  const { commands } = world(on)
  await wrapUp($)
  await press($, 'compact-here')
  expect(commands).toEqual([{ command: 'compact', args: 'KEEP THE GOAL' }])
  expect(await buttons($)).toEqual([])
})

test('a wrap up from rightsize carries the end-at-Handoff-written context; the person\'s own does not', async ($, on) => {
  const { submitted } = world(on)
  await wrapUp($, { kind: 'plugin', name: 'rightsize' })
  const ctx = submitted[0].context?.join('\n') ?? ''
  expect(ctx).toContain('end it at the "Handoff written: docs/project/HANDOFF.md" line')
  expect(ctx).toContain('leave out the "Choose above the prompt" line')
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
  expect(await buttons($, 'desktop')).toEqual(ALL)
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
