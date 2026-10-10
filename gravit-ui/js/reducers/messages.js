// gravit-ui/js/reducers/messages.js — the conversation side: routes, drafts, sending, answering, details, banners, calls
import { nextId } from '../ids.js';
import { DAY } from '../time.js';
import { byId } from '../data/plugins.js';
import { isClosed } from '../messages.js';

const closed = isClosed;
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
    let s = { ...state, route, detailsOpen: false, settingsOpen: false, edit: null, confirm: null };
    // the first level's Messages key returns to the conversation you last had open
    if (route.screen === 'messages' && route.id && route.id !== 'new') s.lastConv = route.id;
    // Discover's drawer, trash-key ask and toast belong to Discover; they do not follow you out of it
    if (route.screen !== 'discover' && (s.discover.drawer || s.discover.create || s.discover.toast)) {
      s = { ...s, discover: { ...s.discover, drawer: null, create: null, toast: null } };
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
  // "+ 加个 bot" opens a picker of the installed bots; each one is picked on its own (spec §5.5)
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
    if (!clean) return state;
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
        title: d.title.trim() || (clean.length > 24 ? clean.slice(0, 24) + '…' : clean),
        kind: members.length > 1 ? 'group' : 'gravit', members, plugins: bots, now,
        until: d.limit?.until ?? now + 6 * DAY,
        intentLimit: d.attach && d.limit ? { perOrder: d.limit.perOrder, total: d.limit.total, spent: 0, venue: d.limit.venue } : null,
      });
      s = { ...made.state, draft: null, route: { screen: 'messages', id: made.conv.id } };
      convId = made.conv.id;
    }
    const st = stampMessage(s, { from: 'you', kind: 'text', text: clean, data: {} }, now);
    return push(st.state, convId, st.msg);
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

  toggleDetails: s => ({ ...s, detailsOpen: !s.detailsOpen, edit: null, confirm: null }),
  stopGravit(s, { convId, now }) {
    if (closed(s.conversations.find(c => c.id === convId))) return s;
    const st = stampMessage(s, { from: 'system', kind: 'text', text: 'Gravit 停了，这件事不再动。', data: {} }, now);
    return upd(push(st.state, convId, st.msg), convId, c => ({ ...c, status: 'stopped' }));
  },
  withdraw(s, { convId, now }) {
    if (closed(s.conversations.find(c => c.id === convId))) return s;
    const st = stampMessage(s, { from: 'system', kind: 'text', text: '委托撤了。', data: {} }, now);
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
  incomingCall: (s, call) => ({ ...s, call }),
  // the call leaves a call card in the thread, answered or missed (spec §6, kind 14)
  answerCall(s, { accept, now }) {
    if (!s.call) return s;
    const convId = targetConv(s);
    const { from = 'gravit', about } = s.call;
    const text = accept ? `接了：${about}` : `没接。它想说：${about}。`;
    let st = { ...s, call: null };
    if (convId) {
      const r = stampMessage(st, { from, kind: 'call', text, data: { about }, answer: accept ? 'accepted' : 'missed' }, now);
      st = push(r.state, convId, r.msg);
    }
    return st;
  },
};
