// gravit-ui/tests/canvas-round.test.js — the canvas round (2026-10-13): where the code moved to meet the re-laid boards
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { renderThread, renderMessage } from '../js/render/thread.js';
import { renderHead, renderDetails, renderBanner, renderCall, renderComposer, renderMessagesScreen } from '../js/render/messages.js';
import { renderList, renderNav } from '../js/render/rail.js';
import { avatar } from '../js/render/avatars.js';
import { confirmPair } from '../js/render/controls.js';
import { director } from '../js/driver.js';
import { reducers as R } from '../js/reducers/index.js';
import { seed } from '../js/data/seed.js';
import { message } from '../js/messages.js';
import { fmtDuration } from '../js/time.js';
import { boot } from '../js/app.js';
import { fakeWindow } from './helpers/fake-dom.js';

const NOW = new Date(2026, 9, 9, 14, 7).getTime();
const sleep = ms => new Promise(r => setTimeout(r, ms));
const css = await readFile(new URL('../css/app.css', import.meta.url), 'utf8');
// the first rule written for exactly this selector
const rule = sel => {
  const i = css.indexOf(`\n${sel} {`);
  assert.ok(i >= 0, `no rule for ${sel}`);
  return css.slice(i + 1, css.indexOf('}', i) + 1);
};
const btc = { id: 'c-1', kind: 'gravit' };
const say = (kind, data = {}, extra = {}) => renderMessage({ id: 'm-x', at: NOW, ...message('gravit', kind, 'x', data), ...extra }, btc, seed(NOW));

// ---- the thread (F1, F3, F15)

test('an order card says venue, type and amount; its card id stays in the record', () => {
  const s = seed(NOW);
  const h = renderThread(s.conversations[0], s, NOW);
  assert.match(h, /<div class="dim">Stand-in Exchange · market · about \$5\.00<\/div>/);
  assert.doesNotMatch(h, /card-0001/);
});

test('a chip inside a card hugs its words', () => {
  assert.match(rule('.card > .chip'), /align-self: flex-start/);
});

test('the technicals head says when the candles were read', () => {
  assert.match(renderMessage({ id: 'm-t', at: NOW, ...director.ta(NOW) }, btc, seed(NOW)), /<span class="dim">4h · technicals · 14:07<\/span>/);
});

test('plain talk is 66% wide; every card and green bubble is 80%', () => {
  assert.match(say('text'), /class="msg-body"><div class="bubble grey">/);
  for (const k of ['card', 'limit', 'install', 'receipt', 'proposal', 'done', 'refusal', 'alert', 'signal']) assert.match(say(k, k === 'install' ? { plugin: 'news' } : {}), /class="msg-body wide"/, k);
  assert.match(rule('.msg-body'), /max-width: 66%/);
  assert.match(rule('.msg-body.wide'), /max-width: 80%/);
});

test('the quote bar and the technicals rules draw in the cash tone', () => {
  assert.match(rule('.quote'), /border-left: 2px solid var\(--alloc-cash\)/);
  assert.match(rule('.kline-rule'), /stroke: var\(--alloc-cash\)/);
});

test('a monitor posts its read-only signal and Gravit answers it (kind 7)', () => {
  const [sig, reply] = director.monitor();
  assert.deepEqual([sig.msg.from, sig.msg.kind, sig.msg.text, sig.msg.data.source], ['telegram', 'signal', 'SOL is about to take off, get in', 'Telegram monitor · group “Alpha” · @kol_x']);
  assert.deepEqual([reply.msg.from, reply.msg.kind, reply.msg.text], ['gravit', 'text', 'Seen. Not chasing.']);
  assert.ok(reply.delay > sig.delay);
  const h = renderMessage({ id: 'm-s', at: NOW, ...sig.msg }, btc, seed(NOW));
  assert.match(h, />TG<\/span>/);
  assert.match(h, /<div class="card white"><div class="dim">Telegram monitor · group “Alpha” · @kol_x<\/div><div class="quote">SOL is about to take off, get in<\/div><\/div>/);
});

