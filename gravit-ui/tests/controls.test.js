// gravit-ui/tests/controls.test.js — the in-page controls that replaced the browser's prompt and confirm: inline editors and two-step confirms
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { reducers as R } from '../js/reducers/index.js';
import { seed, SEED_VERSION } from '../js/data/seed.js';
import { renderDetails, renderMessagesScreen } from '../js/render/messages.js';
import { renderMemory, renderSettings } from '../js/render/account.js';
import { DAY } from '../js/time.js';

const NOW = new Date(2026, 9, 9, 14, 7).getTime();
const fresh = () => seed(NOW);
const conv = (s, id) => s.conversations.find(c => c.id === id);

test('the state shape grew, so the seed version moved on', () => {
  assert.equal(SEED_VERSION, 4);
  const s = fresh();
  assert.deepEqual([s.edit, s.confirm], [null, null]);
});

test('an inline edit starts, cancels, and commits through one reducer', () => {
  let s = R.startEdit(fresh(), { kind: 'rename', convId: 'c-1' });
  assert.deepEqual(s.edit, { kind: 'rename', convId: 'c-1' });
  assert.equal(R.cancelEdit(s).edit, null);
  const named = R.commitEdit(s, { values: { title: '  BTC 小仓  ' }, now: NOW });
  assert.equal(conv(named, 'c-1').title, 'BTC 小仓');
  assert.equal(named.edit, null);
  const blank = R.commitEdit(s, { values: { title: '  ' }, now: NOW });
  assert.equal(blank.edit.error, '不能是空的');
  assert.equal(conv(blank, 'c-1').title, conv(fresh(), 'c-1').title);
  const f = fresh();
  assert.equal(R.commitEdit(f, { values: {}, now: NOW }), f, 'nothing to commit without an edit');
});

test('draft limit chips edit in place: numbers above zero, days ahead, a venue from the list', () => {
  let s = R.startDraft(fresh(), { now: NOW });
  const edit = (key, values) => R.commitEdit(R.startEdit(s, { kind: 'draftLimit', key }), { values, now: NOW });
  assert.equal(edit('perOrder', { value: '40' }).draft.limit.perOrder, 40);
  assert.equal(edit('perOrder', { value: '0' }).edit.error, '要一个大于 0 的数');
  assert.equal(edit('total', { value: 'abc' }).edit.error, '要一个大于 0 的数');
  assert.equal(edit('until', { value: '3' }).draft.limit.until, NOW + 3 * DAY);
  assert.equal(edit('venue', { value: 'Stand-in Broker' }).draft.limit.venue, 'Stand-in Broker');
  assert.equal(edit('venue', { value: 'Nowhere' }).edit.error, '选一个场所');
});

test('Change limit edits both numbers; a per-order above the total is refused', () => {
  const s = R.startEdit(fresh(), { kind: 'limit', convId: 'c-1' });
  const ok = R.commitEdit(s, { values: { perOrder: '30', total: '200' }, now: NOW });
  assert.deepEqual([conv(ok, 'c-1').intent.limit.perOrder, conv(ok, 'c-1').intent.limit.total], [30, 200]);
  assert.equal(R.commitEdit(s, { values: { perOrder: '300', total: '200' }, now: NOW }).edit.error, '每单不能超过总额');
});

test('End limit closes what is left: the total drops to what was spent', () => {
  const s = R.endLimit(fresh(), { convId: 'c-1' });
  assert.equal(conv(s, 'c-1').intent.limit.total, 5);
  const f = fresh();
  assert.equal(R.endLimit(f, { convId: 'c-3' }), f, 'no limit attached, nothing to end');
});

test('a memory edits in place; a blank one is refused', () => {
  const s = R.startEdit(fresh(), { kind: 'memory', id: 'mem-2' });
  assert.equal(R.commitEdit(s, { values: { text: '不碰杠杆，也不碰期权' }, now: NOW }).memory.entries[1].text, '不碰杠杆，也不碰期权');
  assert.equal(R.commitEdit(s, { values: { text: ' ' }, now: NOW }).edit.error, '不能是空的');
});

