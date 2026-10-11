// gravit-ui/tests/thread.test.js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderThread, renderMessage, chip, key, ticker, candles } from '../js/render/thread.js';
import { seed } from '../js/data/seed.js';
import { director, CANDLES } from '../js/driver.js';
import { message } from '../js/messages.js';

const NOW = new Date(2026, 9, 9, 14, 7).getTime();
const count = (h, re) => (h.match(re) ?? []).length;
const s = seed(NOW);
const btc = s.conversations[0];
const group = s.conversations[3];
const ctx = { id: 'c-1', kind: 'gravit' };

test('the BTC thread: dividers, owner bubbles right, Gravit left, an answered card without keys, a live limit with ✓ ✗, an install with + ✗', () => {
  const h = renderThread(btc, s, NOW);
  assert.match(h, /class="divider">Today 14:01</);
  assert.equal(count(h, /class="divider"/g), 1, 'messages inside 15 minutes share one divider');
  assert.equal(count(h, /class="msg you"/g), 2);
  assert.equal(count(h, /class="msg left"/g), 5);
  assert.match(h, /class="bubble you">Buy a small BTC position/);
  assert.match(h, /class="card orange"/);
  assert.doesNotMatch(h, /answer by/, 'the seeded card is answered: no deadline left to meet');
  assert.match(h, /class="card orange"><div class="card-head"><div class="card-title">Your call: buy 0.00008 BTC<\/div><span class="chip up">Approved<\/span>/);
  const live = renderMessage({ id: 'm-x', at: NOW, ...message('gravit', 'card', 'Your call', { title: 'Your call', by: NOW + 26 * 60_000 }) }, ctx, s);
  assert.match(live, /<span class="chip warn">answer by 14:33<\/span>/, 'a card still waiting carries its deadline');
  const cardPart = h.slice(h.indexOf('card orange'), h.indexOf('class="msg you">', h.indexOf('card orange')));
  assert.doesNotMatch(cardPart, /class="key/, 'an answered card has no keys');
  assert.match(h, /class="bubble green"[\s\S]*?filled/);
  assert.match(h, /class="key no"[^>]*aria-label="Decline"[^>]*data-action="answer"[^>]*data-answer="declined"/);
  assert.match(h, /class="key yes"[^>]*aria-label="Grant"[^>]*data-answer="granted"/);
  assert.match(h, /class="key plus"[^>]*aria-label="Install"[^>]*data-action="installAsk"[^>]*data-plugin="news"/);
  assert.match(h, /class="key no"[^>]*aria-label="No"[^>]*data-answer="no"/);
  assert.doesNotMatch(h, /intent-0003/, 'no meta text in bubbles');
  assert.doesNotMatch(h, /sender-name/, 'no sender names outside groups');
});

test('a group thread writes the sender over bot bubbles and draws the two-order card', () => {
  const h = renderThread(group, s, NOW);
  assert.match(h, /class="sender-name">US politician bot</);
  assert.match(h, /class="sender-name">Buffett bot</);
  assert.match(h, /class="sender-name">Gravit</);
  assert.equal(count(h, /class="order-row"/g), 2);
  assert.match(h, /KO is on the book/);
});

test('every kind renders at its level', () => {
  const r = m => renderMessage({ id: 'm-x', at: NOW, ...m }, ctx, s);
  assert.match(r(message('gravit', 'text', 'hi')), /class="bubble grey">hi</);
  assert.match(r(message('fraud', 'signal', 'q', { source: 'Address fraud check' })), /class="card white"[\s\S]*Address fraud check[\s\S]*class="quote">q</);
  assert.match(r(message('gravit', 'refusal', '$30 is above', { code: 'E_MANDATE_PER_ORDER_CAP' })), /class="card red"[\s\S]*E_MANDATE_PER_ORDER_CAP/);
  assert.match(r(message('gravit', 'alert', 'bad')), /class="card red">[\s\S]*bad/);
  assert.match(r(message('gravit', 'receipt', 'x', { status: 'paid' })), /class="bubble green"[\s\S]*>paid</);
  assert.match(r(message('gravit', 'done', 'x', { foot: 'Ledger reconciled' })), /class="bubble green"[\s\S]*class="foot">Ledger reconciled/);
  assert.match(r(message('politician', 'proposal', 'x', { status: 'filled', ord: 'ord-0004', venue: 'Stand-in Broker' })), /class="bubble green"[\s\S]*ord-0004 · Stand-in Broker/);
  const brief = r(director.brief(NOW));
  assert.match(brief, /class="card white"/);
  assert.match(brief, /Morning brief · Oct 9/);
  assert.equal(count(brief, /class="ticker" href="#\/markets\/BTC"/g), 2);
  const ta = r(director.ta(NOW));
  assert.match(ta, /class="ticker" href="#\/markets\/NVDA"/);
  assert.equal(count(ta, /<rect /g), 14);
  assert.match(ta, /Resistance 192/);
  assert.match(r(message('gravit', 'breaking', 'x', { headline: 'H', body: 'B' })), /class="card red"[\s\S]*>Breaking<[\s\S]*H/);
  const call = r({ ...message('gravit', 'call', 'Call', { about: 'About BTC' }), answer: 'missed' });
  assert.match(call, /class="card red"[\s\S]*Missed/);
  assert.match(r({ from: 'system', kind: 'text', text: 'Delegation withdrawn.', data: {} }), /class="sysline">Delegation withdrawn\.</);
});

test('helpers: chip, key, ticker, candles', () => {
  assert.equal(chip('filled', 'up'), '<span class="chip up">filled</span>');
  assert.match(key('yes', 'Approve', { 'data-answer': 'approved' }), /^<button type="button" class="key yes" aria-label="Approve" data-answer="approved">/);
  assert.equal(ticker('KO'), `<a class="ticker" href="#/markets/KO">KO<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 6l6 6-6 6"></path></svg></a>`);
  const svg = candles({ candles: CANDLES, support: 178, resistance: 192, ticker: 'NVDA', tf: '4h' });
  assert.match(svg, /^<svg class="kline" viewBox="0 0 300 68"/);
  assert.match(svg, /stroke="var\(--up\)"/);
  assert.match(svg, /fill="var\(--down\)"/);
});

test('a stopped conversation shows no answer keys', async () => {
  const { reducers: R } = await import('../js/reducers/index.js');
  const stopped = R.stopGravit(seed(NOW), { convId: 'c-1', now: NOW });
  const h = renderThread(stopped.conversations[0], stopped, NOW);
  assert.doesNotMatch(h, /class="key /);
});