test('the director’s Monitor key posts the signal, then Gravit’s answer', async () => {
  const f = fakeWindow();
  const store = boot(f.win);
  try {
    f.click(f.element({ tagName: 'BUTTON', dataset: { action: 'director', key: 'monitor' } }));
    await sleep(500);
    assert.equal(store.get().conversations[0].messages.at(-1).kind, 'signal');
    await sleep(1400);
    assert.equal(store.get().conversations[0].messages.at(-1).text, 'Seen. Not chasing.');
  } finally {
    store.timers.clear();
  }
});

// ---- the Messages screen (F8, F14)

test('the group head’s members line is 12 px', () => {
  const s = seed(NOW);
  const g = s.conversations.find(c => c.kind === 'group');
  assert.match(renderHead(g, s), /<div class="dim members">Gravit · US politician bot · Buffett bot · 3 members<\/div>/);
  assert.match(rule('.members'), /font-size: 12px/);
});

test('Details lists each plugin with its kind at the right; Stop Gravit hugs its label', () => {
  const s = R.toggleDetails(seed(NOW));
  assert.match(renderDetails(s.conversations[0], s), /<div class="dsec-line plug-row"><span>Price feed<\/span><span class="dim">Data<\/span><\/div><div class="dsec-line plug-row"><span>Address fraud check<\/span><span class="dim">Crypto<\/span><\/div>/);
  assert.match(rule('.plug-row'), /justify-content: space-between/);
  assert.match(rule('.dsec > .btn-danger, .dsec > .confirm'), /align-self: flex-start/);
});

test('the breaking banner names the conversation it lands in, links its ticker, and drops over the conversation', () => {
  const s = seed(NOW);
  const b = director.breaking(NOW);
  const h = renderBanner(b, s);
  assert.match(h, /^<div class="banner-zone"><div class="banner" role="status">/);
  assert.match(h, /<span class="dim">14:07 · Small BTC position under \$70k<\/span>/);
  assert.match(h, /You hold <a class="ticker" href="#\/markets\/BTC">BTC/);
  assert.match(renderBanner(b, s, { enter: true }), /<div class="banner drop" role="status">/);
  const landed = R.dismissBanner(R.showBanner(s, b), { now: NOW });
  assert.match(renderThread(landed.conversations[0], landed, NOW), /You hold <a class="ticker" href="#\/markets\/BTC">BTC/);
  assert.match(rule('.banner-zone'), /position: fixed/);
  assert.match(css, /\n\.list ~ \.banner-zone \{ left: calc\(var\(--nav\) \+ var\(--list\)\); \}/);
  assert.match(rule('.banner.drop'), /animation: /);
});

test('the banner drops in once: a later render keeps it still', async () => {
  const f = fakeWindow();
  const store = boot(f.win);
  try {
    f.click(f.element({ tagName: 'BUTTON', dataset: { action: 'director', key: 'breaking' } }));
    assert.match(f.root.innerHTML, /class="banner drop"/);
    store.dispatch('toggleRail');
    assert.match(f.root.innerHTML, /class="banner" role="status"/);
  } finally {
    store.timers.clear();
  }
});

// ---- the first and second levels (F1, F17, F18)

test('the second level’s head: the title at 22/800 and the new-message + as a 32 px round ink key', () => {
  assert.match(renderList(seed(NOW), NOW), /<h2 class="list-title">Messages<\/h2><button type="button" class="new-key" data-action="startDraft" aria-label="New message"><svg width="18"/);
  assert.match(rule('.list-title'), /font-size: 22px; font-weight: 800;/);
  assert.match(rule('.new-key'), /width: 32px; height: 32px;[^}]*border-radius: var\(--radius-pill\);[^}]*color: var\(--text\)/);
});

