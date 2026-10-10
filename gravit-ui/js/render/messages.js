// gravit-ui/js/render/messages.js — the Messages screen in its states: a conversation (F1/F14), new (F7), empty (F6), Details (F8); the banner and the call
import { esc, attrs, cls, money } from '../html.js';
import { icon } from '../icons.js';
import { fmtDate, fmtClock } from '../time.js';
import { byId } from '../data/plugins.js';
import { avatar, cluster } from './avatars.js';
import { renderThread, chip } from './thread.js';
import { senderName } from './rail.js';
import { seg, kv, inlineEdit, confirmPair } from './controls.js';
import { VENUES } from '../data/seed.js';
import { DAY } from '../time.js';

export function currentConversation(state) {
  const id = state.route.screen === 'messages' ? state.route.id : null;
  return state.conversations.find(c => c.id === id) ?? state.conversations[0] ?? null;
}

export function renderComposer({ placeholder = 'Tell Gravit…', above = '' } = {}) {
  return `<form class="composer" data-action="send">${above}<div class="composer-pill">` +
    `<button type="button" class="round-key" aria-label="Add a file">${icon('plus', 14, 2.4)}</button>` +
    `<label for="say" class="sr-only">Tell Gravit</label><input id="say" class="composer-input" type="text" autocomplete="off"${attrs({ placeholder })}>` +
    `<button type="button" class="round-key" aria-label="Voice input">${icon('mic', 14, 2.2)}</button>` +
    `<button type="submit" class="send-key" aria-label="Sign and send">${icon('send', 18, 2.4)}</button></div></form>`;
}

const STATUS = { working: ['Working', 'up'], done: ['Done', 'grey'], stopped: ['Stopped', 'down'], withdrawn: ['Withdrawn', 'grey'] };

function headRight(conv, state) {
  const [label, tone] = STATUS[conv.status] ?? STATUS.working;
  return `<span class="status ${tone}"><span class="status-dot"></span>${label}</span>` +
    `<button type="button"${attrs({ class: cls('btn-sm', state.detailsOpen && 'pressed'), 'data-action': 'toggleDetails', 'aria-expanded': state.detailsOpen ? 'true' : 'false' })}>Details${icon('chevRight', 14, 2.2)}</button>`;
}

export function renderHead(conv, state) {
  if (conv.kind !== 'group') return `<header class="head"><h1 class="head-title">${esc(conv.title)}</h1>${headRight(conv, state)}</header>`;
  const names = conv.members.map(m => senderName(m, state)).join(' · ');
  return `<header class="head centered"><div class="head-right">${headRight(conv, state)}</div>${cluster(conv.members, 44, state)}` +
    `<div class="head-task">${esc(conv.title)}</div><div class="dim">${esc(names)} · ${conv.members.length} 位</div></header>`;
}

function draftHead(state) {
  const d = state.draft;
  // the bots picked for this conversation; an older draft that only had group: true takes every installed bot
  const installedBots = state.plugins.installed.filter(id => byId(id, state.plugins.uploaded)?.kind === 'Bots');
  const bots = d.bots ?? (d.group ? installedBots : []);
  const who = bots.length ? cluster(['gravit', ...bots], 44, state) : avatar('gravit', 44);
  const toChips = ['gravit', ...bots].map(m => `<span class="to-chip">${avatar(m, 20, state)}${esc(senderName(m, state))}</span>`).join('');
  // "+ 加个 bot" opens the picker: each installed bot is a chip that joins or leaves the conversation (spec §5.5)
  const picker = d.picking ? `<div class="to-picker">${installedBots.map(id => `<button type="button"${attrs({ class: cls('to-pick', bots.includes(id) && 'on'), 'data-action': 'toggleDraftBot', 'data-id': id, 'aria-pressed': bots.includes(id) ? 'true' : 'false' })}>${avatar(id, 20, state)}${esc(senderName(id, state))}</button>`).join('')}</div>` : '';
  return `<header class="head centered draft"><button type="button" class="btn-sm head-cancel" data-action="cancelDraft">Cancel</button>${who}` +
    `<label for="nm-title" class="sr-only">这件事叫什么</label><input id="nm-title" class="title-input" type="text" autocomplete="off" placeholder="这件事叫什么（不填就用你第一句话）" data-action="draftTitle"${attrs({ value: d.title })}>` +
    `<div class="to-line"><span class="to-label">To:</span>${toChips}<button type="button" class="to-add" data-action="toggleDraftPicker" aria-expanded="${d.picking ? 'true' : 'false'}">${icon('plus', 11, 2.4)}加个 bot，就成群聊</button></div>${picker}</header>`;
}

