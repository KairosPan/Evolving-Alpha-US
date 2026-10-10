// gravit-ui/js/reducers/discover.js — the store: search, 我的插件, the drawer, install/uninstall, the MCP connector
import { nextId } from '../ids.js';
import { DAY } from '../time.js';
import { byId, ICON_CHOICES, hostOf } from '../data/plugins.js';
import { stampMessage, closeOverlays } from './messages.js';

const disc = (s, patch) => ({ ...s, discover: { ...s.discover, ...patch } });

// the MCP connector Create opens (a remote MCP server becomes your own plugin)
const EMPTY_FORM = { name: '', url: '', auth: '无', key: '', clientId: '', clientSecret: '', kind: 'Quant', visibility: 'private', icon: 0 };
const URL_OK = /^https?:\/\/[^\s/?#]+\.[^\s/?#]+(?:[/?#]\S*)?$/i;
const nameFromHost = host => { const w = host.split('.')[0] ?? ''; return w ? w[0].toUpperCase() + w.slice(1) : 'Connector'; };
const withCreate = (s, patch) => (s.discover.create ? disc(s, { create: { ...s.discover.create, ...patch } }) : s);

export const reducers = {
  setQuery: (s, query) => disc(s, { query: query ?? '' }),
  toggleInstalledOnly: s => disc(s, { installedOnly: !s.discover.installedOnly }),
  openPlugin: (s, id) => disc(closeOverlays(s), { drawer: id }),
  closeDrawer: s => disc(s, { drawer: null }),
  dismissToast: s => (s.discover.toast ? disc(s, { toast: null }) : s),

  openCreate: s => disc(closeOverlays(s), { create: { step: 'form', form: { ...EMPTY_FORM }, tools: [], error: null } }),
  closeCreate: s => (s.discover.create ? disc(s, { create: null }) : s),
  setCreateField(s, { key, value }) {
    const c = s.discover.create;
    if (!c || !(key in EMPTY_FORM)) return s;
    return withCreate(s, { form: { ...c.form, [key]: value }, error: key === 'url' ? null : c.error });
  },
  cycleCreateIcon: s => (s.discover.create ? withCreate(s, { form: { ...s.discover.create.form, icon: (s.discover.create.form.icon + 1) % ICON_CHOICES.length } }) : s),
  connectMcp(s) {
    const c = s.discover.create;
    if (!c || c.step !== 'form') return s;
    if (!URL_OK.test(c.form.url.trim())) return withCreate(s, { error: '地址要以 https:// 开头' });
    return withCreate(s, { step: 'connecting', error: null });
  },
  // the scripted server answered with its tool list (app.js schedules it a moment after connectMcp)
  mcpConnected(s, { tools }) {
    const c = s.discover.create;
    if (!c || c.step !== 'connecting') return s;
    return withCreate(s, { step: 'tools', tools: tools.map(name => ({ name, on: true })) });
  },
  backToForm: s => withCreate(s, { step: 'form' }),
  toggleMcpTool(s, i) {
    const c = s.discover.create;
    if (!c || !c.tools[i]) return s;
    return withCreate(s, { tools: c.tools.map((t, k) => (k === i ? { ...t, on: !t.on } : t)) });
  },
  // the connected server becomes your own plugin: installed, with a conversation that teaches its tools
  addMcp(state, { now }) {
    const c = state.discover.create;
    if (!c || c.step !== 'tools') return state;
    const f = c.form;
    const url = f.url.trim();
    const host = hostOf(url);
    const name = f.name.trim() || nameFromHost(host);
    const tools = c.tools.filter(t => t.on).map(t => t.name);
    const { id, counters } = nextId(state.counters, 'plugin');
    const glyph = ICON_CHOICES[f.icon];
    const p = {
      id, kind: f.kind, name, blurb: host, by: '@you', visibility: f.visibility === 'public' ? 'public' : 'private', installs: '', url,
      logo: glyph ? { type: 'glyph', icon: glyph } : { type: 'letter', text: name[0].toUpperCase() }, avatar: null,
      asks: [], writes: tools.map(t => `${t} 的结果`), never: ['动钱', '付人', '改额度'],
      needs: f.auth === 'API key' ? '一把 API key。' : f.auth === 'OAuth' ? 'OAuth 授权。' : '没有。',
      tools: tools.join('\n'), teach: `你好，这是你接上的 ${name}。我有 ${tools.length} 个工具：${tools.join('、') || '（没选）'}。`, at: now,
    };
    let s = { ...state, counters, plugins: { ...state.plugins, uploaded: [...state.plugins.uploaded, p], mine: [...state.plugins.mine, id] } };
    s = reducers.install(s, { id, now });
    const convId = s.conversations[0].id;
    return disc(s, { create: null, toast: { text: `${name} 已添加 · ${p.visibility === 'private' ? 'Private' : 'Public · 等过审'}`, action: { label: 'Open', route: { screen: 'messages', id: convId } } } });
  },

  install(state, { id, now }) {
    const p = byId(id, state.plugins.uploaded);
    if (!p || state.plugins.installed.includes(id)) return state;
    const c1 = nextId(state.counters, 'conv');
    const c2 = nextId(c1.counters, 'intent');
    let s = { ...state, counters: c2.counters, plugins: { ...state.plugins, installed: [...state.plugins.installed, id] } };
    // the plugin opens a conversation that teaches its use (spec §7.5)
    const st = stampMessage(s, { from: id, kind: 'text', text: p.teach, data: {} }, now);
    const conv = {
      id: c1.id, title: `${p.name}：怎么用我`, kind: 'bot', members: ['gravit', id], unread: true, status: 'working', teach: id,
      intent: { id: c2.id, created: now, until: now + 6 * DAY, limit: null }, plugins: [id], messages: [st.msg],
    };
    s = { ...st.state, conversations: [conv, ...st.state.conversations] };
    // every conversation that was waiting on this install gets its answer and a word from Gravit
    for (const c of s.conversations) {
      if (!c.messages.some(m => m.kind === 'install' && m.data?.plugin === id && !m.answer)) continue;
      const said = stampMessage(s, { from: 'gravit', kind: 'text', text: `${p.name} 装好了，我接着看。`, data: {} }, now);
      s = { ...said.state, conversations: said.state.conversations.map(x => (x.id !== c.id ? x : {
        ...x, plugins: x.plugins.includes(id) ? x.plugins : [...x.plugins, id],
        messages: [...x.messages.map(m => (m.kind === 'install' && m.data?.plugin === id && !m.answer ? { ...m, answer: 'installed' } : m)), said.msg],
      })) };
    }
    return disc(s, { drawer: null, toast: { text: `${p.name} 装好了 · Gravit 开了一个会话教你用`, action: { label: 'Open', route: { screen: 'messages', id: conv.id } } } });
  },

  uninstall(s, id) {
    if (!s.plugins.installed.includes(id)) return s;
    const next = { ...s, plugins: { ...s.plugins, installed: s.plugins.installed.filter(x => x !== id) } };
    return next.discover.drawer === id ? disc(next, { drawer: null }) : next;
  },

};
