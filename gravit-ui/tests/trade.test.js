// gravit-ui/tests/trade.test.js — the owner's hand orders after Linqi's Trade: prepare, sign and place, the stand-in fill, and what it changes
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { reducers as R } from '../js/reducers/index.js';
import { seed, SEED_VERSION } from '../js/data/seed.js';
import { QUOTE_MS } from '../js/data/markets.js';
import { prepare, revalue, legsOf, routeOf, handOver, mentions } from '../js/trade.js';
import { instrument } from '../js/data/markets.js';

const NOW = new Date(2026, 9, 9, 14, 7).getTime();
const fresh = () => seed(NOW);
const held = (s, name, venue) => s.account.holdings.find(h => h.name === name && (!venue || h.venue === venue));
// a ticket on id with the given fields typed in
const ticket = (s, id, fields = {}, open = {}) => Object.entries(fields).reduce((st, [field, value]) => R.setTicket(st, { field, value, now: NOW }), R.openTicket(s, { id, now: NOW, ...open }));
const filled = s => { const t = s.trade.ticket.placing; return R.settleOrder(s, { id: t, now: NOW }); };

test('seed 4: holdings carry quantities, the venues hold cash, the account has orders; revalue agrees with the numbers shown', () => {
  assert.equal(SEED_VERSION, 4);
  const s = fresh();
  assert.equal(s.account.holdings.length, 4);
  assert.deepEqual(held(s, 'BTC'), { key: 'crypto:BTC', name: 'BTC', venue: 'Stand-in Exchange', qty: 0.05955, value: 3739.74, chg: 1.2 });
  assert.deepEqual(s.account.cash, { 'Stand-in Exchange': 1182.73, 'Stand-in Broker': 2500 });
  assert.deepEqual(s.account.orders.map(o => [o.id, o.status, o.by]), [['ord-0001', 'filled', 'gravit'], ['ord-0009', 'filled', 'gravit'], ['ord-0008', 'open', 'gravit'], ['ord-0004', 'filled', 'gravit']]);
  assert.equal(s.counters.ord, 9);
  assert.deepEqual(s.markets, { tab: 'all', sort: 'volume', q: '', interval: '1h', watch: ['BTC', 'FED-DEC', 'DOGE'] });
  assert.deepEqual(s.trade, { kind: 'crypto', q: '', ticket: null });
  const r = revalue(s.account);
  assert.equal(r.netWorth, 12480);
  assert.deepEqual(r.alloc, s.account.alloc);
  assert.deepEqual(r.holdings.map(h => h.value), s.account.holdings.map(h => h.value));
});

test('legs and routes: connected venues first by ask with the best marked; public ones after; a public-only market connects', () => {
  const a = fresh().account;
  assert.deepEqual(legsOf(instrument('BTC'), a).map(l => [l.venue, l.state, !!l.best]), [['Stand-in Exchange', 'able', true], ['Stand-in Wallet', 'able', false], ['Coinbase', 'public', false]]);
  assert.deepEqual(routeOf(instrument('BTC'), a), { act: 'trade' });
  assert.deepEqual(routeOf(instrument('DOGE'), a), { act: 'connect', venue: 'Coinbase' });
  assert.deepEqual(routeOf(instrument('FED-DEC'), a), { act: 'connect', venue: 'Polymarket' });
  assert.deepEqual(legsOf(instrument('FED-DEC'), a, 1).map(l => [l.bid, l.ask]), [[0.37, 0.39]], 'an outcome brings its own book');
});

test('prepare: at rest without a ticket, picking without a venue, then ready with what will be signed', () => {
  assert.equal(prepare(fresh(), NOW).state, 'rest');
  assert.equal(prepare(R.openTicket(fresh(), { id: 'DOGE', now: NOW }), NOW).state, 'pick');
  const s = ticket(fresh(), 'BTC', { amount: '25' });
  const p = prepare(s, NOW);
  assert.deepEqual([p.state, p.qty, p.notional, p.maxUsd, p.fee, p.deadline], ['ready', 0.00039, 24.49, 24.98, 0.02, s.trade.ticket.preparedAt + QUOTE_MS]);
  assert.deepEqual(p.fields.map(f => f[0]), ['venue', 'symbol', 'side', 'orderType', 'qty', 'limitPrice', 'maxNotional', 'deadline', 'nonce']);
  assert.deepEqual(p.fields.slice(0, 5), [['venue', 'Stand-in Exchange'], ['symbol', 'BTC/USDT'], ['side', 'buy'], ['orderType', 'market'], ['qty', '0.00039']]);
});

