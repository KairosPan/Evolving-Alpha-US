// gravit-ui/tests/data.test.js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import * as plugins from '../js/data/plugins.js';
import { PLUGINS, KINDS, SHELVES, SHOP_MCP, byId, search, likeFor, fromManifest } from '../js/data/plugins.js';
import { seed, SEED_VERSION } from '../js/data/seed.js';
import { MIN, DAY } from '../js/time.js';

test('the catalogue: unique ids, known kinds, every shelf id resolves, Serenity has her line', () => {
  const ids = PLUGINS.map(p => p.id);
  assert.equal(new Set(ids).size, ids.length);
  for (const p of PLUGINS) {
    assert.ok(KINDS.includes(p.kind), p.id);
    assert.ok(['letter', 'glyph', 'portrait'].includes(p.logo.type), p.id);
    assert.ok(p.teach.length > 0, p.id);
  }
  for (const s of SHELVES.filter(s => s.id !== 'like')) for (const id of s.ids) assert.ok(byId(id), id);
  assert.equal(byId('serenity').blurb, '科技产业链分析');
  assert.equal(plugins.byline, undefined, 'no author or price line is made any more');
  assert.equal(byId('nope'), null);
  assert.equal(byId('p-1', [{ id: 'p-1', name: 'Mine' }]).name, 'Mine');
});

test('search matches name, blurb and kind, case-insensitively; blank query is empty', () => {
  assert.deepEqual(search('buffett').map(p => p.id), ['buffett']);
  assert.ok(search('骗子').some(p => p.id === 'fraud'));
  assert.ok(search('quant').length >= 3);
  assert.deepEqual(search('   '), []);
});

test('likeFor reads the style out of Memory', () => {
  assert.deepEqual(likeFor({ entries: [{ text: '偏价值，不追热点' }] }), ['buffett', 'research', 'politician', 'quantteam']);
  assert.equal(likeFor({ entries: [{ text: '我做高频' }] })[0], 'hft');
  assert.equal(likeFor({ entries: [{ text: '想试试量化' }] })[0], 'quantteam');
  assert.equal(likeFor({ entries: [] })[0], 'buffett');
});

test('firstRun: the seed with no conversations, for the F6 empty state', async () => {
  const { firstRun } = await import('../js/data/seed.js');
  const now = new Date(2026, 9, 9, 14, 7).getTime();
  const s = firstRun(now);
  assert.equal(s.v, SEED_VERSION);
  assert.deepEqual(s.conversations, []);
  assert.deepEqual(s.route, { screen: 'messages', id: null });
  assert.equal(s.memory.entries.length, 9, 'Memory and the account stay');
});

test('seed: four conversations shaped as the boards, memory, account, counters', () => {
  const now = new Date(2026, 9, 9, 14, 7).getTime();
  const s = seed(now);
  assert.equal(s.v, SEED_VERSION);
  assert.equal(s.conversations.length, 4);
  const [btc, pelosi, addr, group] = s.conversations;
  assert.equal(btc.id, 'c-1');
  assert.equal(btc.title, '小仓位 BTC，$70k 以下');
  assert.equal(btc.intent.id, 'intent-0003');
  assert.deepEqual(btc.intent.limit, { perOrder: 25, total: 100, spent: 5, venue: 'Stand-in Exchange' });
  assert.equal(btc.messages[0].from, 'you');
  assert.equal(btc.messages[0].at, now - 6 * MIN);
  assert.equal(btc.messages.at(-1).at, now);
  assert.equal(btc.messages.find(m => m.kind === 'card').answer, 'approved');
  assert.equal(btc.messages.at(-1).kind, 'install');
  assert.equal(pelosi.kind, 'bot');
  assert.equal(pelosi.unread, true);
  assert.equal(pelosi.messages.at(-1).from, 'politician');
  assert.ok(addr.messages[0].at < now - DAY + 60 * MIN);
  assert.equal(group.kind, 'group');
  assert.deepEqual(group.members, ['gravit', 'politician', 'buffett']);
  const ids = s.conversations.flatMap(c => c.messages.map(m => m.id));
  assert.equal(new Set(ids).size, ids.length, 'message ids are unique');
  assert.ok(ids.every(id => /^m-\d+$/.test(id)));
  assert.equal(s.counters.msg, ids.length);
  assert.equal(s.counters.conv, 4);
  assert.equal(s.memory.entries.length, 9);
  assert.deepEqual(s.memory.entries.map(e => e.group).filter((g, i, a) => a.indexOf(g) === i), ['风格', '规矩', '场所和人']);
  assert.deepEqual(s.plugins.installed, ['pricefeed', 'fraud', 'politician', 'buffett', 'pairs']);
  assert.deepEqual(s.plugins.mine, ['pairs']);
  assert.equal(s.account.netWorth, 12480);
  assert.equal(s.account.holdings.length, 4);
  assert.equal(s.route.id, 'c-1');
  assert.equal(s.draft, null);
});

test('Discover is itself an MCP server: its address, its seven tools, a line for each client; a manifest becomes your plugin', () => {
  assert.equal(SHOP_MCP.url, 'https://discover.stand-in/mcp');
  assert.deepEqual(SHOP_MCP.tools, ['shop.search', 'shop.get', 'shop.install', 'shop.uninstall', 'shop.publish', 'shop.mine', 'plugin.call']);
  assert.deepEqual(Object.keys(SHOP_MCP.clients), ['Claude Code', 'Cursor', 'Codex']);
  assert.deepEqual(SHOP_MCP.clients['Claude Code'], { file: null, code: 'claude mcp add --transport http discover https://discover.stand-in/mcp' });
  assert.equal(SHOP_MCP.clients.Cursor.file, '~/.cursor/mcp.json');
  assert.deepEqual(JSON.parse(SHOP_MCP.clients.Cursor.code), { mcpServers: { discover: { url: 'https://discover.stand-in/mcp' } } });
  assert.deepEqual(SHOP_MCP.clients.Codex, { file: '~/.codex/config.toml', code: '[mcp_servers.discover]\nurl = "https://discover.stand-in/mcp"' });
  for (const sh of SHELVES.filter(x => x.id !== 'like')) assert.ok(KINDS.includes(sh.kind), sh.id);
  const m = { id: 'moat', name: 'Moat score', kind: 'Data', blurb: '护城河打分，按 ticker 问', icon: null, tools: ['moat.score', 'moat.compare'], writes: ['message'], needs: 'none', visibility: 'private' };
  const p = fromManifest(m, 'public', 1000);
  assert.deepEqual([p.id, p.kind, p.by, p.visibility, p.logo, p.needs, p.writes, p.tools, p.review, p.at], ['moat', 'Data', '@you', 'public', { type: 'letter', text: 'M' }, '没有。', ['消息，发进会话'], ['moat.score', 'moat.compare'], null, 1000]);
  assert.equal(p.teach, '你好，我是 Moat score。护城河打分，按 ticker 问。我有 2 个工具：moat.score、moat.compare。');
  assert.deepEqual(fromManifest({ ...m, icon: 'bell', needs: 'exchange key' }, 'private', 1000).logo, { type: 'glyph', icon: 'bell' });
  assert.equal(fromManifest({ ...m, needs: 'exchange key' }, 'private', 1000).needs, '一把交易所 key。');
  assert.equal(plugins.ICON_CHOICES, undefined, 'the round-2 connector form is gone');
  assert.equal(plugins.hostOf, undefined);
  assert.equal(seed(1000).counters.mail, 3);
});
