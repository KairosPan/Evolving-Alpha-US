// gravit-ui/js/reducers/account.js — Account: mode, Memory, settings
import { closeOverlays } from './messages.js';
import { nextId } from '../ids.js';

const mem = (s, patch) => ({ ...s, memory: { ...s.memory, ...patch } });

export const reducers = {
  setMode: (s, mode) => ({ ...s, account: { ...s.account, mode } }),
  openSettings: s => ({ ...closeOverlays(s), settingsOpen: true }),
  closeSettings: s => ({ ...s, settingsOpen: false, edit: null, confirm: null }),
  addMemory(s, { text, now }) {
    const t = (text ?? '').trim();
    if (!t) return s;
    const { id, counters } = nextId(s.counters, 'mem');
    return { ...mem(s, { entries: [...s.memory.entries, { id, group: '你加的', text: t, source: '你说的', at: now }] }), counters };
  },
  editMemory: (s, { id, text }) => mem(s, { entries: s.memory.entries.map(e => (e.id === id ? { ...e, text: (text ?? '').trim() || e.text } : e)) }),
  forgetMemory: (s, id) => mem(s, { entries: s.memory.entries.filter(e => e.id !== id) }),
  forgetAll: s => mem(s, { entries: [] }),
  setMemorySwitch: (s, { key, value }) => (['remember', 'askFirst', 'botsRead'].includes(key) ? mem(s, { [key]: !!value }) : s),
};
