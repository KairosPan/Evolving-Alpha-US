// gravit-ui/js/app.js — boot: the store, the hash router, one render per change, event delegation on data-action, the driver's timers, the director
import { createStore } from './store.js';
import { reducers } from './reducers/index.js';
import { seed, firstRun, SEED_VERSION } from './data/seed.js';
import { parseHash, toHash } from './router.js';
import { renderRail } from './render/rail.js';
import { renderMessagesScreen, renderBanner, renderCall, renderMail, renderStub, currentConversation } from './render/messages.js';
import { renderDiscover } from './render/discover.js';
import { renderAccount } from './render/account.js';
import { replyTo, followUp, director, toolsFor } from './driver.js';

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
const TOAST_MS = 6000;
const REVOKE_MS = 1000;
const CONNECT_MS = 1200;
const LISTEN_MS = 1800;
const PICKUP_MS = 1500;
// what the scripted mic hears, in turn
const HEARD = ['小仓位买 BTC，$70k 以下', 'Pelosi 最近买了什么', '查一下这个地址是不是骗子', '额度改到每单 $50'];
const usable = saved => !!saved && saved.v === SEED_VERSION && Array.isArray(saved.conversations);

// a banner, a ringing call, an open drawer, a trash-key ask and a toast belong to their moment: a reload starts without them
const withoutMoments = s => ({
  ...s, banner: null, call: null, edit: null, confirm: null,
  discover: { ...s.discover, drawer: null, create: null, toast: null },
  compose: { files: [], listening: false },
  mail: s.mail ? { ...s.mail, open: false, reading: null } : s.mail,
  account: { ...s.account, panel: null, connecting: null, copied: false, panelError: null },
});

export function initialState(storage, now = Date.now()) {
  try {
    const raw = storage?.getItem(KEY);
    const saved = raw ? JSON.parse(raw) : null;
    if (usable(saved)) return withoutMoments(saved);
  } catch { /* fall through to the seed */ }
  return seed(now);
}