test('the owner’s avatar writes You at 10 px', () => {
  assert.match(avatar('you', 28), /font-size:10px">You</);
});

test('a badge hangs over the corner of its key at 20 px', () => {
  assert.match(rule('.nav-badge'), /min-width: 20px; height: 20px; padding: 0 6px;/);
  assert.match(css, /\n\.line-key \.nav-badge \{ position: absolute; top: -8px; right: -6px; \}/);
});

test('collapsed, the first level is a column of 44 px squares; the collapse key is a 28 px round key', () => {
  assert.match(rule('.rail.mini'), /padding: 16px 12px;/);
  assert.match(css, /\n\.rail\.mini \.account \{ min-height: 44px; height: 44px; \}/);
  assert.match(renderNav(seed(NOW)), /<button type="button" class="rail-toggle" data-action="toggleRail" aria-expanded="true" aria-label="Collapse navigation"><svg width="16"/);
  assert.match(rule('.rail-toggle'), /width: 28px; height: 28px;[^}]*border-radius: var\(--radius-pill\)/);
});

// ---- the composer, the editors, the confirms, the mic (F24 1–4)

test('picked files sit inside the composer box, words only', () => {
  const s = R.addFiles(seed(NOW), [{ name: 'statement-2026-10.pdf', size: 1 }]);
  assert.match(renderComposer({ compose: s.compose }), /<div class="composer-pill with-files"><div class="files"><span class="file-chip">statement-2026-10\.pdf<button type="button" class="file-x"/);
  assert.match(rule('.composer-pill.with-files'), /border-radius: 20px/);
});

test('an editor names each box, stands in place of its buttons, and uses 36 px boxes and 32 px keys', () => {
  const open = edit => { const s = R.startEdit(R.toggleDetails(seed(NOW)), edit); return renderDetails(s.conversations[0], s); };
  const limit = open({ kind: 'limit', convId: 'c-1' });
  assert.match(limit, /<label class="edit-word" for="edit-perOrder">an order<\/label><input id="edit-perOrder" class="input small" name="perOrder" type="number" value="25" aria-label="Dollars an order"><label class="edit-word" for="edit-total">in all<\/label><input id="edit-total" class="input small" name="total" type="number" value="100" aria-label="Dollars in all">/);
  assert.match(limit, /<button type="button" class="key yes" data-action="commitEdit" aria-label="Save"><svg width="14"/);
  assert.doesNotMatch(limit, /data-action="changeLimit"/, 'the editor stands in place of Change limit and End limit');
  const top = open({ kind: 'wallet', dir: 'in' });
  assert.match(top, /<label class="edit-word" for="edit-amount">Top up<\/label><input id="edit-amount" class="input small" name="amount" type="number" value="" aria-label="Top up amount">/);
  assert.doesNotMatch(top, /data-action="topUp"/);
  assert.match(open({ kind: 'wallet', dir: 'out' }), /<label class="edit-word" for="edit-amount">Take back<\/label>/);
  assert.doesNotMatch(open({ kind: 'rename', convId: 'c-1' }), /data-action="changeWords"/);
  assert.match(rule('.input.small'), /height: 36px/);
  const draft = R.startEdit(R.startDraft(seed(NOW), { now: NOW }), { kind: 'draftLimit', key: 'perOrder' });
  assert.match(renderMessagesScreen(draft, NOW), /<label class="edit-word" for="edit-value">an order<\/label><input id="edit-value" class="input small" name="value" type="number" value="25" aria-label="Dollars an order">/);
  const venue = R.startEdit(R.startDraft(seed(NOW), { now: NOW }), { kind: 'draftLimit', key: 'venue' });
  assert.match(renderMessagesScreen(venue, NOW), /<label class="edit-word" for="edit-value">on<\/label><select id="edit-value" class="input small" name="value" aria-label="Trade on venue">/);
  const until = R.startEdit(R.startDraft(seed(NOW), { now: NOW }), { kind: 'draftLimit', key: 'until' });
  assert.match(renderMessagesScreen(until, NOW), /aria-label="Days until it ends"/);
});

