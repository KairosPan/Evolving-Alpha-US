// gravit-ui/tests/discover.test.js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderDiscover, card, keyFor, pluginDrawer, renderCreate, renderToast } from '../js/render/discover.js';
import { byId } from '../js/data/plugins.js';
import { reducers as R } from '../js/reducers/index.js';
import { seed } from '../js/data/seed.js';

const NOW = new Date(2026, 9, 9, 14, 7).getTime();
const count = (h, re) => (h.match(re) ?? []).length;
const disc = (s = seed(NOW)) => R.nav(s, { screen: 'discover', id: null });

test('the store page: header with search, 我的插件 · n, Create; six shelves, each with See all and its cards; no price, no subtitle', () => {
  const h = renderDiscover(disc());
  assert.match(h, /<h1 class="head-title">Discover<\/h1>/);
  assert.match(h, /id="dq"[^>]*placeholder="Search plugins"[^>]*data-action="query"/);
  assert.match(h, /data-action="toggleInstalledOnly" aria-pressed="false">我的插件 · 5</);
  assert.doesNotMatch(h, /Installed ·/);
  assert.match(h, /class="pill" data-action="openCreate">[\s\S]*?Create<\/button>/);
  assert.doesNotMatch(h, /Upload a plugin/);
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

test('a card: 44 px logo top-left, kind top-right, name, one line, and no author or price line; installed shows ✓ beside the trash key', () => {
  const s = disc();
  const h = card(byId('buffett'), s);
  assert.match(h, /^<div class="pcard" data-action="openPlugin" data-id="buffett" role="button" tabindex="0">/);
  assert.match(h, /av-portrait tone-warm/);
  assert.match(h, /class="pcard-kind">BOTS</);
  assert.match(h, /class="pcard-name">Buffett bot</);
  assert.doesNotMatch(h, /pcard-by|Free|by Gravit/);
  const installed = keyFor(byId('buffett'), s);
  assert.match(installed, /^<span class="pkeys"><span class="pkey-done" role="img" aria-label="已安装">/);
  assert.match(installed, /<button type="button" class="pkey uninstall" data-action="uninstall" data-id="buffett" aria-label="Uninstall Buffett bot">/);
  assert.doesNotMatch(installed, /Installed/);
  assert.match(keyFor(byId('news'), s), /^<button type="button" class="pkey install" data-action="install" data-id="news" aria-label="Install News sentiment">/);
  assert.doesNotMatch(card(byId('pairs'), s), /Free|by @you/);
  assert.match(card(byId('news'), s, { pressed: true }), /class="pcard pressed"/);
});

test('the drawer: sections, the signature table inline, Install at the foot; installed shows Uninstall; no author, price or 怎么付', () => {
  const s = R.openPlugin(disc(), 'news');
  const h = renderDiscover(s);
  assert.match(h, /<aside class="drawer" aria-label="News sentiment">/);
  assert.match(h, /class="pcard pressed" data-action="openPlugin" data-id="news"/);
  const d = pluginDrawer(byId('news'), s);
  assert.match(d, /class="dsec-label">它能被问什么</);
  assert.match(d, /class="dsec-label">它会写什么</);
  assert.match(d, /不会：动钱、付人、改额度/);
  assert.doesNotMatch(d, /怎么付|免费|Free|by Gravit/);
  assert.match(pluginDrawer(byId('buffett'), s), /class="dim">Bots · 1\.2k 装了</);
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

test('我的插件 view: the pill pressed, every card with ✓ and the trash key, 你创建的 for your own, the just-installed card links to its conversation', () => {
  let s = R.install(disc(), { id: 'news', now: NOW });
  s = R.toggleInstalledOnly(s);
  const h = renderDiscover(s);
  assert.match(h, /aria-pressed="true">我的插件 · 6</);
  assert.equal(count(h, /class="shelf"/g), 0);
  assert.equal(count(h, /class="pkey uninstall"/g), 6, 'five installed that are not yours plus the private Pairs you made');
  assert.equal(count(h, /class="pkey-done"/g), 6);
  assert.match(h, /class="grid-title">你创建的</);
  assert.doesNotMatch(h, /刚装好/);
  assert.match(h, /class="toast" role="status">News sentiment 装好了/);
  assert.match(h, /class="toast-key" href="#\/messages\/c-5">Open</);
  assert.match(h, /data-action="open" data-id="c-5" href="#\/messages\/c-5">Open in Messages ›/, 'the link opens the conversation, not the card drawer');
});

test('the just-installed card keeps Open in Messages, with no 刚装好 chip, and only while it is installed', () => {
  const s = R.install(disc(), { id: 'news', now: NOW });
  const h = renderDiscover(s);
  assert.doesNotMatch(h, /刚装好/);
  assert.match(h, /<div class="pcard-extra"><a class="link" data-action="open" data-id="c-5" href="#\/messages\/c-5">Open in Messages ›<\/a><\/div>/);
  assert.doesNotMatch(renderDiscover(R.uninstall(s, 'news')), /Open in Messages/);
});

test('the signature follows the plugin: only a bot may propose; uninstalling signs only what and for; empty sections are left out', () => {
  const s = disc();
  assert.match(pluginDrawer(byId('news'), s), /May<\/span><span class="kv-v">answer when asked · write into the conversation/);
  assert.match(pluginDrawer(byId('telegram'), s), /May<\/span><span class="kv-v">read what you point it at · write signals, never orders/);
  assert.match(pluginDrawer(byId('politician'), { ...s, plugins: { ...s.plugins, installed: [] } }), /May<\/span><span class="kv-v">read Portfolio · propose in your limit/);
  const inst = pluginDrawer(byId('buffett'), s);
  assert.match(inst, /uninstall buffett/);
  assert.doesNotMatch(inst, />May</);
  const bare = pluginDrawer(byId('onchain'), s);
  assert.doesNotMatch(bare, /它还没写/);
  assert.doesNotMatch(bare, /它能被问什么/);
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

test('Create pops up the MCP connector: name, server address, auth, icon, kind, visibility, Cancel and Connect', () => {
  const s = R.openCreate(disc());
  const h = renderDiscover(s);
  assert.match(h, /<div class="modal-scrim"><div class="modal" role="dialog" aria-label="添加 MCP 连接器">/);
  const m = renderCreate(s);
  assert.match(m, /<form class="mcp-form" data-action="connectMcp">/);
  assert.match(m, /<input id="mcp-name"[^>]*name="name"/);
  const url = m.match(/<input id="mcp-url"[^>]*>/)?.[0] ?? '';
  for (const a of ['type="url"', 'name="url"', 'placeholder="https://example.com/mcp"']) assert.ok(url.includes(a), a);
  assert.equal(count(m, /type="radio" name="auth"/g), 3);
  assert.match(m, /type="radio" name="auth" value="无" data-action="mcpField" checked/);
  assert.doesNotMatch(m, /id="mcp-key"/, 'no key field until API key is picked');
  assert.match(m, /class="icon-slot" id="mcp-icon">P</);
  assert.match(m, /data-action="cycleCreateIcon">换一张图</);
  assert.equal(count(m, /type="radio" name="kind"/g), 5);
  assert.match(m, /type="radio" name="visibility" value="private" data-action="mcpField" checked/);
  assert.match(m, /data-action="closeCreate">取消</);
  assert.match(m, /type="submit" class="btn-primary">连接</);
  const key = renderCreate(R.setCreateField(s, { key: 'auth', value: 'API key' }));
  assert.match(key, /<input id="mcp-key"[^>]*type="password"/);
  const oauth = renderCreate(R.setCreateField(s, { key: 'auth', value: 'OAuth' }));
  assert.match(oauth, /id="mcp-client-id"/);
  assert.match(oauth, /id="mcp-client-secret"/);
});

test('the connector shows a bad address, then connecting, then the tools it found with a check each', () => {
  let s = R.openCreate(disc());
  s = R.connectMcp(R.setCreateField(s, { key: 'url', value: 'pairs.example.com' }));
  const bad = renderCreate(s);
  assert.match(bad, /id="mcp-url"[^>]*aria-invalid="true"/);
  assert.match(bad, /class="field-error">地址要以 https:\/\/ 开头</);
  s = R.connectMcp(R.setCreateField(s, { key: 'url', value: 'https://pairs.example.com/mcp' }));
  assert.match(renderCreate(s), /class="mcp-status">正在连接 pairs.example.com…</);
  s = R.mcpConnected(s, { tools: ['pairs.search', 'pairs.get', 'pairs.watch'] });
  const found = renderCreate(s);
  assert.match(found, /class="modal-title">发现 3 个工具</);
  assert.equal(count(found, /type="checkbox"[^>]*data-action="toggleMcpTool"/g), 3);
  assert.match(found, /data-action="addMcp">添加</);
  assert.match(found, /data-action="backToForm">返回</);
});

test('renderToast', () => {
  assert.equal(renderToast({ text: 'x', action: null }), '<div class="toast" role="status">x<button type="button" class="toast-x" data-action="dismissToast" aria-label="Dismiss">×</button></div>');
});