test('Top up and Take back move USDC between you and Gravit\'s wallet; taking back more than it holds is refused', () => {
  const up = R.commitEdit(R.startEdit(fresh(), { kind: 'wallet', dir: 'in' }), { values: { amount: '20' }, now: NOW });
  assert.equal(up.account.wallet.usdc, 32.4);
  assert.equal(up.account.holdings.find(h => h.key === 'stable:USDC').value, 2470);
  assert.match(up.account.activity[0].text, /Top up \$20/);
  const back = R.commitEdit(R.startEdit(fresh(), { kind: 'wallet', dir: 'out' }), { values: { amount: '5' }, now: NOW });
  assert.equal(back.account.wallet.usdc, 7.4);
  assert.equal(R.commitEdit(R.startEdit(fresh(), { kind: 'wallet', dir: 'out' }), { values: { amount: '50' }, now: NOW }).edit.error, '钱包里只有 $12.40');
});

test('a two-step confirm is asked and cancelled', () => {
  const s = R.askConfirm(fresh(), { action: 'withdraw', id: 'c-2' });
  assert.deepEqual(s.confirm, { action: 'withdraw', id: 'c-2' });
  assert.equal(R.cancelConfirm(s).confirm, null);
});

test('Details: Change words, Change limit, Top up and Take back open inline editors; Withdraw, End limit and Stop ask first', () => {
  const s = R.toggleDetails(fresh());
  const plain = renderDetails(s.conversations[0], s);
  for (const a of ['changeWords', 'changeLimit', 'topUp', 'takeBack', 'withdraw', 'endLimit', 'stopGravit']) assert.match(plain, new RegExp(`data-action="${a}"`), a);
  const rename = renderDetails(s.conversations[0], R.startEdit(s, { kind: 'rename', convId: 'c-1' }));
  assert.match(rename, /<span class="inline-edit"><input id="edit-title" class="input small" name="title" type="text" value="小仓位 BTC，\$70k 以下" aria-label="这件事叫什么">/);
  assert.match(rename, /data-action="commitEdit" aria-label="Save"/);
  assert.match(rename, /data-action="cancelEdit" aria-label="Cancel"/);
  const limit = renderDetails(s.conversations[0], R.startEdit(s, { kind: 'limit', convId: 'c-1' }));
  assert.match(limit, /name="perOrder" type="number" value="25"/);
  assert.match(limit, /name="total" type="number" value="100"/);
  const err = renderDetails(s.conversations[0], R.commitEdit(R.startEdit(s, { kind: 'limit', convId: 'c-1' }), { values: { perOrder: '300', total: '100' }, now: NOW }));
  assert.match(err, /class="field-error">每单不能超过总额</);
  const wallet = renderDetails(s.conversations[0], R.startEdit(s, { kind: 'wallet', dir: 'out' }));
  assert.match(wallet, /name="amount" type="number"/);
  const asking = renderDetails(s.conversations[0], R.askConfirm(s, { action: 'withdraw', id: 'c-1' }));
  assert.match(asking, /<span class="confirm"><button type="button" class="btn-danger small" data-action="confirmYes">确认撤回<\/button><button type="button" class="btn-sm" data-action="cancelConfirm">取消<\/button><\/span>/);
  assert.match(renderDetails(s.conversations[0], R.askConfirm(s, { action: 'stopGravit', id: 'c-1' })), />确认停掉</);
  assert.match(renderDetails(s.conversations[0], R.askConfirm(s, { action: 'endLimit', id: 'c-1' })), />确认结束额度</);
});

test('the draft limit chip turns into its editor; the venue is a pick list', () => {
  const d = R.startDraft(fresh(), { now: NOW });
  const per = renderMessagesScreen(R.startEdit(d, { kind: 'draftLimit', key: 'perOrder' }), NOW);
  assert.match(per, /<span class="inline-edit"><input id="edit-value" class="input small" name="value" type="number" value="25" aria-label="每单上限">/);
  const venue = renderMessagesScreen(R.startEdit(d, { kind: 'draftLimit', key: 'venue' }), NOW);
  assert.match(venue, /<select id="edit-value" class="input small" name="value" aria-label="场所"><option value="Stand-in Exchange" selected>/);
});

