// gravit-ui/tests/driver.test.js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { replyTo, followUp, director, CANDLES } from '../js/driver.js';
import { message } from '../js/messages.js';

const NOW = new Date(2026, 9, 9, 14, 7).getTime();
const ctx = { installed: ['pricefeed', 'fraud'], now: NOW };

test('replyTo scripts by what the owner said', () => {
  const btc = replyTo('小仓位买 BTC，$70k 以下', ctx);
  assert.equal(btc.length, 2);
  assert.equal(btc[0].msg.kind, 'text');
  assert.equal(btc[1].msg.kind, 'card');
  assert.equal(btc[1].msg.data.by, NOW + 26 * 60_000);
  assert.ok(btc[1].delay > btc[0].delay);
  const askInstall = replyTo('跟单 Pelosi', ctx);
  assert.equal(askInstall[0].msg.kind, 'install');
  assert.equal(askInstall[0].msg.data.plugin, 'politician');
  const withBot = replyTo('跟单 Pelosi', { ...ctx, installed: ['politician'] });
  assert.equal(withBot.at(-1).msg.from, 'politician');
  assert.equal(withBot.at(-1).msg.kind, 'proposal');
  const addr = replyTo('查 0x9f3a1234 是不是骗子', ctx);
  assert.equal(addr[1].msg.from, 'fraud');
  assert.equal(addr[1].msg.kind, 'signal');
  assert.equal(addr[2].msg.kind, 'alert');
  const limit = replyTo('额度不够', ctx);
  assert.equal(limit[0].msg.kind, 'limit');
  const other = replyTo('今天天气', ctx);
  assert.equal(other.length, 2);
  assert.ok(other.every(e => e.msg.from === 'gravit' && e.msg.kind === 'text'));
  for (const e of [...btc, ...askInstall, ...addr, ...other]) {
    assert.equal(e.msg.id, undefined);
    assert.equal(e.msg.at, undefined);
    assert.equal(typeof e.delay, 'number');
  }
});

test('followUp continues the scripted story and never answers twice', () => {
  const card = message('gravit', 'card', '要你答', { title: 'x' });
  const ok = followUp(card, 'approved', ctx);
  assert.equal(ok[0].msg.kind, 'receipt');
  assert.equal(ok[1].msg.kind, 'limit');
  assert.equal(followUp(card, 'rejected', ctx)[0].msg.kind, 'text');
  assert.deepEqual(followUp({ ...card, answer: 'approved' }, 'approved', ctx), []);
  const limit = message('gravit', 'limit', 'x', { from: 25, to: 50 });
  const granted = followUp(limit, 'granted', ctx);
  assert.match(granted[0].msg.text, /\$50/);
  assert.equal(granted[1].msg.kind, 'install');
  assert.match(followUp(limit, 'declined', ctx)[0].msg.text, /\$25/);
  const install = message('gravit', 'install', 'x', { plugin: 'news' });
  assert.equal(followUp(install, 'no', ctx)[0].msg.kind, 'text');
  assert.deepEqual(followUp(install, 'installed', ctx), []);
  assert.deepEqual(followUp(null, 'approved', ctx), []);
});

test('the director hands out the brief, a K-line card, a breaking banner, a call and a bot line', () => {
  const brief = director.brief(NOW);
  assert.equal(brief.kind, 'brief');
  assert.equal(brief.data.date, 'Oct 9');
  assert.ok(brief.data.lines.some(l => l.includes('{{BTC}}')));
  const ta = director.ta(NOW);
  assert.equal(ta.kind, 'ta');
  assert.equal(ta.data.ticker, 'NVDA');
  assert.equal(ta.data.candles.length, 14);
  assert.equal(CANDLES.length, 14);
  for (const [o, c, l, h] of CANDLES) assert.ok(h <= Math.min(o, c) && l >= Math.max(o, c), 'y grows downward: high is the smallest');
  const b = director.breaking(NOW);
  assert.equal(b.at, NOW);
  assert.match(b.headline, /Stand-in Exchange/);
  assert.equal(director.call().from, 'gravit');
  assert.equal(director.bot().from, 'buffett');
});

test('the coin words match whole words only', () => {
  assert.ok(replyTo('can you do something about NVDA', ctx).every(e => e.msg.kind === 'text'));
  assert.ok(replyTo('the method matters', ctx).every(e => e.msg.kind === 'text'));
  assert.equal(replyTo('买btc', ctx).at(-1).msg.kind, 'card');
  assert.equal(replyTo('再看看 eth', ctx).at(-1).msg.kind, 'card');
  assert.equal(replyTo('买一点 SOL', ctx).at(-1).msg.kind, 'card');
});

test('the card and the receipt name the coin that was asked for', () => {
  const sol = replyTo('小仓位买 SOL，别超过 $30 一次', ctx).at(-1).msg;
  assert.equal(sol.data.coin, 'SOL');
  assert.equal(sol.text, '要你答：买 0.034 SOL');
  assert.match(followUp(sol, 'approved', ctx)[0].msg.text, /^0\.034 SOL @ 147 · /);
  const eth = replyTo('再看看 eth', ctx).at(-1).msg;
  assert.equal(eth.data.title, '要你答：买 0.0019 ETH');
  assert.match(followUp(message('gravit', 'card', 'x', {}), 'approved', ctx)[0].msg.text, /^0\.00008 BTC @ 62,500/, 'a card without a coin is the seed BTC card');
});

