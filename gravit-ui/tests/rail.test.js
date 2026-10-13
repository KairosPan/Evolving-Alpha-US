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
  assert.match(avatar('you', 28), /class="av av-you"[^>]*>You</);
  assert.match(avatar('gravit', 36), /class="av av-g" style="width:36px;height:36px/);
  assert.match(avatar('politician', 28), /av-letter tone-blue[^>]*>P</);
  assert.match(avatar('buffett', 28), /av-portrait tone-warm/);
  assert.match(avatar('buffett', 28), /aria-label="Buffett bot’s portrait"/);
  assert.match(avatar('fraud', 28), /av-glyph/);
  assert.match(avatar('p-1', 28, { plugins: { uploaded: [{ id: 'p-1', name: 'Zed', logo: { type: 'letter', text: 'Z' } }] } }), />Z</);
  assert.match(avatar('ghost', 28), />G</, 'an unknown sender gets its first letter');
  assert.match(logo(byId('telegram')), /border-radius:10px/);
  assert.equal(count(cluster(['gravit', 'politician', 'buffett'], 44), /class="cluster-item"/g), 3);
  assert.equal(count(groupMark(['gravit', 'politician', 'buffett'], 36), /class="av /g), 2);
});

test('previewOf: the last message in words, with the sender in a group', () => {
  const s = seed(NOW);
  assert.equal(previewOf(s.conversations[0]), 'There is a News sentiment plugin in Discover. With it I can read sentiment before adding.');
  assert.equal(previewOf(s.conversations[1]), 'Disclosure: Pelosi bought NVDA. Bought $20 the same way, inside the limit, filled directly.');
  assert.equal(previewOf(s.conversations[3]), 'Gravit: filled · NVDA $25 @ 187.40 · ord-0009 · ledger #58');
  assert.equal(previewOf({ kind: 'gravit', messages: [] }), '');
  const stopped = R.stopGravit(seed(NOW), { convId: 'c-4', now: NOW });
  assert.equal(previewOf(stopped.conversations[3]), 'Gravit stopped. This task no longer moves.', 'a system line in a group has no sender');
});

test('the first level: brand and its collapse key, Messages · Discover · Markets · Trade, phone and mail, Account; Messages carries the unread count', () => {
  const h = renderRail(seed(NOW), NOW);
  assert.match(h, /<nav class="rail" aria-label="Gravit">/);
  assert.match(h, /data-action="toggleRail" aria-expanded="true" aria-label="Collapse navigation"/);
  assert.match(h, /class="nav-item current" aria-current="page" href="#\/messages\/c-1"[^>]*>[\s\S]*?<span class="nav-label">Messages<\/span><span class="nav-badge">1<\/span>/);
  assert.match(h, /href="#\/discover"[^>]*>[\s\S]*?<span class="nav-label">Discover</);
  assert.match(h, /href="#\/markets"/);
  assert.match(h, /href="#\/trade"/);
  assert.match(h, /data-action="phoneCall" aria-label="Phone"/);
  assert.match(h, /<a id="mail-key" class="line-key" href="#\/mail" aria-label="Mail">[\s\S]*?<span class="nav-badge">2<\/span><\/a>/, 'the mail key is a link to the mailbox, with its unread count');
  assert.doesNotMatch(h, /openMail/);
  assert.match(h, /href="#\/account\/portfolio"[^>]*class="account"/);
  assert.match(h, /\$12,480 · Guard/);
  assert.doesNotMatch(h, /Trading on/);
});

test('the second level opens with Messages: its title, the new-message key, the rows, the current one, the unread dot', () => {
  const h = renderRail(seed(NOW), NOW);
  assert.match(h, /<aside class="list" aria-label="Messages"><div class="list-head"><h2 class="list-title">Messages<\/h2><button type="button" class="icon-key" data-action="startDraft" aria-label="New message">/);
  assert.equal(count(h, /class="row(?: current)?"/g), 4);
  assert.equal(count(h, /class="row current" aria-current="page" href="#\/messages\/c-1"/g), 1);
  assert.equal(count(h, /class="dot on"/g), 1, 'one unread conversation');
  assert.match(h, /row-time">14:07</);
  assert.match(h, /row-time">Yesterday</);
  assert.match(h, /<div class="rail-rows"><a class="row/, 'the rows scroll on their own');
  const d = renderRail(R.startDraft(seed(NOW), { now: NOW }), NOW);
  assert.match(d, /class="row current draft"/);
  assert.equal(count(d, /class="row(?: current)?(?: draft)?"/g), 5);
});

test('off Messages there is no second level; the first level marks its screen; Messages links back to the last conversation', () => {
  const s = R.nav(R.nav(seed(NOW), { screen: 'messages', id: 'c-3' }), { screen: 'discover' });
  const disc = renderRail(s, NOW);
  assert.doesNotMatch(disc, /class="list"/);
  assert.match(disc, /class="nav-item current" aria-current="page" href="#\/discover"/);
  assert.match(disc, /class="nav-item" href="#\/messages\/c-3"/);
  const acct = renderRail(R.nav(seed(NOW), { screen: 'account', tab: 'memory' }), NOW);
  assert.match(acct, /class="account current" aria-current="page"/);
});

test('collapsed, the first level is a strip of icons: names stay for screen readers and as titles, the second level stays', () => {
  const c = renderRail(R.toggleRail(seed(NOW)), NOW);
  assert.match(c, /<nav class="rail mini" aria-label="Gravit">/);
  assert.match(c, /data-action="toggleRail" aria-expanded="false" aria-label="Expand navigation"/);
  assert.match(c, /class="nav-item current"[^>]*title="Messages"/);
  assert.match(c, /<span class="nav-label">Discover<\/span>/);
  assert.match(c, /class="list"/);
});

test('on Mail the mail key is current, Messages is not, and the second level lists the letters', () => {
  const s = R.nav(seed(NOW), { screen: 'mail', id: null });
  const h = renderRail(s, NOW);
  assert.match(h, /<a id="mail-key" class="line-key current" href="#\/mail" aria-label="Mail" aria-current="page">/);
  assert.doesNotMatch(h, /class="nav-item current"/);
  assert.match(h, /<aside class="list" aria-label="Mail"><div class="list-head"><div><h2 class="list-title">Mail<\/h2><div class="list-sub mono">gravit@mail.stand-in<\/div><\/div><\/div>/);
  assert.doesNotMatch(h, /data-action="startDraft"/, 'no new-message key in the mailbox');
  assert.equal(count(h, /<a id="mr-mail-\d" class="row(?: unread)?" href="#\/mail\/mail-\d"/g), 3);
  assert.equal(count(h, /class="row unread"/g), 2);
  assert.match(h, /href="#\/mail\/mail-1"><span class="dot on"><\/span>[\s\S]*?<span class="row-title">Stand-in Broker<\/span><span class="row-time">12:07<\/span><\/span><span class="row-preview">October statement<\/span>/);
  const reading = renderRail(R.nav(seed(NOW), { screen: 'mail', id: 'mail-2' }), NOW);
  assert.match(reading, /<a id="mr-mail-2" class="row current" href="#\/mail\/mail-2" aria-current="page"><span class="dot"><\/span>/, 'the open letter is current and read');
  assert.match(reading, /<span class="nav-badge">1<\/span><\/a>/, 'one letter left unread');
  assert.match(renderRail({ ...s, railCollapsed: true }, NOW), /<a id="mail-key" class="line-key current" href="#\/mail" aria-label="Mail" aria-current="page" title="Mail">/);
});

test('on a plugin page Discover stays current', () => {
  const h = renderRail(R.nav(seed(NOW), { screen: 'plugin', id: 'buffett' }), NOW);
  assert.match(h, /class="nav-item current" aria-current="page" href="#\/discover"/);
});
