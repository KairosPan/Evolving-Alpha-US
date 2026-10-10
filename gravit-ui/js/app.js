// gravit-ui/js/app.js — boot: the store, the hash router, one render per change, event delegation on data-action, the driver's timers, the director
import { createStore } from './store.js';
import { reducers } from './reducers/index.js';
import { seed, firstRun, SEED_VERSION } from './data/seed.js';
import { parseHash, toHash } from './router.js';
import { renderRail } from './render/rail.js';
import { renderMessagesScreen, renderBanner, renderCall, currentConversation } from './render/messages.js';
import { renderMarkets } from './render/markets.js';
import { renderTrade } from './render/trade.js';
import { QUOTE_MS } from './data/markets.js';
import { closeIn, leftWords } from './market-fmt.js';
import { handOver } from './trade.js';
import { VENUES } from './data/seed.js';
import { renderMailScreen } from './render/mail.js';
import { renderDiscover } from './render/discover.js';
import { renderAccount } from './render/account.js';
import { replyTo, followUp, director, nextUpload } from './driver.js';
import { SHOP_MCP } from './data/plugins.js';
import { fmtDuration } from './time.js';

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
const COPIED_MS = 1500;
// the scripted client on Discover's MCP face: it connects, then asks shop.publish a moment later
const CLIENT_CONNECT_MS = 1500;
const CLIENT_PUBLISH_MS = 1500;
// a stand-in venue answers a signed order a moment later; countdowns tick each second
const FILL_MS = 900;
const CLOCK_MS = 1000;
// what the scripted mic hears, in turn
const HEARD = ['小仓位买 BTC，$70k 以下', 'Pelosi 最近买了什么', '查一下这个地址是不是骗子', '额度改到每单 $50'];
const usable = saved => !!saved && saved.v === SEED_VERSION && Array.isArray(saved.conversations);

