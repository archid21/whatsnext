import type { On } from 'claude-code'
import { expect, mock, test } from 'claude-code/testing'

import { askText, blockedByClaim, parseShared, readStarCheck, reposToAsk } from './star'

const BAND = {
  plugin: 'whatsnext',
  component: 'AbovePrompt',
  surface: 'terminal',
  props: { hasSurvey: false, isWorking: false, maxRows: 6, bodyColumns: 100, scroll: { offset: 0, bodyRows: 5 }, view: {} },
} as const

const TURN = { answer: 'ok', durationMs: 1, isAborted: false, turnId: 't', reason: 'end_turn' } as const
const NOW = Date.parse('2026-11-10T01:00:00Z')
const FILE = '/home/u/.config/archid21/stars.json'
const DONE = 'python3 whatsnext.py plan done P-13 --verify "true"'

type World = {
  shared?: object // the stars file, absent when undefined
  starred?: Record<string, 'starred' | 'not' | 'unknown'> // what `gh api user/starred/<repo>` answers
  canStar?: boolean // whether `gh api -X PUT` works
  canWrite?: boolean
  stored?: Record<string, unknown>
}

// Beneath the plugin: the store, HOME, a clock, the stars file in memory, gh and the browser opener, a Bash tool that
// marks an item done, no progress folder (so no "what's next" tip), and the engine's empty band.
function world(on: On, { shared, starred = {}, canStar = true, canWrite = true, stored }: World = {}) {
  mock.store(on, stored ?? { tips: { tipsOff: false, seen: ['done'] } })
  mock.env(on, { HOME: '/home/u' })
  mock.clock(on, { now: NOW })
  const files = new Map<string, string>(shared ? [[FILE, JSON.stringify(shared)]] : [])
  const ran: string[][] = []
  on('session.cwd', () => ({ value: '/project' }))
  on('session.id', () => ({ value: 's1' }))
  on('turn.complete', () => ({ text: 'ok' }))
  on('tool.call', () => ({ result: { stdout: 'Marked P-13 done. Verified: true passed in 1.0 s.', stderr: '' } }))
  on('fs.list', () => {
    throw new Error('ENOENT')
  })
  on('fs.read', (_, e) => {
    const text = files.get(String(e.path))
    if (text === undefined) throw new Error('ENOENT')

    return { value: text }
  })
  on('fs.write', (_, e) => {
    if (!canWrite) throw new Error('EACCES')
    files.set(String(e.path), e.text)

    return { value: undefined }
  })
  on('process.run', (_, e) => {
    const argv = [...e.argv]
    ran.push(argv)
    if (argv[0] === 'gh' && argv.includes('PUT')) return { value: { exitCode: canStar ? 0 : 1, stdout: '', stderr: canStar ? '' : 'HTTP 403' } }
    if (argv[0] === 'gh') {
      const repo = argv[argv.length - 1].replace('user/starred/', '')
      const answer = starred[repo] ?? 'not'
      if (answer === 'starred') return { value: { exitCode: 0, stdout: '', stderr: '' } }
      if (answer === 'not') return { value: { exitCode: 1, stdout: '', stderr: 'gh: Not Found (HTTP 404)' } }

      return { value: { exitCode: 4, stdout: '', stderr: 'To get started with GitHub CLI, please run:  gh auth login' } }
    }

    return { value: { exitCode: 0, stdout: '', stderr: '' } }
  })
  on('ui.render', ($, e) => {
    const { Text } = $.ui.resolve(e)

    return <Text dimColor>engine</Text>
  })

  return { ran, file: () => (files.has(FILE) ? JSON.parse(files.get(FILE)!) : undefined) }
}

async function look($: any) {
  const ui = await $.ui.mount(BAND)
  const text = async (re: RegExp) => (await ui.find({ type: 'Text', text: re })) !== undefined
  const seen = {
    ask: (await ui.find({ type: 'Button', label: 'Star on GitHub' })) !== undefined,
    both: await text(/whatsnext and rightsize/),
    thanks: await text(/Thanks for the star!/),
    failed: await text(/Could not star from here.*github\.com\/archid21\/whatsnext/),
  }
  await ui.unmount()

  return seen
}