// the limit chips over the new-message composer; the chip being edited turns into its editor
function limitRow(d, state, now) {
  const e = state.edit?.kind === 'draftLimit' ? state.edit : null;
  const days = Math.max(1, Math.round((d.limit.until - now) / DAY));
  const chips = [['perOrder', `每单 $${d.limit.perOrder}`], ['total', `总 $${d.limit.total}`], ['until', `到 ${fmtDate(d.limit.until)}`], ['venue', `在 ${d.limit.venue}`]];
  const editor = k => inlineEdit([{
    perOrder: { name: 'value', value: d.limit.perOrder, type: 'number', label: '每单上限' },
    total: { name: 'value', value: d.limit.total, type: 'number', label: '总额' },
    until: { name: 'value', value: days, type: 'number', label: '几天后到期' },
    venue: { name: 'value', value: d.limit.venue, label: '场所', options: VENUES },
  }[k]], e.error);
  return `<div class="limit-row"><span class="limit-label">附一份额度</span>` +
    (d.attach ? chips.map(([k, t]) => (e?.key === k ? editor(k) : `<button type="button" class="chip white" data-action="draftLimit" data-key="${k}">${esc(t)} ▾</button>`)).join('') : '') +
    `<button type="button" class="limit-off" data-action="toggleDraftAttach">${d.attach ? '不附' : '附上'}</button></div>`;
}

function draftScreen(state, now) {
  const d = state.draft;
  const group = (d.bots ?? []).length > 0 || (!d.bots && d.group);
  return `<main class="main">${draftHead(state)}<div class="thread" id="thread"></div>${renderComposer({ above: limitRow(d, state, now), placeholder: group ? 'Tell Gravit… 打 @ 点名一个 bot' : 'Tell Gravit…' })}</main>`;
}

function emptyScreen() {
  const chips = ['小仓位买 BTC', '跟单 Pelosi', '查一个地址'].map(t => `<button type="button" class="btn-sm" data-action="suggest"${attrs({ 'data-text': t })}>${esc(t)}</button>`).join('');
  return `<main class="main"><header class="head"><h1 class="head-title">Gravit</h1></header><div class="empty">${avatar('gravit', 56)}` +
    `<div class="empty-title">还没有交给 Gravit 的事</div><div class="empty-line">在下面说一句你想让它做的事，或者点左上角的 + 先起个名。</div><div class="suggest">${chips}</div></div>${renderComposer()}</main>`;
}

