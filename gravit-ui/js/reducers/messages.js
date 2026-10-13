// gravit-ui/js/reducers/messages.js — the conversation side: routes, drafts, sending, answering, details, banners, calls
import { nextId } from '../ids.js';
import { DAY, fmtDuration } from '../time.js';
import { byId } from '../data/plugins.js';
import { instrument } from '../data/markets.js';
import { isClosed } from '../messages.js';

const closed = isClosed;

// one drawer at a time: an opener first closes whatever else was open, with any editor or confirm in it
export const closeOverlays = s => ({
  ...s, detailsOpen: false, settingsOpen: false, edit: null, confirm: null,
  account: { ...s.account, panel: null, panelError: null },
  discover: { ...s.discover, create: null },
});
const installedBots = s => s.plugins.installed.filter(id => byId(id, s.plugins.uploaded)?.kind === 'Bots');
const upd = (state, id, fn) => ({ ...state, conversations: state.conversations.map(c => (c.id === id ? fn(c) : c)) });
const push = (state, convId, msg) => upd(state, convId, c => ({ ...c, messages: [...c.messages, msg] }));

export function stampMessage(state, msg, at) {
  const { id, counters } = nextId(state.counters, 'msg');
  return { state: { ...state, counters }, msg: { ...msg, id, at } };
}

// the driver writes {ord} / {ledger} / {card}; each gets the next id from the counters, once per message
function fillIds(counters, msg) {
  const got = {};
  let c = counters;
  const fill = v => (typeof v === 'string' ? v.replace(/\{(ord|ledger|card)\}/g, (_, k) => {
    if (!got[k]) { const r = nextId(c, k); c = r.counters; got[k] = r.id; }
    return got[k];
  }) : v);
  const text = fill(msg.text);
  const data = Object.fromEntries(Object.entries(msg.data ?? {}).map(([k, v]) => [k, fill(v)]));
  return { counters: c, msg: { ...msg, text, data } };
}

// where a banner's message lands: the conversation on screen, else the first
const targetConv = s => (s.route.screen === 'messages' && s.conversations.some(c => c.id === s.route.id) ? s.route.id : s.conversations[0]?.id ?? null);

function newConversation(state, { title, kind, members, intentLimit, until, plugins, now }) {
  const c1 = nextId(state.counters, 'conv');
  const c2 = nextId(c1.counters, 'intent');
  const conv = {
    id: c1.id, title, kind, members, unread: false, status: 'working',
    intent: { id: c2.id, created: now, until, limit: intentLimit }, plugins, messages: [],
  };
  return { state: { ...state, counters: c2.counters, conversations: [conv, ...state.conversations] }, conv };
}

