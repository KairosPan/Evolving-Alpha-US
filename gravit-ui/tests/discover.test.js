// gravit-ui/tests/discover.test.js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderDiscover, card, keyFor, pluginDrawer, renderCreate, renderToast } from '../js/render/discover.js';
import { byId } from '../js/data/plugins.js';
import { nextUpload } from '../js/driver.js';
import { reducers as R } from '../js/reducers/index.js';
import { seed } from '../js/data/seed.js';

const NOW = new Date(2026, 9, 9, 14, 7).getTime();
const count = (h, re) => (h.match(re) ?? []).length;
const disc = (s = seed(NOW)) => R.nav(s, { screen: 'discover', id: null });

test('the store page: header with search, My plugins with no count, Create; six shelves, each with See all and its cards; no price, no subtitle', () => {
  const h = renderDiscover(disc());
  assert.match(h, /<h1 class="head-title">Discover<\/h1>/);
  assert.match(h, /id="dq"[^>]*placeholder="Search plugins"[^>]*data-action="query"/);
  assert.match(h, /data-action="toggleInstalledOnly" aria-pressed="false">My plugins</);
  assert.doesNotMatch(h, /我的插件|My plugins · \d/);
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

test('My plugins view: the pill pressed, every card with ✓ and the trash key, 你创建的 for your own, the just-installed card links to its conversation', () => {
  let s = R.install(disc(), { id: 'news', now: NOW });
  s = R.toggleInstalledOnly(s);
  const h = renderDiscover(s);
  assert.match(h, /aria-pressed="true">My plugins</);
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

const atSign = (s, manifest) => { const r = s.discover.create.run; return R.clientPublishes(R.clientConnected(R.startClient(s, { run: r }), { run: r }), { run: r, manifest }); };

test('Create opens Discover\'s own MCP face: its address, its seven tools, a line per client to copy, a status; nothing to type in', () => {
  const s = R.openCreate(disc());
  assert.match(renderDiscover(s), /<div class="modal-scrim"><div class="modal wide" role="dialog" aria-label="Discover MCP">/);
  const m = renderCreate(s);
  assert.match(m, /<h2 class="modal-title">Discover MCP<\/h2>/);
  assert.match(m, /<div class="field"><span class="field-label">地址<\/span><span class="mono">https:\/\/discover\.stand-in\/mcp<\/span><\/div>/);
  assert.equal(count(m, /class="chip grey mono"/g), 7);
  for (const t of ['shop.search', 'shop.get', 'shop.install', 'shop.uninstall', 'shop.publish', 'shop.mine', 'plugin.call']) assert.ok(m.includes(`class="chip grey mono">${t}<`), t);
  assert.equal(count(m, /type="radio" name="client" value="[^"]+" data-action="mcpClient"/g), 3);
  assert.match(m, /type="radio" name="client" value="Claude Code" data-action="mcpClient" checked/);
  assert.match(m, /<pre class="snippet-code mono">claude mcp add --transport http discover https:\/\/discover\.stand-in\/mcp<\/pre>/);
  assert.doesNotMatch(m, /snippet-file/);
  assert.match(m, /<button type="button" id="mcp-copy" class="btn-sm" data-action="copyMcp">复制<\/button>/);
  assert.match(m, /<span class="status grey"><span class="status-dot"><\/span>等待连接<\/span>/);
  assert.doesNotMatch(m, /type="(?:text|url|password)"|<textarea|<form/, 'nothing to type, so no secret can be typed');
  assert.doesNotMatch(m, /添加 MCP 连接器|认证|API key|OAuth|换一张图|服务器地址/);
  const cursor = renderCreate(R.setClient(s, 'Cursor'));
  assert.match(cursor, /<div class="snippet-file mono">~\/\.cursor\/mcp\.json<\/div><pre class="snippet-code mono">\{[\s\S]*?&quot;mcpServers&quot;/);
  assert.match(cursor, /value="Cursor" data-action="mcpClient" checked/);
  assert.match(renderCreate(R.setClient(s, 'Codex')), /<div class="snippet-file mono">~\/\.codex\/config\.toml<\/div><pre class="snippet-code mono">\[mcp_servers\.discover\]\nurl = &quot;https:\/\/discover\.stand-in\/mcp&quot;<\/pre>/);
  assert.match(renderCreate(R.setCreateCopied(s, true)), /data-action="copyMcp">已复制<\/button>/);
});

test('the client connects and calls shop.mine, then asks shop.publish: the owner sees the manifest and signs, or refuses', () => {
  const s0 = R.openCreate(disc());
  const r = s0.discover.create.run;
  const connected = R.clientConnected(R.startClient(s0, { run: r }), { run: r });
  const c = renderCreate(connected);
  assert.match(c, /<span class="status up"><span class="status-dot"><\/span>Claude Code 已连接<\/span>/);
  assert.doesNotMatch(c, /name="client"|mcp-copy/, 'the line to copy has done its job');
  assert.match(c, /<div class="tool-row"><span class="mono">shop\.mine\(\)<\/span><span class="spacer"><\/span><span class="tool-state ok">/);
  const sign = R.clientPublishes(connected, { run: r, manifest: nextUpload([]) });
  const m = renderCreate(sign);
  assert.match(m, /<span class="mono">shop\.publish\(moat, private\)<\/span><span class="spacer"><\/span><span class="tool-state wait">…<\/span>/);
  assert.match(m, /<div class="manifest">[\s\S]*?class="pcard-name">Moat score<[\s\S]*?class="pcard-blurb">护城河打分，按 ticker 问<[\s\S]*?class="pcard-kind">DATA</);
  assert.match(m, /<span class="kv-k">工具<\/span><span class="kv-v"><span class="mono">moat\.score · moat\.compare<\/span>/);
  assert.match(m, /<span class="kv-k">要你什么<\/span><span class="kv-v">没有。/);
  assert.match(m, /type="radio" name="visibility" value="private" data-action="uploadVisibility" checked><span>只给我自己 · Private<\/span>/);
  assert.match(m, /value="public" data-action="uploadVisibility"><span>放进 Public shop<\/span>/);
  assert.match(m, /<span class="kv-k">What you sign<\/span><span class="kv-v"><b>publish moat · private<\/b>/);
  assert.match(m, /<span class="kv-k">For<\/span><span class="kv-v">Gravit · 0xec4c…16c1/);
  assert.match(m, /<span class="kv-k">May<\/span><span class="kv-v">answer when asked · write into the conversation/);
  assert.match(m, /<span class="kv-k">Until<\/span><span class="kv-v">you uninstall/);
  assert.match(m, /data-action="rejectUpload">拒绝<\/button><button type="button" class="btn-primary" data-action="publishUpload">Publish<\/button>/);
  const pub = renderCreate(R.setUploadVisibility(sign, 'public'));
  assert.match(pub, /shop\.publish\(moat, public\)/);
  assert.match(pub, /<b>publish moat · public<\/b>/);
  assert.match(pub, /<span class="kv-k">For<\/span><span class="kv-v">Public shop/);
  assert.doesNotMatch(pub, /Until/);
  const no = renderCreate(R.rejectUpload(sign));
  assert.match(no, /shop\.publish\(moat, private\)<\/span><span class="spacer"><\/span><span class="tool-state no">/);
  assert.doesNotMatch(no, /publishUpload|manifest/);
});

test('a private upload lands first on its shelf, installed, with Open in Messages; a public one waits for review behind a clock key', () => {
  let s = R.publishUpload(atSign(R.openCreate(disc()), nextUpload([])), { now: NOW });
  const h = renderDiscover(s);
  const data = h.slice(h.indexOf('shelf-title">Data'), h.indexOf('shelf-title">Monitors'));
  assert.match(data, /<div class="shelf-row"><div class="pcard" data-action="openPlugin" data-id="moat"/, 'first on the Data shelf');
  assert.match(data, /data-id="moat"[\s\S]*?Open in Messages ›[\s\S]*?class="pkey uninstall" data-action="uninstall" data-id="moat"/);
  assert.match(h, /class="toast" role="status">Moat score 已上传 · Private<a class="toast-key" href="#\/messages\/c-5">Open<\/a>/);
  const moat = byId('moat', s.plugins.uploaded);
  assert.match(pluginDrawer(moat, s), /class="dim">Data · Private</);
  assert.match(pluginDrawer(moat, s), /<div class="dsec-label">工具<\/div><div class="dsec-line"><span class="mono">moat\.score<\/span><\/div>/);
  assert.match(pluginDrawer(byId('pairs'), s), /class="dim">Quant · Private</, 'your own plugin says where it is, not who made it');
  assert.match(renderDiscover(R.nav(s, { screen: 'discover', id: 'data' })), /<div class="grid"><div class="pcard grid" data-action="openPlugin" data-id="moat"/, 'and first in See all');
  s = R.publishUpload(R.setUploadVisibility(atSign(R.openCreate(s), nextUpload(s.plugins.uploaded)), 'public'), { now: NOW });
  const cpi = byId('cpi', s.plugins.uploaded);
  assert.match(keyFor(cpi, s), /^<span class="pkey-wait" role="img" aria-label="审核中">/);
  const d = pluginDrawer(cpi, s);
  assert.match(d, /class="dim">Data · 审核中</);
  assert.match(d, /<button type="button" class="btn-primary" disabled>审核中<\/button>/);
  assert.doesNotMatch(d, /你签的是/);
  assert.match(renderDiscover(s), /class="toast" role="status">CPI 速读 已上传 · 审核中<button type="button" class="toast-x"/);
  const passed = R.reviewPassed(s, { id: 'cpi', now: NOW });
  assert.match(keyFor(byId('cpi', passed.plugins.uploaded), passed), /class="pkey install" data-action="install" data-id="cpi"/);
  assert.match(pluginDrawer(byId('cpi', passed.plugins.uploaded), passed), /class="dim">Data · Public</);
  assert.match(renderToast(passed.discover.toast), /<button type="button" class="toast-key" data-action="openPlugin" data-id="cpi">Open<\/button>/);
  for (const st of [s, passed]) assert.doesNotMatch(renderDiscover(R.toggleInstalledOnly(st)) + renderDiscover(st), /Free|by @|by Gravit|by community|刚装好/);
});

test('renderToast', () => {
  assert.equal(renderToast({ text: 'x', action: null }), '<div class="toast" role="status">x<button type="button" class="toast-x" data-action="dismissToast" aria-label="Dismiss">×</button></div>');
});