test('prepare refuses what the venue or the account would refuse, in words', () => {
  const text = s => prepare(s, NOW).text;
  assert.equal(text(ticket(fresh(), 'BTC', { amount: '150' })), '$152.46 is more than the most one order may be ($100.00).');
  assert.equal(text(ticket(fresh(), 'BTC', { amount: '5' })), 'Stand-in Exchange: the smallest order in BTC/USDT is 0.0001 BTC ($6.28 at 62,803.6)');
  assert.equal(text(ticket(fresh(), 'BTC', { amount: '25', orderType: 'limit' })), 'Type the limit price.');
  assert.equal(text(ticket(fresh(), 'BTC', {})), 'Type an amount.');
  assert.equal(text(ticket(fresh(), 'NVDA', { amount: '0.3', unit: 'qty' }, { side: 'sell' })), 'Sells only what you hold · 0.2402 held.');
  const poor = { ...fresh(), account: { ...fresh().account, cash: { ...fresh().account.cash, 'Stand-in Exchange': 10 } } };
  assert.equal(text(ticket(poor, 'BTC', { amount: '25' })), 'Stand-in Exchange has $10.00 to trade with.');
  const poly = R.venueConnected(fresh(), 'Polymarket');
  assert.equal(text(ticket(poly, 'FED-DEC', { amount: '10', orderType: 'limit', limit: '120' })), 'A price in cents is between 0 and 100: a contract pays $1.00 at most.');
  assert.deepEqual([prepare(ticket(fresh(), 'BTC', { amount: '25' }), NOW).state, prepare(ticket(fresh(), 'BTC', { amount: '150' }), NOW).state], ['ready', 'refused']);
});

test('openTicket picks the venue: the best able one, where it is held for a sell, none for a public-only market', () => {
  const b = R.openTicket(fresh(), { id: 'btc', now: NOW });
  assert.deepEqual([b.trade.ticket.id, b.trade.ticket.venue, b.trade.ticket.kind, b.trade.kind], ['BTC', 'Stand-in Exchange', 'crypto', 'crypto']);
  assert.equal(R.openTicket(fresh(), { id: 'FED-DEC', now: NOW }).trade.ticket.venue, null);
  const n = R.openTicket(fresh(), { id: 'NVDA', side: 'sell', now: NOW });
  assert.deepEqual([n.trade.ticket.venue, n.trade.ticket.side, n.trade.kind], ['Stand-in Broker', 'sell', 'stocks']);
  assert.equal(R.openTicket(fresh(), { id: 'BTC', venue: 'Stand-in Wallet', now: NOW }).trade.ticket.venue, 'Stand-in Wallet');
  const s = fresh();
  assert.equal(R.openTicket(s, { id: 'USDC', now: NOW }), s, 'nothing to trade on a stablecoin');
  assert.equal(R.openTicket(s, { id: 'NOPE', now: NOW }), s);
  assert.equal(R.closeTicket(b).trade.ticket, null);
});

test('setTicket: a change prepares the order again and clears the last word; no change, no new state; unknown fields refused', () => {
  const s = R.openTicket(fresh(), { id: 'BTC', now: NOW });
  const t = R.setTicket(s, { field: 'amount', value: '25', now: NOW + 1 });
  assert.deepEqual([t.trade.ticket.amount, t.trade.ticket.preparedAt, t.trade.ticket.said], ['25', NOW + 1, null]);
  assert.equal(R.setTicket(t, { field: 'amount', value: '25', now: NOW + 2 }), t);
  assert.equal(R.setTicket(t, { field: 'venue', value: 'x', now: NOW }), t);
  assert.equal(R.setTicket(t, { field: 'unit', value: 'yen', now: NOW }), t);
  assert.equal(R.ticketVenue(t, { venue: 'Coinbase', now: NOW }), t, 'a public venue cannot be picked before it connects');
  assert.equal(R.ticketVenue(t, { venue: 'Stand-in Wallet', now: NOW }).trade.ticket.venue, 'Stand-in Wallet');
  assert.equal(R.ticketSide(t, { side: 'sell', now: NOW }).trade.ticket.side, 'sell');
  assert.equal(R.toggleSigns(t).trade.ticket.signs, true);
});

