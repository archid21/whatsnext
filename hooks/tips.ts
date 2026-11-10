// whatsnext tips (P-35): the tip list, and the state that survives sessions in `$.store`.
// No engine calls here except a `store` with `get` and `set`, so the tests can reach it.

export const GUIDE = 'https://github.com/archid21/whatsnext/blob/main/docs/GUIDE.md'

export type Tip = {
  id: string
  say?: string // the exact words to type (none for a tip whose button does the work)
  text: string // the one line the band shows
  link: string // where the guide explains it
  offerOnly?: boolean // shown only when something offers it (never by Next tip)
  action?: 'turn-on-idle' | 'star' // the band shows this tip's own two buttons, not Next tip and Stop tips
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
  {
    // Last in the Next tip walk, so a person who said No thanks can still find it (P-65, ADR-0021). Also offered once
    // after the first verified done. The band replaces this text with the repos still to star.
    id: 'star',
    text: 'Finding whatsnext useful? Star it on GitHub so other people can find it.',
    link: `${GUIDE}#tips`,
    action: 'star',
  },
  {
    id: 'idle',
    say: 'wrap up',
    text:
      'Claude auto-compact is on. It keeps what it thinks matters, not your goal. Turn on auto wrap-up: after 45 idle minutes whatsnext saves your goal and next step first ("wrap up").',
    link: `${GUIDE}#change-a-setting`,
    offerOnly: true,
    action: 'turn-on-idle',
  },
  {
    id: 'manual',
    say: 'wrap up',
    text:
      'Claude auto-compact is off, so nothing saves your goal for you. Before you /clear or /compact, say "wrap up".',
    link: `${GUIDE}#save-and-resume-a-session`,
    offerOnly: true,
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

// The first tip in list order that is not seen and not skipped, starting after `afterId` when given and wrapping no
// further. `skip` holds tips that do not apply now (the star tip once the repo is starred).
export function nextTip(seen: readonly string[], afterId?: string, skip: readonly string[] = []): Tip | undefined {
  const start = afterId === undefined ? 0 : TIPS.findIndex(t => t.id === afterId) + 1

  return TIPS.slice(start).find(t => !t.offerOnly && !seen.includes(t.id) && !skip.includes(t.id))
}