export function renderDetails(conv, state) {
  const L = conv.intent.limit;
  const e = state.edit;
  const editing = (kind, match = {}) => !!e && e.kind === kind && Object.entries(match).every(([k, v]) => e[k] === v);
  const asking = action => state.confirm?.action === action && state.confirm?.id === conv.id;
  const btn = (action, label) => `<button type="button" class="btn-sm" data-action="${action}" data-conv="${conv.id}">${label}</button>`;
  const plugs = conv.plugins.map(id => byId(id, state.plugins.uploaded)?.name ?? id);
  const w = state.account.wallet;
  const title = editing('rename', { convId: conv.id }) ? inlineEdit([{ name: 'title', value: conv.title, label: '这件事叫什么' }], e.error) : `<div class="dsec-title">${esc(conv.title)}</div>`;
  const limit = editing('limit', { convId: conv.id })
    ? inlineEdit([{ name: 'perOrder', value: L?.perOrder ?? 25, type: 'number', label: '每单上限' }, { name: 'total', value: L?.total ?? 100, type: 'number', label: '总额' }], e.error)
    : L ? kv([['每单', money(L.perOrder)], ['总额', money(L.total)], ['剩余', money(L.total - L.spent)], ['在', esc(L.venue)]]) : '<div class="dim">没附额度</div>';
  const wallet = editing('wallet') ? inlineEdit([{ name: 'amount', value: '', type: 'number', label: e.dir === 'in' ? 'Top up 多少' : 'Take back 多少' }], e.error) : '';
  return `<aside class="drawer details" aria-label="Details">
  <div class="drawer-head"><h2>Details</h2><button type="button" class="close-key" data-action="toggleDetails" aria-label="Close">×</button></div>
  <div class="drawer-body">
    <section class="dsec"><div class="dsec-label">这件事</div>${title}<div class="dim">你委托于 ${fmtDate(conv.intent.created)} · 到 ${fmtDate(conv.intent.until)} · ${esc(conv.intent.id)}</div>
      <div class="btn-row">${asking('withdraw') ? confirmPair('确认撤回') : btn('changeWords', 'Change words') + btn('withdraw', 'Withdraw')}</div></section>
    <section class="dsec"><div class="dsec-label">额度</div>${limit}
      <div class="btn-row">${asking('endLimit') ? confirmPair('确认结束额度') : btn('changeLimit', 'Change limit') + btn('endLimit', 'End limit')}</div></section>
    <section class="dsec"><div class="dsec-label">插件</div>${plugs.length ? plugs.map(n => `<div class="dsec-line">${esc(n)}</div>`).join('') : '<div class="dim">没有</div>'}<a class="link" href="#/discover">Find more in Discover ›</a></section>
    <section class="dsec"><div class="dsec-label">Gravit 的钱包</div>${kv([['USDC', money(w.usdc)], ['链', esc(w.chain)], ['地址', `<span class="mono">${esc(w.address)}</span>`]])}${wallet}
      <div class="btn-row">${btn('topUp', 'Top up…')}${btn('takeBack', 'Take back…')}</div></section>
    <section class="dsec"><div class="dsec-label">模式</div>${seg(['Guard', 'Beast'], state.account.mode === 'beast' ? 'Beast' : 'Guard', 'setMode')}</section>
    <section class="dsec">${asking('stopGravit') ? confirmPair('确认停掉') : `<button type="button" class="btn-danger" data-action="stopGravit" data-conv="${conv.id}">Stop Gravit</button>`}</section>
  </div>
</aside>`;
}

export function renderMessagesScreen(state, now) {
  if (state.draft) return draftScreen(state, now);
  const conv = currentConversation(state);
  if (!conv) return emptyScreen();
  const placeholder = conv.kind === 'group' ? 'Tell Gravit… 打 @ 点名一个 bot' : 'Tell Gravit…';
  return `<main class="${cls('main', state.detailsOpen && 'with-drawer')}">${renderHead(conv, state)}<div class="thread" id="thread">${renderThread(conv, state, now)}</div>${renderComposer({ placeholder })}${state.detailsOpen ? renderDetails(conv, state) : ''}</main>`;
}

export function renderBanner(b, state) {
  // the thread the banner covers, where its message will land (reducers/messages.js dismissBanner)
  const first = currentConversation(state)?.id ?? '';
  return `<div class="banner" role="status"><div class="banner-head">${chip('突发', 'down')}<span class="dim">${fmtClock(b.at)}</span><span class="spacer"></span><button type="button" class="close-key small" data-action="dismissBanner" aria-label="Dismiss">×</button></div>` +
    `<div class="card-title">${esc(b.headline)}</div><div class="dim">${esc(b.body)}</div><a class="link" href="#/messages/${esc(first)}" data-action="dismissBanner">去会话 ›</a></div>`;
}

export function renderCall(c) {
  return `<div class="call-scrim"><div class="call" role="dialog" aria-label="Gravit 来电">${avatar('gravit', 44)}<div class="card-title">Gravit 来电</div><div class="dim">${esc(c.about)}</div>` +
    `<div class="call-keys"><button type="button" class="key no big" data-action="answerCall" data-accept="0" aria-label="Decline">${icon('phoneOff', 18, 2.1)}</button>` +
    `<button type="button" class="key yes big" data-action="answerCall" data-accept="1" aria-label="Accept">${icon('phone', 18, 2.1)}</button></div></div></div>`;
}

// Markets and Trade are Linqi's pages; this pure front end only shows where a ticker would land
export function renderStub(route) {
  const title = route.screen === 'markets' ? 'Markets' : 'Trade';
  const sub = route.screen === 'markets' && route.id ? `Markets › ${esc(route.id)}` : '';
  return `<main class="main"><header class="head"><h1 class="head-title">${title}</h1></header><div class="stub">${sub ? `<div class="head-task">${sub}</div>` : ''}</div></main>`;
}
