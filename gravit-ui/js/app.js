// gravit-ui/js/app.js — boot: the store, the hash router, one render per change, event delegation on data-action, the driver's timers, the director
import { createStore } from './store.js';
import { reducers } from './reducers/index.js';
import { seed, SEED_VERSION } from './data/seed.js';
import { parseHash, toHash } from './router.js';
import { renderRail } from './render/rail.js';
import { renderMessagesScreen, renderBanner, renderCall, renderStub, currentConversation } from './render/messages.js';
import { renderDiscover } from './render/discover.js';
import { renderAccount } from './render/account.js';
import { replyTo, followUp, director } from './driver.js';
import { DAY } from './time.js';

export class Timers {
  constructor() { this.set = new Set(); }
  after(ms, fn) {
    const t = setTimeout(() => { this.set.delete(t); fn(); }, ms);
    this.set.add(t);
    return t;
  }
  clear() { for (const t of this.set) clearTimeout(t); this.set.clear(); }
  get size() { return this.set.size; }
}

const KEY = 'gravit-ui.state';
const BANNER_MS = 5000;
const usable = saved => !!saved && saved.v === SEED_VERSION && Array.isArray(saved.conversations);

export function initialState(storage, now = Date.now()) {
  try {
    const raw = storage?.getItem(KEY);
    const saved = raw ? JSON.parse(raw) : null;
    if (usable(saved)) return saved;
  } catch { /* fall through to the seed */ }
  return seed(now);
}

// the store boot uses: the same version check, so createStore cannot load a stale save on its own (Review Focus 2)
export function makeStore(storage, now = Date.now()) {
  return createStore({ initial: initialState(storage, now), reducers, storage, key: KEY, accept: usable });
}

export function scheduleEvents(store, timers, convId, events, now = () => Date.now()) {
  for (const e of events) timers.after(e.delay, () => store.dispatch('append', { convId, msg: e.msg, at: now() }));
}

// route by the hash; returns the hash the address bar should show when the route was normalised, else null
export function settle(store, hash) {
  store.dispatch('nav', parseHash(hash));
  const h = toHash(store.get().route);
  return h === hash ? null : h;
}

// breaking news: the banner for 5 s, then its red-edged message in the thread (spec §6, kind 13)
export function showBreaking(store, timers, banner, now = () => Date.now(), ms = BANNER_MS) {
  store.dispatch('showBanner', banner);
  timers.after(ms, () => { if (store.get().banner?.id === banner.id) store.dispatch('dismissBanner', { now: now() }); });
}

// answer a card once; the follow-up is scheduled only for the first answer (Review Focus 4)
export function answerFlow(store, timers, { conv, msg, answer }, now = () => Date.now(), schedule = scheduleEvents) {
  const before = store.get().conversations.find(c => c.id === conv)?.messages.find(m => m.id === msg);
  if (!before || before.answer) return;
  const events = followUp(before, answer, { installed: store.get().plugins.installed, now: now() });
  store.dispatch('answer', { convId: conv, msgId: msg, answer, now: now() });
  schedule(store, timers, conv, events, now);
}

const DIRECTOR = [['早报', 'brief'], ['技术分析', 'ta'], ['突发', 'breaking'], ['来电', 'call'], ['bot 插话', 'bot'], ['重置 demo', 'reset']];

