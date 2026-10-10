// gravit-ui/js/reducers/discover.js — the store: search, the Installed filter, the drawer, install/uninstall, upload
import { nextId } from '../ids.js';
import { DAY } from '../time.js';
import { byId } from '../data/plugins.js';
import { stampMessage } from './messages.js';

const disc = (s, patch) => ({ ...s, discover: { ...s.discover, ...patch } });

export const reducers = {
  setQuery: (s, query) => disc(s, { query: query ?? '' }),
  toggleInstalledOnly: s => disc(s, { installedOnly: !s.discover.installedOnly }),
  openPlugin: (s, id) => disc(s, { drawer: id, upload: false }),
  closeDrawer: s => disc(s, { drawer: null, upload: false }),
  openUpload: s => disc(s, { upload: true, drawer: null }),
  dismissToast: s => (s.discover.toast ? disc(s, { toast: null }) : s),

  install(state, { id, now }) {
    const p = byId(id, state.plugins.uploaded);
    if (!p || state.plugins.installed.includes(id)) return state;
    const c1 = nextId(state.counters, 'conv');
    const c2 = nextId(c1.counters, 'intent');
    let s = { ...state, counters: c2.counters, plugins: { ...state.plugins, installed: [...state.plugins.installed, id] } };
    // the plugin opens a conversation that teaches its use (spec §7.5)
    const st = stampMessage(s, { from: id, kind: 'text', text: p.teach, data: {} }, now);
    const conv = {
      id: c1.id, title: `${p.name}：怎么用我`, kind: 'bot', members: ['gravit', id], unread: true, status: 'working',
      intent: { id: c2.id, created: now, until: now + 6 * DAY, limit: null }, plugins: [id], messages: [st.msg],
    };
    s = { ...st.state, conversations: [conv, ...st.state.conversations] };
    return disc(s, { drawer: null, toast: { text: `${p.name} 装好了 · Gravit 开了一个会话教你用`, action: { label: 'Open', route: { screen: 'messages', id: conv.id } } } });
  },

  uninstall(s, id) {
    if (!s.plugins.installed.includes(id)) return s;
    const next = { ...s, plugins: { ...s.plugins, installed: s.plugins.installed.filter(x => x !== id) } };
    return next.discover.drawer === id ? disc(next, { drawer: null }) : next;
  },

  publish(state, { manifest, now }) {
    const name = (manifest.name ?? '').trim();
    if (!name) return state;
    const { id, counters } = nextId(state.counters, 'plugin');
    const p = {
      id, kind: manifest.kind, name, blurb: (manifest.blurb ?? '').trim(), by: '@you', visibility: manifest.visibility === 'public' ? 'public' : 'private', installs: '',
      logo: { type: 'letter', text: name[0].toUpperCase() }, avatar: null, asks: [], writes: ['你写的工具的输出'], never: ['动钱', '付人', '改额度'],
      needs: manifest.needs || '没有。', tools: manifest.tools ?? '', teach: `你好，这是你自己写的 ${name}。工具：${manifest.tools || '（没写）'}。`, at: now,
    };
    const s = { ...state, counters, plugins: { ...state.plugins, uploaded: [...state.plugins.uploaded, p], mine: [...state.plugins.mine, id], installed: [...state.plugins.installed, id] } };
    return disc(s, { upload: false, toast: { text: `${name} 发布了 · ${p.visibility === 'private' ? '只有你的 Gravit 看得见' : '等过审'}`, action: null } });
  },
};
