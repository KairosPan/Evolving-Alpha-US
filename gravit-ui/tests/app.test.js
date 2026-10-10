// gravit-ui/tests/app.test.js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseHash, toHash } from '../js/router.js';
import { Timers, initialState, scheduleEvents, makeStore, settle, showBreaking, answerFlow, replyFlow, watchToast } from '../js/app.js';
import { createStore } from '../js/store.js';
import { reducers } from '../js/reducers/index.js';
import { seed, SEED_VERSION } from '../js/data/seed.js';

const NOW = new Date(2026, 9, 9, 14, 7).getTime();
const sleep = ms => new Promise(r => setTimeout(r, ms));

test('parseHash and toHash round-trip, unknown screens fall back to messages', () => {
  assert.deepEqual(parseHash('#/messages/c-2'), { screen: 'messages', id: 'c-2' });
  assert.deepEqual(parseHash('#/messages/new'), { screen: 'messages', id: 'new' });
  assert.deepEqual(parseHash('#/discover'), { screen: 'discover', id: null });
  assert.deepEqual(parseHash('#/discover/bots'), { screen: 'discover', id: 'bots' });
  assert.deepEqual(parseHash('#/account'), { screen: 'account', tab: 'portfolio' });
  assert.deepEqual(parseHash('#/account/memory'), { screen: 'account', tab: 'memory' });
  assert.deepEqual(parseHash('#/account/nope'), { screen: 'account', tab: 'portfolio' });
  assert.deepEqual(parseHash('#/markets/NVDA'), { screen: 'markets', id: 'NVDA' });
  assert.deepEqual(parseHash('#/trade'), { screen: 'trade' });
  assert.deepEqual(parseHash(''), { screen: 'messages', id: null });
  assert.deepEqual(parseHash('#/whatever'), { screen: 'messages', id: null });
  assert.equal(toHash({ screen: 'messages', id: 'c-1' }), '#/messages/c-1');
  assert.equal(toHash({ screen: 'account', tab: 'memory' }), '#/account/memory');
  assert.equal(toHash({ screen: 'discover', id: null }), '#/discover');
});

test('initialState: a saved state of the same version is kept; another version or garbage boots the seed', () => {
  const saved = { ...seed(NOW), theme: 'black' };
  const storage = { getItem: () => JSON.stringify(saved), setItem() {} };
  assert.equal(initialState(storage, NOW).theme, 'black');
  const old = { getItem: () => JSON.stringify({ ...saved, v: SEED_VERSION + 1 }), setItem() {} };
  assert.equal(initialState(old, NOW).theme, 'system');
  const junk = { getItem: () => '{nope', setItem() {} };
  assert.equal(initialState(junk, NOW).v, SEED_VERSION);
  assert.equal(initialState(null, NOW).conversations.length, 4);
});

test('Timers tracks pending timers and clear() cancels them', async () => {
  const t = new Timers();
  let fired = 0;
  t.after(5, () => fired++);
  t.after(5, () => fired++);
  assert.equal(t.size, 2);
  t.clear();
  assert.equal(t.size, 0);
  await sleep(15);
  assert.equal(fired, 0);
  t.after(5, () => fired++);
  await sleep(15);
  assert.equal(fired, 1);
  assert.equal(t.size, 0, 'a fired timer leaves the set');
});

test('scheduleEvents appends each event after its delay; a reset in between drops the rest', async () => {
  const store = createStore({ initial: seed(NOW), reducers });
  const timers = new Timers();
  const events = [{ delay: 5, msg: { from: 'gravit', kind: 'text', text: 'one', data: {} } }, { delay: 30, msg: { from: 'gravit', kind: 'text', text: 'two', data: {} } }];
  scheduleEvents(store, timers, 'c-1', events, () => NOW);
  await sleep(15);
  assert.equal(store.get().conversations[0].messages.at(-1).text, 'one');
  timers.clear();
  store.reset(seed(NOW));
  await sleep(40);
  assert.equal(store.get().conversations[0].messages.at(-1).kind, 'install', 'the fresh seed never saw "two"');
});

const saving = value => ({ map: new Map([['gravit-ui.state', value]]), getItem(k) { return this.map.get(k) ?? null; }, setItem(k, v) { this.map.set(k, v); } });

test('makeStore, the store boot builds: a save of another version or garbage boots the seed, a good one is kept', () => {
  const good = { ...seed(NOW), theme: 'black' };
  assert.equal(makeStore(saving(JSON.stringify(good)), NOW).get().theme, 'black');
  assert.equal(makeStore(saving(JSON.stringify({ ...good, v: SEED_VERSION + 1 })), NOW).get().theme, 'system');
  assert.equal(makeStore(saving('{nope'), NOW).get().v, SEED_VERSION);
  assert.equal(makeStore(null, NOW).get().conversations.length, 4);
});

