// gravit-ui/tests/reducers.test.js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { reducers as R } from '../js/reducers/index.js';
import { seed } from '../js/data/seed.js';
import { MIN } from '../js/time.js';

const NOW = new Date(2026, 9, 9, 14, 7).getTime();
const fresh = () => seed(NOW);
const conv = (s, id) => s.conversations.find(c => c.id === id);

test('nav opens a conversation, clears its unread dot, closes drawers and drops a draft', () => {
  let s = R.startDraft(fresh(), { now: NOW });
  assert.ok(s.draft);
  s = R.nav(s, { screen: 'messages', id: 'c-2' });
  assert.equal(conv(s, 'c-2').unread, false);
  assert.equal(s.draft, null);
  assert.equal(s.detailsOpen, false);
  const same = R.nav(s, { screen: 'discover' });
  assert.equal(same.route.screen, 'discover');
});

test('send: blank text is ignored; otherwise an owner bubble joins the open conversation', () => {
  const s0 = fresh();
  assert.equal(R.send(s0, { text: '   ', now: NOW }), s0);
  const s1 = R.send(s0, { text: ' 再看看 ETH ', now: NOW + MIN });
  const last = conv(s1, 'c-1').messages.at(-1);
  assert.equal(last.from, 'you');
  assert.equal(last.text, '再看看 ETH');
  assert.equal(last.at, NOW + MIN);
  assert.equal(last.id, 'm-' + (s0.counters.msg + 1));
});

test('send from a draft creates the conversation, titled by the draft or the first words, with the attached limit', () => {
  let s = R.startDraft(fresh(), { now: NOW });
  s = R.setDraftTitle(s, '买一点 SOL');
  s = R.setDraftLimit(s, { key: 'perOrder', value: 30 });
  s = R.send(s, { text: '小仓位买 SOL，别超过 $30 一次', now: NOW });
  assert.equal(s.draft, null);
  assert.equal(s.route.id, 'c-5');
  const c = conv(s, 'c-5');
  assert.equal(c.title, '买一点 SOL');
  assert.equal(c.intent.id, 'intent-0005');
  assert.equal(c.intent.limit.perOrder, 30);
  assert.equal(c.messages[0].text, '小仓位买 SOL，别超过 $30 一次');
  assert.equal(s.conversations[0].id, 'c-5', 'the new conversation is first in the list');

  let t = R.startDraft(fresh(), { now: NOW });
  t = R.toggleDraftAttach(t);
  t = R.send(t, { text: '帮我盯一下这个很长很长很长很长很长很长很长很长的事情', now: NOW });
  assert.equal(conv(t, 'c-5').intent.limit, null);
  assert.equal(conv(t, 'c-5').title.length, 25);
  assert.ok(conv(t, 'c-5').title.endsWith('…'));
});

test('append stamps id and time and marks unread only when the conversation is not open', () => {
  const s0 = fresh();
  const s1 = R.append(s0, { convId: 'c-3', msg: { from: 'gravit', kind: 'text', text: 'x', data: {} }, at: NOW });
  assert.equal(conv(s1, 'c-3').unread, true);
  assert.equal(conv(s1, 'c-3').messages.at(-1).at, NOW);
  const s2 = R.append(s0, { convId: 'c-1', msg: { from: 'gravit', kind: 'text', text: 'x', data: {} }, at: NOW });
  assert.equal(conv(s2, 'c-1').unread, false);
  assert.equal(R.append(s0, { convId: 'c-99', msg: { from: 'gravit', kind: 'text', text: 'x', data: {} }, at: NOW }), s0);
});

test('answer records the answer once, adds the owner word, and a grant raises the limit', () => {
  const s0 = fresh();
  const limitMsg = conv(s0, 'c-1').messages.find(m => m.kind === 'limit');
  const s1 = R.answer(s0, { convId: 'c-1', msgId: limitMsg.id, answer: 'granted', now: NOW });
  assert.equal(conv(s1, 'c-1').messages.find(m => m.id === limitMsg.id).answer, 'granted');
  assert.equal(conv(s1, 'c-1').messages.at(-1).text, 'Granted.');
  assert.equal(conv(s1, 'c-1').intent.limit.perOrder, 50);
  assert.equal(R.answer(s1, { convId: 'c-1', msgId: limitMsg.id, answer: 'granted', now: NOW }), s1, 'a second answer is a no-op');
  const installMsg = conv(s0, 'c-1').messages.find(m => m.kind === 'install');
  const s2 = R.answer(s0, { convId: 'c-1', msgId: installMsg.id, answer: 'installed', now: NOW });
  assert.equal(conv(s2, 'c-1').messages.at(-1).kind, 'install', 'installing adds no owner bubble');
});