test('Sign and place: the order is pending under a new id; a second press places nothing; a stale quote must be prepared again', () => {
  const s = ticket(fresh(), 'BTC', { amount: '25' });
  assert.equal(R.placeOrder(R.openTicket(fresh(), { id: 'BTC', now: NOW }), { now: NOW }).account.orders.length, 4, 'nothing to place without an amount');
  const p = R.placeOrder(s, { now: NOW });
  assert.deepEqual([p.account.orders[0].id, p.account.orders[0].status, p.account.orders[0].by, p.trade.ticket.placing, p.counters.ord], ['ord-0010', 'pending', 'you', 'ord-0010', 10]);
  assert.equal(R.placeOrder(p, { now: NOW }), p);
  const late = R.placeOrder(s, { now: s.trade.ticket.preparedAt + QUOTE_MS });
  assert.equal(late.account.orders.length, 4);
  assert.deepEqual(late.trade.ticket.said, { ok: false, text: 'this order was good for ten minutes after it was prepared: prepare it again' });
});

test('a market buy fills at the ask: holding, cash, statement, net worth and the allocation all move; the ticket says so and clears', () => {
  const s = filled(R.placeOrder(ticket(fresh(), 'BTC', { amount: '25' }), { now: NOW }));
  const o = s.account.orders[0];
  assert.deepEqual([o.status, o.price, o.fee, o.usd], ['filled', 62803.6, 0.02, 24.49]);
  assert.deepEqual(s.account.activity[0], { at: NOW, text: 'Fill · 0.00039 BTC @ 62,803.6 · ord-0010', amount: -24.51 });
  assert.deepEqual([held(s, 'BTC').qty, held(s, 'BTC').value], [0.05994, 3764.23]);
  assert.equal(s.account.cash['Stand-in Exchange'], 1158.22);
  assert.equal(s.account.netWorth, 12479.98);
  assert.deepEqual(s.account.alloc.map(x => x.pct), [29, 20, 30, 21]);
  assert.deepEqual(s.trade.ticket.said, { ok: true, text: 'Bought: ord-0010 · filled at 62,803.6 · fee $0.02' });
  assert.deepEqual([s.trade.ticket.placing, s.trade.ticket.amount], [null, '']);
  assert.equal(R.settleOrder(s, { id: 'ord-0010', now: NOW }), s, 'it settles once');
});

test('limits rest on the book below the ask and fill at the ask above it', () => {
  const rest = filled(R.placeOrder(ticket(fresh(), 'BTC', { amount: '25', orderType: 'limit', limit: '60000' }), { now: NOW }));
  assert.deepEqual([rest.account.orders[0].status, rest.account.orders[0].qty, rest.account.orders[0].note], ['open', 0.00041, "on Stand-in Exchange's book at 60,000"]);
  assert.equal(held(rest, 'BTC').qty, 0.05955);
  assert.equal(rest.trade.ticket.said.text, "Placed: ord-0010 · on Stand-in Exchange's book at 60,000");
  const fill = filled(R.placeOrder(ticket(fresh(), 'BTC', { amount: '25', orderType: 'limit', limit: '63000' }), { now: NOW }));
  assert.deepEqual([fill.account.orders[0].status, fill.account.orders[0].price], ['filled', 62803.6]);
});

test('sells, new holdings and the wallet: all of NVDA goes, SOL arrives, USDY is paid in USDC', () => {
  const sold = filled(R.placeOrder(ticket(fresh(), 'NVDA', { amount: '0.2402', unit: 'qty' }, { side: 'sell' }), { now: NOW }));
  assert.equal(held(sold, 'NVDA'), undefined);
  assert.equal(sold.account.cash['Stand-in Broker'], 2545.01);
  assert.equal(sold.account.netWorth, 12480);
  assert.equal(sold.trade.ticket.said.text, 'Sold: ord-0010 · filled at 187.38');
  const sol = filled(R.placeOrder(ticket(fresh(), 'SOL', { amount: '20' }), { now: NOW }));
  assert.deepEqual([held(sol, 'SOL').key, held(sol, 'SOL').qty, held(sol, 'SOL').value], ['crypto:SOL', 0.136, 19.99]);
  const usdy = filled(R.placeOrder(ticket(fresh(), 'USDY', { amount: '50' }), { now: NOW }));
  assert.equal(held(usdy, 'USDC').qty, 2439.86);
  assert.equal(held(usdy, 'USDY').value, 49.98);
  assert.ok(usdy.account.alloc.some(x => x.token === 'rwa'));
});

