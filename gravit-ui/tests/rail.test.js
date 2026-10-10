// gravit-ui/tests/rail.test.js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { avatar, logo, cluster, groupMark } from '../js/render/avatars.js';
import { renderRail, previewOf } from '../js/render/rail.js';
import { seed } from '../js/data/seed.js';
import { byId } from '../js/data/plugins.js';
import { reducers as R } from '../js/reducers/index.js';

const NOW = new Date(2026, 9, 9, 14, 7).getTime();
const count = (h, re) => (h.match(re) ?? []).length;

test('avatars: you, Gravit, a bot letter, a portrait slot, a glyph; logos are rounded squares', () => {
  assert.match(avatar('you', 28), /class="av av-you"[^>]*>你</);
  assert.match(avatar('gravit', 36), /class="av av-g" style="width:36px;height:36px/);
  assert.match(avatar('politician', 28), /av-letter tone-blue[^>]*>P</);
  assert.match(avatar('buffett', 28), /av-portrait tone-warm/);
  assert.match(avatar('buffett', 28), /aria-label="Buffett bot 的头像图"/);
  assert.match(avatar('fraud', 28), /av-glyph/);
  assert.match(avatar('p-1', 28, { plugins: { uploaded: [{ id: 'p-1', name: 'Zed', logo: { type: 'letter', text: 'Z' } }] } }), />Z</);
  assert.match(avatar('ghost', 28), />G</, 'an unknown sender gets its first letter');
  assert.match(logo(byId('telegram')), /border-radius:10px/);
  assert.equal(count(cluster(['gravit', 'politician', 'buffett'], 44), /class="cluster-item"/g), 3);
  assert.equal(count(groupMark(['gravit', 'politician', 'buffett'], 36), /class="av /g), 2);
});

test('previewOf: the last message in words, with the sender in a group', () => {
  const s = seed(NOW);
  assert.equal(previewOf(s.conversations[0]), 'Discover 里有个 News sentiment。装上我就能看情绪再加仓。');
  assert.equal(previewOf(s.conversations[1]), '披露：Pelosi 买 NVDA。照它买 $20，在额度里，直接成交。');
  assert.equal(previewOf(s.conversations[3]), 'Gravit：filled · NVDA $25 @ 187.40 · ord-0009 · 账本 #58');
  assert.equal(previewOf({ kind: 'gravit', messages: [] }), '');
});

test('renderRail: brand, Messages header with + and chevron, four rows, the current one, the unread dot, nav, phone/mail, Account', () => {
  const s = seed(NOW);
  const h = renderRail(s, NOW);
  assert.match(h, /<nav class="rail"/);
  assert.match(h, /Messages/);
  assert.match(h, /data-action="startDraft"[^>]*aria-label="New message"/);
  assert.match(h, /data-action="toggleRail"[^>]*aria-expanded="true"/);
  assert.equal(count(h, /class="row(?: current)?"/g), 4);
  assert.equal(count(h, /class="row current" aria-current="page" href="#\/messages\/c-1"/g), 1);
  assert.equal(count(h, /class="dot on"/g), 1, 'one unread conversation');
  assert.match(h, /row-time">14:07</);
  assert.match(h, /row-time">昨天</);
  assert.match(h, /href="#\/discover"/);
  assert.match(h, /href="#\/markets"/);
  assert.match(h, /href="#\/trade"/);
  assert.match(h, /aria-label="Phone"/);
  assert.match(h, /aria-label="Email"/);
  assert.match(h, /href="#\/account\/portfolio"[^>]*class="account"/);
  assert.match(h, /\$12,480 · Guard/);
  assert.doesNotMatch(h, /Trading on/);
});

test('renderRail: a draft row leads the list; the discover nav is current on that screen; collapsed hides the rows', () => {
  const d = R.startDraft(seed(NOW), { now: NOW });
  const h = renderRail(d, NOW);
  assert.match(h, /class="row current draft"/);
  assert.match(h, /New message/);
  assert.equal(count(h, /class="row(?: current)?(?: draft)?"/g), 5);
  const disc = renderRail(R.nav(seed(NOW), { screen: 'discover' }), NOW);
  assert.match(disc, /class="nav-item current" aria-current="page" href="#\/discover"/);
  const acct = renderRail(R.nav(seed(NOW), { screen: 'account', tab: 'memory' }), NOW);
  assert.match(acct, /class="account current" aria-current="page"/);
  const collapsed = renderRail(R.toggleRail(seed(NOW)), NOW);
  assert.match(collapsed, /aria-expanded="false"/);
  assert.equal(count(collapsed, /class="row/g), 0);
});