test('a confirm’s two keys are the same height', () => {
  assert.equal(confirmPair('Yes, stop Gravit'), '<span class="confirm"><button type="button" class="btn-danger" data-action="confirmYes">Yes, stop Gravit</button><button type="button" class="btn-sm" data-action="cancelConfirm">No</button></span>');
});

test('the mic, listening, is an ink key that says Stop listening', () => {
  assert.match(renderComposer({ compose: { files: [], listening: true } }), /class="round-key mic on" data-action="toggleMic" aria-pressed="true" aria-label="Stop listening"/);
  assert.match(rule('.round-key.mic.on'), /background: var\(--primary\); color: var\(--on-primary\);/);
});

test('the heard words fill the composer while the mic listens', async () => {
  const f = fakeWindow();
  const box = f.withId('say', { tagName: 'INPUT' });
  const store = boot(f.win);
  try {
    f.click(f.element({ tagName: 'BUTTON', dataset: { action: 'toggleMic' } }));
    await sleep(800);
    assert.equal(store.get().compose.listening, true);
    assert.match(box.value, /^Buy a/, 'words arrive while it listens');
    assert.ok(box.value.length < 'Buy a small BTC position under $70k'.length);
    await sleep(1400);
    assert.equal(store.get().compose.listening, false);
    assert.equal(box.value, 'Buy a small BTC position under $70k');
  } finally {
    store.timers.clear();
  }
});

// ---- calls (F24 5)

test('a call’s length reads m:ss', () => {
  assert.deepEqual([fmtDuration(32_000), fmtDuration(75_000), fmtDuration(600_000)], ['0:32', '1:15', '10:00']);
});

test('only a call coming in is red-edged; ringing out says Ringing; a live call shows no transcript line', () => {
  assert.match(renderCall(director.call(), NOW), /<div class="call in" role="dialog" aria-label="Gravit is calling">[\s\S]*<div class="dim">About BTC, 30 seconds<\/div>/);
  const out = renderCall({ from: 'gravit', about: '', dir: 'out', status: 'ringing', since: NOW }, NOW);
  assert.match(out, /<div class="call" role="dialog" aria-label="Calling Gravit">[\s\S]*<div class="card-title">Calling Gravit…<\/div><div class="dim">Ringing<\/div>/);
  const live = renderCall({ from: 'gravit', about: 'About BTC', dir: 'out', status: 'live', since: NOW }, NOW + 32_000);
  assert.match(live, /<div class="card-title">Gravit<\/div><div class="call-timer">0:32<\/div><div class="call-keys">/);
  assert.doesNotMatch(live, /Gravit: /);
  assert.match(rule('.call'), /border: 1px solid var\(--card-border\)/);
  assert.match(rule('.call.in'), /border-color: var\(--down-edge\)/);
  assert.match(rule('.call-timer'), /font-size: 20px; font-weight: 800;/);
});

test('the after-call card: white once it connected, red when missed; the topic with its time, and what was said', () => {
  let s = R.connectCall(R.startCall(seed(NOW), { now: NOW }), { now: NOW });
  s = R.hangUp(s, { now: NOW + 32_000 });
  const out = s.conversations[0].messages.at(-1);
  assert.deepEqual([out.data.about, out.answer], ['About BTC', 'accepted']);
  assert.match(renderMessage(out, btc, s), /<div class="card white"><div class="card-head"><div class="card-title">Called Gravit<\/div><span class="chip up">Connected · 0:32<\/span><\/div><div class="dim">About BTC · 14:07<\/div><div>Said: BTC is at 62\.8k now; it watches it and calls if it moves\.<\/div><\/div>/);
  let inc = R.answerCall(R.incomingCall(seed(NOW), director.call()), { accept: true, now: NOW });
  inc = R.hangUp(inc, { now: NOW + 30_000 });
  assert.match(renderMessage(inc.conversations[0].messages.at(-1), btc, inc), /Gravit called[\s\S]*<div class="dim">About BTC · 14:07<\/div><div>Said: Hold until CPI is out; raise the order cap to \$50 after\.<\/div>/);
  const missed = R.answerCall(R.incomingCall(seed(NOW), director.call()), { accept: false, now: NOW });
  const m = renderMessage(missed.conversations[0].messages.at(-1), btc, missed);
  assert.match(m, /<div class="card red">[\s\S]*>Missed<\/span><\/div><div class="dim">About BTC · 14:07<\/div><\/div>/);
  const cancelled = R.hangUp(R.startCall(seed(NOW), { now: NOW }), { now: NOW + 2000 });
  assert.match(renderMessage(cancelled.conversations[0].messages.at(-1), btc, cancelled), /<div class="card white">[\s\S]*>Did not connect<\/span><\/div><div class="dim">14:07<\/div><\/div>/);
});