test('details, stop, withdraw, banner, call', () => {
  let s = R.toggleDetails(fresh());
  assert.equal(s.detailsOpen, true);
  s = R.stopGravit(s, { convId: 'c-1', now: NOW });
  assert.equal(conv(s, 'c-1').status, 'stopped');
  assert.equal(conv(s, 'c-1').messages.at(-1).from, 'system');
  s = R.withdraw(s, { convId: 'c-2', now: NOW });
  assert.equal(conv(s, 'c-2').status, 'withdrawn');
  s = R.changeLimit(s, { convId: 'c-1', limit: { total: 200 } });
  assert.equal(conv(s, 'c-1').intent.limit.total, 200);
  assert.equal(conv(s, 'c-1').intent.limit.perOrder, 25);
  s = R.showBanner(s, { id: 'b1', headline: 'h', body: 'b', at: NOW });
  assert.equal(s.banner.id, 'b1');
  s = R.dismissBanner(s);
  assert.equal(s.banner, null);
  s = R.incomingCall(s, { from: 'gravit', about: '想说 BTC 的事' });
  s = R.answerCall(s, { accept: false, now: NOW });
  assert.equal(s.call, null);
  assert.match(s.conversations[0].messages.at(-1).text, /没接/);
});

test('discover: install adds the plugin, a teaching conversation and a toast; uninstall removes', () => {
  const s0 = R.openPlugin(fresh(), 'news');
  assert.equal(s0.discover.drawer, 'news');
  const s1 = R.install(s0, { id: 'news', now: NOW });
  assert.ok(s1.plugins.installed.includes('news'));
  assert.equal(s1.discover.drawer, null);
  assert.match(s1.discover.toast.text, /News sentiment 装好了/);
  assert.equal(s1.conversations[0].title, 'News sentiment：怎么用我');
  assert.equal(s1.conversations[0].unread, true);
  assert.equal(s1.conversations[0].members[1], 'news');
  assert.equal(s1.discover.toast.action.route.id, s1.conversations[0].id);
  assert.equal(R.install(s1, { id: 'news', now: NOW }), s1, 'installing twice is a no-op');
  const s2 = R.uninstall(s1, 'news');
  assert.ok(!s2.plugins.installed.includes('news'));
  assert.equal(s2.conversations[0].title, 'News sentiment：怎么用我', 'the conversation stays');
  const s3 = s2;
  const s4 = R.setQuery(R.toggleInstalledOnly(s3), 'bot');
  assert.equal(s4.discover.installedOnly, true);
  assert.equal(s4.discover.query, 'bot');
  assert.equal(R.dismissToast(s4).discover.toast, null);
});

test('account: mode, memory add/edit/forget/forget all, switches, settings', () => {
  let s = R.setMode(fresh(), 'beast');
  assert.equal(s.account.mode, 'beast');
  assert.equal(R.addMemory(s, { text: '  ', now: NOW }), s);
  s = R.addMemory(s, { text: '周五不开新仓', now: NOW });
  const added = s.memory.entries.at(-1);
  assert.equal(added.id, 'mem-10');
  assert.equal(added.source, '你说的');
  s = R.editMemory(s, { id: 'mem-10', text: '周五不开新仓，周一也不' });
  assert.equal(s.memory.entries.at(-1).text, '周五不开新仓，周一也不');
  s = R.forgetMemory(s, 'mem-1');
  assert.equal(s.memory.entries.length, 9);
  s = R.setMemorySwitch(s, { key: 'askFirst', value: true });
  assert.equal(s.memory.askFirst, true);
  s = R.forgetAll(s);
  assert.deepEqual(s.memory.entries, []);
  s = R.openSettings(s);
  assert.equal(s.settingsOpen, true);
  assert.equal(R.closeSettings(s).settingsOpen, false);
});

test('nav normalises a missing or empty conversation id to the first; new without a draft too', () => {
  assert.equal(R.nav(fresh(), { screen: 'messages', id: 'c-99' }).route.id, 'c-1');
  assert.equal(R.nav(fresh(), { screen: 'messages', id: null }).route.id, 'c-1');
  assert.equal(R.nav(fresh(), { screen: 'messages', id: 'new' }).route.id, 'c-1');
  const drafting = R.startDraft(fresh(), { now: NOW });
  assert.equal(R.nav(drafting, { screen: 'messages', id: 'new' }).route.id, 'new');
  const empty = { ...fresh(), conversations: [] };
  assert.equal(R.nav(empty, { screen: 'messages', id: 'c-1' }).route.id, null);
});

