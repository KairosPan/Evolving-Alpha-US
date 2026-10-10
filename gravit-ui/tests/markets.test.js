// gravit-ui/tests/markets.test.js — the stand-in market catalogue, its price series, and the Markets screen with its drawer
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { INSTRUMENTS, TABS, KINDS, instrument, instrumentOf, listed, kindOf, seriesOf } from '../js/data/markets.js';
import { VENUES, CONNECTABLE } from '../js/data/seed.js';
import { HOUR } from '../js/time.js';

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