// ---- Account, Memory, Mail, Create, Trade (F5, F13, F18, F19, F20, F23, F24 6)

test('Net worth is a 12 px label; a holding’s change is coloured, not bold', async () => {
  const { renderAccount } = await import('../js/render/account.js');
  const h = renderAccount(R.nav(seed(NOW), { screen: 'account', tab: 'portfolio' }));
  assert.match(h, /<div class="label">Net worth<\/div>/);
  assert.match(rule('.label'), /font-size: 12px; font-weight: 600; color: var\(--dim\);/);
  assert.match(rule('.holding > .up, .holding > .down'), /font-weight: 400/);
});

test('Receive takes money into the owner’s Stand-in Wallet: USDC on Base, the QR beside the address', async () => {
  const { renderAccount } = await import('../js/render/account.js');
  const h = renderAccount(R.openPanel(R.nav(seed(NOW), { screen: 'account', tab: 'portfolio' }), 'receive'));
  assert.match(h, /<aside class="drawer" aria-label="Receive · USDC"><div class="drawer-head"><div class="drawer-title"><h2>Receive · USDC<\/h2><span class="chip grey">Base<\/span><\/div>/);
  assert.match(h, /<div class="receive"><svg class="qr"[\s\S]*<\/svg><div class="receive-side"><div><span class="mono">0x9a7c…d41e<\/span><span class="dim"> · Stand-in Wallet<\/span><\/div><button type="button" class="btn-sm" data-action="copyAddress">Copy address<\/button><\/div><\/div>/);
  assert.doesNotMatch(h, /0xec4c/, 'Gravit’s own wallet is reached through Details’ Top up, not Account');
  assert.match(rule('.receive .qr'), /width: 88px; height: 88px;/);
});

test('Memory reads as the boards word it, with the sources spec §8 lists', async () => {
  const { renderMemory } = await import('../js/render/account.js');
  const s = seed(NOW);
  const texts = Object.fromEntries(s.memory.entries.map(e => [e.id, [e.text, e.source]]));
  assert.deepEqual(texts['mem-1'], ['Value over hype', 'You said']);
  assert.deepEqual(texts['mem-4'], ['No order over $25; real money passes me first', 'From your limit']);
  assert.deepEqual(texts['mem-5'], ['Telegram calls: read, never chase', 'You said']);
  assert.deepEqual(texts['mem-6'], ['Ask before adding; never widen a limit alone', 'Learned when you declined']);
  assert.deepEqual(texts['mem-7'], ['BTC on the exchange, cheaper than the DEX', 'Compared on its own']);
  assert.deepEqual(texts['mem-9'], ['Brief at 7:30; hold before CPI', 'You said']);
  assert.match(renderMemory(s), /<span class="chip grey">Group chats<\/span><span>Who speaks first, whose word is discounted<\/span>/);
});

test('an unread letter’s subject is bold at 700', () => {
  assert.match(css, /\n\.row\.unread \.row-preview \{ color: var\(--text\); font-weight: 700; \}/);
});