test('send into a route that names a missing conversation writes into the first one', () => {
  const s0 = { ...fresh(), route: { screen: 'messages', id: 'c-99' } };
  const s1 = R.send(s0, { text: 'x', now: NOW });
  assert.equal(s1.conversations.length, 4);
  assert.equal(conv(s1, 'c-1').messages.at(-1).text, 'x');
  assert.equal(s1.route.id, 'c-1');
});

test('a stopped or withdrawn conversation takes no more messages from Gravit or a bot', () => {
  const stopped = R.stopGravit(fresh(), { convId: 'c-1', now: NOW });
  assert.equal(R.append(stopped, { convId: 'c-1', msg: { from: 'gravit', kind: 'text', text: 'late', data: {} }, at: NOW }), stopped);
  const withdrawn = R.withdraw(fresh(), { convId: 'c-2', now: NOW });
  assert.equal(R.append(withdrawn, { convId: 'c-2', msg: { from: 'politician', kind: 'text', text: 'late', data: {} }, at: NOW }), withdrawn);
});

test('a call leaves a call card; dismissing a banner leaves the breaking message', () => {
  let s = R.incomingCall(fresh(), { from: 'gravit', about: '想说 BTC 的事' });
  s = R.answerCall(s, { accept: false, now: NOW });
  const missed = s.conversations[0].messages.at(-1);
  assert.equal(missed.kind, 'call');
  assert.equal(missed.answer, 'missed');
  assert.equal(missed.data.about, '想说 BTC 的事');
  const took = R.answerCall(R.incomingCall(fresh(), { from: 'gravit', about: 'x' }), { accept: true, now: NOW });
  assert.equal(took.conversations[0].messages.at(-1).answer, 'accepted');
  const b = R.showBanner(fresh(), { id: 'b1', headline: 'H', body: 'B', at: NOW });
  const d = R.dismissBanner(b, { now: NOW });
  assert.equal(d.banner, null);
  const last = d.conversations[0].messages.at(-1);
  assert.equal(last.kind, 'breaking');
  assert.deepEqual([last.data.headline, last.data.body, last.at], ['H', 'B', NOW]);
  assert.equal(R.dismissBanner(d, { now: NOW }), d);
});

test('the MCP connector: a bad address is refused; a good one connects, lists its tools, and adding makes your own installed plugin', () => {
  let s = R.openCreate(fresh());
  assert.equal(s.discover.create.step, 'form');
  assert.equal(R.connectMcp(s).discover.create.error, '地址要以 https:// 开头', 'an empty address');
  s = R.setCreateField(s, { key: 'url', value: 'ftp://pairs.example.com' });
  assert.equal(R.connectMcp(s).discover.create.step, 'form');
  s = R.setCreateField(s, { key: 'url', value: 'https://pairs.example.com/mcp' });
  assert.equal(s.discover.create.error, null, 'typing clears the error');
  s = R.connectMcp(s);
  assert.equal(s.discover.create.step, 'connecting');
  assert.equal(R.mcpConnected(R.openCreate(fresh()), { tools: ['x'] }).discover.create.step, 'form', 'a late answer for a form not connecting changes nothing');
  s = R.mcpConnected(s, { tools: ['pairs.search', 'pairs.get', 'pairs.watch'] });
  assert.deepEqual(s.discover.create.tools.map(t => [t.name, t.on]), [['pairs.search', true], ['pairs.get', true], ['pairs.watch', true]]);
  s = R.toggleMcpTool(s, 2);
  assert.equal(s.discover.create.tools[2].on, false);
  assert.equal(R.backToForm(s).discover.create.step, 'form');
  s = R.cycleCreateIcon(s);
  const done = R.addMcp(s, { now: NOW });
  assert.equal(done.discover.create, null);
  const p = done.plugins.uploaded[0];
  assert.deepEqual([p.id, p.name, p.by, p.visibility, p.url], ['p-1', 'Pairs', '@you', 'private', 'https://pairs.example.com/mcp'], 'the name falls back to the host');
  assert.equal(p.tools, 'pairs.search\npairs.get');
  assert.equal(p.logo.type, 'glyph', 'the icon was changed once');
  assert.ok(done.plugins.mine.includes('p-1') && done.plugins.installed.includes('p-1'));
  assert.equal(done.conversations[0].teach, 'p-1');
  assert.match(done.discover.toast.text, /^Pairs 已添加 · Private/);
  const pub = R.addMcp(R.mcpConnected(R.connectMcp(R.setCreateField(R.setCreateField(R.setCreateField(R.openCreate(fresh()), { key: 'url', value: 'https://x.dev/mcp' }), { key: 'name', value: 'Zed' }), { key: 'visibility', value: 'public' })), { tools: ['zed.run'] }), { now: NOW });
  assert.match(pub.discover.toast.text, /^Zed 已添加 · Public · 等过审/);
  assert.equal(R.closeCreate(R.openCreate(fresh())).discover.create, null);
});

