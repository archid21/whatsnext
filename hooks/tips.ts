// whatsnext tips (P-35): the tip list, and the state that survives sessions in `$.store`.
// No engine calls here except a `store` with `get` and `set`, so the tests can reach it.

export const GUIDE = 'https://github.com/archid21/whatsnext/blob/main/docs/GUIDE.md'

export type Tip = {
  id: string
  say: string // the exact words to type
  text: string // the one line the band shows
  link: string // where the guide explains it
}

// Order matters: Next tip walks this list.
export const TIPS: readonly Tip[] = [
  {
    id: 'save',
    say: 'wrap up',
    text: 'To save this session, say "wrap up". Then run /clear, and say "what\'s next?" on the new screen.',
    link: `${GUIDE}#save-and-resume-a-session`,
  },
  {
    id: 'pick',
    say: "what's next?",
    text: 'To pick the next piece of work, say "what\'s next?".',
    link: `${GUIDE}#pick-and-start-work`,
  },
  {
    id: 'done',
    say: 'mark P-13 done',
    text: 'To close a plan item, say "mark P-13 done" (use your item\'s id). A passing command is the proof.',
    link: `${GUIDE}#mark-work-done`,
  },
]

export type TipsState = { tipsOff: boolean; seen: string[] }

export const STORE_KEY = 'tips'

type StoreHost = {
  store: {
    get: (key: string) => Promise<unknown>
    set: (key: string, value: unknown) => Promise<void>
  }
}

// What an older or damaged value reads as: tips on, nothing seen.
export function parseState(raw: unknown): TipsState {
  const value = (raw ?? {}) as { tipsOff?: unknown; seen?: unknown }
  const known = new Set(TIPS.map(t => t.id))
  const seen = Array.isArray(value.seen)
    ? value.seen.filter((id): id is string => typeof id === 'string' && known.has(id))
    : []

  return { tipsOff: value.tipsOff === true, seen: [...new Set(seen)] }
}

export async function loadState($: StoreHost): Promise<TipsState> {
  return parseState(await $.store.get(STORE_KEY))
}

export async function saveState($: StoreHost, state: TipsState): Promise<void> {
  await $.store.set(STORE_KEY, { tipsOff: state.tipsOff, seen: state.seen })
}

export async function markSeen($: StoreHost, id: string): Promise<TipsState> {
  const state = await loadState($)
  const next = state.seen.includes(id) ? state : { ...state, seen: [...state.seen, id] }
  await saveState($, next)

  return next
}

export async function stopTips($: StoreHost): Promise<TipsState> {
  const next = { ...(await loadState($)), tipsOff: true }
  await saveState($, next)

  return next
}

export async function restartTips($: StoreHost): Promise<TipsState> {
  const next: TipsState = { tipsOff: false, seen: [] }
  await saveState($, next)

  return next
}

// The first tip in list order that is not seen, starting after `afterId` when given and wrapping no further.
export function nextTip(seen: readonly string[], afterId?: string): Tip | undefined {
  const start = afterId === undefined ? 0 : TIPS.findIndex(t => t.id === afterId) + 1

  return TIPS.slice(start).find(t => !seen.includes(t.id))
}