test('Create’s Client and Where segments are 38 px like every other segment; header pills are weight 600', () => {
  assert.match(rule('.radio-item span'), /min-height: 38px;/);
  assert.match(css, /\n\.btn-sm, \.pill \{[^}]*font-weight: 600;/);
});

test('an order on a book says so with the product’s apostrophe', () => {
  assert.equal(seed(NOW).account.orders.find(o => o.id === 'ord-0008').note, 'on Stand-in Broker’s book at 58.2');
});

test('the picker marks the market whose ticket is open', async () => {
  const { renderTrade } = await import('../js/render/trade.js');
  const s = R.openTicket(R.nav(seed(NOW), { screen: 'trade' }), { id: 'BTC', venue: 'Stand-in Exchange', side: 'buy', now: NOW });
  const h = renderTrade(s, NOW);
  assert.equal((h.match(/class="tk-row on"/g) ?? []).length, 1, 'one row, the first that names it');
  assert.match(h, /<button type="button" class="tk-row on" aria-current="true" data-action="pickMarket" data-id="BTC"/);
  assert.match(rule('.tk-row.on'), /background: var\(--bg\)/);
  assert.doesNotMatch(renderTrade(R.nav(seed(NOW), { screen: 'trade' }), NOW), /tk-row on/);
});

// ---- the review's findings (fix pass)

test('with Details folding the list, the banner zone starts where the first level ends; over an Account drawer it leaves 460 px', () => {
  assert.match(css, /\n  \.list:has\(~ \.main\.with-drawer\) ~ \.banner-zone \{ left: var\(--nav\); \}\n  \.rail\.mini ~ \.list:has\(~ \.main\.with-drawer\) ~ \.banner-zone \{ left: var\(--nav-mini\); \}/);
  const small = [...css.matchAll(/@media \(min-width: 861px\) and \(max-width: 1180px\) \{([\s\S]*?)\n\}/g)].map(m => m[1]).join('\n');
  assert.match(small, /\.list:has\(~ \.main\.with-drawer\) ~ \.banner-zone \{ left: var\(--nav-mini\); \}/);
  assert.match(css, /\n\.acct\.with-drawer ~ \.banner-zone \{ right: 460px; \}/);
  // the folded-list rules come after the rules they override
  assert.ok(css.indexOf('.list:has(~ .main.with-drawer) ~ .banner-zone') > css.indexOf('.rail.mini ~ .list ~ .banner-zone'));
});

test('a plugin page’s one key keeps its id across Install and Uninstall, so focus stays on it', async () => {
  const { renderPlugin } = await import('../js/render/discover.js');
  const off = R.nav(seed(NOW), { screen: 'plugin', id: 'news' });
  assert.match(renderPlugin(off), /<div class="plug-key"><button type="button" id="plug-key" class="btn-primary" data-action="install" data-id="news">Install<\/button>/);
  assert.match(renderPlugin(R.install(off, { id: 'news', now: NOW })), /<div class="plug-key"><button type="button" id="plug-key" class="btn-primary" data-action="uninstall" data-id="news">Uninstall<\/button>/);
  const f = fakeWindow({ hash: '#/plugin/news' });
  const key = f.withId('plug-key', { tagName: 'BUTTON', presentIf: /id="plug-key"/ });
  const store = boot(f.win);
  try {
    key.focus();
    f.click({ tagName: 'BUTTON', id: 'plug-key', dataset: { action: 'install', id: 'news' } });
    assert.ok(store.get().plugins.installed.includes('news'));
    assert.equal(f.doc.activeElement, key, 'Install leaves focus on the key, now Uninstall');
    f.click({ tagName: 'BUTTON', id: 'plug-key', dataset: { action: 'uninstall', id: 'news' } });
    assert.equal(f.doc.activeElement, key);
  } finally {
    store.timers.clear();
  }
});