test('connecting a public venue brings its stand-in cash; a prediction then buys contracts; a waiting ticket takes the venue', () => {
  const poly = R.venueConnected(fresh(), 'Polymarket');
  assert.deepEqual([poly.account.cash.Polymarket, poly.account.netWorth], [300, 12780]);
  assert.deepEqual(poly.account.venues.at(-1), { name: 'Polymarket', line: 'Connected · stand-in · Gravit: read only', state: 'Healthy' });
  const yes = filled(R.placeOrder(ticket(poly, 'FED-DEC', { amount: '10' }), { now: NOW }));
  const h = held(yes, 'FED-DEC');
  assert.deepEqual([h.outcome, h.qty, h.value, h.venue], ['Yes', 15, 9.3, 'Polymarket']);
  assert.equal(yes.account.netWorth, 12779.85);
  assert.equal(yes.account.activity[0].text, 'Fill · 15 FED-DEC Yes @ 63¢ · ord-0010');
  assert.ok(yes.account.alloc.some(x => x.token === 'event'));
  const waiting = R.openTicket(fresh(), { id: 'DOGE', now: NOW });
  assert.equal(R.venueConnected(waiting, 'Coinbase').trade.ticket.venue, 'Coinbase');
});

test('cancelling: your own open order at once; Gravit\'s leaves a line in its conversation; a filled one stays', () => {
  const mine = filled(R.placeOrder(ticket(fresh(), 'BTC', { amount: '25', orderType: 'limit', limit: '60000' }), { now: NOW }));
  assert.equal(R.cancelOrder(mine, { id: 'ord-0010', now: NOW }).account.orders[0].status, 'canceled');
  const ko = R.cancelOrder(fresh(), { id: 'ord-0008', now: NOW });
  assert.equal(ko.account.orders.find(o => o.id === 'ord-0008').status, 'canceled');
  const c4 = ko.conversations.find(c => c.id === 'c-4');
  assert.deepEqual([c4.messages.at(-1).from, c4.messages.at(-1).text, c4.unread], ['system', '你在 Trade 里撤了 ord-0008（KO limit 58.2）。', true]);
  const s = fresh();
  assert.equal(R.cancelOrder(s, { id: 'ord-0001', now: NOW }), s);
});

test('moving funds and the wallet keep quantity and value together; net worth stays', () => {
  const p = R.openPanel(R.nav(fresh(), { screen: 'account', tab: 'portfolio' }), 'move');
  const moved = R.moveFunds(p, { from: 'Stand-in Wallet', to: 'Stand-in Exchange', asset: 'USDC', amount: '200', now: NOW });
  for (const h of moved.account.holdings.filter(x => x.name === 'USDC')) assert.equal(h.qty, h.value);
  assert.equal(moved.account.netWorth, 12480);
  const top = R.commitEdit(R.startEdit(fresh(), { kind: 'wallet', dir: 'in' }), { values: { amount: '10' }, now: NOW });
  assert.deepEqual([held(top, 'USDC').qty, held(top, 'USDC').value, top.account.netWorth], [2480, 2480, 12480]);
});

test('Hand to Gravit words the ticket for the composer; mentions keeps ETH apart from ETH-3K', () => {
  const s = ticket(fresh(), 'BTC', { amount: '25' });
  assert.deepEqual(handOver(s, s.trade.ticket), { words: '买 $25 的 BTC', venue: 'Stand-in Exchange', perOrder: 25, attach: true });
  const poly = ticket(R.venueConnected(fresh(), 'Polymarket'), 'FED-DEC', { amount: '10' });
  assert.equal(handOver(poly, poly.trade.ticket).attach, false, 'Gravit has no limit at Polymarket');
  assert.equal(mentions('小仓位 BTC，$70k 以下', 'BTC'), true);
  assert.equal(mentions('Will ETH-3K close', 'ETH'), false);
  assert.equal(mentions('Fill · 0.00008 BTC @ 62,500', 'BTC'), true);
});