async function press($: any, key: string) {
  const ui = await $.ui.mount(BAND)
  await $.ui.press({ plugin: 'whatsnext', key, surface: 'terminal' })
  await ui.unmount()
}

const puts = (ran: string[][]) => ran.filter(a => a[0] === 'gh' && a.includes('PUT')).map(a => a[a.length - 1])

test('the shared file: damaged reads as empty; claims, repos and the line', () => {
  expect(parseShared('not json')).toEqual({ installed: {}, starred: {} })
  expect(parseShared('{"starred":{"a/b":"yes","c/d":true},"claim":{"by":3}}')).toEqual({ installed: {}, starred: { 'c/d': true } })

  const day = 24 * 60 * 60 * 1000
  const claimed = (by: string, ago: number) => parseShared(JSON.stringify({ claim: { by, at: new Date(NOW - ago).toISOString() } }))
  expect(blockedByClaim(claimed('rightsize', 2 * day), NOW)).toBe(true)
  expect(blockedByClaim(claimed('rightsize', 8 * day), NOW)).toBe(false)
  expect(blockedByClaim(claimed('whatsnext', 0), NOW)).toBe(false)

  const both = parseShared(JSON.stringify({ installed: { whatsnext: 'x', rightsize: 'x', other: 'x' } }))
  expect(reposToAsk(both)).toEqual(['archid21/whatsnext', 'archid21/rightsize'])
  expect(reposToAsk({ ...both, starred: { 'archid21/rightsize': true } })).toEqual(['archid21/whatsnext'])
  expect(askText(['archid21/whatsnext'])).toBe('Finding whatsnext useful? Star it on GitHub so other people can find it.')
  expect(askText(['archid21/whatsnext', 'archid21/rightsize'])).toContain('whatsnext and rightsize useful? Star them')

  expect(readStarCheck({ exitCode: 0, stderr: '' })).toBe('starred')
  expect(readStarCheck({ exitCode: 1, stderr: 'HTTP 404' })).toBe('not')
  expect(readStarCheck({ exitCode: 4, stderr: 'gh auth login' })).toBe('unknown')
  expect(readStarCheck(undefined)).toBe('unknown')
})

test('session start says whatsnext is installed in the shared file', async ($, on) => {
  const w = world(on)
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('command.register', (_, e) => ({ value: { command: e.name } }))
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  expect(w.file().installed.whatsnext).toBe('2026-11-10T01:00:00.000Z')
})

test('the ask shows at the turn end after a verified done, never before; Star stars the repo and says thanks', async ($, on) => {
  const w = world(on)
  await $.turn.complete(TURN)
  expect((await look($)).ask).toBe(false)

  await $.tool.call({ tool: 'Bash', command: DONE })
  await $.turn.complete(TURN)
  const seen = await look($)
  expect(seen.ask).toBe(true)
  expect(seen.both).toBe(false)
  expect(w.file().claim.by).toBe('whatsnext')

  await press($, 'star')
  expect(puts(w.ran)).toEqual(['user/starred/archid21/whatsnext'])
  expect(await look($)).toEqual({ ask: false, both: false, thanks: true, failed: false })
  expect(w.file().starred).toEqual({ 'archid21/whatsnext': true })
  expect(w.file().answered).toBe('2026-11-10T01:00:00.000Z')
})

test('with rightsize installed, one ask names both and Star stars both', async ($, on) => {
  const w = world(on, { shared: { installed: { rightsize: '2026-11-01T00:00:00Z' } }, stored: { tips: { tipsOff: false, seen: ['done'] }, star: { earned: true } } })
  await $.turn.complete(TURN)
  expect((await look($)).both).toBe(true)
  await press($, 'star')
  expect(puts(w.ran)).toEqual(['user/starred/archid21/whatsnext', 'user/starred/archid21/rightsize'])
})