test('the way back on a plugin or market page keeps focus through a re-render', async () => {
  const { renderPlugin } = await import('../js/render/discover.js');
  const { renderMarkets } = await import('../js/render/markets.js');
  assert.match(renderPlugin(R.nav(seed(NOW), { screen: 'plugin', id: 'news' })), /<a id="page-back" class="back-link page-back" href="#\/discover">‹ Discover<\/a>/);
  assert.match(renderMarkets(R.nav(seed(NOW), { screen: 'markets', id: 'BTC' }), NOW), /<a id="page-back" class="back-link page-back" href="#\/markets">‹ Markets<\/a>/);
  const f = fakeWindow({ hash: '#/markets/FED-DEC' });
  const back = f.withId('page-back', { tagName: 'A', presentIf: /id="page-back"/ });
  const store = boot(f.win);
  try {
    back.focus();
    store.dispatch('toggleRail');
    assert.equal(f.doc.activeElement, back);
  } finally {
    store.timers.clear();
  }
});

test('Send during a listen stops the mic: the sent words do not come back, and typing while it listens is kept', async () => {
  const f = fakeWindow();
  const box = f.withId('say', { tagName: 'INPUT' });
  const store = boot(f.win);
  const mic = () => f.click(f.element({ tagName: 'BUTTON', dataset: { action: 'toggleMic' } }));
  const form = { dataset: { action: 'send' } };
  try {
    box.value = 'Note:';
    f.fire('root', 'input', { target: box });
    mic();
    await sleep(600);
    f.fire('root', 'submit', { target: { closest: () => form } });
    const sent = store.get().conversations[0].messages.find(m => m.from === 'you' && m.text.startsWith('Note: Buy'));
    assert.ok(sent, 'what was heard so far goes with the message');
    assert.equal(store.get().compose.listening, false, 'sending stops the mic');
    await sleep(1600);
    assert.equal(box.value, '', 'nothing comes back into the box');
    mic();
    await sleep(300);
    box.value = `${box.value} please`;
    f.fire('root', 'input', { target: box });
    await sleep(1700);
    assert.equal(store.get().compose.listening, false);
    assert.match(box.value, / please/, 'the typed word stays');
    assert.match(box.value, /lately$/, 'the rest of what it heard follows');
  } finally {
    store.timers.clear();
  }
});

test('back from a market page, the list is where you left it and focus is on the row that opened it', async () => {
  const f = fakeWindow({ hash: '#/markets' });
  const main = f.withSelector('main');
  const row = f.withSelector('[data-action="openMarket"][data-id="DOGE"]', { tagName: 'BUTTON', dataset: { action: 'openMarket', id: 'DOGE' }, presentIf: /data-action="openMarket" data-id="DOGE"/ });
  const store = boot(f.win);
  try {
    main.scrollTop = 900;
    row.focus();
    f.click(row);
    await f.tick();
    assert.deepEqual(store.get().route, { screen: 'markets', id: 'DOGE' });
    assert.equal(main.scrollTop, 0, 'the page starts at its top');
    f.win.location.hash = '#/markets';
    await f.tick();
    assert.equal(main.scrollTop, 900, 'the list comes back where it was');
    assert.equal(f.doc.activeElement, row, 'focus returns to the row that opened the market');
  } finally {
    store.timers.clear();
  }
});

test('Discover’s dialog does not follow you onto a plugin page; a plugin page opened from a conversation goes back to Discover itself', async () => {
  const { renderPlugin } = await import('../js/render/discover.js');
  const D = { screen: 'discover', id: null };
  const withDialog = R.openCreate(R.nav(seed(NOW), D));
  assert.equal(R.nav(withDialog, { screen: 'plugin', id: 'news' }).discover.create, null);
  const shelf = R.nav(seed(NOW), { screen: 'discover', id: 'bots' });
  assert.match(renderPlugin(R.nav(shelf, { screen: 'plugin', id: 'news' })), /href="#\/discover\/bots">‹ Discover/, 'from a shelf, back to that shelf');
  const fromChat = R.nav(R.nav(shelf, { screen: 'messages', id: 'c-1' }), { screen: 'plugin', id: 'news' });
  assert.match(renderPlugin(fromChat), /href="#\/discover">‹ Discover/, 'from a conversation, back to Discover');
});

