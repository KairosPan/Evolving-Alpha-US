// gravit-ui/tests/markets-dom.test.js — boot() against a fake window: Markets' drawer, a hand trade end to end, the signature clock
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { boot, settle, placeFlow, makeStore, Timers } from '../js/app.js';
import { fakeWindow } from './helpers/fake-dom.js';
import { seed } from '../js/data/seed.js';
import { QUOTE_MS } from '../js/data/markets.js';

const sleep = ms => new Promise(r => setTimeout(r, ms));
const noDialogs = { prompt: () => { throw new Error('prompt() is gone'); }, confirm: () => { throw new Error('confirm() is gone'); } };
const btn = (f, action, data = {}) => f.element({ tagName: 'BUTTON', dataset: { action, ...data } });

test('a market opens its drawer by its route, focus goes in, Escape closes it and focus returns to the row', async () => {
  const f = fakeWindow({ ...noDialogs, hash: '#/markets' });
  const opener = f.withSelector('[data-action="openMarket"][data-id="BTC"]', { tagName: 'BUTTON', dataset: { action: 'openMarket', id: 'BTC' } });
  const close = f.withSelector('.drawer .close-key', { tagName: 'BUTTON', presentIf: /class="drawer/ });
  const store = boot(f.win);
  try {
    assert.match(f.html(), /<main class="main mkts">/);
    opener.focus();
    f.click(opener);
    await f.tick();
    assert.deepEqual(store.get().route, { screen: 'markets', id: 'BTC' });
    assert.equal(f.doc.activeElement, close);
    f.fire('doc', 'keydown', { key: 'Escape' });
    await f.tick();
    assert.equal(store.get().route.id, null);
    assert.equal(f.doc.activeElement, opener);
    assert.equal(settle(store, '#/markets/btc'), '#/markets/BTC');
    assert.equal(settle(store, '#/markets/nope'), '#/markets');
  } finally {
    store.timers.clear();
  }
});

test('a hand trade: Trade on a row opens the ticket, the amount is typed, Sign and place, the stand-in fills it a moment later', async () => {
  const f = fakeWindow({ ...noDialogs, hash: '#/markets' });
  const amount = f.withId('tk-amount', { tagName: 'INPUT', name: 'amount', dataset: { action: 'ticketField' } });
  const store = boot(f.win);
  try {
    f.click(btn(f, 'tradeFrom', { id: 'BTC' }));
    await f.tick();
    assert.equal(store.get().route.screen, 'trade');
    assert.match(f.html(), /<main class="main trade">/);
    amount.value = '25';
    f.fire('root', 'input', { target: amount });
    assert.equal(store.get().trade.ticket.amount, '25');
    assert.equal(amount.value, '25', 'what was typed stays in the box after the render');
    f.fire('root', 'submit', { target: { closest: () => ({ dataset: { action: 'placeOrder' } }) } });
    assert.equal(store.get().account.orders[0].status, 'pending');
    await sleep(950);
    const s = store.get();
    assert.equal(s.account.orders[0].status, 'filled');
    assert.deepEqual(s.account.activity[0].text, 'Fill · 0.00039 BTC @ 62,803.6 · ord-0010');
    assert.match(f.html(), /\$12,479\.98 · Guard/, 'the rail shows the new net worth');
    assert.equal(amount.value, '', 'the filled order clears its amount');
  } finally {
    store.timers.clear();
  }
});

test('the signature clock counts down in place, and a quote that runs out is prepared again', async () => {
  const f = fakeWindow({ ...noDialogs, hash: '#/trade' });
  const left = f.withSelector('[data-left]', { tagName: 'DIV' });
  const store = boot(f.win);
  try {
    store.dispatch('openTicket', { id: 'BTC', now: Date.now() });
    store.dispatch('setTicket', { field: 'amount', value: '25', now: Date.now() });
    await sleep(1500);
    assert.match(left.textContent, /^Your signature is good for 9:5\d more\.$/);
    const old = Date.now() - QUOTE_MS + 300;
    store.dispatch('requote', { now: old });
    await sleep(1500);
    assert.ok(store.get().trade.ticket.preparedAt > old, 'prepared again when the ten minutes ran out');
  } finally {
    store.timers.clear();
  }
});

test('cancelling Gravit\'s order asks first, then leaves a line in its conversation', () => {
  const f = fakeWindow({ ...noDialogs, hash: '#/trade' });
  const store = boot(f.win);
  try {
    f.click(btn(f, 'cancelOrder', { id: 'ord-0008' }));
    assert.deepEqual(store.get().confirm, { action: 'cancelOrder', id: 'ord-0008' });
    f.click(btn(f, 'confirmYes'));
    assert.equal(store.get().account.orders.find(o => o.id === 'ord-0008').status, 'canceled');
    assert.equal(store.get().conversations.find(c => c.id === 'c-4').messages.at(-1).text, '你在 Trade 里撤了 ord-0008（KO limit 58.2）。');
  } finally {
    store.timers.clear();
  }
});

test('Connect to trade connects the public venue a moment later; its markets turn to Trade and its cash joins net worth', async () => {
  const f = fakeWindow({ ...noDialogs, hash: '#/markets' });
  const store = boot(f.win);
  try {
    f.click(btn(f, 'connectVenue', { name: 'Polymarket' }));
    assert.equal(store.get().account.connecting, 'Polymarket');
    await sleep(1300);
    assert.equal(store.get().account.cash.Polymarket, 300);
    assert.equal(store.get().account.netWorth, 12780);
    assert.match(f.html(), /data-action="tradeFrom" data-id="FED-DEC"/);
  } finally {
    store.timers.clear();
  }
});

test('Hand to Gravit opens a new message with the words and the limit set from the ticket', async () => {
  const f = fakeWindow({ ...noDialogs, hash: '#/trade' });
  const say = f.withId('say', { tagName: 'INPUT' });
  const store = boot(f.win);
  try {
    store.dispatch('openTicket', { id: 'BTC', now: Date.now() });
    store.dispatch('setTicket', { field: 'amount', value: '25', now: Date.now() });
    f.click(btn(f, 'handToGravit'));
    await f.tick();
    const s = store.get();
    assert.deepEqual(s.route, { screen: 'messages', id: 'new' });
    assert.deepEqual([s.draft.limit.venue, s.draft.limit.perOrder, s.draft.limit.total, s.draft.attach], ['Stand-in Exchange', 25, 100, true]);
    assert.equal(say.value, '买 $25 的 BTC');
  } finally {
    store.timers.clear();
  }
});

test('a pending order a reload interrupted still settles; placeFlow schedules the venue\'s answer once', async () => {
  const s = seed(Date.now());
  const pending = { ...s.account.orders[2], id: 'ord-0010', status: 'pending', inst: 'BTC', venue: 'Stand-in Exchange', symbol: 'BTC/USDT', type: 'market', qty: 0.00039, limit: null, by: 'you', conv: null, how: null };
  const saved = { ...s, account: { ...s.account, orders: [pending, ...s.account.orders] }, counters: { ...s.counters, ord: 10 } };
  const f = fakeWindow({ storage: { getItem: () => JSON.stringify(saved), setItem() {}, removeItem() {} } });
  const store = boot(f.win);
  try {
    await sleep(1000);
    assert.equal(store.get().account.orders[0].status, 'filled');
  } finally {
    store.timers.clear();
  }
  const timers = new Timers();
  const st = makeStore(null, Date.now());
  const now = () => Date.now();
  st.dispatch('openTicket', { id: 'BTC', now: now() });
  st.dispatch('setTicket', { field: 'amount', value: '25', now: now() });
  placeFlow(st, timers, now, 5);
  placeFlow(st, timers, now, 5);
  assert.equal(st.get().account.orders.filter(o => o.status === 'pending').length, 1);
  await sleep(20);
  assert.equal(st.get().account.orders[0].status, 'filled');
  timers.clear();
});

// ---- review fixes

test('after Reset demo the signature clock still runs on Trade', async () => {
  const f = fakeWindow({ ...noDialogs, hash: '#/trade' });
  const left = f.withSelector('[data-left]', { tagName: 'DIV' });
  const store = boot(f.win);
  try {
    store.dispatch('openTicket', { id: 'BTC', now: Date.now() });
    f.fire('doc', 'keydown', { key: 'd' });
    f.click(btn(f, 'director', { key: 'reset' }));
    f.win.location.hash = '#/trade';
    await f.tick();
    store.dispatch('openTicket', { id: 'BTC', now: Date.now() });
    store.dispatch('setTicket', { field: 'amount', value: '25', now: Date.now() });
    await sleep(1500);
    assert.match(left.textContent, /^Your signature is good for 9:5\d more\.$/);
  } finally {
    store.timers.clear();
  }
});

test('closing a market drawer replaces its history entry, so Back does not reopen it', async () => {
  const f = fakeWindow({ ...noDialogs, hash: '#/markets/BTC' });
  const replaced = [];
  const replace = f.win.history.replaceState;
  f.win.history.replaceState = (a, b, h) => { replaced.push(h); replace(a, b, h); };
  const store = boot(f.win);
  try {
    f.click(btn(f, 'closeMarket'));
    await f.tick();
    assert.deepEqual(store.get().route, { screen: 'markets', id: null });
    assert.ok(replaced.includes('#/markets'));
  } finally {
    store.timers.clear();
  }
});

test('Watch inside the drawer keeps focus inside the drawer', () => {
  const f = fakeWindow({ ...noDialogs, hash: '#/markets/BTC' });
  const star = f.withSelector('[data-action="toggleWatch"][data-id="BTC"]', { tagName: 'BUTTON', dataset: { action: 'toggleWatch', id: 'BTC' } });
  const inDrawer = f.withSelector('.drawer [data-action="toggleWatch"][data-id="BTC"]', { tagName: 'BUTTON', dataset: { action: 'toggleWatch', id: 'BTC' }, closestMap: { '.drawer': {} } });
  const store = boot(f.win);
  try {
    inDrawer.focus();
    f.click(inDrawer);
    assert.equal(store.get().markets.watch.includes('BTC'), false);
    assert.equal(f.doc.activeElement, inDrawer);
    assert.notEqual(f.doc.activeElement, star);
  } finally {
    store.timers.clear();
  }
});

test('the ticket keeps its own scroll while you type, and a new ticket is brought into view with the amount ready', async () => {
  const f = fakeWindow({ ...noDialogs, hash: '#/markets' });
  let shown = 0;
  const panel = f.withSelector('.tk-panel', { tagName: 'ASIDE', scrollIntoView() { shown++; } });
  const amount = f.withId('tk-amount', { tagName: 'INPUT', name: 'amount', dataset: { action: 'ticketField' } });
  const store = boot(f.win);
  try {
    f.click(btn(f, 'tradeFrom', { id: 'BTC' }));
    await f.tick();
    assert.equal(store.get().route.screen, 'trade');
    assert.equal(shown, 1, 'the ticket is scrolled into view');
    assert.equal(f.doc.activeElement, amount, 'the amount takes focus');
    panel.scrollTop = 200;
    amount.value = '2';
    f.fire('root', 'input', { target: amount });
    assert.equal(panel.scrollTop, 200, 'typing does not jump the ticket back to its top');
    assert.equal(shown, 1, 'and does not scroll it into view again');
  } finally {
    store.timers.clear();
  }
});