for (const [name, w] of [
  ['already starred', { starred: { 'archid21/whatsnext': 'starred' } }],
  ['GitHub cannot say', { starred: { 'archid21/whatsnext': 'unknown' } }],
  ['rightsize asked 2 days ago', { shared: { claim: { by: 'rightsize', at: '2026-11-08T00:00:00Z' } } }],
  ['the person answered before', { shared: { answered: '2026-11-01T00:00:00Z' } }],
  ['the file cannot be written', { canWrite: false }],
] as const) {
  test(`no ask: ${name}`, async ($, on) => {
    const got = world(on, { ...(w as World), stored: { tips: { tipsOff: false, seen: ['done'] }, star: { earned: true } } })
    await $.turn.complete(TURN)
    expect((await look($)).ask).toBe(false)
    if (name === 'already starred') expect(got.file().starred).toEqual({ 'archid21/whatsnext': true })
  })
}

test('a rightsize claim older than 7 days does not block the ask', async ($, on) => {
  world(on, { shared: { claim: { by: 'rightsize', at: '2026-11-01T00:00:00Z' } }, stored: { tips: { tipsOff: false, seen: ['done'] }, star: { earned: true } } })
  await $.turn.complete(TURN)
  expect((await look($)).ask).toBe(true)
})

test('Stop tips also stops the star ask', async ($, on) => {
  world(on, { stored: { tips: { tipsOff: true, seen: [] }, star: { earned: true } } })
  await $.turn.complete(TURN)
  expect((await look($)).ask).toBe(false)
})

test('No thanks saves the answer for both plugins and stars nothing', async ($, on) => {
  const w = world(on, { stored: { tips: { tipsOff: false, seen: ['done'] }, star: { earned: true } } })
  await $.turn.complete(TURN)
  await press($, 'no-thanks')
  expect(puts(w.ran)).toEqual([])
  expect((await look($)).ask).toBe(false)
  expect(w.file().answered).toBe('2026-11-10T01:00:00.000Z')
})

test('when Star fails, the page opens in the browser and the line gives the link', async ($, on) => {
  const w = world(on, { canStar: false, stored: { tips: { tipsOff: false, seen: ['done'] }, star: { earned: true } } })
  await $.turn.complete(TURN)
  await press($, 'star')
  expect(w.ran.some(a => a[0] === 'open' && a[1] === 'https://github.com/archid21/whatsnext')).toBe(true)
  expect((await look($)).failed).toBe(true)
  expect(w.file().starred).toEqual({})
})

test('Next tip walks from mark done to the star tip, and skips it once the repo is starred', async ($, on) => {
  world(on, { stored: { tips: { tipsOff: false, seen: [] } } })
  await $.tool.call({ tool: 'Bash', command: DONE }) // shows the mark done tip
  await press($, 'next')
  expect((await look($)).ask).toBe(true)
})

test('Next tip from mark done shows nothing when the shared file says starred', async ($, on) => {
  world(on, { shared: { starred: { 'archid21/whatsnext': true } }, stored: { tips: { tipsOff: false, seen: [] } } })
  await $.tool.call({ tool: 'Bash', command: DONE })
  await press($, 'next')
  expect((await look($)).ask).toBe(false)
})

test('Next tip asks GitHub first: a repo already starred is not named', async ($, on) => {
  const w = world(on, {
    shared: { installed: { rightsize: '2026-11-01T00:00:00Z' } },
    starred: { 'archid21/rightsize': 'starred' },
    stored: { tips: { tipsOff: false, seen: [] } },
  })
  await $.tool.call({ tool: 'Bash', command: DONE })
  await press($, 'next')
  const seen = await look($)
  expect(seen.ask).toBe(true)
  expect(seen.both).toBe(false)
  expect(w.file().starred).toEqual({ 'archid21/rightsize': true })
  await press($, 'star')
  expect(puts(w.ran)).toEqual(['user/starred/archid21/whatsnext'])
})

test('Next tip skips the star tip when GitHub says this repo is starred', async ($, on) => {
  const w = world(on, { starred: { 'archid21/whatsnext': 'starred' }, stored: { tips: { tipsOff: false, seen: [] } } })
  await $.tool.call({ tool: 'Bash', command: DONE })
  await press($, 'next')
  expect((await look($)).ask).toBe(false)
  expect(w.file().starred).toEqual({ 'archid21/whatsnext': true })
})
