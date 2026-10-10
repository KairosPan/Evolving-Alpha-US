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

test('discover: install adds the plugin, a teaching conversation and a toast; uninstall removes; publish adds a private plugin of yours', () => {
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
  const s3 = R.publish(R.openUpload(s2), { manifest: { name: 'Pairs 2', blurb: '价差', kind: 'Quant', tools: 'pairs2.scan', needs: '没有。', visibility: 'private' }, now: NOW });
  assert.equal(s3.discover.upload, false);
  assert.equal(s3.plugins.uploaded[0].id, 'p-1');
  assert.ok(s3.plugins.mine.includes('p-1'));
  assert.ok(s3.plugins.installed.includes('p-1'));
  assert.equal(R.publish(s3, { manifest: { name: '  ', blurb: '', kind: 'Quant', tools: '', needs: '', visibility: 'private' }, now: NOW }), s3);
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

test('publish toasts data only; pressing Installed asks before the trash key', () => {
  const s = R.publish(fresh(), { manifest: { name: 'Pairs 2', blurb: '价差', kind: 'Quant', tools: '', needs: '没有。', visibility: 'private' }, now: NOW });
  assert.equal(s.discover.toast.text, 'Pairs 2 发布了 · Private');
  const pub = R.publish(fresh(), { manifest: { name: 'Pub', blurb: '', kind: 'Data', tools: '', needs: '没有。', visibility: 'public' }, now: NOW });
  assert.equal(pub.discover.toast.text, 'Pub 发布了 · Public · 等过审');
  const asked = R.askUninstall(fresh(), 'buffett');
  assert.equal(asked.discover.asking, 'buffett');
  assert.equal(R.uninstall(asked, 'buffett').discover.asking, null);
  assert.equal(R.closeDrawer(asked).discover.asking, null);
  assert.equal(R.openPlugin(asked, 'news').discover.asking, null);
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