test('the composer holds picked files; a send carries them, even with no words, and empties the tray', async () => {
  const { renderComposer } = await import('../js/render/messages.js');
  const { renderMessage } = await import('../js/render/thread.js');
  let s = R.addFiles(fresh(), [{ name: 'q3.pdf', size: 120000 }, { name: 'chart.png', size: 4000 }]);
  assert.deepEqual(s.compose.files.map(f => f.name), ['q3.pdf', 'chart.png']);
  assert.deepEqual(R.addFiles(s, [{ name: 'q3.pdf', size: 1 }]).compose.files.length, 2, 'the same name twice is one file');
  assert.deepEqual(R.removeFile(s, 0).compose.files.map(f => f.name), ['chart.png']);
  const c = renderComposer({ compose: s.compose });
  assert.match(c, /<input id="attach-input" class="sr-only" type="file" multiple data-action="attachFiles" tabindex="-1">/);
  assert.match(c, /data-action="pickFile" aria-label="Add a file"/);
  assert.match(c, /<span class="file-chip">[\s\S]*?q3.pdf<button type="button" class="file-x" data-action="removeFile" data-id="0" aria-label="移除 q3.pdf">/);
  const sent = R.send(s, { text: '  ', now: NOW });
  const last = conv(sent, 'c-1').messages.at(-1);
  assert.deepEqual([last.from, last.text, last.data.files], ['you', '', ['q3.pdf', 'chart.png']]);
  assert.deepEqual(sent.compose.files, []);
  assert.match(renderMessage(last, conv(sent, 'c-1'), sent), /<div class="bubble you"><span class="file-chip">[\s\S]*?q3.pdf<\/span>/);
  const f = fresh();
  assert.equal(R.send(f, { text: ' ', now: NOW }), f, 'no words and no files: nothing is sent');
});

test('the mic key shows it is listening and the placeholder says so', async () => {
  const { renderComposer } = await import('../js/render/messages.js');
  const on = R.setListening(fresh(), true);
  assert.equal(on.compose.listening, true);
  const c = renderComposer({ compose: on.compose });
  assert.match(c, /class="round-key mic on" data-action="toggleMic" aria-pressed="true" aria-label="Voice input"/);
  assert.match(c, /placeholder="正在听…"/);
  assert.match(renderComposer({ compose: fresh().compose }), /class="round-key mic" data-action="toggleMic" aria-pressed="false"/);
});

test('calls: you ring Gravit, it picks up, you hang up and a card stays; an accepted incoming call goes live the same way', async () => {
  const { renderCall } = await import('../js/render/messages.js');
  let s = R.startCall(fresh(), { now: NOW });
  assert.deepEqual([s.call.dir, s.call.status], ['out', 'ringing']);
  assert.equal(R.startCall(s, { now: NOW }), s, 'one call at a time');
  assert.match(renderCall(s.call, NOW), /正在呼叫 Gravit…[\s\S]*data-action="hangUp" aria-label="Hang up"/);
  s = R.connectCall(s, { now: NOW });
  assert.deepEqual([s.call.status, s.call.since], ['live', NOW]);
  const live = renderCall(s.call, NOW + 75_000);
  assert.match(live, /class="call-timer">01:15</);
  assert.match(live, /data-action="toggleMute" aria-pressed="false" aria-label="Mute"/);
  assert.equal(R.toggleMute(s).call.muted, true);
  const ended = R.hangUp(s, { now: NOW + 75_000 });
  assert.equal(ended.call, null);
  const card = conv(ended, 'c-1').messages.at(-1);
  assert.deepEqual([card.kind, card.answer, card.data.duration, card.data.dir], ['call', 'accepted', 75_000, 'out']);
  const cancelled = R.hangUp(R.startCall(fresh(), { now: NOW }), { now: NOW + 2000 });
  assert.equal(conv(cancelled, 'c-1').messages.at(-1).answer, 'cancelled');
  let inc = R.answerCall(R.incomingCall(fresh(), { from: 'gravit', about: '想说 BTC 的事' }), { accept: true, now: NOW });
  assert.deepEqual([inc.call.status, inc.call.dir], ['live', 'in']);
  inc = R.hangUp(inc, { now: NOW + 8000 });
  assert.deepEqual([conv(inc, 'c-1').messages.at(-1).answer, conv(inc, 'c-1').messages.at(-1).data.about], ['accepted', '想说 BTC 的事']);
});

test('the call card says how it went', async () => {
  const { renderMessage } = await import('../js/render/thread.js');
  const s = fresh();
  const r = m => renderMessage({ id: 'm-x', at: NOW, from: 'gravit', kind: 'call', text: '', ...m }, s.conversations[0], s);
  assert.match(r({ answer: 'accepted', data: { dir: 'out', duration: 75_000 } }), /打给 Gravit[\s\S]*class="chip up">接通 · 01:15</);
  assert.match(r({ answer: 'missed', data: { dir: 'in', about: 'x' } }), /Gravit 来电[\s\S]*>没接</);
  assert.match(r({ answer: 'cancelled', data: { dir: 'out' } }), />没打通</);
});