test('settle routes by the hash and says which hash the address bar should show', () => {
  const store = makeStore(null, NOW);
  assert.equal(settle(store, '#/messages/c-99'), '#/messages/c-1');
  assert.equal(store.get().route.id, 'c-1');
  assert.equal(settle(store, '#/account'), '#/account/portfolio');
  assert.equal(settle(store, '#/messages/c-2'), null);
  assert.equal(store.get().conversations.find(c => c.id === 'c-2').unread, false);
  assert.equal(settle(store, '#/messages/new'), '#/messages/c-1', 'new without a draft');
});

test('showBreaking: the banner shows, then closes itself and leaves its message; an older timer never closes a newer banner', async () => {
  const store = makeStore(null, NOW);
  const timers = new Timers();
  showBreaking(store, timers, { id: 'b1', headline: 'H1', body: 'B', at: NOW }, () => NOW, 10);
  assert.equal(store.get().banner.id, 'b1');
  await sleep(4);
  showBreaking(store, timers, { id: 'b2', headline: 'H2', body: 'B', at: NOW }, () => NOW, 30);
  await sleep(14);
  assert.equal(store.get().banner?.id, 'b2', 'b1 timer fired but b2 stays');
  await sleep(30);
  assert.equal(store.get().banner, null);
  assert.equal(store.get().conversations[0].messages.at(-1).text, 'H2');
});

test('answerFlow: a double click answers once and schedules the follow-up once', async () => {
  const store = makeStore(null, NOW);
  const timers = new Timers();
  const limit = store.get().conversations[0].messages.find(m => m.kind === 'limit');
  const fast = (store2, t, convId, events, now) => scheduleEvents(store2, t, convId, events.map(e => ({ ...e, delay: 1 })), now);
  answerFlow(store, timers, { conv: 'c-1', msg: limit.id, answer: 'granted' }, () => NOW, fast);
  answerFlow(store, timers, { conv: 'c-1', msg: limit.id, answer: 'granted' }, () => NOW, fast);
  await sleep(20);
  const texts = store.get().conversations[0].messages.map(m => m.text);
  assert.equal(texts.filter(t => t === 'Granted.').length, 1);
  assert.equal(texts.filter(t => t === '改到 $50 了。').length, 1);
  const asks = store.get().conversations[0].messages.filter(m => m.kind === 'install' && m.data.plugin === 'news');
  assert.equal(asks.length, 1, 'the seed already asks for News sentiment; the grant does not ask again');
});

const fast = (store, t, convId, events, now) => scheduleEvents(store, t, convId, events.map(e => ({ ...e, delay: 1 })), now);

test('answerFlow hands the driver the real limit: a $50 cap gets no ask for the $30 add', async () => {
  const store = makeStore(null, NOW);
  const timers = new Timers();
  store.dispatch('changeLimit', { convId: 'c-1', limit: { perOrder: 50 } });
  store.dispatch('append', { convId: 'c-1', msg: { from: 'gravit', kind: 'card', text: '要你答', data: { title: '要你答' } }, at: NOW });
  const card = store.get().conversations[0].messages.at(-1);
  answerFlow(store, timers, { conv: 'c-1', msg: card.id, answer: 'approved' }, () => NOW, fast);
  await sleep(15);
  const after = store.get().conversations[0].messages.slice(-2);
  assert.deepEqual(after.map(m => m.kind), ['text', 'receipt']);
  assert.equal(store.get().conversations[0].intent.limit.spent, 10);
});

test('replyFlow hands the driver the conversation: in the group the @named bot answers', async () => {
  const store = makeStore(null, NOW);
  const timers = new Timers();
  replyFlow(store, timers, 'c-4', '@Buffett 你怎么看 KO', () => NOW, fast);
  await sleep(15);
  assert.equal(store.get().conversations.find(c => c.id === 'c-4').messages.at(-1).from, 'buffett');
});

test('watchToast dismisses a toast after a while, and never a newer one', async () => {
  const store = makeStore(null, NOW);
  const timers = new Timers();
  watchToast(store, timers, 10);
  store.dispatch('install', { id: 'news', now: NOW });
  await sleep(5);
  store.dispatch('install', { id: 'serenity', now: NOW });
  await sleep(8);
  assert.match(store.get().discover.toast?.text ?? '', /Serenity/, 'the first timer fired but the newer toast stays');
  await sleep(10);
  assert.equal(store.get().discover.toast, null);
});

test('a saved state boots without the moment-only overlays: banner, call, drawer, connector and toast', () => {
  const s = seed(NOW);
  const saved = { ...s, banner: { id: 'b', headline: 'h', body: 'b', at: NOW }, call: { from: 'gravit', about: 'x' }, discover: { ...s.discover, drawer: 'news', create: { step: 'form', form: {}, tools: [], error: null }, toast: { text: 't', action: null } } };
  const st = initialState({ getItem: () => JSON.stringify(saved), setItem() {} }, NOW);
  assert.deepEqual([st.banner, st.call, st.discover.drawer, st.discover.create, st.discover.toast], [null, null, null, null, null]);
  const store = makeStore({ getItem: () => JSON.stringify(saved), setItem() {} }, NOW);
  assert.equal(store.get().banner, null);
});