export function boot(win) {
  const doc = win.document;
  const storage = (() => { try { return win.localStorage; } catch { return null; } })();
  const store = makeStore(storage);
  const timers = new Timers();
  const root = doc.getElementById('app');
  const now = () => Date.now();
  let directorOpen = false;
  let composerText = '';

  function applyTheme(theme) {
    if (theme === 'cream' || theme === 'black') doc.documentElement.dataset.theme = theme; else delete doc.documentElement.dataset.theme;
    try { if (theme === 'cream' || theme === 'black') storage?.setItem('gravit-ui.theme', theme); else storage?.removeItem('gravit-ui.theme'); } catch { /* ignore */ }
  }

  function syncIcon() {
    const name = doc.getElementById('up-name');
    const slot = doc.getElementById('up-icon');
    if (name && slot) slot.textContent = (name.value.trim()[0] ?? 'P').toUpperCase();
  }

  function render() {
    const s = store.get();
    const active = doc.activeElement;
    const activeId = active?.id;
    const caret = activeId && typeof active.selectionStart === 'number' ? [active.selectionStart, active.selectionEnd] : null;
    // what the person is typing survives a re-render (an arriving reply, a toast): text fields by id, picked radios by name
    const typed = new Map([...root.querySelectorAll('input[id]:not([type=radio]), textarea[id]')].map(el => [el.id, el.value]));
    const picked = [...root.querySelectorAll('.upload-form input[type=radio]:checked')].map(el => [el.name, el.value]);
    const screen = s.route.screen === 'discover' ? renderDiscover(s) : s.route.screen === 'account' ? renderAccount(s) : (s.route.screen === 'markets' || s.route.screen === 'trade') ? renderStub(s.route) : renderMessagesScreen(s, now());
    const overlays = (s.banner ? renderBanner(s.banner, s) : '') + (s.call ? renderCall(s.call) : '') +
      (directorOpen ? `<div class="director" role="menu">${DIRECTOR.map(([l, k]) => `<button type="button" class="director-key" data-action="director" data-key="${k}">${l}</button>`).join('')}</div>` : '');
    root.innerHTML = renderRail(s, now()) + screen + overlays;
    for (const [id, value] of typed) { const el = doc.getElementById(id); if (el && id !== 'say') el.value = value; }
    for (const [name, value] of picked) { const el = root.querySelector(`.upload-form input[type=radio][name="${name}"][value="${value}"]`); if (el) el.checked = true; }
    const say = doc.getElementById('say');
    if (say) say.value = composerText;
    syncIcon();
    const back = activeId && doc.getElementById(activeId);
    if (back) { back.focus(); if (caret && typeof back.setSelectionRange === 'function') back.setSelectionRange(caret[0], caret[1]); }
    const thread = doc.getElementById('thread');
    if (thread) thread.scrollTop = thread.scrollHeight;
  }

  function go(route) {
    const h = toHash(route);
    if (win.location.hash !== h) win.location.hash = h; else store.dispatch('nav', route);
  }

  // route by the address bar; a normalised route rewrites the hash without a new history entry
  function follow() {
    const fixed = settle(store, win.location.hash);
    if (fixed) win.history.replaceState(null, '', fixed);
  }

  function reply(convId, text) {
    const s = store.get();
    scheduleEvents(store, timers, convId, replyTo(text, { installed: s.plugins.installed, now: now() }), now);
  }

  function reset() {
    timers.clear();
    store.reset(seed(now()));
    applyTheme(store.get().theme);
    composerText = '';
    go({ screen: 'messages', id: 'c-1' });
  }

  const actions = {
    open: el => go({ screen: 'messages', id: el.dataset.id }),
    startDraft: () => { store.dispatch('startDraft', { now: now() }); go({ screen: 'messages', id: 'new' }); },
    cancelDraft: () => { store.dispatch('cancelDraft'); go(store.get().route); },
    toggleRail: () => store.dispatch('toggleRail'),
    toggleDraftAttach: () => store.dispatch('toggleDraftAttach'),
    toggleDraftGroup: () => store.dispatch('toggleDraftGroup'),
    draftLimit: el => {
      const key = el.dataset.key;
      const d = store.get().draft;
      if (!d) return;
      if (key === 'venue') {
        const venues = ['Stand-in Exchange', 'Stand-in Broker', 'Stand-in Wallet'];
        store.dispatch('setDraftLimit', { key, value: venues[(venues.indexOf(d.limit.venue) + 1) % venues.length] });
      } else if (key === 'until') {
        const days = Number(win.prompt('几天后到期？', '6'));
        if (days > 0) store.dispatch('setDraftLimit', { key, value: now() + days * DAY });
      } else {
        const v = Number(win.prompt(key === 'perOrder' ? '每单上限（$）' : '总额（$）', String(d.limit[key])));
        if (v > 0) store.dispatch('setDraftLimit', { key, value: v });
      }
    },
    suggest: el => { composerText = el.dataset.text; render(); doc.getElementById('say')?.focus(); },
    answer: el => answerFlow(store, timers, el.dataset, now),
    installAsk: el => {
      const { conv, msg, plugin } = el.dataset;
      store.dispatch('answer', { convId: conv, msgId: msg, answer: 'installed', now: now() });
      store.dispatch('openPlugin', plugin);
      go({ screen: 'discover', id: null });
    },
    toggleDetails: () => store.dispatch('toggleDetails'),
    changeWords: el => {
      const c = store.get().conversations.find(x => x.id === el.dataset.conv);
      const title = win.prompt('这件事叫什么', c?.title ?? '');
      if (title != null) store.dispatch('rename', { convId: el.dataset.conv, title });
    },
    withdraw: el => { if (win.confirm('撤回这条委托？')) store.dispatch('withdraw', { convId: el.dataset.conv, now: now() }); },
    changeLimit: el => {
      const c = store.get().conversations.find(x => x.id === el.dataset.conv);
      const L = c?.intent.limit ?? { perOrder: 25, total: 100 };
      const perOrder = Number(win.prompt('每单上限（$）', String(L.perOrder)));
      const total = Number(win.prompt('总额（$）', String(L.total)));
      if (perOrder > 0 && total > 0) store.dispatch('changeLimit', { convId: el.dataset.conv, limit: { perOrder, total } });
    },
    endLimit: el => {
      const c = store.get().conversations.find(x => x.id === el.dataset.conv);
      if (c?.intent.limit) store.dispatch('changeLimit', { convId: el.dataset.conv, limit: { total: c.intent.limit.spent } });
    },
    stopGravit: el => { if (win.confirm('停掉 Gravit？这件事不再动。')) store.dispatch('stopGravit', { convId: el.dataset.conv, now: now() }); },
    setMode: el => store.dispatch('setMode', el.dataset.value === 'Beast' ? 'beast' : 'guard'),
    // the banner's link dismisses it and still goes to the thread it names
    dismissBanner: el => { store.dispatch('dismissBanner', { now: now() }); if (el.tagName === 'A') go(parseHash(el.getAttribute('href'))); },
    answerCall: el => store.dispatch('answerCall', { accept: el.dataset.accept === '1', now: now() }),
    // Discover
    openPlugin: el => store.dispatch('openPlugin', el.dataset.id),
    closeDrawer: () => store.dispatch('closeDrawer'),
    install: el => store.dispatch('install', { id: el.dataset.id, now: now() }),
    uninstall: el => store.dispatch('uninstall', el.dataset.id),
    // pressing "✓ Installed" turns the key into the trash key (spec §7.3); the trash key uninstalls
    uninstallAsk: el => store.dispatch('askUninstall', el.dataset.id),
    toggleInstalledOnly: () => store.dispatch('toggleInstalledOnly'),
    openUpload: () => store.dispatch('openUpload'),
    dismissToast: () => store.dispatch('dismissToast'),
    // Account
    openSettings: () => store.dispatch('openSettings'),
    closeSettings: () => store.dispatch('closeSettings'),
    setTheme: el => { const t = el.dataset.value.toLowerCase(); store.dispatch('setTheme', t); applyTheme(t); },
    resetDemo: () => { if (win.confirm('回到最初的样子？')) reset(); },
    editMemory: el => {
      const e = store.get().memory.entries.find(x => x.id === el.dataset.id);
      const text = win.prompt('改成', e?.text ?? '');
      if (text != null) store.dispatch('editMemory', { id: el.dataset.id, text });
    },
    forgetMemory: el => store.dispatch('forgetMemory', el.dataset.id),
    forgetAll: () => { if (win.confirm('全部忘掉？')) store.dispatch('forgetAll'); },
    memorySwitch: el => store.dispatch('setMemorySwitch', { key: el.dataset.key, value: el.getAttribute('aria-checked') !== 'true' }),
    exportMemory: () => {
      const blob = new win.Blob([JSON.stringify(store.get().memory, null, 2)], { type: 'application/json' });
      const a = doc.createElement('a');
      a.href = win.URL.createObjectURL(blob);
      a.download = 'gravit-memory.json';
      a.click();
      win.URL.revokeObjectURL(a.href);
    },
    // the director
    director: el => {
      const k = el.dataset.key;
      const s = store.get();
      const convId = currentConversation(s)?.id ?? s.conversations[0]?.id;
      if (k === 'reset') return reset();
      if (k === 'breaking') return showBreaking(store, timers, director.breaking(now()), now);
      if (k === 'call') return store.dispatch('incomingCall', director.call());
      if (convId) store.dispatch('append', { convId, msg: director[k](now()), at: now() });
    },
  };

  root.addEventListener('click', ev => {
    const el = ev.target.closest('[data-action]');
    if (!el || el.tagName === 'FORM' || el.tagName === 'INPUT') return;
    const fn = actions[el.dataset.action];
    if (!fn) return;
    if (el.tagName === 'A' && el.dataset.action !== 'open' && el.dataset.action !== 'dismissBanner') return;
    if (el.tagName === 'A') { ev.preventDefault(); }
    fn(el);
  });

  root.addEventListener('submit', ev => {
    const form = ev.target.closest('form[data-action]');
    if (!form) return;
    ev.preventDefault();
    const action = form.dataset.action;
    if (action === 'send') {
      const text = composerText.trim();
      if (!text) return;
      const before = store.get();
      const after = store.dispatch('send', { text, now: now() });
      if (after === before) return;
      composerText = '';
      const convId = after.route.id;
      if (after.route.id !== before.route.id) win.location.hash = toHash(after.route);
      reply(convId, text);
    } else if (action === 'publish') {
      const f = new win.FormData(form);
      form.reset();
      store.dispatch('publish', { manifest: { name: f.get('name'), blurb: f.get('blurb'), kind: f.get('kind'), tools: f.get('tools'), needs: f.get('needs') === '没有' ? '没有。' : `你的${f.get('needs')}。`, visibility: f.get('visibility') }, now: now() });
    } else if (action === 'addMemory') {
      const f = new win.FormData(form);
      form.reset();
      store.dispatch('addMemory', { text: f.get('text'), now: now() });
    }
  });

  // typing: the composer keeps its words outside the store; the title and the search go through it.
  // While an IME is composing (pinyin), nothing is dispatched: a re-render would break the composition.
  function typed(el) {
    if (el.id === 'say') composerText = el.value;
    else if (el.id === 'up-name') syncIcon();
    else if (el.dataset.action === 'draftTitle') store.dispatch('setDraftTitle', el.value);
    else if (el.dataset.action === 'query') store.dispatch('setQuery', el.value);
  }
  root.addEventListener('input', ev => { if (!ev.isComposing) typed(ev.target); });
  root.addEventListener('compositionend', ev => typed(ev.target));

  doc.addEventListener('keydown', ev => {
    if (ev.key === 'Escape') {
      const s = store.get();
      if (s.call) return;
      if (s.discover.drawer || s.discover.upload || s.discover.asking) store.dispatch('closeDrawer');
      else if (s.detailsOpen) store.dispatch('toggleDetails');
      else if (s.settingsOpen) store.dispatch('closeSettings');
      else if (directorOpen) { directorOpen = false; render(); }
      return;
    }
    // a card is a div with role=button: Enter and Space press it, as they would a real button
    const a = doc.activeElement;
    if ((ev.key === 'Enter' || ev.key === ' ') && a?.getAttribute('role') === 'button' && actions[a.dataset.action]) {
      ev.preventDefault();
      actions[a.dataset.action](a);
      return;
    }
    const typing = ['INPUT', 'TEXTAREA'].includes(doc.activeElement?.tagName);
    if (ev.key === 'd' && !typing && !ev.metaKey && !ev.ctrlKey) { directorOpen = !directorOpen; render(); }
  });

  win.addEventListener('hashchange', follow);
  store.subscribe(render);
  applyTheme(store.get().theme);
  if (!win.location.hash) win.history.replaceState(null, '', toHash(store.get().route));
  follow();
  render();
  return store;
}

if (typeof window !== 'undefined' && window.document) boot(window);
