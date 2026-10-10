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
  assert.equal(SEED_VERSION, 2);
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

test('Memory edits in place, Forget all asks first, and Reset demo asks first', () => {
  const s = R.nav(fresh(), { screen: 'account', tab: 'memory' });
  assert.match(renderMemory(R.startEdit(s, { kind: 'memory', id: 'mem-1' })), /<span class="inline-edit"><input id="edit-text" class="input small" name="text" type="text" value="偏价值，不追热点" aria-label="改成">/);
  assert.match(renderMemory(R.askConfirm(s, { action: 'forgetAll' })), /data-action="confirmYes">确认全部忘掉</);
  assert.match(renderSettings(R.askConfirm(s, { action: 'resetDemo' })), /data-action="confirmYes">确认重置</);
});
