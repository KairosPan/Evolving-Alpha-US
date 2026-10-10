// gravit-ui/tests/market-fmt.test.js — Linqi's market formatters, as Markets and Trade print numbers
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { usd, dollars, px, cents, vol, qtyFmt, closeIn, leftWords, chgHtml, floorTo, round2 } from '../js/market-fmt.js';
import { MIN, HOUR, DAY } from '../js/time.js';

test('dollars and prices: two decimals at a dollar and up, four figures under it; a dash for nothing', () => {
  assert.equal(usd(62800), '$62,800.00');
  assert.equal(usd(0.12136), '$0.1214');
  assert.equal(usd(null), '—');
  assert.equal(usd(NaN), '—');
  assert.equal(dollars(-5), '-$5.00');
  assert.equal(dollars(152.456), '$152.46');
  assert.equal(px(62803.6), '62,803.6');
  assert.equal(px(0.12144), '0.12144');
  assert.equal(round2(24.485), 24.49);
});

test('cents and volume', () => {
  assert.equal(cents(0.62), '62¢');
  assert.equal(cents(0.625), '62.5¢');
  assert.equal(cents(0.63), '63¢');
  assert.equal(cents(1.2), '100¢');
  assert.equal(cents(-0.1), '0¢');
  assert.equal(vol(1.94e9), '$1.9B');
  assert.equal(vol(3.05e10), '$30.5B');
  assert.equal(vol(1.2e8), '$120M');
  assert.equal(vol(880000), '$880k');
  assert.equal(vol(undefined), '—');
});

test('countdowns: days and hours:minutes, then hours:minutes:seconds, then Closed; the signature window in minutes', () => {
  assert.equal(closeIn(2 * DAY + 4 * HOUR + 12 * MIN + 30_000), 'Closes in 2d 04:12');
  assert.equal(closeIn(6 * HOUR + 48 * MIN + 10_000), 'Closes in 06:48:10');
  assert.equal(closeIn(0), 'Closed');
  assert.equal(closeIn(-5), 'Closed');
  assert.equal(leftWords(599_000), 'Your signature is good for 9:59 more.');
  assert.equal(leftWords(600_000), 'Your signature is good for 10:00 more.');
});

test('a change: an arrow and words for screen readers; one decimal from 1%, two under; cents; flat at zero or nothing', () => {
  const up = chgHtml(1.2);
  assert.equal(up, '<span class="up"><span aria-hidden="true">▲</span><span class="sr-only">up</span> 1.2%</span>');
  assert.equal(chgHtml(-0.4), '<span class="down"><span aria-hidden="true">▼</span><span class="sr-only">down</span> 0.40%</span>');
  assert.match(chgHtml(4, '¢'), /▲<\/span><span class="sr-only">up<\/span> 4¢<\/span>$/);
  assert.equal(chgHtml(0), '<span class="flat">0.00%</span>');
  assert.equal(chgHtml(null), '<span class="flat">—</span>');
});

test('quantities floor to the venue step and print without trailing zeros', () => {
  assert.equal(floorTo(25 / 62803.6, 0.00001), 0.00039);
  assert.equal(floorTo(10 / 0.63, 1), 15);
  assert.equal(floorTo(50 / 1.1055, 0.01), 45.22);
  assert.equal(qtyFmt(2490), '2,490');
  assert.equal(qtyFmt(0.00039), '0.00039');
});
