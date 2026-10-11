// gravit-ui/tests/app-dom.test.js — boot() against a fake window: what the person sees after typing, sending, scrolling and pressing keys
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { boot } from '../js/app.js';
import { fakeWindow } from './helpers/fake-dom.js';
import { seed } from '../js/data/seed.js';
import { fromManifest } from '../js/data/plugins.js';
import { nextUpload } from '../js/driver.js';

const sleep = ms => new Promise(r => setTimeout(r, ms));
const send = (f, el) => { const form = { dataset: { action: 'send' } }; f.fire('root', 'submit', { target: { closest: () => form } }); };

test('the composer is empty right after a send', () => {
  const f = fakeWindow();
  const say = f.withId('say', { tagName: 'INPUT' });
  const store = boot(f.win);
  say.value = 'Look at ETH again';
  f.fire('root', 'input', { target: say });
  send(f, say);
  assert.equal(store.get().conversations[0].messages.at(-1).text, 'Look at ETH again');
  assert.equal(say.value, '');
  store.timers.clear();
});

test('nothing re-renders while an IME is composing; the held render runs at compositionend', () => {
  const f = fakeWindow();
  const say = f.withId('say', { tagName: 'INPUT' });
  const store = boot(f.win);
  f.fire('root', 'compositionstart', { target: say });
  const before = f.writes;
  store.dispatch('toggleRail');
  assert.equal(f.writes, before, 'a reply arriving mid-pinyin must not replace the input');
  f.fire('root', 'compositionend', { target: say });
  assert.equal(f.writes, before + 1);
  store.timers.clear();
});

test('a re-render keeps the thread where the person was reading; a new message in it scrolls to the bottom', () => {
  const f = fakeWindow();
  const thread = f.withId('thread');
  const store = boot(f.win);
  thread.scrollTop = 100; // 500 px above the bottom
  store.dispatch('toggleRail');
  assert.equal(thread.scrollTop, 100);
  store.dispatch('append', { convId: 'c-1', msg: { from: 'gravit', kind: 'text', text: 'x', data: {} }, at: Date.now() });
  assert.equal(thread.scrollTop, thread.scrollHeight);
  store.timers.clear();
});

test('a re-render keeps the scroll of the page, the rail rows, a drawer and each shelf row', () => {
  const f = fakeWindow({ hash: '#/discover' });
  const main = f.withSelector('main');
  const rows = f.withSelector('.rail-rows');
  const drawer = f.withSelector('.drawer-body');
  const shelf = f.withSelector('.shelf-row');
  const store = boot(f.win);
  store.dispatch('openPlugin', 'news');
  assert.equal(drawer.scrollTop, 0, 'a drawer that just opened starts at its top');
  main.scrollTop = 300; rows.scrollTop = 40; drawer.scrollTop = 120; shelf.scrollLeft = 260;
  store.dispatch('setQuery', ''); store.dispatch('toggleInstalledOnly'); store.dispatch('toggleInstalledOnly'); // re-renders while the same drawer stays open
  assert.deepEqual([main.scrollTop, rows.scrollTop, drawer.scrollTop, shelf.scrollLeft], [300, 40, 120, 260]);
  store.timers.clear();
});

test('focus stays on the key that was pressed, moves into a drawer that opens, and returns to its opener on Escape', () => {
  const f = fakeWindow();
  const rail = f.withSelector('[data-action="toggleRail"]', { tagName: 'BUTTON', dataset: { action: 'toggleRail' } });
  const details = f.withSelector('[data-action="toggleDetails"]', { tagName: 'BUTTON', dataset: { action: 'toggleDetails' } });
  const close = f.withSelector('.drawer .close-key', { tagName: 'BUTTON' });
  const store = boot(f.win);
  rail.focus();
  f.click(rail);
  assert.equal(f.doc.activeElement, rail);
  details.focus();
  f.click(details);
  assert.equal(store.get().detailsOpen, true);
  assert.equal(f.doc.activeElement, close);
  f.fire('doc', 'keydown', { key: 'Escape' });
  assert.equal(store.get().detailsOpen, false);
  assert.equal(f.doc.activeElement, details);
  store.timers.clear();
});

