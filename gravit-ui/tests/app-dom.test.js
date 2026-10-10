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
  store.dispatch('askUninstall', 'buffett'); // a re-render while the same drawer stays open
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
