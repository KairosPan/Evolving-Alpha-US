// gravit-ui/js/reducers/messages.js — the conversation side: routes, drafts, sending, answering, details, banners, calls
import { nextId } from '../ids.js';
import { DAY } from '../time.js';
import { byId } from '../data/plugins.js';

const upd = (state, id, fn) => ({ ...state, conversations: state.conversations.map(c => (c.id === id ? fn(c) : c)) });
const push = (state, convId, msg) => upd(state, convId, c => ({ ...c, messages: [...c.messages, msg] }));

export function stampMessage(state, msg, at) {
  const { id, counters } = nextId(state.counters, 'msg');
  return { state: { ...state, counters }, msg: { ...msg, id, at } };
}

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
    let s = { ...state, route, detailsOpen: false, settingsOpen: false };
    if (route.screen === 'messages' && route.id && route.id !== 'new') s = upd(s, route.id, c => (c.unread ? { ...c, unread: false } : c));
    if (!(route.screen === 'messages' && route.id === 'new')) s.draft = null;
    return s;
  },
  toggleRail: s => ({ ...s, railCollapsed: !s.railCollapsed }),
  setTheme: (s, theme) => ({ ...s, theme }),

  startDraft(s, { now }) {
    return { ...s, draft: { title: '', attach: true, limit: { perOrder: 25, total: 100, until: now + 6 * DAY, venue: 'Stand-in Exchange' } }, route: { screen: 'messages', id: 'new' }, detailsOpen: false };
  },
  cancelDraft: s => ({ ...s, draft: null, route: { screen: 'messages', id: s.conversations[0]?.id } }),
  setDraftTitle: (s, title) => (s.draft ? { ...s, draft: { ...s.draft, title } } : s),
  setDraftLimit: (s, { key, value }) => (s.draft ? { ...s, draft: { ...s.draft, limit: { ...s.draft.limit, [key]: value } } } : s),
  toggleDraftAttach: s => (s.draft ? { ...s, draft: { ...s.draft, attach: !s.draft.attach } } : s),
  toggleDraftGroup: s => (s.draft ? { ...s, draft: { ...s.draft, group: !s.draft.group } } : s),
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
    if (s.draft || !s.conversations.some(c => c.id === convId)) {
      const d = s.draft ?? { title: '', attach: false, limit: null };
      const bots = d.group ? s.plugins.installed.filter(id => byId(id, s.plugins.uploaded)?.kind === 'Bots') : [];
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
    if (!state.conversations.some(c => c.id === convId)) return state;
    const st = stampMessage(state, msg, at);
    const open = state.route.screen === 'messages' && state.route.id === convId;
    return upd(st.state, convId, c => ({ ...c, unread: c.unread || (!open && msg.from !== 'you'), messages: [...c.messages, st.msg] }));
  },

  answer(state, { convId, msgId, answer, now }) {
    const conv = state.conversations.find(c => c.id === convId);
    const msg = conv?.messages.find(m => m.id === msgId);
    if (!msg || msg.answer) return state;
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

  toggleDetails: s => ({ ...s, detailsOpen: !s.detailsOpen }),
  stopGravit(s, { convId, now }) {
    const st = stampMessage(s, { from: 'system', kind: 'text', text: 'Gravit 停了，这件事不再动。', data: {} }, now);
    return upd(push(st.state, convId, st.msg), convId, c => ({ ...c, status: 'stopped' }));
  },
  withdraw(s, { convId, now }) {
    const st = stampMessage(s, { from: 'system', kind: 'text', text: '委托撤了。', data: {} }, now);
    return upd(push(st.state, convId, st.msg), convId, c => ({ ...c, status: 'withdrawn' }));
  },
  changeLimit: (s, { convId, limit }) => upd(s, convId, c => ({ ...c, intent: { ...c.intent, limit: { ...(c.intent.limit ?? { perOrder: 25, total: 100, spent: 0, venue: 'Stand-in Exchange' }), ...limit } } })),

  showBanner: (s, banner) => ({ ...s, banner }),
  dismissBanner: s => (s.banner ? { ...s, banner: null } : s),
  incomingCall: (s, call) => ({ ...s, call }),
  answerCall(s, { accept, now }) {
    if (!s.call) return s;
    const convId = s.conversations[0]?.id;
    const text = accept ? `接了 Gravit 的电话：${s.call.about}。` : `没接。它想说：${s.call.about}。`;
    let st = { ...s, call: null };
    if (convId) {
      const r = stampMessage(st, { from: 'gravit', kind: 'text', text, data: {} }, now);
      st = push(r.state, convId, r.msg);
    }
    return st;
  },
};
