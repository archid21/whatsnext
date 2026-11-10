import { expect, test } from 'claude-code/testing'

import { GUIDE, TIPS, loadState, markSeen, nextTip, restartTips, stopTips } from './tips'

test('three phrase tips and the star tip in order, then two that are only offered; each has its phrase and a guide link', () => {
  expect(TIPS.filter(t => !t.offerOnly).map(t => t.say)).toEqual(['wrap up', "what's next?", 'mark P-13 done', undefined])
  expect(TIPS.map(t => t.id)).toEqual(['save', 'pick', 'done', 'star', 'idle', 'manual'])
  expect(TIPS.filter(t => t.offerOnly).map(t => t.id)).toEqual(['idle', 'manual'])
  expect(TIPS.find(t => t.id === 'star')?.action).toBe('star')

  for (const tip of TIPS) {
    if (tip.say !== undefined) expect(tip.text).toContain(tip.say)
    expect(tip.link.startsWith(GUIDE)).toBe(true)
    expect(tip.link).toContain('docs/GUIDE.md')
  }
})

// The test's `$` has no `store` noun to call (a plugin's `$.store` is answered beneath it), so the helpers take
// any host with `store.get` and `set`. This one is a map; the plugin's own use of `$.store` is tested in P-36.
function fakeHost(entries: Record<string, unknown> = {}) {
  const data = new Map<string, unknown>(Object.entries(entries))

  return {
    data,
    store: {
      get: async (key: string) => (data.has(key) ? JSON.parse(JSON.stringify(data.get(key))) : undefined),
      set: async (key: string, value: unknown) => void data.set(key, JSON.parse(JSON.stringify(value))),
    },
  }
}

test('the seen list and tipsOff are kept in the store under one key and survive a new session', async () => {
  const host = fakeHost()

  expect(await loadState(host)).toEqual({ tipsOff: false, seen: [] })
  await markSeen(host, 'save')
  await markSeen(host, 'save')
  await markSeen(host, 'pick')
  await stopTips(host)

  // A second session reads the same store.
  const second = fakeHost(Object.fromEntries(host.data))
  expect(await loadState(second)).toEqual({ tipsOff: true, seen: ['save', 'pick'] })
  expect([...host.data.keys()]).toEqual(['tips'])

  await restartTips(host)
  expect(await loadState(host)).toEqual({ tipsOff: false, seen: [] })
})

test('a store written by something else reads as tips on, nothing seen', async () => {
  const host = fakeHost({ tips: { tipsOff: 'yes', seen: ['gone', 3, 'done'] } })

  expect(await loadState(host)).toEqual({ tipsOff: false, seen: ['done'] })
})

test('nextTip walks the list and skips seen tips', () => {
  expect(nextTip([])?.id).toBe('save')
  expect(nextTip(['save'])?.id).toBe('pick')
  expect(nextTip(['save'], 'pick')?.id).toBe('done')
  expect(nextTip([], 'done')?.id).toBe('star')
  expect(nextTip(['save', 'pick', 'done'])?.id).toBe('star')
  expect(nextTip(['save', 'pick', 'done', 'star'])).toBeUndefined()
  // A starred repo skips the star tip.
  expect(nextTip([], 'done', ['star'])).toBeUndefined()
})
