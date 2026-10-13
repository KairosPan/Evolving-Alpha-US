// gravit-ui/js/reducers/discover.js — the store: search, My plugins, the drawer, install/uninstall, and Create: Discover's own MCP face
import { nextId } from '../ids.js';
import { DAY } from '../time.js';
import { byId, SHOP_MCP, fromManifest } from '../data/plugins.js';
import { stampMessage, closeOverlays } from './messages.js';

const disc = (s, patch) => ({ ...s, discover: { ...s.discover, ...patch } });

// a public upload is reviewed this long (run in a sandbox, its permissions and author read) before the shop lists it
export const REVIEW_MS = 5000;

// Create's dialog moves only on its own run and only from the step it expects, so a closed or reopened dialog ignores late timers
const inRun = (s, run, step) => s.discover.create?.run === run && s.discover.create.step === step;
const withCreate = (s, patch) => disc(s, { create: { ...s.discover.create, ...patch } });

export const reducers = {
  setQuery: (s, query) => disc(s, { query: query ?? '' }),
  toggleInstalledOnly: s => disc(s, { installedOnly: !s.discover.installedOnly }),
  dismissToast: s => (s.discover.toast ? disc(s, { toast: null }) : s),

  // Create: Discover's MCP face, waiting for a client to connect
  openCreate(s) {
    const { id, counters } = nextId(s.counters, 'run');
    return disc({ ...closeOverlays(s), counters }, { create: { run: id, step: 'wait', client: 'Claude Code', started: false, copied: false, manifest: null, visibility: 'private' } });
  },
  closeCreate: s => (s.discover.create ? disc(s, { create: null }) : s),
  // which client's line to show; fixed once the scripted client started
  setClient(s, name) {
    const c = s.discover.create;
    return c && c.step === 'wait' && !c.started && name in SHOP_MCP.clients && name !== c.client ? withCreate(s, { client: name }) : s;
  },
  setCreateCopied: (s, on) => (s.discover.create ? withCreate(s, { copied: !!on }) : s),
  // the scripted client (app.js): started by the copy key or the director, then it connects, calls shop.mine and asks shop.publish
  startClient: (s, { run }) => (inRun(s, run, 'wait') && !s.discover.create.started ? withCreate(s, { started: true }) : s),
  clientConnected: (s, { run }) => (inRun(s, run, 'wait') && s.discover.create.started ? withCreate(s, { step: 'connected' }) : s),
  clientPublishes: (s, { run, manifest }) => (inRun(s, run, 'connected') ? withCreate(s, { step: 'sign', manifest, visibility: manifest.visibility === 'public' ? 'public' : 'private' }) : s),
  setUploadVisibility(s, v) {
    const c = s.discover.create;
    return c?.step === 'sign' && (v === 'private' || v === 'public') && v !== c.visibility ? withCreate(s, { visibility: v }) : s;
  },
  rejectUpload: s => (s.discover.create?.step === 'sign' ? withCreate(s, { step: 'refused' }) : s),
  // the owner's one signature for shop.publish: a private plugin is published and installed; a public one goes to review first
  publishUpload(state, { now }) {
    const c = state.discover.create;
    if (!c || c.step !== 'sign') return state;
    const p = { ...fromManifest(c.manifest, c.visibility, now), review: c.visibility === 'public' ? { until: now + REVIEW_MS } : null };
    let s = disc({ ...state, plugins: { ...state.plugins, uploaded: [...state.plugins.uploaded, p], mine: [...state.plugins.mine, p.id] } }, { create: null, query: '', installedOnly: false });
    if (p.review) return disc(s, { toast: { text: `${p.name} uploaded · In review`, action: null } });
    s = reducers.install(s, { id: p.id, now });
    return disc(s, { toast: { text: `${p.name} uploaded · Private`, action: { label: 'Open', route: { screen: 'messages', id: s.conversations[0].id } } } });
  },
  // the review passed: the shop lists it, and Discover writes to Gravit's mailbox
  reviewPassed(state, { id, now }) {
    const p = state.plugins.uploaded.find(x => x.id === id);
    if (!p?.review) return state;
    const { id: mailId, counters } = nextId(state.counters, 'mail');
    const letter = { id: mailId, from: 'Discover', subject: `${p.name} passed review`, at: now, read: false, body: `Listed under ${p.kind} · Public. Ran in the sandbox; never moves money, pays anyone or changes limits.` };
    const s = {
      ...state, counters, mail: { ...state.mail, items: [letter, ...state.mail.items] },
      plugins: { ...state.plugins, uploaded: state.plugins.uploaded.map(x => (x.id === id ? { ...x, review: null } : x)) },
    };
    // a toast only where it can be seen; elsewhere the letter carries the news
    return s.route.screen === 'discover' ? disc(s, { toast: { text: `${p.name} passed review · Public`, action: { label: 'Open', plugin: id } } }) : s;
  },

  install(state, { id, now }) {
    const p = byId(id, state.plugins.uploaded);
    if (!p || p.review || state.plugins.installed.includes(id)) return state;
    const c1 = nextId(state.counters, 'conv');
    const c2 = nextId(c1.counters, 'intent');
    let s = { ...state, counters: c2.counters, plugins: { ...state.plugins, installed: [...state.plugins.installed, id] } };
    // the plugin opens a conversation that teaches its use (spec §7.5)
    const st = stampMessage(s, { from: id, kind: 'text', text: p.teach, data: {} }, now);
    const conv = {
      id: c1.id, title: `${p.name}: how to use me`, kind: 'bot', members: ['gravit', id], unread: true, status: 'working', teach: id,
      intent: { id: c2.id, created: now, until: now + 6 * DAY, limit: null }, plugins: [id], messages: [st.msg],
    };
    s = { ...st.state, conversations: [conv, ...st.state.conversations] };
    // every conversation that was waiting on this install gets its answer and a word from Gravit
    for (const c of s.conversations) {
      if (!c.messages.some(m => m.kind === 'install' && m.data?.plugin === id && !m.answer)) continue;
      const said = stampMessage(s, { from: 'gravit', kind: 'text', text: `${p.name} installed. Carrying on.`, data: {} }, now);
      s = { ...said.state, conversations: said.state.conversations.map(x => (x.id !== c.id ? x : {
        ...x, plugins: x.plugins.includes(id) ? x.plugins : [...x.plugins, id],
        messages: [...x.messages.map(m => (m.kind === 'install' && m.data?.plugin === id && !m.answer ? { ...m, answer: 'installed' } : m)), said.msg],
      })) };
    }
    return disc(s, { toast: { text: `${p.name} installed · Gravit opened a conversation to show you how`, action: { label: 'Open', route: { screen: 'messages', id: conv.id } } } });
  },

  uninstall(s, id) {
    if (!s.plugins.installed.includes(id)) return s;
    return { ...s, plugins: { ...s.plugins, installed: s.plugins.installed.filter(x => x !== id) } };
  },

};
