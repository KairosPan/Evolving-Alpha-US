// gravit-ui/tests/messages-screen.test.js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { currentConversation, renderMessagesScreen, renderHead, renderComposer, renderDetails, renderBanner, renderCall, renderStub } from '../js/render/messages.js';
import { seg, segLinks, kv, sec } from '../js/render/controls.js';
import { reducers as R } from '../js/reducers/index.js';
import { seed } from '../js/data/seed.js';

const NOW = new Date(2026, 9, 9, 14, 7).getTime();
const count = (h, re) => (h.match(re) ?? []).length;

test('currentConversation falls back to the first when the route names nothing or a missing id', () => {
  const s = seed(NOW);
  assert.equal(currentConversation(s).id, 'c-1');
  assert.equal(currentConversation({ ...s, route: { screen: 'messages', id: 'c-99' } }).id, 'c-1');
  assert.equal(currentConversation({ ...s, route: { screen: 'messages', id: 'c-3' } }).id, 'c-3');
  assert.equal(currentConversation({ ...s, conversations: [] }), null);
});

test('F1: the head is title + Working + Details; the thread and the composer follow; no small print', () => {
  const s = seed(NOW);
  const h = renderMessagesScreen(s, NOW);
  assert.match(h, /<main class="main">/);
  assert.match(h, /<h1 class="head-title">小仓位 BTC，\$70k 以下<\/h1>/);
  assert.match(h, /class="status up"[^>]*>[\s\S]*?Working/);
  assert.match(h, /data-action="toggleDetails" aria-expanded="false"/);
  assert.match(h, /class="thread" id="thread"/);
  assert.match(h, /<form class="composer" data-action="send">/);
  assert.match(h, /aria-label="Add a file"/);
  assert.match(h, /aria-label="Voice input"/);
  assert.match(h, /type="submit" class="send-key" aria-label="Sign and send"/);
  assert.match(h, /placeholder="Tell Gravit…"/);
  assert.doesNotMatch(h, /发出去就是/);
  assert.doesNotMatch(h, /class="drawer/);
});

test('F14: a group gets the cluster head with the members line and the @ placeholder', () => {
  const s = R.nav(seed(NOW), { screen: 'messages', id: 'c-4' });
  const h = renderMessagesScreen(s, NOW);
  assert.match(h, /<header class="head centered">/);
  assert.equal(count(h, /class="cluster-item"/g), 3);
  assert.match(h, /class="head-task">跟 Pelosi 和 Buffett 挑股</);
  assert.match(h, /Gravit · 美国政客 bot · Buffett bot · 3 位/);
  assert.match(h, /placeholder="Tell Gravit… 打 @ 点名一个 bot"/);
});

test('F7: the draft head is avatar + title input + To line; the limit chips sit over the composer; a group draft shows the cluster', () => {
  let s = R.startDraft(seed(NOW), { now: NOW });
  s = R.setDraftTitle(s, '买一点 SOL');
  const h = renderMessagesScreen(s, NOW);
  assert.match(h, /<header class="head centered draft">/);
  assert.match(h, /data-action="cancelDraft"/);
  assert.match(h, /id="nm-title"[^>]*data-action="draftTitle"[^>]*value="买一点 SOL"/);
  assert.match(h, /class="to-label">To:</);
  assert.match(h, /class="to-chip">[\s\S]*Gravit</);
  assert.match(h, /data-action="toggleDraftGroup"/);
  assert.match(h, /class="limit-label">附一份额度</);
  assert.match(h, /data-action="draftLimit" data-key="perOrder">每单 \$25/);
  assert.match(h, /data-key="until">到 Oct 15/);
  assert.match(h, /data-key="venue">在 Stand-in Exchange/);
  assert.match(h, /data-action="toggleDraftAttach">不附</);
  const off = renderMessagesScreen(R.toggleDraftAttach(s), NOW);
  assert.doesNotMatch(off, /data-key="perOrder"/);
  assert.match(off, /data-action="toggleDraftAttach">附上</);
  const g = R.toggleDraftGroup(s);
  assert.equal(g.draft.group, true);
  const gh = renderMessagesScreen(g, NOW);
  assert.equal(count(gh, /class="cluster-item"/g), 3, 'Gravit plus the two installed bots');
  const sent = R.send(g, { text: '两位看看 KO', now: NOW });
  assert.equal(sent.conversations[0].kind, 'group');
  assert.deepEqual(sent.conversations[0].members, ['gravit', 'politician', 'buffett']);
});

test('F6: no conversations → the empty state with three suggestion chips', () => {
  const s = { ...seed(NOW), conversations: [], route: { screen: 'messages', id: null } };
  const h = renderMessagesScreen(s, NOW);
  assert.match(h, /class="empty-title">还没有交给 Gravit 的事</);
  assert.equal(count(h, /data-action="suggest"/g), 3);
  assert.match(h, /data-text="跟单 Pelosi"/);
  assert.match(h, /<form class="composer"/);
});

test('F8: Details drawer sections and keys', () => {
  const s = R.toggleDetails(seed(NOW));
  const h = renderMessagesScreen(s, NOW);
  assert.match(h, /<main class="main with-drawer">/);
  assert.match(h, /<aside class="drawer details" aria-label="Details">/);
  assert.match(h, /data-action="toggleDetails" aria-expanded="true"/);
  const d = renderDetails(s.conversations[0], s);
  assert.match(d, /你委托于 Oct 9 · 到 Oct 15 · intent-0003/);
  assert.match(d, /data-action="withdraw" data-conv="c-1"/);
  assert.match(d, /data-action="changeWords" data-conv="c-1"/);
  assert.match(d, /\$95/, 'what is left of the limit');
  assert.match(d, /data-action="endLimit" data-conv="c-1"/);
  assert.match(d, /Price feed/);
  assert.match(d, /href="#\/discover"/);
  assert.match(d, /0xec4c…16c1/);
  assert.match(d, /class="seg-item pressed" aria-pressed="true" data-action="setMode" data-value="Guard"/);
  assert.match(d, /class="btn-danger" data-action="stopGravit" data-conv="c-1"/);
  const none = renderDetails({ ...s.conversations[2] }, s);
  assert.match(none, /没附额度/);
  const renamed = R.rename(s, { convId: 'c-1', title: '  BTC 小仓  ' });
  assert.equal(renamed.conversations[0].title, 'BTC 小仓');
  assert.equal(R.rename(s, { convId: 'c-1', title: '  ' }), s);
});

test('banner, call, stub and the controls', () => {
  const s = seed(NOW);
  const b = renderBanner({ id: 'b', headline: 'H', body: 'B', at: NOW }, s);
  assert.match(b, /class="banner" role="status"/);
  assert.match(b, />突发</);
  assert.match(b, /14:07/);
  assert.match(b, /data-action="dismissBanner" aria-label="Dismiss"/);
  assert.match(b, /href="#\/messages\/c-1"/);
  const c = renderCall({ from: 'gravit', about: '想说 BTC 的事' });
  assert.match(c, /class="call-scrim"/);
  assert.match(c, /class="key no big" data-action="answerCall" data-accept="0" aria-label="Decline"/);
  assert.match(c, /class="key yes big" data-action="answerCall" data-accept="1" aria-label="Accept"/);
  assert.match(renderStub({ screen: 'markets', id: 'NVDA' }), /Markets › NVDA/);
  assert.match(renderStub({ screen: 'trade' }), /<h1 class="head-title">Trade<\/h1>/);
  assert.equal(seg(['A', 'B'], 'B', 'pick'), '<div class="seg"><button type="button" class="seg-item" aria-pressed="false" data-action="pick" data-value="A">A</button><button type="button" class="seg-item pressed" aria-pressed="true" data-action="pick" data-value="B">B</button></div>');
  assert.match(segLinks([['Portfolio', '#/account/portfolio', 'portfolio'], ['Memory', '#/account/memory', 'memory']], 'memory'), /class="seg-item pressed" aria-current="page" href="#\/account\/memory"/);
  assert.equal(kv([['For', '<b>x</b>']]), '<div class="kv-list"><div class="kv"><span class="kv-k">For</span><span class="kv-v"><b>x</b></span></div></div>');
  assert.equal(sec('怎么付', ['<免费>']), '<div class="dsec"><div class="dsec-label">怎么付</div><div class="dsec-line">&lt;免费&gt;</div></div>');
  assert.match(renderComposer({ placeholder: 'x', above: '<i>a</i>' }), /<form class="composer" data-action="send"><i>a<\/i>/);
});