test('the incoming call takes focus on its decline key', () => {
  const f = fakeWindow();
  const decline = f.withSelector('.call [data-accept="0"]', { tagName: 'BUTTON' });
  const store = boot(f.win);
  store.dispatch('incomingCall', { from: 'gravit', about: 'x' });
  assert.equal(f.doc.activeElement, decline);
  store.timers.clear();
});

test('Export revokes the download link later, not in the tick of the click', async () => {
  const f = fakeWindow({ hash: '#/account/memory' });
  const store = boot(f.win);
  f.click(f.element({ tagName: 'BUTTON', dataset: { action: 'exportMemory' } }));
  assert.equal(f.revoked.length, 0);
  await sleep(1100);
  assert.deepEqual(f.revoked, ['blob:fake']);
  store.timers.clear();
});

test('+ on an install request opens the drawer and leaves the request waiting', async () => {
  const f = fakeWindow();
  const store = boot(f.win);
  const ask = store.get().conversations[0].messages.find(m => m.kind === 'install');
  f.click(f.element({ tagName: 'BUTTON', dataset: { action: 'installAsk', conv: 'c-1', msg: ask.id, plugin: 'news' } }));
  await f.tick();
  assert.equal(store.get().conversations[0].messages.find(m => m.id === ask.id).answer, undefined);
  assert.equal(store.get().route.screen, 'discover');
  assert.equal(store.get().discover.drawer, 'news');
  store.timers.clear();
});

test('the director opens the first-run state, the refusal and the close', async () => {
  const f = fakeWindow();
  const store = boot(f.win);
  const dir = key => f.click(f.element({ tagName: 'BUTTON', dataset: { action: 'director', key } }));
  dir('refusal');
  assert.equal(store.get().conversations[0].messages.at(-1).kind, 'refusal');
  dir('done');
  assert.equal(store.get().conversations[0].messages.at(-1).kind, 'done');
  dir('firstRun');
  await f.tick();
  assert.deepEqual(store.get().conversations, []);
  assert.equal(f.win.location.hash, '#/messages');
  store.timers.clear();
});

const noDialogs = { prompt: () => { throw new Error('prompt() is gone'); }, confirm: () => { throw new Error('confirm() is gone'); } };

test('Change words edits in place: the editor takes focus, Enter commits, Escape cancels; no browser prompt', () => {
  const f = fakeWindow(noDialogs);
  const title = f.withSelector('.inline-edit [name]', { tagName: 'INPUT', name: 'title', closestMap: { '.inline-edit': {} } });
  const store = boot(f.win);
  store.dispatch('toggleDetails');
  f.click(f.element({ tagName: 'BUTTON', dataset: { action: 'changeWords', conv: 'c-1' } }));
  assert.deepEqual(store.get().edit, { kind: 'rename', convId: 'c-1' });
  assert.equal(f.doc.activeElement, title, 'the editor takes focus');
  title.value = 'Small BTC';
  f.fire('doc', 'keydown', { key: 'Enter' });
  assert.equal(store.get().conversations[0].title, 'Small BTC');
  assert.equal(store.get().edit, null);
  f.click(f.element({ tagName: 'BUTTON', dataset: { action: 'changeLimit', conv: 'c-1' } }));
  f.fire('doc', 'keydown', { key: 'Escape' });
  assert.equal(store.get().edit, null);
  assert.equal(store.get().detailsOpen, true, 'Escape cancels the editor before it closes the drawer');
  store.timers.clear();
});

test('Withdraw, Stop, End limit, Forget all and Reset ask in place and act on the second press; no browser confirm', () => {
  const f = fakeWindow(noDialogs);
  const store = boot(f.win);
  const click = (action, conv) => f.click(f.element({ tagName: 'BUTTON', dataset: conv ? { action, conv } : { action } }));
  click('withdraw', 'c-2');
  assert.deepEqual(store.get().confirm, { action: 'withdraw', id: 'c-2' });
  click('cancelConfirm');
  assert.equal(store.get().confirm, null);
  click('withdraw', 'c-2');
  click('confirmYes');
  assert.equal(store.get().conversations.find(c => c.id === 'c-2').status, 'withdrawn');
  click('endLimit', 'c-1');
  click('confirmYes');
  assert.equal(store.get().conversations[0].intent.limit.total, 5);
  click('forgetAll');
  click('confirmYes');
  assert.deepEqual(store.get().memory.entries, []);
  click('resetDemo');
  click('confirmYes');
  assert.equal(store.get().memory.entries.length, 9, 'reset brings the seed back');
  store.timers.clear();
});