// a banner, a ringing call, an open drawer, a trash-key ask and a toast belong to their moment: a reload starts without them
const withoutMoments = s => ({
  ...s, banner: null, call: null, edit: null, confirm: null,
  discover: { ...s.discover, drawer: null, create: null, toast: null },
  compose: { files: [], listening: false },
  account: { ...s.account, panel: null, connecting: null, copied: false, panelError: null },
  trade: s.trade ? { ...s.trade, ticket: null } : s.trade,
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

// Sign and place: the order goes to the stand-in venue, which answers once, a moment later
export function placeFlow(store, timers, now = () => Date.now(), ms = FILL_MS) {
  const before = store.get().trade.ticket?.placing;
  store.dispatch('placeOrder', { now: now() });
  const id = store.get().trade.ticket?.placing;
  if (id && id !== before) timers.after(ms, () => store.dispatch('settleOrder', { id, now: now() }));
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

const DIRECTOR = [['早报', 'brief'], ['技术分析', 'ta'], ['突发', 'breaking'], ['来电', 'call'], ['bot 插话', 'bot'], ['拒单', 'refusal'], ['收尾', 'done'], ['插件上传', 'upload'], ['空白开始', 'firstRun'], ['重置 demo', 'reset']];

// a key that finds "the same control" after a re-render: its id, or every data-* attribute it carries
function focusKey(el) {
  if (!el || el.tagName === 'BODY') return null;
  if (el.id) return { id: el.id };
  if (!el.dataset?.action) return null;
  const q = v => String(v).replace(/"/g, '\\"');
  // controls that share an action (the connector's fields, its radios) are told apart by their name, and a radio or checkbox by its value
  const own = [el.name ? `[name="${q(el.name)}"]` : '', el.type === 'radio' || el.type === 'checkbox' ? `[value="${q(el.value)}"]` : ''].join('');
  const data = Object.entries(el.dataset).map(([k, v]) => `[data-${k.replace(/[A-Z]/g, c => '-' + c.toLowerCase())}="${q(v)}"]`).join('');
  return { sel: data + own };
}

// which overlay is up: focus moves into it when it opens and back to its opener when it closes
// a market's drawer is its route (#/markets/<id>)
const marketDrawer = s => s.route.screen === 'markets' && !!s.route.id;
const overlayOf = s => (s.call ? 'call' : s.discover.create ? 'modal' : s.account.panel || s.detailsOpen || s.settingsOpen || s.discover.drawer || marketDrawer(s) ? 'drawer' : null);
// Markets keeps its scroll while a drawer opens and closes over it
const screenOf = s => (s.route.screen === 'markets' ? 'markets/' : `${s.route.screen}/${s.route.id ?? s.route.tab ?? ''}`);
// which editor is open, by what it edits (its error may change; the editor stays the same)
const editorOf = e => (e ? [e.kind, e.key, e.convId, e.id, e.dir].join('|') : null);
// which dialog step is up: its body keeps its scroll only while the step stays the same
const dialogOf = s => (s.discover.create ? `${s.discover.create.run}:${s.discover.create.step}` : null);
const drawerOf = s => (s.account.panel ? `panel:${s.account.panel}` : null) ?? s.discover.drawer ?? (s.detailsOpen ? 'details' : s.settingsOpen ? 'settings' : null) ?? (marketDrawer(s) ? `market:${s.route.id}` : null);

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
  let clocking = false;
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
    // typed text only: a file input refuses a path written back, and radios and checkboxes carry state, not text
    const typed = new Map([...root.querySelectorAll('input[id]:not([type=radio]):not([type=checkbox]):not([type=file]), textarea[id], select[id]')].map(el => [el.id, el.value]));
    const thread0 = doc.getElementById('thread');
    const threadAt = thread0 ? { top: thread0.scrollTop, bottom: thread0.scrollHeight - thread0.scrollTop - thread0.clientHeight < 40 } : null;
    const scrolls = { main: root.querySelector('main')?.scrollTop, rows: root.querySelector('.rail-rows')?.scrollTop, drawer: root.querySelector('.drawer-body')?.scrollTop, dialog: root.querySelector('.modal-body')?.scrollTop, shelves: [...root.querySelectorAll('.shelf-row')].map(e => e.scrollLeft) };

    const screen = s.route.screen === 'discover' ? renderDiscover(s) : s.route.screen === 'account' ? renderAccount(s) : s.route.screen === 'mail' ? renderMailScreen(s, now())
      : s.route.screen === 'markets' ? renderMarkets(s, now()) : s.route.screen === 'trade' ? renderTrade(s, now()) : renderMessagesScreen(s, now());
    const overlays = (s.banner ? renderBanner(s.banner, s) : '') + (s.call ? renderCall(s.call, now()) : '') +
      (directorOpen ? `<div class="director" role="menu">${DIRECTOR.map(([l, k]) => `<button type="button" class="director-key" data-action="director" data-key="${k}">${l}</button>`).join('')}</div>` : '');
    root.innerHTML = renderRail(s, now()) + screen + overlays;

    const sameEditor = editorOf(s.edit) === last.editor;
    for (const [id, value] of typed) {
      const el = doc.getElementById(id);
      // an editor's box (edit-*) keeps what was typed only while the same editor stays open
      if (el && id !== 'say' && (sameEditor || !id.startsWith('edit-'))) el.value = value;
    }
    const say = doc.getElementById('say');
    if (say) say.value = composerText;
    // the search box says what the store searches: Publish and 插件上传 clear it
    const dq = doc.getElementById('dq');
    if (dq) dq.value = s.discover.query;
    // Markets' and Trade's boxes say what the store holds, so a fill clears the amount it used
    const mq = doc.getElementById('mq');
    if (mq) mq.value = s.markets.q;
    const tq = doc.getElementById('tq');
    if (tq) tq.value = s.trade.q;
    const tk = s.trade.ticket;
    if (tk) for (const [id, v] of [['tk-amount', tk.amount], ['tk-unit', tk.unit], ['tk-type', tk.orderType], ['tk-limit', tk.limit]]) { const el = doc.getElementById(id); if (el) el.value = v; }

    // scroll: the second level keeps its rows while it lists the same thing (conversations or letters); the page and the shelves keep theirs
    // on the same screen; a drawer while it stays the same drawer
    const sameScreen = last.screen === screenOf(s);
    const rows = root.querySelector('.rail-rows');
    if (rows && scrolls.rows != null && last.screen?.split('/')[0] === s.route.screen) rows.scrollTop = scrolls.rows;
    const main = root.querySelector('main');
    if (main && sameScreen && scrolls.main != null) main.scrollTop = scrolls.main;
    if (sameScreen) [...root.querySelectorAll('.shelf-row')].forEach((e, i) => { if (scrolls.shelves[i] != null) e.scrollLeft = scrolls.shelves[i]; });
    const drawerBody = root.querySelector('.drawer-body');
    if (drawerBody && last.drawer && last.drawer === drawerOf(s) && scrolls.drawer != null) drawerBody.scrollTop = scrolls.drawer;
    const dialogBody = root.querySelector('.modal-body');
    if (dialogBody && last.dialog && last.dialog === dialogOf(s) && scrolls.dialog != null) dialogBody.scrollTop = scrolls.dialog;
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
      target = overlay === 'call' ? root.querySelector('.call [data-accept="0"]') ?? root.querySelector('.call [data-action="hangUp"]') : overlay === 'modal' ? doc.getElementById('mcp-copy') ?? root.querySelector('.modal .close-key') : root.querySelector('.drawer .close-key');
    } else if (!overlay && last.overlay) {
      target = find(last.opener) ?? target;
      opener = null;
    } else if (s.edit && editorOf(s.edit) !== last.editor) {
      target = root.querySelector('.inline-edit [name]') ?? target; // an editor that just opened takes focus
    } else if (s.confirm && s.confirm !== last.confirm) {
      target = root.querySelector('.confirm [data-action="confirmYes"]') ?? target; // a confirm that just asked takes focus
    } else if (!target && activeKey) {
      // the pressed control went away (an answered card's keys, a read mail row): stay inside the overlay if one is up, else the composer
      target = overlay === 'call' ? root.querySelector('.call [data-action="hangUp"]') ?? root.querySelector('.call [data-accept="0"]')
        : overlay === 'modal' ? root.querySelector('.modal .close-key')
          : overlay === 'drawer' ? root.querySelector('.drawer .close-key') : say;
    }
    if (target) {
      target.focus();
      if (caret && target === find(activeKey) && typeof target.setSelectionRange === 'function') target.setSelectionRange(caret[0], caret[1]);
    }
    last = { overlay, opener, screen: screenOf(s), drawer: drawerOf(s), dialog: dialogOf(s), thread: threadSig, editor: editorOf(s.edit), confirm: s.confirm };
    if (s.call?.status === 'live' && !ticking) tick();
    if ((s.route.screen === 'markets' || s.route.screen === 'trade') && !clocking) clock();
  }

  // Markets' and Trade's countdowns: only their text changes; a quote whose ten minutes ran out is prepared again
  function clock() {
    clocking = true;
    timers.after(CLOCK_MS, () => {
      clocking = false;
      const s = store.get();
      if (s.route.screen !== 'markets' && s.route.screen !== 'trade') return;
      const t = now();
      for (const el of root.querySelectorAll('.mk-close[data-close]')) { const w = closeIn(Date.parse(el.dataset.close) - t); if (el.textContent !== w) el.textContent = w; }
      const tk = s.trade.ticket;
      if (tk?.id && tk.preparedAt != null) {
        if (t >= tk.preparedAt + QUOTE_MS) store.dispatch('requote', { now: t });
        else { const el = root.querySelector('[data-left]'); if (el) el.textContent = leftWords(tk.preparedAt + QUOTE_MS - t); }
      }
      clock();
    });
  }

  // a live call's timer: only its text changes each second; the page and the call's keys stay as they are
  function tick() {
    ticking = true;
    timers.after(1000, () => {
      ticking = false;
      const c = store.get().call;
      if (c?.status !== 'live') return;
      const el = root.querySelector('.call-timer');
      if (el) el.textContent = fmtDuration(now() - c.since);
      tick();
    });
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

  // save a file the page made: Safari and Firefox start the download after the click returns, so the link is revoked a moment later
  function download(name, type, text) {
    const blob = new win.Blob([text], { type });
    const a = doc.createElement('a');
    const href = win.URL.createObjectURL(blob);
    a.href = href;
    a.download = name;
    doc.body?.appendChild(a);
    a.click();
    a.remove?.();
    setTimeout(() => win.URL.revokeObjectURL(href), REVOKE_MS);
  }

  // the scripted client on Discover's MCP face: it connects a moment after its line is used, calls shop.mine, then asks shop.publish
  function runClient() {
    const c = store.get().discover.create;
    if (!c || c.step !== 'wait' || c.started) return;
    const { run } = c;
    store.dispatch('startClient', { run });
    timers.after(CLIENT_CONNECT_MS, () => store.dispatch('clientConnected', { run }));
    timers.after(CLIENT_CONNECT_MS + CLIENT_PUBLISH_MS, () => store.dispatch('clientPublishes', { run, manifest: nextUpload(store.get().plugins.uploaded) }));
  }

  // a public upload passes review when its time is up; boot picks up the ones a reload left waiting
  function scheduleReview(p) {
    if (!p?.review) return;
    timers.after(Math.max(0, p.review.until - now()), () => store.dispatch('reviewPassed', { id: p.id, now: now() }));
  }

  // the director's 插件上传: Discover on its shelves, Create open, the scripted client started without the clipboard
  function startUpload() {
    directorOpen = false;
    const c = store.get().discover.create;
    // an upload under way is left to finish; a refused one makes way for a fresh one
    if (c && c.step !== 'refused' && (c.step !== 'wait' || c.started)) { render(); return; }
    if (c?.step === 'refused') store.dispatch('closeCreate');
    store.dispatch('nav', { screen: 'discover', id: null });
    go({ screen: 'discover', id: null });
    if (store.get().discover.query) store.dispatch('setQuery', '');
    if (store.get().discover.installedOnly) store.dispatch('toggleInstalledOnly');
    if (!store.get().discover.create) store.dispatch('openCreate');
    runClient();
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
    else if (c.action === 'cancelOrder') store.dispatch('cancelOrder', { id: c.id, now: now() });
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
    // Discover
    openPlugin: el => store.dispatch('openPlugin', el.dataset.id),
    closeDrawer: () => store.dispatch('closeDrawer'),
    install: el => store.dispatch('install', { id: el.dataset.id, now: now() }),
    uninstall: el => store.dispatch('uninstall', el.dataset.id),
    toggleInstalledOnly: () => store.dispatch('toggleInstalledOnly'),
    // Create: Discover's own MCP face; copying a client's line starts the scripted client
    openCreate: () => store.dispatch('openCreate'),
    closeCreate: () => store.dispatch('closeCreate'),
    copyMcp: () => {
      const c = store.get().discover.create;
      if (!c) return;
      try { win.navigator?.clipboard?.writeText(SHOP_MCP.clients[c.client].code)?.catch?.(() => {}); } catch { /* the demo has no clipboard to fail loudly */ }
      store.dispatch('setCreateCopied', true);
      timers.after(COPIED_MS, () => store.dispatch('setCreateCopied', false));
      runClient();
    },
    rejectUpload: () => store.dispatch('rejectUpload'),
    // the owner's signature: the shop takes the plugin, and the page shows the shelves it landed on
    publishUpload: () => {
      const before = store.get().plugins.uploaded.length;
      store.dispatch('publishUpload', { now: now() });
      const s = store.get();
      if (s.plugins.uploaded.length === before) return;
      go({ screen: 'discover', id: null });
      scheduleReview(s.plugins.uploaded.at(-1));
    },
    dismissToast: () => store.dispatch('dismissToast'),
    // Account
    openSettings: () => store.dispatch('openSettings'),
    closeSettings: () => store.dispatch('closeSettings'),
    setTheme: el => { const t = el.dataset.value.toLowerCase(); store.dispatch('setTheme', t); applyTheme(t); },
    forgetMemory: el => store.dispatch('forgetMemory', el.dataset.id),
    memorySwitch: el => store.dispatch('setMemorySwitch', { key: el.dataset.key, value: el.getAttribute('aria-checked') !== 'true' }),
    exportMemory: () => download('gravit-memory.json', 'application/json', JSON.stringify(store.get().memory, null, 2)),
    // Account's panels
    openPanel: el => store.dispatch('openPanel', el.dataset.panel),
    closePanel: () => store.dispatch('closePanel'),
    connectVenue: el => {
      const name = el.dataset.name;
      store.dispatch('connectVenue', name);
      if (store.get().account.connecting === name) timers.after(CONNECT_MS, () => store.dispatch('venueConnected', name));
    },
    copyAddress: () => {
      const w = store.get().account.wallet;
      try { win.navigator?.clipboard?.writeText(w.full ?? w.address); } catch { /* the label still says copied: the demo has no clipboard to fail loudly */ }
      store.dispatch('setCopied', true);
      timers.after(COPIED_MS, () => store.dispatch('setCopied', false));
    },
    exportStatement: () => {
      const rows = store.get().account.activity.map(x => [new Date(x.at).toISOString(), `"${x.text.replace(/"/g, '""')}"`, x.amount].join(','));
      download('gravit-statement.csv', 'text/csv', ['at,what,amount', ...rows].join('\n'));
    },
    // Markets: tabs, sort, the chart interval, the watchlist; a market's drawer is its route
    openMarket: el => go({ screen: 'markets', id: el.dataset.id }),
    closeMarket: () => go({ screen: 'markets', id: null }),
    mkTab: el => store.dispatch('setMarketsTab', el.dataset.value),
    mkSort: el => store.dispatch('setMarketsSort', el.dataset.value),
    mkInterval: el => store.dispatch('setMarketsInterval', el.dataset.value),
    mkClear: () => store.dispatch('setMarketsQuery', ''),
    toggleWatch: el => store.dispatch('toggleWatch', el.dataset.id),
    // Trade: the ticket opened from a row, a drawer or the picker
    tradeFrom: el => {
      store.dispatch('openTicket', { id: el.dataset.id, side: el.dataset.side || 'buy', outcome: Number(el.dataset.outcome || 0), venue: el.dataset.venue || null, now: now() });
      go({ screen: 'trade' });
    },
    pickMarket: el => store.dispatch('openTicket', { id: el.dataset.id, venue: el.dataset.venue || null, now: now() }),
    tradeKind: el => store.dispatch('setTradeKind', el.dataset.value),
    closeTicket: () => store.dispatch('closeTicket'),
    ticketSide: el => store.dispatch('ticketSide', { side: el.dataset.value, now: now() }),
    ticketOutcome: el => store.dispatch('ticketOutcome', { outcome: Number(el.dataset.value), now: now() }),
    ticketVenue: el => store.dispatch('ticketVenue', { venue: el.dataset.venue, now: now() }),
    toggleSigns: () => store.dispatch('toggleSigns'),
    // your own order goes at once; Gravit's asks first
    cancelOrder: el => {
      const o = store.get().account.orders.find(x => x.id === el.dataset.id);
      if (!o) return;
      if (o.by === 'gravit') store.dispatch('askConfirm', { action: 'cancelOrder', id: o.id });
      else store.dispatch('cancelOrder', { id: o.id, now: now() });
    },
    // Hand to Gravit instead: a new message with the ticket in words and the limit chips set where Gravit may trade
    handToGravit: el => {
      const s = store.get();
      const h = handOver(s, el.dataset.id ? { id: el.dataset.id } : s.trade.ticket);
      composerText = h.words;
      store.dispatch('startDraft', { now: now() });
      if (h.venue && VENUES.includes(h.venue)) store.dispatch('setDraftLimit', { key: 'venue', value: h.venue });
      if (h.perOrder) {
        store.dispatch('setDraftLimit', { key: 'perOrder', value: h.perOrder });
        store.dispatch('setDraftLimit', { key: 'total', value: Math.max(100, h.perOrder) });
      }
      if (!h.attach && store.get().draft.attach) store.dispatch('toggleDraftAttach');
      go({ screen: 'messages', id: 'new' });
    },
    openStatement: () => {
      store.dispatch('nav', { screen: 'account', tab: 'portfolio' });
      store.dispatch('openPanel', 'statement');
      go({ screen: 'account', tab: 'portfolio' });
    },
    // the director
    director: el => {
      const k = el.dataset.key;
      const s = store.get();
      const convId = currentConversation(s)?.id ?? s.conversations[0]?.id;
      if (k === 'reset') return reset();
      if (k === 'upload') return startUpload();
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
    } else if (action === 'moveFunds') {
      const f = new win.FormData(form);
      store.dispatch('moveFunds', { from: f.get('from'), to: f.get('to'), asset: f.get('asset'), amount: f.get('amount'), now: now() });
    } else if (action === 'placeOrder') {
      placeFlow(store, timers, now);
    } else if (action === 'addMemory') {
      const f = new win.FormData(form);
      form.reset();
      store.dispatch('addMemory', { text: f.get('text'), now: now() });
    }
  });

  // typing: the composer keeps its words outside the store; the title and the search go through it
  function typed(el) {
    if (el.id === 'say') composerText = el.value;
    else if (el.dataset?.action === 'draftTitle') store.dispatch('setDraftTitle', el.value);
    else if (el.dataset?.action === 'query') store.dispatch('setQuery', el.value);
    else if (el.dataset?.action === 'mkQuery') store.dispatch('setMarketsQuery', el.value);
    else if (el.dataset?.action === 'tradeQuery') store.dispatch('setTradeQuery', el.value);
    else if (el.dataset?.action === 'ticketField' && el.tagName !== 'SELECT') store.dispatch('setTicket', { field: el.name, value: el.value, now: now() });
  }
  root.addEventListener('input', ev => { if (!ev.isComposing && !composing) typed(ev.target); });
  // radios report on change: Create's client and where an upload goes
  root.addEventListener('change', ev => {
    const el = ev.target;
    if (el.id === 'attach-input') {
      // read the picked files, then empty the picker before the render (so the same file can be picked again)
      const files = [...(el.files ?? [])].map(x => ({ name: x.name, size: x.size }));
      el.value = '';
      store.dispatch('addFiles', files);
    } else if (el.type === 'radio' && el.dataset?.action === 'mcpClient') store.dispatch('setClient', el.value);
    else if (el.type === 'radio' && el.dataset?.action === 'uploadVisibility') store.dispatch('setUploadVisibility', el.value);
    else if (el.tagName === 'SELECT' && el.dataset?.action === 'ticketField') store.dispatch('setTicket', { field: el.name, value: el.value, now: now() });
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
      if (s.account.panel) { store.dispatch('closePanel'); return; }
      if (s.confirm) { store.dispatch('cancelConfirm'); return; }
      if (marketDrawer(s)) { go({ screen: 'markets', id: null }); return; }
      if (s.discover.create) store.dispatch('closeCreate');
      else if (s.discover.drawer) store.dispatch('closeDrawer');
      else if (s.detailsOpen) store.dispatch('toggleDetails');
      else if (s.settingsOpen) store.dispatch('closeSettings');
      else if (directorOpen) { directorOpen = false; render(); }
      return;
    }
    const a = doc.activeElement;
    if (ev.key === 'Enter' && !ev.isComposing && ev.keyCode !== 229 && store.get().edit && a?.closest?.('.inline-edit') && a.tagName !== 'BUTTON') { ev.preventDefault(); commitEdit(); return; }
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
  for (const p of store.get().plugins.uploaded) scheduleReview(p);
  // an order a reload interrupted on its way still gets the venue's answer
  for (const o of store.get().account.orders) if (o.status === 'pending') timers.after(FILL_MS, () => store.dispatch('settleOrder', { id: o.id, now: now() }));
  return Object.assign(store, { timers });
}

if (typeof window !== 'undefined' && window.document) boot(window);
