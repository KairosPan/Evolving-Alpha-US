// gravit-ui/tests/app-dom.test.js — boot() against a fake window: what the person sees after typing, sending, scrolling and pressing keys
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { boot } from '../js/app.js';
import { fakeWindow } from './helpers/fake-dom.js';

const sleep = ms => new Promise(r => setTimeout(r, ms));
const send = (f, el) => { const form = { dataset: { action: 'send' } }; f.fire('root', 'submit', { target: { closest: () => form } }); };

test('the composer is empty right after a send', () => {
  const f = fakeWindow();
  const say = f.withId('say', { tagName: 'INPUT' });
  const store = boot(f.win);
  say.value = '再看看 ETH';
  f.fire('root', 'input', { target: say });
  send(f, say);
  assert.equal(store.get().conversations[0].messages.at(-1).text, '再看看 ETH');
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

test('Create: type a name and an address, Connect, wait for the tools, untick one, Add; Escape closes the dialog', async () => {
  const f = fakeWindow({ hash: '#/discover' });
  const store = boot(f.win);
  const btn = action => f.element({ tagName: 'BUTTON', dataset: { action } });
  f.click(btn('openCreate'));
  assert.equal(store.get().discover.create.step, 'form');
  const input = (name, value) => f.fire('root', 'input', { target: f.element({ tagName: 'INPUT', type: 'text', name, value, dataset: { action: 'mcpField' } }) });
  input('name', 'Pairs');
  input('url', 'https://pairs.example.com/mcp');
  f.fire('root', 'change', { target: f.element({ tagName: 'INPUT', type: 'radio', name: 'visibility', value: 'public', dataset: { action: 'mcpField' } }) });
  const form = { dataset: { action: 'connectMcp' } };
  f.fire('root', 'submit', { target: { closest: () => form } });
  assert.equal(store.get().discover.create.step, 'connecting');
  await sleep(1300);
  assert.deepEqual(store.get().discover.create.tools.map(t => t.name), ['pairs.search', 'pairs.get', 'pairs.watch']);
  f.fire('root', 'change', { target: f.element({ tagName: 'INPUT', type: 'checkbox', dataset: { action: 'toggleMcpTool', id: '2' } }) });
  f.click(btn('addMcp'));
  const p = store.get().plugins.uploaded.at(-1);
  assert.deepEqual([p.name, p.visibility, p.tools], ['Pairs', 'public', 'pairs.search\npairs.get']);
  f.click(btn('openCreate'));
  f.fire('doc', 'keydown', { key: 'Escape' });
  assert.equal(store.get().discover.create, null);
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
  title.value = 'BTC 小仓';
  f.fire('doc', 'keydown', { key: 'Enter' });
  assert.equal(store.get().conversations[0].title, 'BTC 小仓');
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
  const store = boot(f.win);
  f.click(f.element({ tagName: 'BUTTON', dataset: { action: 'phoneCall' } }));
  assert.deepEqual([store.get().call.dir, store.get().call.status], ['out', 'ringing']);
  assert.equal(f.doc.activeElement, hang, 'the call takes focus on its hang-up key');
  await sleep(1600);
  assert.equal(store.get().call.status, 'live');
  const writes = f.writes;
  await sleep(1100);
  assert.ok(f.writes > writes, 'the live call re-renders each second for its timer');
  f.click(f.element({ tagName: 'BUTTON', dataset: { action: 'hangUp' } }));
  assert.equal(store.get().call, null);
  const card = store.get().conversations[0].messages.at(-1);
  assert.deepEqual([card.kind, card.answer, card.data.dir], ['call', 'accepted', 'out']);
  store.timers.clear();
});

test('the mail key opens the mailbox; a message opens and reads; Escape closes it', () => {
  const f = fakeWindow(noDialogs);
  const store = boot(f.win);
  const click = (action, id) => f.click(f.element({ tagName: 'BUTTON', dataset: id ? { action, id } : { action } }));
  click('openMail');
  assert.equal(store.get().mail.open, true);
  click('readMail', 'mail-2');
  assert.equal(store.get().mail.reading, 'mail-2');
  click('backToInbox');
  assert.equal(store.get().mail.reading, null);
  f.fire('doc', 'keydown', { key: 'Escape' });
  assert.equal(store.get().mail.open, false);
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