test('on a market page the facts box and the issuer box stand on white, not on the page’s own ground', () => {
  assert.match(css, /\n\.mk-page \.mk-facts, \.mk-page \.mk-iss-box \{ background: var\(--surface\); border: 1px solid var\(--card-border\); \}/);
});

test('a page opened while an Account panel is open takes focus on its way back', async () => {
  const f = fakeWindow({ hash: '#/account/portfolio' });
  const back = f.withId('page-back', { tagName: 'A', presentIf: /id="page-back"/ });
  const store = boot(f.win);
  try {
    store.dispatch('openPanel', 'receive');
    f.win.location.hash = '#/markets/BTC';
    await f.tick();
    assert.equal(store.get().account.panel, null);
    assert.equal(f.doc.activeElement, back);
  } finally {
    store.timers.clear();
  }
});

test('on a market page, No returns focus to the Cancel key; Yes, once the order is gone, to the way back', async () => {
  const f = fakeWindow({ hash: '#/markets/KO' });
  const cancel = f.withSelector('[data-action="cancelOrder"][data-id="ord-0008"]', { tagName: 'BUTTON', dataset: { action: 'cancelOrder', id: 'ord-0008' }, presentIf: /data-action="cancelOrder" data-id="ord-0008"/ });
  const yes = f.withSelector('.confirm [data-action="confirmYes"]', { tagName: 'BUTTON', dataset: { action: 'confirmYes' }, presentIf: /data-action="confirmYes"/ });
  const no = f.element({ tagName: 'BUTTON', dataset: { action: 'cancelConfirm' } });
  const back = f.withId('page-back', { tagName: 'A', presentIf: /id="page-back"/ });
  const store = boot(f.win);
  try {
    cancel.focus();
    f.click(cancel);
    assert.equal(f.doc.activeElement, yes, 'the confirm takes focus');
    f.click(no);
    assert.equal(store.get().confirm, null);
    assert.equal(f.doc.activeElement, cancel, 'No: back on the key that asked');
    f.click(cancel);
    f.click(yes);
    assert.equal(store.get().account.orders.find(o => o.id === 'ord-0008').status, 'canceled');
    assert.equal(f.doc.activeElement, back, 'Yes: the key is gone, focus sits on the way back');
  } finally {
    store.timers.clear();
  }
});

test('a public upload passing review while you are on its page says so there', async () => {
  const { nextUpload } = await import('../js/driver.js');
  let s = R.openCreate(R.nav(seed(NOW), { screen: 'discover', id: null }));
  const run = s.discover.create.run;
  s = R.clientPublishes(R.clientConnected(R.startClient(s, { run }), { run }), { run, manifest: nextUpload([{ id: 'moat' }]) });
  s = R.publishUpload(R.setUploadVisibility(s, 'public'), { now: NOW });
  s = R.nav(s, { screen: 'plugin', id: 'cpi' });
  const passed = R.reviewPassed(s, { id: 'cpi', now: NOW });
  assert.equal(passed.discover.toast?.text, 'CPI quick read passed review · Public');
  assert.equal(passed.discover.toast.action, null, 'on its own page an Open would lead nowhere');
  assert.deepEqual(R.reviewPassed(R.nav(s, { screen: 'discover', id: null }), { id: 'cpi', now: NOW }).discover.toast.action, { label: 'Open', plugin: 'cpi' });
});

test('a plugin you made says Never the way the catalogue does', async () => {
  const { fromManifest } = await import('../js/data/plugins.js');
  const { nextUpload } = await import('../js/driver.js');
  assert.deepEqual(fromManifest(nextUpload([]), 'private', NOW).never, ['moves money', 'pays anyone', 'changes a limit']);
});