test('Mail is a screen: a letter opens by its route and is marked read; an unknown letter falls back to the inbox', async () => {
  const { renderMailScreen } = await import('../js/render/mail.js');
  assert.equal(R.openMail, undefined, 'no mailbox drawer any more');
  assert.equal('open' in fresh().mail, false);
  let s = R.nav(R.toggleDetails(fresh()), { screen: 'mail', id: null });
  assert.equal(s.detailsOpen, false, 'going to Mail closes Details');
  const inbox = renderMailScreen(s, NOW);
  assert.match(inbox, /^<main class="main mail">/);
  assert.match(inbox, /<div class="mail-none">[\s\S]*?<span class="dim">没选中邮件<\/span><\/div>/);
  s = R.nav(s, { screen: 'mail', id: 'mail-1' });
  assert.equal(s.mail.items[0].read, true);
  const one = renderMailScreen(s, NOW);
  assert.match(one, /^<main class="main mail has-letter">/);
  assert.match(one, /<header class="head"><h1 class="head-title">10 月对账单<\/h1><\/header>/);
  assert.match(one, /<div class="mail-meta dim">Stand-in Broker · Today 12:07<\/div>/);
  assert.match(one, /<span class="file-chip">[\s\S]*?statement-2026-10\.pdf<\/span>/);
  assert.match(one, /<p class="mail-body">本月成交 2 笔：NVDA \$25、KO 挂单中。持仓市值 \$2,510。<\/p>/);
  assert.doesNotMatch(one, /附件/);
  assert.deepEqual(R.nav(fresh(), { screen: 'mail', id: 'mail-9' }).route, { screen: 'mail', id: null });
});

test('Account panels: Move shifts a holding between venues and logs it; bad moves are refused in the panel', () => {
  let s = R.openPanel(R.openSettings(R.nav(fresh(), { screen: 'account', tab: 'portfolio' })), 'move');
  assert.deepEqual([s.account.panel, s.settingsOpen], ['move', false], 'one drawer at a time');
  const moved = R.moveFunds(s, { from: 'Stand-in Wallet', to: 'Stand-in Exchange', asset: 'USDC', amount: '200', now: NOW });
  assert.equal(moved.account.panel, null);
  assert.equal(moved.account.holdings.find(h => h.name === 'USDC' && h.venue === 'Stand-in Wallet').value, 2290);
  assert.equal(moved.account.holdings.find(h => h.name === 'USDC' && h.venue === 'Stand-in Exchange').value, 200);
  assert.match(moved.account.activity[0].text, /Move \$200 USDC · Stand-in Wallet → Stand-in Exchange/);
  assert.equal(moved.account.netWorth, 12480, 'a move does not change what you own');
  const again = R.moveFunds(R.openPanel(moved, 'move'), { from: 'Stand-in Wallet', to: 'Stand-in Exchange', asset: 'USDC', amount: '10', now: NOW });
  assert.equal(again.account.holdings.find(h => h.name === 'USDC' && h.venue === 'Stand-in Exchange').value, 210, 'a second move adds to the same holding');
  const err = (from, to, asset, amount) => R.moveFunds(s, { from, to, asset, amount, now: NOW }).account.panelError;
  assert.equal(err('Stand-in Wallet', 'Stand-in Exchange', 'USDC', '0'), '要一个大于 0 的数');
  assert.equal(err('Stand-in Wallet', 'Stand-in Wallet', 'USDC', '5'), '换一个去处');
  assert.equal(err('Stand-in Exchange', 'Stand-in Broker', 'AAPL', '5'), 'Stand-in Exchange 没有 AAPL');
  assert.equal(err('Stand-in Wallet', 'Stand-in Exchange', 'USDC', '9999'), 'Stand-in Wallet 只有 $2,490');
});