test('limit asks read the conversation\'s real limit, and a fill carries its amount', () => {
  const card = message('gravit', 'card', 'x', {});
  const after50 = followUp(card, 'approved', { ...ctx, limit: { perOrder: 50, total: 100, spent: 5 } });
  assert.equal(after50.length, 1, 'a $50 cap already covers the $30 add: no ask');
  assert.equal(after50[0].msg.data.amount, 5);
  const ask = followUp(card, 'approved', { ...ctx, limit: { perOrder: 20, total: 100, spent: 0 } })[1].msg;
  assert.match(ask.text, /每单上限是 \$20。改到 \$40？/);
  assert.deepEqual([ask.data.from, ask.data.to], [20, 40]);
  const more = replyTo('额度不够', { ...ctx, limit: { perOrder: 30, total: 100, spent: 0 } })[0].msg;
  assert.deepEqual([more.data.from, more.data.to], [30, 60]);
});

test('in a group the @named bot answers, and only Gravit proposes', () => {
  const group = { kind: 'group', members: ['gravit', 'politician', 'buffett'] };
  const named = replyTo('@Buffett 你怎么看 KO', { ...ctx, conv: group });
  assert.equal(named.length, 1);
  assert.equal(named[0].msg.from, 'buffett');
  assert.equal(named[0].msg.kind, 'text');
  const byShortName = replyTo('@政客 你最近怎么看', { ...ctx, conv: group });
  assert.deepEqual(byShortName.map(e => [e.msg.from, e.msg.kind]), [['politician', 'text']], 'the short name 政客 is a mention, not the Pelosi branch');
  const pelosi = replyTo('跟一下 Pelosi', { ...ctx, installed: ['politician', 'buffett'], conv: group });
  assert.deepEqual(pelosi.map(e => [e.msg.from, e.msg.kind]), [['politician', 'text'], ['gravit', 'card']]);
});

test('a teaching conversation is answered by the plugin it teaches', () => {
  const r = replyTo('两年', { ...ctx, conv: { kind: 'bot', members: ['gravit', 'buffett'], teach: 'buffett' } });
  assert.equal(r.length, 1);
  assert.equal(r[0].msg.from, 'buffett');
  assert.match(r[0].msg.text, /两年/);
  assert.equal(replyTo('ok', { ...ctx, conv: { kind: 'bot', members: ['gravit', 'whale'], teach: 'whale' } })[0].msg.from, 'whale');
});

test('the director can show the door\'s refusal and the close', () => {
  const ref = director.refusal();
  assert.equal(ref.kind, 'refusal');
  assert.equal(ref.data.code, 'E_MANDATE_PER_ORDER_CAP');
  const done = director.done(NOW);
  assert.equal(done.kind, 'done');
  assert.ok(done.data.foot);
});

test('a connected MCP server answers with three tools named after it', async () => {
  const { toolsFor } = await import('../js/driver.js');
  assert.deepEqual(toolsFor('Pairs', 'https://x.dev/mcp'), ['pairs.search', 'pairs.get', 'pairs.watch']);
  assert.deepEqual(toolsFor('', 'https://alpha-feed.example.com/mcp'), ['alphafeed.search', 'alphafeed.get', 'alphafeed.watch']);
  assert.deepEqual(toolsFor('我的数据', 'https://x.dev'), ['x.search', 'x.get', 'x.watch'], 'a name without latin letters falls back to the host');
});

test('files sent without a task get Gravit reading them', () => {
  const r = replyTo('', { ...ctx, files: ['q3.pdf'] });
  assert.equal(r.length, 2);
  assert.match(r[0].msg.text, /q3.pdf/);
  assert.equal(replyTo('买 BTC', { ...ctx, files: ['q3.pdf'] }).at(-1).msg.kind, 'card', 'words with a task still lead');
});

test('a grant asks for News sentiment only when it is not installed', () => {
  const limit = message('gravit', 'limit', 'x', { from: 25, to: 50 });
  assert.equal(followUp(limit, 'granted', { installed: ['news'], now: NOW }).length, 1);
  assert.equal(followUp(limit, 'granted', { installed: [], now: NOW }).length, 2);
  assert.equal(followUp(limit, 'granted', { installed: [], pending: ['news'], now: NOW }).length, 1, 'an unanswered ask is not repeated');
});

test('fills carry order, ledger and card placeholders for the store to number', () => {
  const card = replyTo('小仓位买 BTC', ctx).at(-1).msg;
  assert.equal(card.data.cardId, '{card}');
  const receipt = followUp(message('gravit', 'card', 'x', {}), 'approved', ctx)[0].msg;
  assert.match(receipt.text, /\{ord\} · 账本 \{ledger\}/);
  const prop = replyTo('跟单 Pelosi', { ...ctx, installed: ['politician'] }).at(-1).msg;
  assert.equal(prop.data.ord, '{ord}');
});
