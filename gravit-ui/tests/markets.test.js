// gravit-ui/tests/markets.test.js — the stand-in market catalogue, its price series, and the Markets screen with its drawer
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { INSTRUMENTS, TABS, KINDS, instrument, instrumentOf, listed, kindOf, seriesOf } from '../js/data/markets.js';
import { VENUES, CONNECTABLE } from '../js/data/seed.js';
import { HOUR } from '../js/time.js';
import { renderMarkets } from '../js/render/markets.js';
import { reducers as R } from '../js/reducers/index.js';
import { seed } from '../js/data/seed.js';

const NOW = new Date(2026, 9, 9, 14, 7).getTime();

test('the catalogue: 17 instruments with unique ids and keys; every listed one trades somewhere we know; bids under asks', () => {
  assert.equal(INSTRUMENTS.length, 17);
  assert.equal(new Set(INSTRUMENTS.map(i => i.id)).size, 17);
  assert.equal(new Set(INSTRUMENTS.map(i => i.key)).size, 17);
  for (const i of INSTRUMENTS.filter(listed)) {
    assert.ok(i.at.length >= 1, i.id);
    for (const leg of i.at) assert.ok([...VENUES, ...CONNECTABLE].includes(leg.venue), `${i.id} at ${leg.venue}`);
    if (i.kind === 'event') {
      assert.equal(i.outcomes.length, 2, i.id);
      for (const o of i.outcomes) assert.ok(o.bid < o.ask && o.ask <= 1, `${i.id} ${o.label}`);
    } else for (const leg of i.at) assert.ok(leg.bid < leg.ask, `${i.id} at ${leg.venue}`);
  }
  assert.equal(instrument('btc').id, 'BTC');
  assert.equal(instrument('nope'), null);
  assert.equal(instrumentOf('AAPL').key, 'equity:AAPL');
  assert.equal(listed(instrument('USDC')), false, 'USDC has a drawer but no row');
  assert.deepEqual(TABS.map(t => t[0]), ['all', 'crypto', 'stocks', 'rwas', 'predictions']);
  assert.deepEqual(KINDS.map(k => k.id), ['crypto', 'stocks', 'rwas', 'predictions']);
  assert.deepEqual(['BTC', 'NVDA', 'USDY', 'FED-DEC'].map(id => kindOf(instrument(id))), ['crypto', 'stocks', 'rwas', 'predictions']);
  assert.equal(instrument('ETH-3K').tabs.includes('crypto'), true, 'a crypto prediction shows under Crypto too');
});

test('a price series: 48 bars a step apart, ending on the price, the same every time; a prediction stays between 0 and 1', () => {
  const s = seriesOf(instrument('BTC'), '1h', NOW);
  assert.equal(s.length, 48);
  assert.equal(s.at(-1).c, 62800);
  assert.equal(s[1].t - s[0].t, HOUR);
  assert.deepEqual(seriesOf(instrument('BTC'), '1h', NOW), s);
  assert.notDeepEqual(seriesOf(instrument('BTC'), '1d', NOW).map(b => b.c), s.map(b => b.c));
  for (const b of seriesOf(instrument('FED-DEC'), '1d', NOW)) assert.ok(b.c > 0 && b.c < 1);
});

const count = (h, re) => (h.match(re) ?? []).length;
const mkts = (s = seed(NOW)) => R.nav(s, { screen: 'markets', id: null });
const rows = h => [...h.matchAll(/<tr data-id="([^"]+)"/g)].map(m => m[1]);

