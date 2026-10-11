// gravit-ui/tests/trade.test.js — the owner's hand orders after Linqi's Trade: prepare, sign and place, the stand-in fill, and what it changes
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { reducers as R } from '../js/reducers/index.js';
import { seed, SEED_VERSION } from '../js/data/seed.js';
import { QUOTE_MS } from '../js/data/markets.js';
import { prepare, revalue, legsOf, routeOf, handOver, mentions } from '../js/trade.js';
import { instrument } from '../js/data/markets.js';
import { renderTrade } from '../js/render/trade.js';

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
  assert.equal(text(ticket(fresh(), 'BTC', { amount: '150' })), '$149.90 is more than the most one order may be ($100.00).');
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
  assert.deepEqual([held(sol, 'SOL').key, held(sol, 'SOL').qty, held(sol, 'SOL').value], ['crypto:SOL', 0.133, 19.55]);
  const usdy = filled(R.placeOrder(ticket(fresh(), 'USDY', { amount: '50' }), { now: NOW }));
  assert.equal(held(usdy, 'USDC').qty, 2440.83);
  assert.equal(held(usdy, 'USDY').value, 49);
  assert.equal(held(usdy, 'USDY').venue, 'Stand-in Wallet');
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
  assert.equal(yes.account.alloc.reduce((a, x) => a + x.pct, 0), 100);
  const waiting = R.openTicket(fresh(), { id: 'DOGE', now: NOW });
  assert.equal(R.venueConnected(waiting, 'Coinbase').trade.ticket.venue, 'Coinbase');
});

test('cancelling: your own open order at once; Gravit\'s leaves a line in its conversation; a filled one stays', () => {
  const mine = filled(R.placeOrder(ticket(fresh(), 'BTC', { amount: '25', orderType: 'limit', limit: '60000' }), { now: NOW }));
  assert.equal(R.cancelOrder(mine, { id: 'ord-0010', now: NOW }).account.orders[0].status, 'canceled');
  const ko = R.cancelOrder(fresh(), { id: 'ord-0008', now: NOW });
  assert.equal(ko.account.orders.find(o => o.id === 'ord-0008').status, 'canceled');
  const c4 = ko.conversations.find(c => c.id === 'c-4');
  assert.deepEqual([c4.messages.at(-1).from, c4.messages.at(-1).text, c4.unread], ['system', 'You canceled ord-0008 (KO limit 58.2) in Trade.', true]);
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
  assert.deepEqual(handOver(s, s.trade.ticket), { words: 'Buy $25 of BTC', venue: 'Stand-in Exchange', perOrder: 25, attach: true });
  const poly = ticket(R.venueConnected(fresh(), 'Polymarket'), 'FED-DEC', { amount: '10' });
  assert.equal(handOver(poly, poly.trade.ticket).attach, false, 'Gravit has no limit at Polymarket');
  assert.equal(mentions('Small BTC position under $70k', 'BTC'), true);
  assert.equal(mentions('Will ETH-3K close', 'ETH'), false);
  assert.equal(mentions('Fill · 0.00008 BTC @ 62,500', 'BTC'), true);
});

// ---- the Trade screen

const count = (h, re) => (h.match(re) ?? []).length;
const onTrade = s => R.nav(s, { screen: 'trade' });