test('Top up commits through its editor and shows in the wallet', () => {
  const f = fakeWindow(noDialogs);
  f.withSelector('.inline-edit [name]', { tagName: 'INPUT', name: 'amount', value: '20', rendered: '20' });
  const store = boot(f.win);
  store.dispatch('toggleDetails');
  f.click(f.element({ tagName: 'BUTTON', dataset: { action: 'topUp', conv: 'c-1' } }));
  f.click(f.element({ tagName: 'BUTTON', dataset: { action: 'commitEdit' } }));
  assert.equal(store.get().account.wallet.usdc, 32.4);
  store.timers.clear();
});

test('+ opens the file picker; picked files join the tray; a send with only files goes out and Gravit reads them', async () => {
  const f = fakeWindow(noDialogs);
  const picker = f.withId('attach-input', { tagName: 'INPUT', type: 'file' });
  f.withId('say', { tagName: 'INPUT' });
  const store = boot(f.win);
  f.click(f.element({ tagName: 'BUTTON', dataset: { action: 'pickFile' } }));
  assert.equal(picker.clicks, 1);
  picker.files = [{ name: 'q3.pdf', size: 1200 }];
  f.fire('root', 'change', { target: picker });
  assert.deepEqual(store.get().compose.files.map(x => x.name), ['q3.pdf']);
  const form = { dataset: { action: 'send' } };
  f.fire('root', 'submit', { target: { closest: () => form } });
  const c1 = () => store.get().conversations.find(c => c.id === 'c-1');
  assert.deepEqual(c1().messages.at(-1).data.files, ['q3.pdf']);
  assert.deepEqual(store.get().compose.files, []);
  await sleep(1100);
  assert.match(c1().messages.at(-1).text, /q3.pdf/);
  store.timers.clear();
});

test('picking a file never writes a path back into the file input (browsers refuse it and the render would stop)', () => {
  const f = fakeWindow(noDialogs);
  const picker = f.withId('attach-input', { tagName: 'INPUT', type: 'file' });
  let held = '';
  Object.defineProperty(picker, 'value', {
    get: () => held,
    set: v => { if (v) throw new Error('InvalidStateError: a file input accepts only the empty string'); held = v; },
  });
  const say = f.withId('say', { tagName: 'INPUT' });
  const store = boot(f.win);
  held = 'C:\\fakepath\\q3.pdf';
  picker.files = [{ name: 'q3.pdf', size: 1 }];
  f.fire('root', 'change', { target: picker });
  assert.deepEqual(store.get().compose.files.map(x => x.name), ['q3.pdf']);
  assert.equal(held, '', 'the picker is emptied so the same file can be picked again');
  assert.equal(say.value, '', 'the render ran to the end: the composer was restored');
  store.timers.clear();
});

test('the mic listens, then writes what it heard into the composer; a second press stops it at once', async () => {
  const f = fakeWindow(noDialogs);
  const say = f.withId('say', { tagName: 'INPUT' });
  const store = boot(f.win);
  const mic = () => f.click(f.element({ tagName: 'BUTTON', dataset: { action: 'toggleMic' } }));
  mic();
  assert.equal(store.get().compose.listening, true);
  await sleep(2000);
  assert.equal(store.get().compose.listening, false);
  assert.ok(say.value.length > 0, 'the transcript is in the composer');
  const first = say.value;
  mic(); mic();
  assert.equal(store.get().compose.listening, false);
  assert.ok(say.value.length > first.length, 'the second sentence is added after the first');
  store.timers.clear();
});