export const reducers = {
  nav(state, route) {
    // a missing id, or new without a draft, opens the first conversation (Review Focus 3)
    if (route.screen === 'messages' && !(route.id === 'new' && state.draft) && !state.conversations.some(c => c.id === route.id)) {
      route = { screen: 'messages', id: state.conversations[0]?.id ?? null };
    }
    // a plugin that is not in the shop opens Discover
    if (route.screen === 'plugin' && !byId(route.id, state.plugins.uploaded)) route = { screen: 'discover', id: null };
    // a market id is matched without case; one that is not a market opens Markets
    if (route.screen === 'markets' && route.id) route = { screen: 'markets', id: instrument(route.id)?.id ?? null };
    // a letter that is not in the mailbox opens the inbox
    if (route.screen === 'mail' && route.id && !state.mail.items.some(m => m.id === route.id)) route = { screen: 'mail', id: null };
    let s = { ...state, route, detailsOpen: false, settingsOpen: false, edit: null, confirm: null };
    // opening a letter reads it, the way opening a conversation clears its dot
    if (route.screen === 'mail' && route.id) s.mail = { ...s.mail, items: s.mail.items.map(m => (m.id === route.id && !m.read ? { ...m, read: true } : m)) };
    // the first level's Messages key returns to the conversation you last had open
    if (route.screen === 'messages' && route.id && route.id !== 'new') s.lastConv = route.id;
    // an Account panel belongs to Account
    if (route.screen !== 'account' && s.account.panel) s.account = { ...s.account, panel: null, panelError: null };
    // a plugin page goes back to the Discover view it was opened from
    if (route.screen === 'discover') s.lastDiscover = route;
    // Discover's dialog and toast belong to Discover and its plugin pages; they do not follow you out of them
    if (route.screen !== 'discover' && route.screen !== 'plugin' && (s.discover.create || s.discover.toast)) {
      s = { ...s, discover: { ...s.discover, create: null, toast: null } };
    }
    if (route.screen === 'messages' && route.id && route.id !== 'new') s = upd(s, route.id, c => (c.unread ? { ...c, unread: false } : c));
    if (!(route.screen === 'messages' && route.id === 'new')) s.draft = null;
    return s;
  },
  toggleRail: s => ({ ...s, railCollapsed: !s.railCollapsed }),
  setTheme: (s, theme) => ({ ...s, theme }),

  startDraft(s, { now }) {
    return { ...s, draft: { title: '', attach: true, bots: [], group: false, picking: false, limit: { perOrder: 25, total: 100, until: now + 6 * DAY, venue: 'Stand-in Exchange' } }, route: { screen: 'messages', id: 'new' }, detailsOpen: false };
  },
  cancelDraft: s => ({ ...s, draft: null, route: { screen: 'messages', id: s.conversations[0]?.id } }),
  setDraftTitle: (s, title) => (s.draft ? { ...s, draft: { ...s.draft, title } } : s),
  setDraftLimit: (s, { key, value }) => (s.draft ? { ...s, draft: { ...s.draft, limit: { ...s.draft.limit, [key]: value } } } : s),
  toggleDraftAttach: s => (s.draft ? { ...s, draft: { ...s.draft, attach: !s.draft.attach } } : s),
  // "+ Add a bot" opens a picker of the installed bots; each one is picked on its own (spec §5.5)
  toggleDraftPicker: s => (s.draft ? { ...s, draft: { ...s.draft, picking: !s.draft.picking } } : s),
  toggleDraftBot(s, id) {
    if (!s.draft) return s;
    const had = s.draft.bots ?? [];
    const bots = had.includes(id) ? had.filter(x => x !== id) : [...had, id];
    return { ...s, draft: { ...s.draft, bots, group: bots.length > 0 } };
  },
  // all installed bots at once, or none
  toggleDraftGroup(s) {
    if (!s.draft) return s;
    const bots = (s.draft.bots ?? []).length ? [] : installedBots(s);
    return { ...s, draft: { ...s.draft, bots, group: bots.length > 0 } };
  },
  rename(s, { convId, title }) {
    const t = (title ?? '').trim();
    if (!t) return s;
    return upd(s, convId, c => ({ ...c, title: t }));
  },

  send(state, { text, now }) {
    const clean = (text ?? '').trim();
    // the composer's picked files go with the words; files alone are a message too
    const files = (state.compose?.files ?? []).map(f => f.name);
    if (!clean && !files.length) return state;
    let s = state;
    let convId = s.route.screen === 'messages' ? s.route.id : null;
    // the screen shows the first conversation for a missing id, so the words go there too
    if (!s.draft && s.conversations.length && !s.conversations.some(c => c.id === convId)) {
      convId = s.conversations[0].id;
      s = { ...s, route: { screen: 'messages', id: convId } };
    }
    if (s.draft || !s.conversations.some(c => c.id === convId)) {
      const d = s.draft ?? { title: '', attach: false, limit: null };
      const bots = d.bots ?? (d.group ? installedBots(s) : []);
      const members = ['gravit', ...bots];
      const made = newConversation(s, {
        title: d.title.trim() || (clean.length > 24 ? clean.slice(0, 24) + '…' : clean) || files[0],
        kind: members.length > 1 ? 'group' : 'gravit', members, plugins: bots, now,
        until: d.limit?.until ?? now + 6 * DAY,
        intentLimit: d.attach && d.limit ? { perOrder: d.limit.perOrder, total: d.limit.total, spent: 0, venue: d.limit.venue } : null,
      });
      s = { ...made.state, draft: null, route: { screen: 'messages', id: made.conv.id } };
      convId = made.conv.id;
    }
    const st = stampMessage(s, { from: 'you', kind: 'text', text: clean, data: files.length ? { files } : {} }, now);
    const sent = push(st.state, convId, st.msg);
    return files.length ? { ...sent, compose: { ...sent.compose, files: [] } } : sent;
  },

  append(state, { convId, msg, at }) {
    const target = state.conversations.find(c => c.id === convId);
    if (!target) return state;
    // after Stop or Withdraw nothing more lands from Gravit or a bot, even replies already scheduled
    if (closed(target) && msg.from !== 'you') return state;
    const filled = fillIds(state.counters, msg);
    const st = stampMessage({ ...state, counters: filled.counters }, filled.msg, at);
    const open = state.route.screen === 'messages' && state.route.id === convId;
    // a fill counts against the limit: Details shows what is left
    const spend = msg.kind === 'receipt' && msg.data?.status === 'filled' && Number(msg.data?.amount) > 0 ? Number(msg.data.amount) : 0;
    return upd(st.state, convId, c => ({
      ...c, unread: c.unread || (!open && msg.from !== 'you'), messages: [...c.messages, st.msg],
      intent: spend && c.intent.limit ? { ...c.intent, limit: { ...c.intent.limit, spent: c.intent.limit.spent + spend } } : c.intent,
    }));
  },

  answer(state, { convId, msgId, answer, now }) {
    const conv = state.conversations.find(c => c.id === convId);
    const msg = conv?.messages.find(m => m.id === msgId);
    if (!msg || msg.answer || closed(conv)) return state;
    const word = { approved: 'Approved.', rejected: 'Rejected.', granted: 'Granted.', declined: 'Declined.', no: 'No.' }[answer];
    let s = upd(state, convId, c => ({ ...c, messages: c.messages.map(m => (m.id === msgId ? { ...m, answer } : m)) }));
    if (word) {
      const st = stampMessage(s, { from: 'you', kind: 'text', text: word, data: {} }, now);
      s = push(st.state, convId, st.msg);
    }
    if (answer === 'granted' && msg.kind === 'limit') {
      s = upd(s, convId, c => ({ ...c, intent: { ...c.intent, limit: { ...(c.intent.limit ?? { total: 100, spent: 0, venue: 'Stand-in Exchange' }), perOrder: msg.data.to } } }));
    }
    return s;
  },

  toggleDetails: s => (s.detailsOpen ? { ...s, detailsOpen: false, edit: null, confirm: null } : { ...closeOverlays(s), detailsOpen: true }),
  stopGravit(s, { convId, now }) {
    if (closed(s.conversations.find(c => c.id === convId))) return s;
    const st = stampMessage(s, { from: 'system', kind: 'text', text: 'Gravit stopped. This task no longer moves.', data: {} }, now);
    return upd(push(st.state, convId, st.msg), convId, c => ({ ...c, status: 'stopped' }));
  },
  withdraw(s, { convId, now }) {
    if (closed(s.conversations.find(c => c.id === convId))) return s;
    const st = stampMessage(s, { from: 'system', kind: 'text', text: 'Delegation withdrawn.', data: {} }, now);
    return upd(push(st.state, convId, st.msg), convId, c => ({ ...c, status: 'withdrawn' }));
  },
  changeLimit: (s, { convId, limit }) => upd(s, convId, c => ({ ...c, intent: { ...c.intent, limit: { ...(c.intent.limit ?? { perOrder: 25, total: 100, spent: 0, venue: 'Stand-in Exchange' }), ...limit } } })),

  showBanner: (s, banner) => ({ ...s, banner }),
  // the banner stays 5 s, then its red-edged message lands in the thread (spec §6, kind 13)
  dismissBanner(s, { now } = {}) {
    if (!s.banner) return s;
    const b = s.banner;
    const convId = targetConv(s);
    let st = { ...s, banner: null };
    if (convId) {
      const r = stampMessage(st, { from: 'gravit', kind: 'breaking', text: b.headline, data: { headline: b.headline, body: b.body } }, now ?? b.at);
      st = push(r.state, convId, r.msg);
    }
    return st;
  },
  // calls (spec §6, kind 14): an incoming one rings; you ring Gravit from the rail's phone key; one call at a time
  incomingCall: (s, call) => (s.call ? s : { ...s, call: { ...call, dir: 'in', status: 'ringing' } }),
  startCall: (s, { now }) => (s.call ? s : { ...s, call: { from: 'gravit', about: '', dir: 'out', status: 'ringing', since: now, muted: false } }),
  connectCall: (s, { now }) => (s.call?.dir === 'out' && s.call.status === 'ringing' ? { ...s, call: { ...s.call, ...PICKED_UP, status: 'live', since: now } } : s),
  toggleMute: s => (s.call?.status === 'live' ? { ...s, call: { ...s.call, muted: !s.call.muted } } : s),
  // accepting an incoming call puts it live; declining leaves a missed-call card
  answerCall(s, { accept, now }) {
    if (!s.call || s.call.status === 'live' || s.call.dir === 'out') return s;
    if (accept) return { ...s, call: { ...s.call, dir: 'in', status: 'live', since: now, muted: false } };
    return callCard({ ...s, call: null }, s.call, { text: `Missed. It wanted to say: ${s.call.about}.`, answer: 'missed', duration: 0 }, now);
  },
  // hanging up leaves a card: how long it lasted, or that it never connected
  hangUp(s, { now }) {
    const c = s.call;
    if (!c) return s;
    const live = c.status === 'live';
    const duration = live ? Math.max(0, now - c.since) : 0;
    const answer = live ? 'accepted' : c.dir === 'out' ? 'cancelled' : 'missed';
    return callCard({ ...s, call: null }, c, { text: live ? `Call ${fmtDuration(duration)}` : 'Did not connect', answer, duration }, now);
  },
};

// what Gravit talks about when you ring it, once it picks up
const PICKED_UP = { about: 'About BTC', said: 'BTC is at 62.8k now; it watches it and calls if it moves.' };

// the call card lands in the conversation on screen, else the first (spec §6, kind 14)
function callCard(s, call, { text, answer, duration }, now) {
  const convId = targetConv(s);
  if (!convId) return s;
  const r = stampMessage(s, { from: call.from ?? 'gravit', kind: 'call', text, data: { about: call.about ?? '', dir: call.dir ?? 'in', duration, said: call.said ?? '' }, answer }, now);
  return push(r.state, convId, r.msg);
}
