import type { On } from 'claude-code'
import { expect, mock, test } from 'claude-code/testing'

// The drift note on the band (P-73, ADR-0028). The Python side writes the pending note to the session's drift.json;
// the band shows it with Add to <item> and Dismiss, and the wrap-up band wins while it shows.
const PROPS = { hasSurvey: false, isWorking: false, maxRows: 6, bodyColumns: 100, scroll: { offset: 0, bodyRows: 5 }, view: {} }
const TURN = { answer: 'ok', durationMs: 1, isAborted: false, turnId: 't', reason: 'end_turn' } as const
const NOW = 1_800_000_000_000
const SESSION = '11111111-2222-3333-4444-555555555555'
const NOTE =
  '2 files changed outside P-12 (tools/a.py, tools/b.py). Add them to P-12 (`progress stamp P-12 --files …`), or plan them as new work?'

type World = { pending?: unknown; written?: boolean; fail?: boolean }

// Beneath the plugin: the drift file, the handoff note's file time, and a record of every `whatsnext` command run.
function world(on: On, { pending, written = false, fail = false }: World = {}) {
  mock.store(on)
  mock.clock(on, { now: NOW })
  const ran: string[][] = []
  let state: unknown = pending === undefined ? null : pending
  on('session.id', () => ({ value: SESSION }))
  on('session.cwd', () => ({ value: '/project' }))
  on('turn.complete', () => ({ text: 'ok' }))
  on('prompt.submit', () => ({ text: 'ok' }))
  on('fs.list', () => {
    throw new Error('ENOENT')
  })
  on('fs.read', (_, e) => {
    if (!String(e.path).endsWith(`.whatsnext/sessions/${SESSION}.drift.json`)) throw new Error('ENOENT')

    return { value: JSON.stringify({ items: {}, pending: state }) }
  })
  on('fs.stat', () => ({ value: { kind: 'file', size: 10, mtimeMs: written ? NOW + 5_000 : NOW - 60_000, isLink: false } }))
  on('process.run', (_, e) => {
    ran.push([...e.argv].slice(2))
    const answered = e.argv.includes('stamp') || e.argv.includes('drift-dismiss')
    if (answered && !fail) state = null
    const stdout = e.argv.includes('status') ? JSON.stringify({ handoff: { path: 'docs/project/HANDOFF.md' } }) : ''

    return { value: { exitCode: answered && fail ? 1 : 0, stdout, stderr: '' } }
  })
  on('ui.render', ($, e) => {
    const { Text } = $.ui.resolve(e)

    return <Text dimColor>engine</Text>
  })

  return {
    ran,
    clear: () => {
      state = null
    },
  }
}

async function mount($: any) {
  return $.ui.mount({ plugin: 'whatsnext', component: 'AbovePrompt', surface: 'terminal', props: PROPS })
}

async function shows($: any, text: RegExp | string, type = 'Text') {
  const ui = await mount($)
  const found = (await ui.find({ type, text })) !== undefined
  await ui.unmount()

  return found
}

async function press($: any, key: string) {
  const ui = await mount($)
  await $.ui.press({ plugin: 'whatsnext', key, surface: 'terminal' })
  await ui.unmount()
}

const PENDING = { item: 'P-12', files: ['tools/a.py', 'tools/b.py'], text: NOTE }

test('a pending note shows on the band after the turn, with Add to P-12 and Dismiss', async ($, on) => {
  world(on, { pending: PENDING })
  expect(await shows($, /changed outside P-12/)).toBe(false) // nothing before a turn ends
  await $.turn.complete(TURN)
  expect(await shows($, /2 files changed outside P-12/)).toBe(true)
  expect(await shows($, 'Add to P-12', 'Button')).toBe(true)
  expect(await shows($, 'Dismiss', 'Button')).toBe(true)
})

test('no pending note shows nothing', async ($, on) => {
  world(on)
  await $.turn.complete(TURN)
  expect(await shows($, 'Dismiss', 'Button')).toBe(false)
})

test('Add to P-12 runs progress stamp with the files and clears the band', async ($, on) => {
  const { ran } = world(on, { pending: PENDING })
  await $.turn.complete(TURN)
  await press($, 'drift-add')
  expect(ran.filter(a => a[0] === 'progress')).toEqual([['progress', 'stamp', 'P-12', '--files', 'tools/a.py,tools/b.py']])
  expect(await shows($, 'Dismiss', 'Button')).toBe(false)
  expect(await shows($, /Added 2 file/)).toBe(true)
})

test('Dismiss runs the dismiss command for this session and clears the band', async ($, on) => {
  const { ran } = world(on, { pending: PENDING })
  await $.turn.complete(TURN)
  await press($, 'drift-dismiss')
  expect(ran.filter(a => a[0] === 'progress')).toEqual([['progress', 'drift-dismiss', '--session', SESSION]])
  expect(await shows($, 'Add to P-12', 'Button')).toBe(false)
})

test('a failed command keeps the note on the band', async ($, on) => {
  world(on, { pending: PENDING, fail: true })
  await $.turn.complete(TURN)
  await press($, 'drift-dismiss')
  expect(await shows($, 'Dismiss', 'Button')).toBe(true)
})

test('the band yields to a survey and a running turn', async ($, on) => {
  world(on, { pending: PENDING })
  await $.turn.complete(TURN)
  for (const props of [{ ...PROPS, hasSurvey: true }, { ...PROPS, isWorking: true }]) {
    const ui = await $.ui.mount({ plugin: 'whatsnext', component: 'AbovePrompt', surface: 'terminal', props })
    expect(await ui.find({ type: 'Button', text: 'Dismiss' })).toBeUndefined()
    await ui.unmount()
  }
})

test('the wrap-up band wins while it shows, and the note comes back after Not now', async ($, on) => {
  world(on, { pending: PENDING, written: true })
  await $.prompt.submit({ text: 'wrap up' })
  await $.turn.complete(TURN)
  expect(await shows($, 'Compact and continue here', 'Button')).toBe(true)
  expect(await shows($, 'Dismiss', 'Button')).toBe(false)
  await press($, 'not-now')
  expect(await shows($, 'Dismiss', 'Button')).toBe(true)
})

test('a note answered elsewhere (progress stamp --files) is gone after the next turn', async ($, on) => {
  const w = world(on, { pending: PENDING })
  await $.turn.complete(TURN)
  expect(await shows($, 'Dismiss', 'Button')).toBe(true)
  w.clear() // the person answers in the chat: the Python side clears the file, and the next turn end reads it
  await $.turn.complete(TURN)
  expect(await shows($, 'Dismiss', 'Button')).toBe(false)
})