test('the phone key rings Gravit, it picks up, the timer runs, hang up leaves the card', async () => {
  const f = fakeWindow(noDialogs);
  const hang = f.withSelector('.call [data-action="hangUp"]', { tagName: 'BUTTON' });
  const timer = f.withSelector('.call-timer', { tagName: 'DIV' });
  const store = boot(f.win);
  try {
    f.click(f.element({ tagName: 'BUTTON', dataset: { action: 'phoneCall' } }));
    assert.deepEqual([store.get().call.dir, store.get().call.status], ['out', 'ringing']);
    assert.equal(f.doc.activeElement, hang, 'the call takes focus on its hang-up key');
    await sleep(1600);
    assert.equal(store.get().call.status, 'live');
    await sleep(1100);
    assert.match(timer.textContent, /^00:0[12]$/, 'the timer runs');
    f.click(f.element({ tagName: 'BUTTON', dataset: { action: 'hangUp' } }));
    assert.equal(store.get().call, null);
    const card = store.get().conversations[0].messages.at(-1);
    assert.deepEqual([card.kind, card.answer, card.data.dir], ['call', 'accepted', 'out']);
  } finally {
    store.timers.clear();
  }
});

test('the mail key switches to the mailbox screen; a letter opens by its link and is read; a bad letter id goes back to the inbox', async () => {
  const f = fakeWindow(noDialogs);
  const store = boot(f.win);
  f.win.location.hash = '#/mail';
  await f.tick();
  assert.deepEqual(store.get().route, { screen: 'mail', id: null });
  assert.match(f.html(), /<main class="main mail">/);
  f.win.location.hash = '#/mail/mail-2';
  await f.tick();
  assert.equal(store.get().mail.items.find(m => m.id === 'mail-2').read, true);
  assert.match(f.html(), /<h1 class="head-title">Form 4: Pelosi reports buying NVDA<\/h1>/);
  f.win.location.hash = '#/mail/nope';
  await f.tick();
  assert.equal(f.win.location.hash, '#/mail', 'the address bar is put right');
  store.timers.clear();
});

test('Account panels: Move submits its form; Connect connects after a moment; Receive copies the full address; Statement exports; Escape closes', async () => {
  const f = fakeWindow({ ...noDialogs, hash: '#/account/portfolio' });
  let copied = null;
  f.win.navigator = { clipboard: { writeText: t => { copied = t; return Promise.resolve(); } } };
  const store = boot(f.win);
  const click = (action, extra = {}) => f.click(f.element({ tagName: 'BUTTON', dataset: { action, ...extra } }));
  click('openPanel', { panel: 'move' });
  assert.equal(store.get().account.panel, 'move');
  const form = { dataset: { action: 'moveFunds' }, fields: { from: 'Stand-in Wallet', asset: 'USDC', to: 'Stand-in Exchange', amount: '100' } };
  f.fire('root', 'submit', { target: { closest: () => form } });
  assert.equal(store.get().account.holdings.find(h => h.venue === 'Stand-in Exchange' && h.name === 'USDC').value, 100);
  click('openPanel', { panel: 'connect' });
  click('connectVenue', { name: 'Polymarket' });
  assert.equal(store.get().account.connecting, 'Polymarket');
  await sleep(1300);
  assert.equal(store.get().account.venues.at(-1).name, 'Polymarket');
  click('openPanel', { panel: 'receive' });
  click('copyAddress');
  assert.equal(copied, '0xec4c3e9d5b7a2f1c8e6d4b2a9f7c5e3d1b8a16c1');
  assert.equal(store.get().account.copied, true);
  click('openPanel', { panel: 'statement' });
  click('exportStatement');
  assert.equal(f.revoked.length, 0);
  f.fire('doc', 'keydown', { key: 'Escape' });
  assert.equal(store.get().account.panel, null);
  store.timers.clear();
});

test('focus stays on the radio that was picked, not on the first radio sharing its action', () => {
  const f = fakeWindow({ ...noDialogs, hash: '#/discover' });
  f.withSelector('[data-action="mcpClient"]', { tagName: 'INPUT', type: 'radio', name: 'client', value: 'Claude Code', rendered: 'Claude Code', dataset: { action: 'mcpClient' } });
  const radio = f.withSelector('[data-action="mcpClient"][name="client"][value="Codex"]', { tagName: 'INPUT', type: 'radio', name: 'client', value: 'Codex', rendered: 'Codex', dataset: { action: 'mcpClient' } });
  const store = boot(f.win);
  store.dispatch('openCreate');
  radio.focus();
  f.fire('root', 'change', { target: radio });
  assert.equal(store.get().discover.create.client, 'Codex');
  assert.equal(f.doc.activeElement, radio);
  store.timers.clear();
});

// round three: Create is Discover's own MCP face