// the store boot uses: initialState already read and cleaned the save, so the store itself loads nothing (Review Focus 2)
export function makeStore(storage, now = Date.now()) {
  // what is saved never holds a moment's overlay, and so never the connector's typed key or secret
  return createStore({ initial: initialState(storage, now), reducers, storage, key: KEY, accept: () => false, persist: withoutMoments });
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

// what the driver needs to know about a conversation: who is in it, which plugin it teaches, its real limit
const context = (store, conv, now) => ({
  installed: store.get().plugins.installed, now: now(), limit: conv?.intent.limit ?? null,
  conv: conv ? { kind: conv.kind, members: conv.members, teach: conv.teach ?? null } : null,
});

// answer a card once; the follow-up is scheduled only for the first answer (Review Focus 4)
export function answerFlow(store, timers, { conv, msg, answer }, now = () => Date.now(), schedule = scheduleEvents) {
  const c = store.get().conversations.find(x => x.id === conv);
  const before = c?.messages.find(m => m.id === msg);
  if (!before || before.answer) return;
  const pending = c.messages.filter(m => m.kind === 'install' && !m.answer).map(m => m.data.plugin);
  const events = followUp(before, answer, { ...context(store, c, now), pending });
  store.dispatch('answer', { convId: conv, msgId: msg, answer, now: now() });
  schedule(store, timers, conv, events, now);
}

// the scripted reply to what the owner just sent into a conversation
export function replyFlow(store, timers, convId, text, now = () => Date.now(), schedule = scheduleEvents, files = []) {
  const c = store.get().conversations.find(x => x.id === convId);
  schedule(store, timers, convId, replyTo(text, { ...context(store, c, now), files }), now);
}

// a toast leaves by itself after a while; a newer toast keeps its own time
export function watchToast(store, timers, ms = TOAST_MS) {
  let last = store.get().discover.toast;
  return store.subscribe(s => {
    const t = s.discover.toast;
    if (t && t !== last) timers.after(ms, () => { if (store.get().discover.toast === t) store.dispatch('dismissToast'); });
    last = t;
  });
}

const DIRECTOR = [['早报', 'brief'], ['技术分析', 'ta'], ['突发', 'breaking'], ['来电', 'call'], ['bot 插话', 'bot'], ['拒单', 'refusal'], ['收尾', 'done'], ['空白开始', 'firstRun'], ['重置 demo', 'reset']];

// a key that finds "the same control" after a re-render: its id, or its data-* attributes
const FOCUS_ATTRS = ['action', 'id', 'conv', 'msg', 'key', 'value', 'answer', 'accept', 'plugin'];
function focusKey(el) {
  if (!el || el.tagName === 'BODY') return null;
  if (el.id) return { id: el.id };
  if (!el.dataset?.action) return null;
  return { sel: FOCUS_ATTRS.filter(a => el.dataset[a] != null).map(a => `[data-${a}="${String(el.dataset[a]).replace(/"/g, '\\"')}"]`).join('') };
}

// which overlay is up: focus moves into it when it opens and back to its opener when it closes
const overlayOf = s => (s.call ? 'call' : s.discover.create ? 'modal' : s.mail?.open || s.detailsOpen || s.settingsOpen || s.discover.drawer ? 'drawer' : null);
const screenOf = s => `${s.route.screen}/${s.route.id ?? s.route.tab ?? ''}`;
const drawerOf = s => (s.mail?.open ? `mail:${s.mail.reading ?? ''}` : null) ?? s.discover.drawer ?? (s.detailsOpen ? 'details' : s.settingsOpen ? 'settings' : null);

export function boot(win) {
  const doc = win.document;
  const storage = (() => { try { return win.localStorage; } catch { return null; } })();
  const store = makeStore(storage);
  const timers = new Timers();
  const root = doc.getElementById('app');
  const now = () => Date.now();
  let directorOpen = false;
  let composerText = '';
  let composing = false;
  let heard = 0;
  let ticking = false;
  let pending = false;
  let last = { overlay: null, opener: null, screen: null, drawer: null, thread: null };

  function applyTheme(theme) {
    if (theme === 'cream' || theme === 'black') doc.documentElement.dataset.theme = theme; else delete doc.documentElement.dataset.theme;
    try { if (theme === 'cream' || theme === 'black') storage?.setItem('gravit-ui.theme', theme); else storage?.removeItem('gravit-ui.theme'); } catch { /* ignore */ }
  }

  function find(key) {
    if (!key) return null;
    return key.id ? doc.getElementById(key.id) : root.querySelector(key.sel);
  }

  function render() {
    const s = store.get();
    // what the person had: focus and caret, typed text, picked radios, and where each scrolling box stood
    const active = doc.activeElement;
    const activeKey = focusKey(active);
    const caret = active && typeof active.selectionStart === 'number' && active.id ? [active.selectionStart, active.selectionEnd] : null;
    const typed = new Map([...root.querySelectorAll('input[id]:not([type=radio]), textarea[id]')].map(el => [el.id, el.value]));
    const thread0 = doc.getElementById('thread');
    const threadAt = thread0 ? { top: thread0.scrollTop, bottom: thread0.scrollHeight - thread0.scrollTop - thread0.clientHeight < 40 } : null;
    const scrolls = { main: root.querySelector('main')?.scrollTop, rows: root.querySelector('.rail-rows')?.scrollTop, drawer: root.querySelector('.drawer-body')?.scrollTop, shelves: [...root.querySelectorAll('.shelf-row')].map(e => e.scrollLeft) };

    const screen = s.route.screen === 'discover' ? renderDiscover(s) : s.route.screen === 'account' ? renderAccount(s) : (s.route.screen === 'markets' || s.route.screen === 'trade') ? renderStub(s.route) : renderMessagesScreen(s, now());
    const overlays = (s.banner ? renderBanner(s.banner, s) : '') + renderMail(s, now()) + (s.call ? renderCall(s.call, now()) : '') +
      (directorOpen ? `<div class="director" role="menu">${DIRECTOR.map(([l, k]) => `<button type="button" class="director-key" data-action="director" data-key="${k}">${l}</button>`).join('')}</div>` : '');
    root.innerHTML = renderRail(s, now()) + screen + overlays;

    for (const [id, value] of typed) { const el = doc.getElementById(id); if (el && id !== 'say') el.value = value; }
    const say = doc.getElementById('say');
    if (say) say.value = composerText;

    // scroll: the rail rows always keep theirs; the page and the shelves keep theirs on the same screen; a drawer while it stays the same drawer
    const sameScreen = last.screen === screenOf(s);
    const rows = root.querySelector('.rail-rows');
    if (rows && scrolls.rows != null) rows.scrollTop = scrolls.rows;
    const main = root.querySelector('main');
    if (main && sameScreen && scrolls.main != null) main.scrollTop = scrolls.main;
    if (sameScreen) [...root.querySelectorAll('.shelf-row')].forEach((e, i) => { if (scrolls.shelves[i] != null) e.scrollLeft = scrolls.shelves[i]; });
    const drawerBody = root.querySelector('.drawer-body');
    if (drawerBody && last.drawer && last.drawer === drawerOf(s) && scrolls.drawer != null) drawerBody.scrollTop = scrolls.drawer;
    // the thread stays where the person was reading, unless it is another conversation, it gained a message, or they were at the bottom
    const open = s.route.screen === 'messages' ? currentConversation(s) : null;
    const threadSig = open ? `${open.id}:${open.messages.length}` : null;
    const thread = doc.getElementById('thread');
    if (thread) thread.scrollTop = threadAt && !threadAt.bottom && threadSig === last.thread ? threadAt.top : thread.scrollHeight;

    // focus: back on the same control; into an overlay that just opened; back to its opener when it closes
    const overlay = overlayOf(s);
    let opener = last.opener;
    let target = find(activeKey);
    if (overlay && overlay !== last.overlay) {
      opener = activeKey;
      target = overlay === 'call' ? root.querySelector('.call [data-accept="0"]') ?? root.querySelector('.call [data-action="hangUp"]') : overlay === 'modal' ? doc.getElementById('mcp-name') : root.querySelector('.drawer .close-key');
    } else if (!overlay && last.overlay) {
      target = find(last.opener) ?? target;
      opener = null;
    } else if (s.edit && s.edit !== last.edit) {
      target = root.querySelector('.inline-edit [name]') ?? target; // an editor that just opened takes focus
    } else if (!target && activeKey) {
      target = say; // the pressed control went away, as an answered card's keys do: the composer is next
    }
    if (target) {
      target.focus();
      if (caret && target === find(activeKey) && typeof target.setSelectionRange === 'function') target.setSelectionRange(caret[0], caret[1]);
    }
    last = { overlay, opener, screen: screenOf(s), drawer: drawerOf(s), thread: threadSig, edit: s.edit };
    // a live call re-renders each second, for its timer
    if (s.call?.status === 'live' && !ticking) {
      ticking = true;
      timers.after(1000, () => { ticking = false; if (store.get().call?.status === 'live') render(); });
    }
  }

  // while an IME composes (pinyin), a render would replace the input and lose the composition: hold it until compositionend
  function requestRender() {
    if (composing) { pending = true; return; }
    render();
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

  function restart(state, route) {
    timers.clear();
    store.reset(state);
    applyTheme(store.get().theme);
    composerText = '';
    go(route);
  }
  const reset = () => restart(seed(now()), { screen: 'messages', id: 'c-1' });

  // the scripted mic: what it heard joins what is already in the composer
  function stopMic() {
    if (!store.get().compose.listening) return;
    const words = HEARD[heard++ % HEARD.length];
    composerText = composerText.trim() ? `${composerText.trim()} ${words}` : words;
    store.dispatch('setListening', false);
  }

  // commit the open editor with what its inputs hold
  function commitEdit() {
    const values = Object.fromEntries([...root.querySelectorAll('.inline-edit [name]')].map(el => [el.name, el.value]));
    store.dispatch('commitEdit', { values, now: now() });
  }

  // the second press of a two-step confirm
  function confirmYes() {
    const c = store.get().confirm;
    if (!c) return;
    store.dispatch('cancelConfirm');
    if (c.action === 'withdraw') store.dispatch('withdraw', { convId: c.id, now: now() });
    else if (c.action === 'stopGravit') store.dispatch('stopGravit', { convId: c.id, now: now() });
    else if (c.action === 'endLimit') store.dispatch('endLimit', { convId: c.id });
    else if (c.action === 'forgetAll') store.dispatch('forgetAll');
    else if (c.action === 'resetDemo') reset();
  }

  const actions = {
    open: el => go({ screen: 'messages', id: el.dataset.id }),
    startDraft: () => { store.dispatch('startDraft', { now: now() }); go({ screen: 'messages', id: 'new' }); },
    cancelDraft: () => { store.dispatch('cancelDraft'); go(store.get().route); },
    toggleRail: () => store.dispatch('toggleRail'),
    toggleDraftAttach: () => store.dispatch('toggleDraftAttach'),
    toggleDraftGroup: () => store.dispatch('toggleDraftGroup'),
    toggleDraftPicker: () => store.dispatch('toggleDraftPicker'),
    toggleDraftBot: el => store.dispatch('toggleDraftBot', el.dataset.id),
    // inline editors (they replaced prompt): a button starts one, ✓ or Enter commits it, × or Escape cancels it
    draftLimit: el => store.dispatch('startEdit', { kind: 'draftLimit', key: el.dataset.key }),
    changeWords: el => store.dispatch('startEdit', { kind: 'rename', convId: el.dataset.conv }),
    changeLimit: el => store.dispatch('startEdit', { kind: 'limit', convId: el.dataset.conv }),
    topUp: () => store.dispatch('startEdit', { kind: 'wallet', dir: 'in' }),
    takeBack: () => store.dispatch('startEdit', { kind: 'wallet', dir: 'out' }),
    editMemory: el => store.dispatch('startEdit', { kind: 'memory', id: el.dataset.id }),
    commitEdit: () => commitEdit(),
    // the composer: + opens the hidden file input; the mic listens a moment, then writes what it heard
    pickFile: () => doc.getElementById('attach-input')?.click(),
    removeFile: el => store.dispatch('removeFile', Number(el.dataset.id)),
    toggleMic: () => {
      if (store.get().compose.listening) return stopMic();
      store.dispatch('setListening', true);
      timers.after(LISTEN_MS, stopMic);
    },
    cancelEdit: () => store.dispatch('cancelEdit'),
    // two-step confirms (they replaced confirm): the first press asks in place, the second acts
    withdraw: el => store.dispatch('askConfirm', { action: 'withdraw', id: el.dataset.conv }),
    endLimit: el => store.dispatch('askConfirm', { action: 'endLimit', id: el.dataset.conv }),
    stopGravit: el => store.dispatch('askConfirm', { action: 'stopGravit', id: el.dataset.conv }),
    forgetAll: () => store.dispatch('askConfirm', { action: 'forgetAll' }),
    resetDemo: () => store.dispatch('askConfirm', { action: 'resetDemo' }),
    confirmYes: () => confirmYes(),
    cancelConfirm: () => store.dispatch('cancelConfirm'),
    suggest: el => { composerText = el.dataset.text; render(); doc.getElementById('say')?.focus(); },
    answer: el => answerFlow(store, timers, el.dataset, now),
    // + on an install request opens the plugin's drawer; the request is answered when the install happens (reducers/discover.js)
    installAsk: el => {
      store.dispatch('openPlugin', el.dataset.plugin);
      go({ screen: 'discover', id: null });
    },
    toggleDetails: () => store.dispatch('toggleDetails'),
    setMode: el => store.dispatch('setMode', el.dataset.value === 'Beast' ? 'beast' : 'guard'),
    // the banner's link dismisses it and still goes to the thread it names
    dismissBanner: el => { store.dispatch('dismissBanner', { now: now() }); if (el.tagName === 'A') go(parseHash(el.getAttribute('href'))); },
    answerCall: el => store.dispatch('answerCall', { accept: el.dataset.accept === '1', now: now() }),
    // the rail's phone key rings Gravit; it picks up a moment later
    phoneCall: () => {
      if (store.get().call) return;
      store.dispatch('startCall', { now: now() });
      timers.after(PICKUP_MS, () => store.dispatch('connectCall', { now: now() }));
    },
    hangUp: () => store.dispatch('hangUp', { now: now() }),
    toggleMute: () => store.dispatch('toggleMute'),
    // the rail's mail key: Gravit's own mailbox
    openMail: () => store.dispatch('openMail'),
    closeMail: () => store.dispatch('closeMail'),
    readMail: el => store.dispatch('readMail', el.dataset.id),
    backToInbox: () => store.dispatch('backToInbox'),
    // Discover
    openPlugin: el => store.dispatch('openPlugin', el.dataset.id),
    closeDrawer: () => store.dispatch('closeDrawer'),
    install: el => store.dispatch('install', { id: el.dataset.id, now: now() }),
    uninstall: el => store.dispatch('uninstall', el.dataset.id),
    toggleInstalledOnly: () => store.dispatch('toggleInstalledOnly'),
    // Create: the MCP connector
    openCreate: () => store.dispatch('openCreate'),
    closeCreate: () => store.dispatch('closeCreate'),
    cycleCreateIcon: () => store.dispatch('cycleCreateIcon'),
    backToForm: () => store.dispatch('backToForm'),
    addMcp: () => store.dispatch('addMcp', { now: now() }),
    dismissToast: () => store.dispatch('dismissToast'),
    // Account
    openSettings: () => store.dispatch('openSettings'),
    closeSettings: () => store.dispatch('closeSettings'),
    setTheme: el => { const t = el.dataset.value.toLowerCase(); store.dispatch('setTheme', t); applyTheme(t); },
    forgetMemory: el => store.dispatch('forgetMemory', el.dataset.id),
    memorySwitch: el => store.dispatch('setMemorySwitch', { key: el.dataset.key, value: el.getAttribute('aria-checked') !== 'true' }),
    exportMemory: () => {
      const blob = new win.Blob([JSON.stringify(store.get().memory, null, 2)], { type: 'application/json' });
      const a = doc.createElement('a');
      const href = win.URL.createObjectURL(blob);
      a.href = href;
      a.download = 'gravit-memory.json';
      doc.body?.appendChild(a);
      a.click();
      a.remove?.();
      // Safari and Firefox start the download after the click returns: revoke the link a moment later
      setTimeout(() => win.URL.revokeObjectURL(href), REVOKE_MS);
    },
    // the director
    director: el => {
      const k = el.dataset.key;
      const s = store.get();
      const convId = currentConversation(s)?.id ?? s.conversations[0]?.id;
      if (k === 'reset') return reset();
      if (k === 'firstRun') return restart(firstRun(now()), { screen: 'messages', id: null });
      if (k === 'breaking') return showBreaking(store, timers, director.breaking(now()), now);
      if (k === 'call') return store.dispatch('incomingCall', director.call());
      if (convId && director[k]) store.dispatch('append', { convId, msg: director[k](now()), at: now() });
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
      const files = store.get().compose.files.map(x => x.name);
      if (!text && !files.length) return;
      const before = store.get();
      // empty the composer before the render the send causes, so the box is clear the moment the bubble appears
      composerText = '';
      const after = store.dispatch('send', { text, now: now() });
      if (after === before) { composerText = text; return; }
      if (after.route.id !== before.route.id) win.location.hash = toHash(after.route);
      replyFlow(store, timers, after.route.id, text, now, scheduleEvents, files);
    } else if (action === 'connectMcp') {
      // the scripted server answers a moment later with its tools; a closed or restarted connector ignores the answer
      store.dispatch('connectMcp');
      const c = store.get().discover.create;
      if (c?.step === 'connecting') timers.after(CONNECT_MS, () => store.dispatch('mcpConnected', { tools: toolsFor(c.form.name, c.form.url) }));
    } else if (action === 'addMemory') {
      const f = new win.FormData(form);
      form.reset();
      store.dispatch('addMemory', { text: f.get('text'), now: now() });
    }
  });

  // typing: the composer keeps its words outside the store; the title and the search go through it
  function typed(el) {
    if (el.id === 'say') composerText = el.value;
    else if (el.dataset?.action === 'mcpField' && el.type !== 'radio') store.dispatch('setCreateField', { key: el.name, value: el.value });
    else if (el.dataset?.action === 'draftTitle') store.dispatch('setDraftTitle', el.value);
    else if (el.dataset?.action === 'query') store.dispatch('setQuery', el.value);
  }
  root.addEventListener('input', ev => { if (!ev.isComposing && !composing) typed(ev.target); });
  // radios and checkboxes report on change: the connector's auth, kind and visibility, and its tool checks
  root.addEventListener('change', ev => {
    const el = ev.target;
    if (el.id === 'attach-input') {
      store.dispatch('addFiles', [...(el.files ?? [])].map(x => ({ name: x.name, size: x.size })));
      el.value = '';
    } else if (el.type === 'radio' && el.dataset?.action === 'mcpField') store.dispatch('setCreateField', { key: el.name, value: el.value });
    else if (el.type === 'checkbox' && el.dataset?.action === 'toggleMcpTool') store.dispatch('toggleMcpTool', Number(el.dataset.id));
  });
  root.addEventListener('compositionstart', () => { composing = true; });
  root.addEventListener('compositionend', ev => {
    composing = false;
    const before = store.get();
    typed(ev.target);
    // run the held render, unless the typed text just caused one
    if (pending && store.get() === before) render();
    pending = false;
  });

  doc.addEventListener('keydown', ev => {
    if (ev.key === 'Escape') {
      const s = store.get();
      if (s.call) return;
      if (s.edit) { store.dispatch('cancelEdit'); return; }
      if (s.mail?.open) { store.dispatch('closeMail'); return; }
      if (s.confirm) { store.dispatch('cancelConfirm'); return; }
      if (s.discover.create) store.dispatch('closeCreate');
      else if (s.discover.drawer) store.dispatch('closeDrawer');
      else if (s.detailsOpen) store.dispatch('toggleDetails');
      else if (s.settingsOpen) store.dispatch('closeSettings');
      else if (directorOpen) { directorOpen = false; render(); }
      return;
    }
    const a = doc.activeElement;
    if (ev.key === 'Enter' && store.get().edit && a?.closest?.('.inline-edit')) { ev.preventDefault(); commitEdit(); return; }
    // a card is a div with role=button: Enter and Space press it, as they would a real button
    if ((ev.key === 'Enter' || ev.key === ' ') && a?.getAttribute?.('role') === 'button' && actions[a.dataset.action]) {
      ev.preventDefault();
      actions[a.dataset.action](a);
      return;
    }
    const typing = ['INPUT', 'TEXTAREA'].includes(doc.activeElement?.tagName);
    if (ev.key === 'd' && !typing && !ev.metaKey && !ev.ctrlKey) { directorOpen = !directorOpen; render(); }
  });

  win.addEventListener('hashchange', follow);
  store.subscribe(requestRender);
  watchToast(store, timers);
  applyTheme(store.get().theme);
  if (!win.location.hash) win.history.replaceState(null, '', toHash(store.get().route));
  follow();
  render();
  return Object.assign(store, { timers });
}

if (typeof window !== 'undefined' && window.document) boot(window);