test('Connect an account: a venue connects after a moment and joins the list; Receive copies; panels render', async () => {
  const { renderAccount } = await import('../js/render/account.js');
  let s = R.openPanel(R.nav(fresh(), { screen: 'account', tab: 'venues' }), 'connect');
  s = R.connectVenue(s, 'Coinbase');
  assert.equal(s.account.connecting, 'Coinbase');
  assert.match(renderAccount(s), /连接中…/);
  s = R.venueConnected(s, 'Coinbase');
  assert.equal(s.account.connecting, null);
  assert.deepEqual(s.account.venues.at(-1), { name: 'Coinbase', line: 'Connected · stand-in · Gravit: read only', state: 'Healthy' });
  assert.match(renderAccount(s), /data-name="Coinbase"[^>]*disabled>已连接</);
  assert.equal(R.venueConnected(s, 'Coinbase'), s, 'connecting twice is one venue');
  const p = R.nav(fresh(), { screen: 'account', tab: 'portfolio' });
  const page = renderAccount(p);
  for (const name of ['move', 'receive', 'statement']) assert.match(page, new RegExp(`data-action="openPanel" data-panel="${name}"`), name);
  assert.match(renderAccount(R.nav(fresh(), { screen: 'account', tab: 'venues' })), /data-action="openPanel" data-panel="connect"/);
  const move = renderAccount(R.openPanel(p, 'move'));
  assert.match(move, /<form class="move-form" data-action="moveFunds">/);
  for (const n of ['from', 'asset', 'to', 'amount']) assert.match(move, new RegExp(`name="${n}"`), n);
  const receive = renderAccount(R.openPanel(p, 'receive'));
  assert.match(receive, /<svg class="qr"/);
  assert.match(receive, /0xec4c…16c1/);
  assert.match(receive, /data-action="copyAddress">复制地址</);
  assert.match(renderAccount(R.setCopied(R.openPanel(p, 'receive'), true)), />已复制</);
  const statement = renderAccount(R.openPanel(p, 'statement'));
  assert.equal((statement.match(/class="activity-row"/g) ?? []).length, 4);
  assert.match(statement, /data-action="exportStatement">Export CSV</);
});

// round-two review fixes

test('Details offers only what still works: no Withdraw or Stop once closed, no End limit without a limit', () => {
  const stopped = R.toggleDetails(R.stopGravit(fresh(), { convId: 'c-1', now: NOW }));
  const d = renderDetails(conv(stopped, 'c-1'), stopped);
  assert.doesNotMatch(d, /data-action="withdraw"/);
  assert.doesNotMatch(d, /data-action="stopGravit"/);
  const open = R.toggleDetails(R.nav(fresh(), { screen: 'messages', id: 'c-3' }));
  assert.doesNotMatch(renderDetails(conv(open, 'c-3'), open), /data-action="endLimit"/, 'c-3 has no limit');
});

test('Top up cannot take more than your USDC holding', () => {
  const s = R.commitEdit(R.startEdit(fresh(), { kind: 'wallet', dir: 'in' }), { values: { amount: '3000' }, now: NOW });
  assert.equal(s.edit.error, '你的 USDC 只有 $2,490');
  assert.equal(s.account.holdings.find(h => h.key === 'stable:USDC').value, 2490);
});

test('one drawer at a time: each opener closes the others, and an Account panel does not follow you off Account', () => {
  const panel = R.openPanel(R.nav(fresh(), { screen: 'account', tab: 'portfolio' }), 'receive');
  const mailed = R.nav(R.askConfirm(panel, { action: 'forgetAll' }), { screen: 'mail', id: null });
  assert.deepEqual([mailed.account.panel, mailed.confirm], [null, null], 'going to Mail closes a panel and drops a pending confirm');
  assert.equal(R.toggleDetails(R.openPlugin(fresh(), 'news')).discover.drawer, null, 'Details replaces a plugin drawer');
  assert.equal(R.openSettings(panel).account.panel, null);
  assert.equal(R.nav(panel, { screen: 'discover', id: null }).account.panel, null, 'leaving Account closes its panel');
  assert.equal(R.nav(panel, { screen: 'account', tab: 'venues' }).account.panel, 'receive', 'moving inside Account keeps it');
});

test('Memory edits in place, Forget all asks first, and Reset demo asks first', () => {
  const s = R.nav(fresh(), { screen: 'account', tab: 'memory' });
  assert.match(renderMemory(R.startEdit(s, { kind: 'memory', id: 'mem-1' })), /<span class="inline-edit"><input id="edit-text" class="input small" name="text" type="text" value="偏价值，不追热点" aria-label="改成">/);
  assert.match(renderMemory(R.askConfirm(s, { action: 'forgetAll' })), /data-action="confirmYes">确认全部忘掉</);
  assert.match(renderSettings(R.askConfirm(s, { action: 'resetDemo' })), /data-action="confirmYes">确认重置</);
});