test('Create: copy the client line, the scripted client connects and asks to publish; Publish lands it; focus never sits on Publish', async () => {
  const f = fakeWindow({ ...noDialogs, hash: '#/discover' });
  let copied = null;
  f.win.navigator = { clipboard: { writeText: t => { copied = t; return Promise.resolve(); } } };
  const copyKey = f.withId('mcp-copy', { tagName: 'BUTTON', dataset: { action: 'copyMcp' }, presentIf: /id="mcp-copy"/ });
  const close = f.withSelector('.modal .close-key', { tagName: 'BUTTON', presentIf: /class="modal/ });
  const store = boot(f.win);
  const btn = action => f.element({ tagName: 'BUTTON', dataset: { action } });
  const radio = (name, value, action) => f.fire('root', 'change', { target: f.element({ tagName: 'INPUT', type: 'radio', name, value, dataset: { action } }) });
  try {
    f.click(btn('openCreate'));
    assert.equal(f.doc.activeElement, copyKey, 'the copy key takes focus');
    radio('client', 'Cursor', 'mcpClient');
    assert.equal(store.get().discover.create.client, 'Cursor');
    f.click(copyKey);
    assert.match(copied, /"mcpServers"/, 'the Cursor line went to the clipboard');
    assert.deepEqual([store.get().discover.create.copied, store.get().discover.create.started], [true, true]);
    await sleep(1600);
    assert.equal(store.get().discover.create.step, 'connected');
    assert.equal(f.doc.activeElement, close, 'the copy key went away: focus stays in the dialog');
    await sleep(1600);
    assert.deepEqual([store.get().discover.create.step, store.get().discover.create.manifest.id], ['sign', 'moat']);
    assert.notEqual(f.doc.activeElement?.dataset?.action, 'publishUpload', 'a stray Enter cannot sign');
    radio('visibility', 'public', 'uploadVisibility');
    assert.equal(store.get().discover.create.visibility, 'public');
    radio('visibility', 'private', 'uploadVisibility');
    f.click(btn('publishUpload'));
    const s = store.get();
    assert.equal(s.discover.create, null);
    assert.ok(s.plugins.installed.includes('moat'));
    assert.equal(f.win.location.hash, '#/discover');
  } finally {
    store.timers.clear();
  }
});

test('Create: Escape mid-run leaves the late client nothing to move, even in a dialog opened again', async () => {
  const f = fakeWindow({ ...noDialogs, hash: '#/discover' });
  f.win.navigator = { clipboard: { writeText: () => Promise.resolve() } };
  const store = boot(f.win);
  const btn = action => f.element({ tagName: 'BUTTON', dataset: { action } });
  try {
    f.click(btn('openCreate'));
    f.click(btn('copyMcp'));
    f.fire('doc', 'keydown', { key: 'Escape' });
    assert.equal(store.get().discover.create, null);
    f.click(btn('openCreate'));
    await sleep(1700);
    assert.deepEqual([store.get().discover.create.step, store.get().discover.create.started], ['wait', false]);
    assert.equal(store.get().plugins.uploaded.length, 0);
  } finally {
    store.timers.clear();
  }
});

test('the director\'s Plugin upload starts an upload from anywhere; a public one passes review and its letter comes', async () => {
  const f = fakeWindow(noDialogs);
  const store = boot(f.win);
  try {
    f.fire('doc', 'keydown', { key: 'd' });
    f.click(f.element({ tagName: 'BUTTON', dataset: { action: 'director', key: 'upload' } }));
    await f.tick();
    assert.equal(store.get().route.screen, 'discover');
    assert.equal(store.get().discover.create.started, true);
    await sleep(3100);
    assert.equal(store.get().discover.create.step, 'sign');
    store.dispatch('setUploadVisibility', 'public');
    f.click(f.element({ tagName: 'BUTTON', dataset: { action: 'publishUpload' } }));
    assert.ok(store.get().plugins.uploaded[0].review);
    await sleep(5100);
    const s = store.get();
    assert.equal(s.plugins.uploaded[0].review, null);
    assert.deepEqual([s.mail.items[0].from, s.mail.items[0].subject, s.mail.items[0].read], ['Discover', 'Moat score passed review', false]);
    assert.equal(s.discover.toast.text, 'Moat score passed review · Public');
  } finally {
    store.timers.clear();
  }
});

test('a review still pending in a save is finished after boot', async () => {
  const s = seed(Date.now());
  const p = { ...fromManifest(nextUpload([]), 'public', Date.now()), review: { until: Date.now() - 1 } };
  const saved = { ...s, plugins: { ...s.plugins, uploaded: [p], mine: [...s.plugins.mine, p.id] } };
  const f = fakeWindow({ storage: { getItem: () => JSON.stringify(saved), setItem() {}, removeItem() {} } });
  const store = boot(f.win);
  try {
    await sleep(10);
    assert.equal(store.get().plugins.uploaded[0].review, null);
    assert.equal(store.get().mail.items[0].from, 'Discover');
  } finally {
    store.timers.clear();
  }
});

// round-two review fixes

test('opening another editor starts from its own value, not the text left in the last one', () => {
  const f = fakeWindow(noDialogs);
  const box = f.withId('edit-text', { tagName: 'INPUT', rendered: 'No leverage' });
  const store = boot(f.win);
  store.dispatch('nav', { screen: 'account', tab: 'memory' });
  store.dispatch('startEdit', { kind: 'memory', id: 'mem-1' });
  box.value = 'Prefers value, half edited';
  store.dispatch('startEdit', { kind: 'memory', id: 'mem-2' });
  assert.equal(box.value, 'No leverage', 'mem-2 shows its own text');
  box.value = 'No leverage, no options either';
  store.dispatch('setMode', 'beast');
  assert.equal(box.value, 'No leverage, no options either', 'while the same editor stays open, typing survives a render');
  store.timers.clear();
});

test('the Move pickers keep their choice across a render, such as an error', () => {
  const f = fakeWindow({ ...noDialogs, hash: '#/account/portfolio' });
  const from = f.withId('mv-from', { tagName: 'SELECT', rendered: 'Stand-in Wallet' });
  const store = boot(f.win);
  store.dispatch('openPanel', 'move');
  from.value = 'Stand-in Exchange';
  store.dispatch('moveFunds', { from: 'Stand-in Exchange', to: 'Stand-in Exchange', asset: 'BTC', amount: '1', now: Date.now() });
  assert.equal(store.get().account.panelError, 'Pick a different destination');
  assert.equal(from.value, 'Stand-in Exchange');
  store.timers.clear();
});

test('Enter on an editor\'s × key does not save', () => {
  const f = fakeWindow(noDialogs);
  f.withSelector('.inline-edit [name]', { tagName: 'INPUT', name: 'title', value: 'X', rendered: 'X' });
  const cancel = f.withSelector('[data-action="cancelEdit"]', { tagName: 'BUTTON', dataset: { action: 'cancelEdit' }, closestMap: { '.inline-edit': {} } });
  const store = boot(f.win);
  store.dispatch('toggleDetails');
  store.dispatch('startEdit', { kind: 'rename', convId: 'c-1' });
  cancel.focus();
  f.fire('doc', 'keydown', { key: 'Enter' });
  assert.notEqual(store.get().conversations[0].title, 'X');
  store.timers.clear();
});

test('focus goes to what replaced the pressed key: the confirm, or the drawer, never the page behind an overlay', () => {
  const f = fakeWindow(noDialogs);
  const yes = f.withSelector('.confirm [data-action="confirmYes"]', { tagName: 'BUTTON' });
  const close = f.withSelector('.drawer .close-key', { tagName: 'BUTTON' });
  const say = f.withId('say', { tagName: 'INPUT' });
  const store = boot(f.win);
  store.dispatch('toggleDetails');
  const withdraw = f.element({ tagName: 'BUTTON', dataset: { action: 'withdraw', conv: 'c-1' } });
  withdraw.focus();
  f.click(withdraw);
  assert.equal(f.doc.activeElement, yes, 'the confirm takes focus');
  store.dispatch('cancelConfirm');
  const gone = f.element({ tagName: 'BUTTON', dataset: { action: 'changeWords', conv: 'c-9' } });
  gone.focus();
  store.dispatch('setMode', 'beast');
  assert.equal(f.doc.activeElement, close, 'the pressed key went away: focus stays in the drawer, not the composer behind it');
  assert.notEqual(f.doc.activeElement, say);
  store.timers.clear();
});

test('focus returns to the same panel key, told apart by every data attribute', () => {
  const f = fakeWindow({ ...noDialogs, hash: '#/account/portfolio' });
  f.withSelector('[data-action="openPanel"]', { tagName: 'BUTTON', dataset: { action: 'openPanel', panel: 'move' } });
  const receive = f.withSelector('[data-action="openPanel"][data-panel="receive"]', { tagName: 'BUTTON', dataset: { action: 'openPanel', panel: 'receive' } });
  const store = boot(f.win);
  receive.focus();
  store.dispatch('setMode', 'beast');
  assert.equal(f.doc.activeElement, receive);
  store.timers.clear();
});

test('a live call updates only its timer each second; the page is not redrawn under the keys', async () => {
  const f = fakeWindow(noDialogs);
  const timer = f.withSelector('.call-timer', { tagName: 'DIV' });
  const store = boot(f.win);
  try {
    store.dispatch('startCall', { now: Date.now() });
    store.dispatch('connectCall', { now: Date.now() - 61_000 });
    const writes = f.writes;
    await sleep(1100);
    assert.equal(f.writes, writes, 'no full redraw while the call runs');
    assert.match(timer.textContent, /^01:0[12]$/);
  } finally {
    store.timers.clear(); // a live call ticks every second: a failed assertion must not leave it running
  }
});

test('the draft picker keys reach the store', () => {
  const f = fakeWindow();
  const store = boot(f.win);
  store.dispatch('startDraft', { now: Date.now() });
  f.click(f.element({ tagName: 'BUTTON', dataset: { action: 'toggleDraftPicker' } }));
  assert.equal(store.get().draft.picking, true);
  f.click(f.element({ tagName: 'BUTTON', dataset: { action: 'toggleDraftBot', id: 'buffett' } }));
  assert.deepEqual(store.get().draft.bots, ['buffett']);
  store.timers.clear();
});

// round-three review fixes

test('when Publish or Plugin upload clears the search, the search box is cleared too', async () => {
  const f = fakeWindow({ ...noDialogs, hash: '#/discover' });
  const dq = f.withId('dq', { tagName: 'INPUT', type: 'search', dataset: { action: 'query' } });
  const store = boot(f.win);
  try {
    dq.value = 'quant';
    f.fire('root', 'input', { target: dq });
    store.dispatch('toggleRail');
    assert.equal(dq.value, 'quant', 'a re-render keeps what was typed while it is the search');
    f.fire('doc', 'keydown', { key: 'd' });
    f.click(f.element({ tagName: 'BUTTON', dataset: { action: 'director', key: 'upload' } }));
    assert.equal(store.get().discover.query, '');
    assert.equal(dq.value, '', 'the box says what the page shows');
  } finally {
    store.timers.clear();
  }
});

test('the dialog body keeps its scroll while the same step changes, and starts at the top on a new step', () => {
  const f = fakeWindow({ ...noDialogs, hash: '#/discover' });
  const body = f.withSelector('.modal-body');
  const store = boot(f.win);
  try {
    store.dispatch('openCreate');
    body.scrollTop = 120;
    store.dispatch('setClient', 'Cursor');
    assert.equal(body.scrollTop, 120, 'switching the client does not jump the dialog');
    const { run } = store.get().discover.create;
    store.dispatch('startClient', { run });
    store.dispatch('clientConnected', { run });
    assert.equal(body.scrollTop, 0, 'a new step starts at its top');
  } finally {
    store.timers.clear();
  }
});

test('after Refuse, the director\'s Plugin upload starts a fresh upload in a new dialog', () => {
  const f = fakeWindow({ ...noDialogs, hash: '#/discover' });
  const store = boot(f.win);
  try {
    store.dispatch('openCreate');
    const { run } = store.get().discover.create;
    store.dispatch('startClient', { run });
    store.dispatch('clientConnected', { run });
    store.dispatch('clientPublishes', { run, manifest: nextUpload([]) });
    store.dispatch('rejectUpload');
    f.fire('doc', 'keydown', { key: 'd' });
    f.click(f.element({ tagName: 'BUTTON', dataset: { action: 'director', key: 'upload' } }));
    const c = store.get().discover.create;
    assert.notEqual(c.run, run);
    assert.deepEqual([c.step, c.started], ['wait', true]);
  } finally {
    store.timers.clear();
  }
});