test('Trade at rest: the head with the cap, the four kinds, the picker, Under way with Gravit\'s order, and the resting ticket', () => {
  const h = renderTrade(onTrade(fresh()), NOW);
  assert.match(h, /^<main class="main trade"><div class="tp"><div class="tp-cols">/);
  assert.match(h, /<h1 class="head-title">Trade<\/h1><span class="chip up">Trading on · \$100 a move<\/span>/);
  assert.equal(count(h, /data-action="tradeKind"/g), 4);
  assert.match(h, /class="seg-item pressed" aria-pressed="true" data-action="tradeKind" data-value="crypto">[\s\S]*?Crypto<\/button>/);
  assert.match(h, /<div class="tk-pg-h">You hold<\/div><ul class="tk-list"><li><button type="button" class="tk-row" data-action="pickMarket" data-id="BTC" data-venue="Stand-in Exchange">/);
  const most = h.slice(h.indexOf('<div class="tk-pg-h">Most traded</div>'));
  assert.equal(count(most.slice(0, most.indexOf('</ul>')), /class="tk-row"/g), 6);
  assert.doesNotMatch(h, /tk-pg-h">Recent</);
  assert.match(h, /<b>Buy 0\.4295 KO · limit 58\.2<\/b>[\s\S]*?by Gravit, approved by you · <a class="link" href="#\/messages\/c-4" data-action="open" data-id="c-4">/);
  assert.match(h, /<span class="tk-st">Open<\/span><span class="tk-why">on Stand-in Broker&#39;s book at 58\.2<\/span>/);
  assert.match(h, /data-action="cancelOrder" data-id="ord-0008">Cancel</);
  assert.match(h, /<h2 class="tk-title">Pick a market<\/h2>/);
  assert.match(h, /data-action="handToGravit">[\s\S]*?Hand to Gravit instead<\/button>/);
  assert.doesNotMatch(h, /Sign and place/);
});

test('the BTC ticket: where with the best venue, Buy and Sell, Amount in dollars or BTC, Market or Limit; nothing to sign yet', () => {
  const h = renderTrade(onTrade(R.openTicket(fresh(), { id: 'BTC', now: NOW })), NOW);
  assert.match(h, /<h2 class="tk-title">Buy BTC<\/h2><\/div><button type="button" class="close-key" data-action="closeTicket" aria-label="Close the ticket">×<\/button>/);
  assert.equal(count(h, /class="tk-at" data-action="ticketVenue"/g), 2);
  assert.equal(count(h, /class="tk-at pub"/g), 1);
  assert.match(h, /data-venue="Stand-in Exchange" aria-pressed="true"><span><b>Stand-in Exchange<\/b><span class="mk-tag up">Best<\/span><\/span><span class="tk-at-r">\$62,803\.60<\/span><\/button>/);
  assert.match(h, /<span class="tk-at-r">\$62,861\.20<span class="tk-worse">0\.09% worse<\/span><\/span>/);
  assert.match(h, /class="tk-path">Type an amount\.</);
  assert.match(h, /<button type="submit" id="tk-go" class="btn-primary tk-go" disabled>Sign and place<\/button>/);
  for (const id of ['tk-amount', 'tk-unit', 'tk-type']) assert.match(h, new RegExp(`id="${id}"`));
  assert.match(h, /<option value="usd" selected>Dollars<\/option><option value="qty">BTC<\/option>/);
  assert.doesNotMatch(h, /id="tk-limit"/);
});

test('a ready quote: what it buys and pays, the fee, the ten minutes, What you sign; refused, placing and done say so', () => {
  const s = onTrade(ticket(fresh(), 'BTC', { amount: '25' }));
  const h = renderTrade(s, NOW);
  assert.match(h, /<div class="tk-big"><span>Buy 0\.00039 BTC<\/span><span>≈ \$24\.49<\/span><\/div>/);
  assert.match(h, /<div class="tk-path">BTC\/USDT at 62,803\.6 · up to \$24\.98 if the price moves<\/div>/);
  assert.match(h, /<div class="tk-path">fee about \$0\.02<\/div>/);
  assert.match(h, /<div class="tk-left" data-left>Your signature is good for 10:00 more\.<\/div>/);
  assert.match(h, /data-action="toggleSigns" aria-expanded="false">What you sign<\/button>/);
  assert.match(h, /<button type="submit" id="tk-go" class="btn-primary tk-go">Sign and place<\/button>/);
  assert.match(renderTrade(R.toggleSigns(s), NOW), /<pre class="tk-signs">venue: Stand-in Exchange\nsymbol: BTC\/USDT\nside: buy\norderType: market\nqty: 0\.00039\nlimitPrice: \nmaxNotional: 24\.98\n/);
  const cap = renderTrade(R.setTicket(s, { field: 'amount', value: '150', now: NOW }), NOW);
  assert.match(cap, /<div class="tk-msg no">\$149\.90 is more than the most one order may be \(\$100\.00\)\.<\/div>/);
  assert.match(cap, /id="tk-go" class="btn-primary tk-go" disabled/);
  const placing = R.placeOrder(s, { now: NOW });
  assert.match(renderTrade(placing, NOW), /<div class="tk-msg wait" role="status">Placing it at Stand-in Exchange…<\/div>/);
  assert.match(renderTrade(placing, NOW), /<span class="tk-st wait">On the way<\/span><span class="tk-why">Stand-in Exchange took it<\/span>/);
  assert.match(renderTrade(filled(placing), NOW), /<div class="tk-msg ok" role="status">Bought: ord-0010 · filled at 62,803\.6 · fee \$0\.02<\/div>/);
  assert.match(renderTrade(R.setTicket(s, { field: 'orderType', value: 'limit', now: NOW }), NOW), /<label class="field-label" for="tk-limit">Limit price<\/label><input id="tk-limit"[^>]*placeholder="62800"/);
});

test('a prediction ticket: Yes and No, a limit in cents, what the contracts pay; a public-only market waits for a venue', () => {
  const poly = onTrade(R.venueConnected(fresh(), 'Polymarket'));
  const h = renderTrade(ticket(poly, 'FED-DEC', { amount: '10' }), NOW);
  assert.match(h, /<div class="tk-out"><button type="button" class="mk-yes pressed" data-action="ticketOutcome" data-value="0" aria-pressed="true">Yes 63¢<\/button><button type="button" class="mk-no" data-action="ticketOutcome" data-value="1" aria-pressed="false">No 39¢<\/button><\/div>/);
  assert.match(h, /<b>15 contracts pay \$15\.00<\/b> if Yes · cost ≈ \$9\.45 · the market gives it 63%/);
  assert.match(h, /<option value="qty">Contracts<\/option>/);
  assert.match(renderTrade(ticket(poly, 'FED-DEC', { amount: '10', orderType: 'limit' }), NOW), /for="tk-limit">Limit \(¢\)<\/label><input id="tk-limit"[^>]*placeholder="63"/);
  const doge = renderTrade(onTrade(R.openTicket(fresh(), { id: 'DOGE', now: NOW })), NOW);
  assert.match(doge, /<div class="tk-at pub"><span><b>Coinbase<\/b><span class="mk-tag">Public<\/span><\/span><span class="tk-at-r">\$0\.1214<button type="button" class="link" data-action="connectVenue" data-name="Coinbase">Connect to trade<\/button><\/span><\/div>/);
  assert.doesNotMatch(doge, /id="tk-amount"/, 'no order to type before a venue can take it');
});

test('Stocks: what you hold; a card Gravit is waiting on shows under Under way; a search narrows the picker; no small print', () => {
  const st = renderTrade(onTrade(R.setTradeKind(fresh(), 'stocks')), NOW);
  assert.match(st, /data-action="pickMarket" data-id="AAPL" data-venue="Stand-in Broker"/);
  assert.match(st, /data-action="pickMarket" data-id="NVDA" data-venue="Stand-in Broker"/);
  const asked = R.append(onTrade(fresh()), { convId: 'c-1', msg: { from: 'gravit', kind: 'card', text: 'Your call: add $25', data: { title: 'Your call: add $25', by: NOW + 600000, rows: [] } }, at: NOW });
  const h = renderTrade(asked, NOW);
  assert.match(h, /<b>Your call: add \$25<\/b>/, 'the card speaks for itself');
  assert.match(h, /<span class="tk-st warn">Waiting for you<\/span>/);
  assert.match(h, /<a class="btn-sm" href="#\/messages\/c-1" data-action="open" data-id="c-1">Review<\/a>/);
  const q = renderTrade(onTrade(R.setTradeQuery(fresh(), 'sol')), NOW);
  assert.match(q, /<div class="tk-pg-h">Results for “sol”<\/div>/);
  assert.doesNotMatch(q, /tk-pg-h">You hold</);
  assert.doesNotMatch(h + st, /Each contract pays|Becomes a stock perpetual|Its own signature|Your words go to the agent|trade from here/);
});

// ---- Markets and Trade review fixes

test('a limit sell is worth what it will fill at, never less than the bid, so the cap holds', () => {
  const s = ticket(fresh(), 'AAPL', { amount: '10', unit: 'qty', orderType: 'limit', limit: '10' }, { side: 'sell' });
  const p = prepare(s, NOW);
  assert.deepEqual([p.state, p.text], ['refused', '$2,283.80 is more than the most one order may be ($100.00).']);
});

test('a market buy in dollars is sized at the worst price it may pay, so $100 fits $100 a move', () => {
  const p = prepare(ticket(fresh(), 'BTC', { amount: '100' }), NOW);
  assert.deepEqual([p.state, p.qty, p.maxUsd], ['ready', 0.00156, 99.93]);
  assert.ok(p.maxUsd <= 100);
});

test('the allocation bar leaves out a class that rounds to 0%', () => {
  const tiny = filled(R.placeOrder(ticket(fresh(), 'USDY', { amount: '5' }), { now: NOW }));
  assert.ok(tiny.account.holdings.some(h => h.name === 'USDY'));
  assert.equal(tiny.account.alloc.some(x => x.pct === 0), false);
  assert.equal(tiny.account.alloc.reduce((a, x) => a + x.pct, 0), 100);
});

test('moving all of a holding moves it whole: no negative quantity is left behind', () => {
  const p = R.openPanel(R.nav(fresh(), { screen: 'account', tab: 'portfolio' }), 'move');
  const m = R.moveFunds(p, { from: 'Stand-in Broker', to: 'Stand-in Exchange', asset: 'AAPL', amount: '2510.12', now: NOW });
  assert.equal(held(m, 'AAPL', 'Stand-in Broker'), undefined);
  assert.equal(held(m, 'AAPL', 'Stand-in Exchange').qty, 10.99);
  for (const h of m.account.holdings) assert.ok(h.qty == null || h.qty > 0, h.key);
});

test('a held prediction sells from its drawer and from the picker', async () => {
  const { renderMarkets } = await import('../js/render/markets.js');
  const yes = filled(R.placeOrder(ticket(R.venueConnected(fresh(), 'Polymarket'), 'FED-DEC', { amount: '10' }), { now: NOW }));
  const d = renderMarkets(R.nav(yes, { screen: 'markets', id: 'FED-DEC' }), NOW);
  assert.match(d, /data-action="tradeFrom" data-id="FED-DEC" data-side="sell" data-venue="Polymarket" data-outcome="0">Sell<\/button>/);
  const t = renderTrade(R.setTradeKind(R.nav(yes, { screen: 'trade' }), 'predictions'), NOW);
  assert.match(t, /<div class="tk-pg-h">You hold<\/div><ul class="tk-list"><li><button type="button" class="tk-row" data-action="pickMarket" data-id="FED-DEC" data-venue="Polymarket" data-side="sell" data-outcome="0">/);
  const sell = R.openTicket(yes, { id: 'FED-DEC', side: 'sell', outcome: 0, venue: 'Polymarket', now: NOW });
  assert.deepEqual([sell.trade.ticket.side, sell.trade.ticket.venue], ['sell', 'Polymarket']);
});