test('append fills order and ledger placeholders from the counters', () => {
  const receipt = { from: 'gravit', kind: 'receipt', text: '0.00008 BTC @ 62,500 · {ord} · 账本 {ledger}', data: { status: 'filled' } };
  const s1 = R.append(fresh(), { convId: 'c-1', msg: receipt, at: NOW });
  const s2 = R.append(s1, { convId: 'c-1', msg: receipt, at: NOW });
  assert.equal(conv(s1, 'c-1').messages.at(-1).text, '0.00008 BTC @ 62,500 · ord-0010 · 账本 #59');
  assert.equal(conv(s2, 'c-1').messages.at(-1).text, '0.00008 BTC @ 62,500 · ord-0011 · 账本 #60');
  const prop = { from: 'politician', kind: 'proposal', text: 'x', data: { status: 'filled', ord: '{ord}', venue: 'Stand-in Broker' } };
  assert.equal(conv(R.append(fresh(), { convId: 'c-2', msg: prop, at: NOW }), 'c-2').messages.at(-1).data.ord, 'ord-0010');
});

// final review fixes

test('a stopped or withdrawn conversation is closed: answers are refused, a second Stop changes nothing', () => {
  const stopped = R.stopGravit(fresh(), { convId: 'c-1', now: NOW });
  const limit = conv(stopped, 'c-1').messages.find(m => m.kind === 'limit');
  assert.equal(R.answer(stopped, { convId: 'c-1', msgId: limit.id, answer: 'granted', now: NOW }), stopped);
  assert.equal(R.stopGravit(stopped, { convId: 'c-1', now: NOW }), stopped);
  const withdrawn = R.withdraw(fresh(), { convId: 'c-2', now: NOW });
  assert.equal(R.withdraw(withdrawn, { convId: 'c-2', now: NOW }), withdrawn);
});

test('a filled receipt with an amount adds to what the limit has spent', () => {
  const r = { from: 'gravit', kind: 'receipt', text: 'x', data: { status: 'filled', amount: 5 } };
  assert.equal(conv(R.append(fresh(), { convId: 'c-1', msg: r, at: NOW }), 'c-1').intent.limit.spent, 10);
  assert.equal(conv(R.append(fresh(), { convId: 'c-3', msg: r, at: NOW }), 'c-3').intent.limit, null, 'no limit, nothing to add to');
});

test('installing answers every waiting ask for that plugin and tells the conversation', () => {
  const s = R.install(fresh(), { id: 'news', now: NOW });
  const c1 = conv(s, 'c-1');
  assert.equal(c1.messages.find(m => m.kind === 'install' && m.data.plugin === 'news').answer, 'installed');
  assert.equal(c1.messages.at(-1).from, 'gravit');
  assert.match(c1.messages.at(-1).text, /News sentiment 装好了/);
});

test('leaving Discover clears its drawer, ask and toast', () => {
  let s = R.install(R.nav(fresh(), { screen: 'discover', id: null }), { id: 'news', now: NOW });
  s = R.openCreate(R.openPlugin(s, 'buffett'));
  s = R.openPlugin(s, 'buffett');
  const away = R.nav(R.openCreate(s), { screen: 'messages', id: 'c-1' });
  assert.deepEqual([away.discover.drawer, away.discover.create, away.discover.toast], [null, null, null]);
  const stay = R.nav(s, { screen: 'discover', id: 'bots' });
  assert.equal(stay.discover.drawer, 'buffett', 'moving inside Discover keeps it');
});

test('the new-message draft picks bots one by one', () => {
  let s = R.startDraft(fresh(), { now: NOW });
  s = R.toggleDraftPicker(s);
  assert.equal(s.draft.picking, true);
  s = R.toggleDraftBot(s, 'buffett');
  assert.deepEqual(s.draft.bots, ['buffett']);
  const sent = R.send(s, { text: '看看 KO', now: NOW });
  assert.equal(sent.conversations[0].kind, 'group');
  assert.deepEqual(sent.conversations[0].members, ['gravit', 'buffett']);
  assert.deepEqual(R.toggleDraftBot(s, 'buffett').draft.bots, []);
  assert.deepEqual(R.toggleDraftGroup(R.startDraft(fresh(), { now: NOW })).draft.bots, ['politician', 'buffett'], 'the group toggle takes every installed bot');
});

test('an install conversation knows which plugin it teaches', () => {
  const s0 = fresh();
  assert.equal(R.install(s0, { id: 'no-such-plugin', now: NOW }), s0);
  const t = R.install(R.uninstall(fresh(), 'buffett'), { id: 'buffett', now: NOW });
  assert.equal(t.conversations[0].teach, 'buffett');
});
