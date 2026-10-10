// gravit-ui/tests/discover.test.js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderDiscover, card, keyFor, pluginDrawer, uploadDrawer, renderToast } from '../js/render/discover.js';
import { byId, SHELVES } from '../js/data/plugins.js';
import { reducers as R } from '../js/reducers/index.js';
import { seed } from '../js/data/seed.js';

const NOW = new Date(2026, 9, 9, 14, 7).getTime();
const count = (h, re) => (h.match(re) ?? []).length;
const disc = (s = seed(NOW)) => R.nav(s, { screen: 'discover', id: null });

test('the store page: header with search, Installed · n, Upload; six shelves, each with See all and its cards; no price, no subtitle', () => {
  const h = renderDiscover(disc());
  assert.match(h, /<h1 class="head-title">Discover<\/h1>/);
  assert.match(h, /id="dq"[^>]*placeholder="Search plugins"[^>]*data-action="query"/);
  assert.match(h, /data-action="toggleInstalledOnly" aria-pressed="false">Installed · 5</);
  assert.match(h, /data-action="openUpload"[^>]*>[\s\S]*Upload a plugin/);
  assert.equal(count(h, /class="shelf"/g), 6);
  assert.equal(count(h, /See all ›/g), 6);
  assert.match(h, /class="shelf-title">Like</);
  assert.match(h, /href="#\/discover\/bots"/);
  assert.doesNotMatch(h, /a call|a minute|\$0\.10/);
  assert.doesNotMatch(h, /shelf-sub/);
  const like = h.slice(h.indexOf('shelf-title">Like'), h.indexOf('shelf-title">Data'));
  assert.equal(count(like, /class="pcard"/g), 4);
  assert.match(like, /Buffett bot/);
});

test('a card: 44 px logo top-left, kind top-right, name, one line, author line, one key in three states', () => {
  const s = disc();
  const h = card(byId('buffett'), s);
  assert.match(h, /^<div class="pcard" data-action="openPlugin" data-id="buffett" role="button" tabindex="0">/);
  assert.match(h, /av-portrait tone-warm/);
  assert.match(h, /class="pcard-kind">BOTS</);
  assert.match(h, /class="pcard-name">Buffett bot</);
  assert.match(h, /class="pcard-by">Free · by Gravit</);
  assert.match(keyFor(byId('buffett'), s), /class="pkey installed" data-action="uninstallAsk" data-id="buffett" aria-label="Installed · uninstall Buffett bot"/);
  assert.match(keyFor(byId('news'), s), /class="pkey install" data-action="install" data-id="news" aria-label="Install News sentiment"/);
  assert.match(keyFor(byId('buffett'), s, 'installed'), /class="pkey uninstall" data-action="uninstall" data-id="buffett"/);
  assert.match(card(byId('pairs'), s), /Free · by @you · Private/);
  assert.match(card(byId('news'), s, { pressed: true }), /class="pcard pressed"/);
});

test('the drawer: sections, the signature table inline, Install at the foot; installed shows Uninstall', () => {
  const s = R.openPlugin(disc(), 'news');
  const h = renderDiscover(s);
  assert.match(h, /<aside class="drawer" aria-label="News sentiment">/);
  assert.match(h, /class="pcard pressed" data-action="openPlugin" data-id="news"/);
  const d = pluginDrawer(byId('news'), s);
  assert.match(d, /class="dsec-label">它能被问什么</);
  assert.match(d, /class="dsec-label">它会写什么</);
  assert.match(d, /不会：动钱、付人、改额度/);
  assert.match(d, /class="dsec-label">怎么付</);
  assert.match(d, /免费。Gravit 只在模型调用和成交的单上抽成。/);
  assert.match(d, /class="dsec-label">要你什么</);
  assert.match(d, /class="dsec-label">你签的是</);
  assert.match(d, /install news/);
  assert.match(d, /Gravit · 0xec4c…16c1/);
  assert.match(d, /you uninstall/);
  assert.match(d, /class="btn-primary" data-action="install" data-id="news">Install</);
  assert.doesNotMatch(d, /签这一下/);
  const inst = pluginDrawer(byId('buffett'), s);
  assert.match(inst, /uninstall buffett/);
  assert.match(inst, /class="btn-primary" data-action="uninstall" data-id="buffett">Uninstall</);
});

test('Installed view: the pill pressed, every card with the trash key, 你上传的 for your own, the just-installed card links to its conversation', () => {
  let s = R.install(disc(), { id: 'news', now: NOW });
  s = R.toggleInstalledOnly(s);
  const h = renderDiscover(s);
  assert.match(h, /aria-pressed="true">Installed · 6</);
  assert.equal(count(h, /class="shelf"/g), 0);
  assert.equal(count(h, /class="pkey uninstall"/g), 6, 'five installed that are not yours plus the private Pairs you uploaded');
  assert.match(h, /class="grid-title">你上传的</);
  assert.match(h, /刚装好/);
  assert.match(h, /href="#\/messages\/c-5">Open in Messages ›/);
  assert.match(h, /class="toast" role="status">News sentiment 装好了/);
  assert.match(h, /class="toast-key" href="#\/messages\/c-5">Open</);
});

test('search shows a results grid; a shelf route shows that shelf as a grid with a way back', () => {
  const h = renderDiscover(R.setQuery(disc(), 'bot'));
  assert.equal(count(h, /class="shelf"/g), 0);
  assert.match(h, /class="grid-title">4 个</);
  const none = renderDiscover(R.setQuery(disc(), 'zzz'));
  assert.match(none, /class="grid-title">0 个</);
  const bots = renderDiscover(R.nav(seed(NOW), { screen: 'discover', id: 'bots' }));
  assert.match(bots, /class="grid-title">Bots</);
  assert.equal(count(bots, /class="pcard grid"/g), 4);
  assert.match(bots, /class="back-link" href="#\/discover"/);
});

test('the upload drawer is a form with the fields of the spec and the private default', () => {
  const h = renderDiscover(R.openUpload(disc()));
  assert.match(h, /<aside class="drawer" aria-label="上传一个插件">/);
  const u = uploadDrawer();
  assert.match(u, /<form class="upload-form" data-action="publish">/);
  assert.match(u, /name="name"/);
  assert.match(u, /name="blurb"/);
  assert.equal(count(u, /name="kind"/g), 5);
  assert.match(u, /name="tools"/);
  assert.equal(count(u, /name="needs"/g), 4);
  assert.match(u, /type="radio" name="visibility" value="private" checked/);
  assert.match(u, /type="radio" name="visibility" value="public"/);
  assert.match(u, /type="submit" class="btn-primary">Publish</);
  assert.doesNotMatch(u, /先过一次审/);
  assert.equal(renderToast({ text: 'x', action: null }), '<div class="toast" role="status">x<button type="button" class="toast-x" data-action="dismissToast" aria-label="Dismiss">×</button></div>');
});