test('Markets: the head with its search, tabs that have rows, one table with one action per row; no small print', () => {
  const h = renderMarkets(mkts(), NOW);
  assert.match(h, /^<main class="main mkts">/);
  assert.match(h, /<h1 class="head-title">Markets<\/h1>/);
  assert.match(h, /<input id="mq" type="search"[^>]*placeholder="Search markets" data-action="mkQuery"/);
  assert.deepEqual([...h.matchAll(/class="mk-tab" data-action="mkTab" data-value="[^"]*" aria-pressed="(?:true|false)">([^<]+)</g)].map(m => m[1]), ['All', 'Crypto', 'Stocks', 'RWAs', 'Predictions', 'Watching']);
  assert.match(h, /data-value="all" aria-pressed="true">All</);
  assert.doesNotMatch(h, /Perps|Pre-IPO/);
  assert.equal(rows(h).length, 16, 'every listed market, USDC excepted');
  assert.match(h, /data-action="tradeFrom" data-id="BTC">Trade</);
  assert.match(h, /data-action="connectVenue" data-name="Coinbase">[\s\S]*?Connect to trade<\/button>/);
  assert.match(h, /<tr data-id="FED-DEC">[\s\S]*?62¢<span class="mk-out-l"> Yes<\/span>/);
  assert.match(h, /data-action="toggleWatch" data-id="BTC" aria-pressed="true" aria-label="Stop watching Bitcoin"/);
  assert.match(h, /data-action="toggleWatch" data-id="ETH" aria-pressed="false" aria-label="Watch Ethereum"/);
  assert.match(h, /<td class="mk-c-where"><span class="mk-where"><span class="mk-v">Stand-in Exchange<\/span> · <span class="mk-v">Stand-in Wallet<\/span> <span class="mk-more">\+1<\/span><\/span><\/td>/);
  assert.match(h, /<td class="r">\$62,800\.00<\/td>/);
  assert.match(h, /<td class="r mk-c-vol">\$1\.9B<\/td>/);
  assert.doesNotMatch(h, /Why these|Not shown|Read-only server|24h at/);
});

test('sorting: most traded, biggest moves, closing soonest', () => {
  assert.equal(rows(renderMarkets(mkts(), NOW))[0], 'NVDA');
  assert.equal(rows(renderMarkets(R.setMarketsSort(mkts(), 'Biggest moves'), NOW))[0], 'DOGE');
  assert.equal(rows(renderMarkets(R.setMarketsSort(mkts(), 'Closing soonest'), NOW))[0], 'CPI-NOV');
  assert.match(renderMarkets(mkts(), NOW), /class="seg-item pressed" aria-pressed="true" data-action="mkSort" data-value="Most traded"/);
});

test('Predictions as cards with Yes and No at the ask; Crypto shows its prediction card above the coins', () => {
  const p = renderMarkets(R.setMarketsTab(mkts(), 'predictions'), NOW);
  assert.match(p, /<section class="mk-cards" aria-label="Predictions">/);
  assert.equal(count(p, /class="mk-card"/g), 4);
  assert.match(p, /<div class="mk-card-top"><span><\/span><span class="mk-close" data-close="2026-12-09T19:00:00Z">Closes in \d+d \d\d:\d\d<\/span><\/div>/);
  assert.match(p, /data-action="connectVenue" data-name="Polymarket">Yes · 63¢<span class="sr-only">: connect Polymarket to trade<\/span><\/button>/);
  assert.match(p, />No · 39¢</);
  const c = renderMarkets(R.setMarketsTab(mkts(), 'crypto'), NOW);
  assert.equal(count(c, /class="mk-card"/g), 1);
  assert.match(c, /data-id="ETH-3K"/);
  assert.equal(rows(c).length, 6);
});

test('Watching: the starred markets without Volume; a search with All results and Clear; nothing found says so', () => {
  const w = renderMarkets(R.setMarketsTab(mkts(), 'watching'), NOW);
  assert.deepEqual(rows(w), ['BTC', 'FED-DEC', 'DOGE']);
  assert.doesNotMatch(w, />Volume</);
  const q = renderMarkets(R.setMarketsQuery(mkts(), 'sol'), NOW);
  assert.match(q, /<p class="mk-q">1 market for “sol” <button type="button" class="mk-clear" data-action="mkClear">Clear<\/button><\/p>/);
  assert.match(q, /data-value="" aria-pressed="true">All results</);
  assert.deepEqual(rows(q), ['SOL']);
  assert.match(renderMarkets(R.setMarketsQuery(mkts(), 'zzz'), NOW), /<p class="mk-empty">Nothing matches “zzz” at your venues or in the public listings\.<\/p>/);
  const unstar = R.toggleWatch(R.toggleWatch(R.toggleWatch(R.setMarketsTab(mkts(), 'watching'), 'BTC'), 'FED-DEC'), 'DOGE');
  assert.match(renderMarkets(unstar, NOW), /data-value="all" aria-pressed="true">All</, 'with nothing starred Watching goes and All shows');
});

test('the BTC drawer: price and facts, the chart, across venues with the best one, what you hold, Gravit on it, the statement', () => {
  const s = R.nav(seed(NOW), { screen: 'markets', id: 'btc' });
  assert.deepEqual(s.route, { screen: 'markets', id: 'BTC' });
  const h = renderMarkets(s, NOW);
  assert.match(h, /^<main class="main mkts with-drawer">/);
  assert.match(h, /<aside class="drawer mk-drawer" aria-label="Bitcoin"><div class="drawer-head"><h2>Bitcoin<\/h2><button type="button" class="close-key" data-action="closeMarket" aria-label="Close">×<\/button>/);
  assert.match(h, /<div class="mk-d-px"><span class="mk-big">\$62,800\.00<\/span><span class="up">/);
  for (const dt of ['Bid', 'Ask', 'Volume 24h']) assert.match(h, new RegExp(`<dt>${dt}</dt>`));
  assert.match(h, /<svg class="mk-chart" viewBox="0 0 400 140" preserveAspectRatio="none" role="img" aria-label="Price at Stand-in Exchange, 1h bars[^"]*"><path class="mk-chart-area" d="M/);
  assert.match(h, /class="seg-item pressed" aria-pressed="true" data-action="mkInterval" data-value="1h"/);
  const across = h.slice(h.indexOf('mk-across'), h.indexOf('</table>', h.indexOf('mk-across')));
  assert.equal(count(across, /<tr>/g), 4, 'a head row and three venues');
  assert.match(across, /Stand-in Exchange <span class="mk-tag up">Best<\/span>/);
  assert.match(across, /Coinbase <span class="mk-tag">Public<\/span>/);
  assert.doesNotMatch(across, /connectVenue/, 'Coinbase needs no connecting while the account trades BTC elsewhere');
  assert.match(h, /<div class="mk-t1">0\.05955 BTC · \$3,739\.74<\/div><div class="mk-t2">Stand-in Exchange<\/div>/);
  assert.match(h, /<a class="mk-line" href="#\/messages\/c-1" data-action="open" data-id="c-1">/);
  assert.match(h, /Fill · 0\.00008 BTC @ 62,500 · ord-0001/);
  assert.match(h, /data-action="tradeFrom" data-id="BTC">Buy<\/button>/);
  assert.match(h, /data-action="tradeFrom" data-id="BTC" data-side="sell" data-venue="Stand-in Exchange">Sell<\/button>/);
  assert.match(h, /data-action="handToGravit" data-id="BTC">/);
  assert.match(h, /class="btn mk-on" data-action="toggleWatch" data-id="BTC" aria-pressed="true">[\s\S]*?Watching<\/button>/);
});

test('the KO drawer: Gravit\'s order on the book can be cancelled, and asks first', () => {
  const s = R.nav(seed(NOW), { screen: 'markets', id: 'KO' });
  const h = renderMarkets(s, NOW);
  assert.match(h, /<div class="mk-t1">Buy 0\.4295 KO · limit 58\.2<\/div><div class="mk-t2">Stand-in Broker · Gravit · 0 of 0\.4295 filled<\/div><\/div><button type="button" class="btn-sm" data-action="cancelOrder" data-id="ord-0008">Cancel<\/button>/);
  const asking = renderMarkets(R.askConfirm(s, { action: 'cancelOrder', id: 'ord-0008' }), NOW);
  assert.match(asking, /class="confirm"/);
  assert.match(asking, /Yes, cancel the order/);
  assert.match(h, /href="#\/messages\/c-4"/);
});

test('the Fed drawer: two outcomes, Connect to trade until Polymarket connects, then Buy Yes and Buy No; USDC has no chart', () => {
  const s = R.nav(seed(NOW), { screen: 'markets', id: 'FED-DEC' });
  const h = renderMarkets(s, NOW);
  assert.equal(count(h, /class="mk-out"/g), 2);
  assert.match(h, /<div class="mk-out"><span class="mk-out-lbl">Yes<\/span><span class="mk-out-px">63¢<\/span>[\s\S]*?data-action="connectVenue" data-name="Polymarket"/);
  assert.doesNotMatch(h, /Buy Yes/);
  assert.match(h, /<dt>Closes<\/dt>/);
  const on = renderMarkets(R.venueConnected(s, 'Polymarket'), NOW);
  assert.match(on, /class="mk-yes mk-buy" data-action="tradeFrom" data-id="FED-DEC" data-outcome="0">Buy Yes<\/button>/);
  assert.match(on, /class="mk-no mk-buy" data-action="tradeFrom" data-id="FED-DEC" data-outcome="1">Buy No<\/button>/);
  const page = renderMarkets(R.nav(seed(NOW), { screen: 'markets', id: 'USDC' }), NOW);
  const usdc = page.slice(page.indexOf('<aside class="drawer mk-drawer"'));
  assert.doesNotMatch(usdc, /aria-label="Price history"|aria-label="Across venues"|data-action="tradeFrom"/);
  assert.match(usdc, /<div class="mk-t1">2,490 USDC · \$2,490\.00<\/div>/);
  assert.equal(R.nav(seed(NOW), { screen: 'markets', id: 'NOPE' }).route.id, null);
});

// ---- review fixes

test('a tab starts from Most traded, as Linqi\'s does; a sort the tab does not offer shows Most traded', () => {
  const m = R.setMarketsSort(mkts(), 'Closing soonest');
  assert.equal(R.setMarketsTab(m, 'stocks').markets.sort, 'volume');
  const stuck = { ...mkts(), markets: { ...mkts().markets, tab: 'stocks', sort: 'closing' } };
  const h = renderMarkets(stuck, NOW);
  assert.match(h, /class="seg-item pressed" aria-pressed="true" data-action="mkSort" data-value="Most traded"/);
  assert.deepEqual(rows(h), ['SPY', 'TSLA', 'AAPL', 'NVDA', 'KO'].sort((a, b) => ({ NVDA: 1, SPY: 2, TSLA: 3, AAPL: 4, KO: 5 })[a] - ({ NVDA: 1, SPY: 2, TSLA: 3, AAPL: 4, KO: 5 })[b]));
});

test('the search count is what the tab shows', () => {
  const s = R.setMarketsQuery(R.setMarketsTab(mkts(), 'stocks'), 'a');
  const h = renderMarkets(s, NOW);
  const shown = rows(h).length + count(h, /class="mk-card"/g);
  assert.match(h, new RegExp(`<p class="mk-q">${shown} markets? for “a”`));
  const all = renderMarkets(R.setMarketsQuery(mkts(), 'a'), NOW);
  assert.ok(rows(all).length > shown, 'the test means something: other tabs match too');
});

test('Gravit asks in the drawer without repeating Your call', () => {
  const s = R.append(R.nav(seed(NOW), { screen: 'markets', id: 'BTC' }), { convId: 'c-1', msg: { from: 'gravit', kind: 'card', text: 'Your call: add $25', data: { title: 'Your call: add $25', rows: [] } }, at: NOW });
  assert.match(renderMarkets(s, NOW), /<div class="mk-t1">Gravit asks: add \$25<\/div>/);
});
