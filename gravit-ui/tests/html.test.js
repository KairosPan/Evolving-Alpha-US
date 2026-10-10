// gravit-ui/tests/html.test.js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { esc, attrs, cls, money } from '../js/html.js';
import { icon, ICONS } from '../js/icons.js';

test('esc neutralises the five HTML characters', () => {
  assert.equal(esc(`<a href="x">it's & more</a>`), '&lt;a href=&quot;x&quot;&gt;it&#39;s &amp; more&lt;/a&gt;');
  assert.equal(esc(null), '');
  assert.equal(esc(12), '12');
});

test('attrs writes string and boolean attributes and skips null/false', () => {
  assert.equal(attrs({ id: 'say', disabled: true, hidden: false, title: null, 'data-n': 3 }), ' id="say" disabled data-n="3"');
  assert.equal(attrs({ 'aria-label': 'Sign & send' }), ' aria-label="Sign &amp; send"');
});

test('cls joins truthy names', () => {
  assert.equal(cls('row', false, 'current', null, ''), 'row current');
});

test('money formats dollars with grouping and up to two decimals', () => {
  assert.equal(money(12480), '$12,480');
  assert.equal(money(0.1), '$0.10');
  assert.equal(money(3740.5), '$3,740.50');
});

test('icon returns an inline svg, aria-hidden, sized as asked', () => {
  const s = icon('check', 14, 2.4);
  assert.match(s, /^<svg width="14" height="14" viewBox="0 0 24 24"/);
  assert.match(s, /stroke-width="2.4"/);
  assert.match(s, /aria-hidden="true"/);
  assert.match(s, /<path d="M5 12l5 5 9-10">/);
  assert.throws(() => icon('nope'), /unknown icon/);
  for (const name of ['chat', 'plus', 'chevDown', 'chevRight', 'compass', 'markets', 'trade', 'phone', 'phoneOff', 'mail', 'wallet', 'search', 'mic', 'send', 'check', 'x', 'trash', 'shield', 'bars', 'book', 'link', 'plane', 'wave', 'calendar', 'columns', 'arrows', 'flame', 'fileCheck', 'team', 'rewind', 'filter', 'pairs', 'upload', 'pencil', 'bell', 'sigma', 'clock', 'bolt']) {
    assert.ok(ICONS[name], name);
  }
});
