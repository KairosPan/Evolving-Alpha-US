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
