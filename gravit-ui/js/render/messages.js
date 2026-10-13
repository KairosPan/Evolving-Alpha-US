// gravit-ui/js/render/messages.js — the Messages screen in its states: a conversation (F1/F14), new (F7), empty (F6), Details (F8); the banner and the call
import { esc, attrs, cls, money } from '../html.js';
import { icon } from '../icons.js';
import { fmtDate, fmtClock } from '../time.js';
import { byId } from '../data/plugins.js';
import { isClosed } from '../messages.js';
import { avatar, cluster } from './avatars.js';
import { renderThread, chip, withTickers } from './thread.js';
import { senderName } from './rail.js';
import { seg, kv, inlineEdit, confirmPair } from './controls.js';
import { VENUES } from '../data/seed.js';
import { DAY, fmtDuration, rowTime } from '../time.js';

export function currentConversation(state) {
  const id = state.route.screen === 'messages' ? state.route.id : null;
  return state.conversations.find(c => c.id === id) ?? state.conversations[0] ?? null;
}

export function renderComposer({ placeholder = 'Tell Gravit…', above = '', compose = null } = {}) {
  const files = compose?.files ?? [];
  const listening = !!compose?.listening;
  // the picked files sit inside the box above the words; the + opens the hidden file input (app.js: pickFile)
  const tray = files.length ? `<div class="files">${files.map((f, i) => `<span class="file-chip">${esc(f.name)}<button type="button" class="file-x" data-action="removeFile" data-id="${i}" aria-label="Remove ${esc(f.name)}">×</button></span>`).join('')}</div>` : '';
  return `<form class="composer" data-action="send">${above}<div class="${cls('composer-pill', files.length && 'with-files')}">${tray}` +
    `<input id="attach-input" class="sr-only" type="file" multiple data-action="attachFiles" tabindex="-1">` +
    `<button type="button" class="round-key" data-action="pickFile" aria-label="Add a file">${icon('plus', 14, 2.4)}</button>` +
    `<label for="say" class="sr-only">Tell Gravit</label><input id="say" class="composer-input" type="text" autocomplete="off"${attrs({ placeholder: listening ? 'Listening…' : placeholder })}>` +
    `<button type="button" class="${cls('round-key', 'mic', listening && 'on')}" data-action="toggleMic" aria-pressed="${listening ? 'true' : 'false'}" aria-label="${listening ? 'Stop listening' : 'Voice input'}">${icon('mic', 14, 2.2)}</button>` +
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
    `<div class="head-task">${esc(conv.title)}</div><div class="dim members">${esc(names)} · ${conv.members.length} members</div></header>`;
}

function draftHead(state) {
  const d = state.draft;
  // the bots picked for this conversation; an older draft that only had group: true takes every installed bot
  const installedBots = state.plugins.installed.filter(id => byId(id, state.plugins.uploaded)?.kind === 'Bots');
  const bots = d.bots ?? (d.group ? installedBots : []);
  const who = bots.length ? cluster(['gravit', ...bots], 44, state) : avatar('gravit', 44);
  const toChips = ['gravit', ...bots].map(m => `<span class="to-chip">${avatar(m, 20, state)}${esc(senderName(m, state))}</span>`).join('');
  // "+ Add a bot" opens the picker: each installed bot is a chip that joins or leaves the conversation (spec §5.5)
  const picker = d.picking ? `<div class="to-picker">${installedBots.map(id => `<button type="button"${attrs({ class: cls('to-pick', bots.includes(id) && 'on'), 'data-action': 'toggleDraftBot', 'data-id': id, 'aria-pressed': bots.includes(id) ? 'true' : 'false' })}>${avatar(id, 20, state)}${esc(senderName(id, state))}</button>`).join('')}</div>` : '';
  return `<header class="head centered draft"><button type="button" class="btn-sm head-cancel" data-action="cancelDraft">Cancel</button>${who}` +
    `<label for="nm-title" class="sr-only">Name this</label><input id="nm-title" class="title-input" type="text" autocomplete="off" placeholder="Name this (or your first line is the name)" data-action="draftTitle"${attrs({ value: d.title })}>` +
    `<div class="to-line"><span class="to-label">To:</span>${toChips}<button type="button" class="to-add" data-action="toggleDraftPicker" aria-expanded="${d.picking ? 'true' : 'false'}">${icon('plus', 11, 2.4)}Add a bot for a group</button></div>${picker}</header>`;
}

// the limit chips over the new-message composer; the chip being edited turns into its editor
function limitRow(d, state, now) {
  const e = state.edit?.kind === 'draftLimit' ? state.edit : null;
  const days = Math.max(1, Math.round((d.limit.until - now) / DAY));
  const chips = [['perOrder', `$${d.limit.perOrder} an order`], ['total', `$${d.limit.total} in all`], ['until', `until ${fmtDate(d.limit.until)}`], ['venue', `on ${d.limit.venue}`]];
  const editor = k => inlineEdit([{
    perOrder: { name: 'value', value: d.limit.perOrder, type: 'number', word: 'an order' },
    total: { name: 'value', value: d.limit.total, type: 'number', word: 'in all' },
    until: { name: 'value', value: days, type: 'number', word: 'days' },
    venue: { name: 'value', value: d.limit.venue, word: 'on', options: VENUES },
  }[k]], e.error);
  return `<div class="limit-row"><span class="limit-label">Attach a limit</span>` +
    (d.attach ? chips.map(([k, t]) => (e?.key === k ? editor(k) : `<button type="button" class="chip white" data-action="draftLimit" data-key="${k}">${esc(t)} ▾</button>`)).join('') : '') +
    `<button type="button" class="limit-off" data-action="toggleDraftAttach">${d.attach ? 'None' : 'Attach'}</button></div>`;
}

function draftScreen(state, now) {
  const d = state.draft;
  const group = (d.bots ?? []).length > 0 || (!d.bots && d.group);
  return `<main class="main">${draftHead(state)}<div class="thread" id="thread"></div>${renderComposer({ above: limitRow(d, state, now), placeholder: group ? 'Tell Gravit… @ a bot by name' : 'Tell Gravit…', compose: state.compose })}</main>`;
}

function emptyScreen(state) {
  const chips = ['Buy a little BTC', 'Follow Pelosi', 'Check an address'].map(t => `<button type="button" class="btn-sm" data-action="suggest"${attrs({ 'data-text': t })}>${esc(t)}</button>`).join('');
  return `<main class="main"><header class="head"><h1 class="head-title">Gravit</h1></header><div class="empty">${avatar('gravit', 56)}` +
    `<div class="empty-title">Nothing handed to Gravit yet</div><div class="suggest">${chips}</div></div>${renderComposer({ compose: state.compose })}</main>`;
}

export function renderDetails(conv, state) {
  const L = conv.intent.limit;
  const e = state.edit;
  const editing = (kind, match = {}) => !!e && e.kind === kind && Object.entries(match).every(([k, v]) => e[k] === v);
  const asking = action => state.confirm?.action === action && state.confirm?.id === conv.id;
  const btn = (action, label) => `<button type="button" class="btn-sm" data-action="${action}" data-conv="${conv.id}">${label}</button>`;
  const plugs = conv.plugins.map(id => byId(id, state.plugins.uploaded) ?? { name: id, kind: '' });
  const w = state.account.wallet;
  const renaming = editing('rename', { convId: conv.id });
  const limiting = editing('limit', { convId: conv.id });
  const moving = editing('wallet');
  const title = renaming ? inlineEdit([{ name: 'title', value: conv.title, label: 'Name this' }], e.error) : `<div class="dsec-title">${esc(conv.title)}</div>`;
  const limit = limiting
    ? inlineEdit([{ name: 'perOrder', value: L?.perOrder ?? 25, type: 'number', word: 'an order' }, { name: 'total', value: L?.total ?? 100, type: 'number', word: 'in all' }], e.error)
    : L ? kv([['Per order', money(L.perOrder)], ['Total', money(L.total)], ['Left', money(L.total - L.spent)], ['On', esc(L.venue)]]) : '<div class="dim">No limit attached</div>';
  const wallet = moving ? inlineEdit([{ name: 'amount', value: '', type: 'number', word: e.dir === 'in' ? 'Top up' : 'Take back' }], e.error) : '';
  return `<aside class="drawer details" aria-label="Details">
  <div class="drawer-head"><h2>Details</h2><button type="button" class="close-key" data-action="toggleDetails" aria-label="Close">×</button></div>
  <div class="drawer-body">
    <section class="dsec"><div class="dsec-label">This task</div>${title}<div class="dim">Delegated ${fmtDate(conv.intent.created)} · until ${fmtDate(conv.intent.until)} · ${esc(conv.intent.id)}</div>
      ${renaming ? '' : `<div class="btn-row">${asking('withdraw') ? confirmPair('Yes, withdraw') : btn('changeWords', 'Change words') + (isClosed(conv) ? '' : btn('withdraw', 'Withdraw'))}</div>`}</section>
    <section class="dsec"><div class="dsec-label">Limit</div>${limit}
      ${limiting ? '' : `<div class="btn-row">${asking('endLimit') ? confirmPair('Yes, end the limit') : btn('changeLimit', 'Change limit') + (L ? btn('endLimit', 'End limit') : '')}</div>`}</section>
    <section class="dsec"><div class="dsec-label">Plugins</div>${plugs.length ? plugs.map(p => `<div class="dsec-line plug-row"><span>${esc(p.name)}</span><span class="dim">${esc(p.kind)}</span></div>`).join('') : '<div class="dim">None</div>'}<a class="link" href="#/discover">Find more in Discover ›</a></section>
    <section class="dsec"><div class="dsec-label">Gravit’s wallet</div>${kv([['USDC', money(w.usdc)], ['Chain', esc(w.chain)], ['Address', `<span class="mono">${esc(w.address)}</span>`]])}${wallet}
      ${moving ? '' : `<div class="btn-row">${btn('topUp', 'Top up…')}${btn('takeBack', 'Take back…')}</div>`}</section>
    <section class="dsec"><div class="dsec-label">Mode</div>${seg(['Guard', 'Beast'], state.account.mode === 'beast' ? 'Beast' : 'Guard', 'setMode')}</section>
    ${isClosed(conv) ? '' : `<section class="dsec">${asking('stopGravit') ? confirmPair('Yes, stop Gravit') : `<button type="button" class="btn-danger" data-action="stopGravit" data-conv="${conv.id}">Stop Gravit</button>`}</section>`}
  </div>
</aside>`;
}

export function renderMessagesScreen(state, now) {
  if (state.draft) return draftScreen(state, now);
  const conv = currentConversation(state);
  if (!conv) return emptyScreen(state);
  const placeholder = conv.kind === 'group' ? 'Tell Gravit… @ a bot by name' : 'Tell Gravit…';
  return `<main class="${cls('main', state.detailsOpen && 'with-drawer')}">${renderHead(conv, state)}<div class="thread" id="thread">${renderThread(conv, state, now)}</div>${renderComposer({ placeholder, compose: state.compose })}${state.detailsOpen ? renderDetails(conv, state) : ''}</main>`;
}

export function renderBanner(b, state, { enter = false } = {}) {
  // the thread the banner covers, where its message will land (reducers/messages.js dismissBanner)
  const conv = currentConversation(state);
  const when = [fmtClock(b.at), conv?.title].filter(Boolean).join(' · ');
  return `<div class="banner-zone"><div class="${cls('banner', enter && 'drop')}" role="status"><div class="banner-head">${chip('Breaking', 'down')}<span class="dim">${esc(when)}</span><span class="spacer"></span><button type="button" class="close-key small" data-action="dismissBanner" aria-label="Dismiss">×</button></div>` +
    `<div class="card-title">${esc(b.headline)}</div><div class="dim">${withTickers(b.body)}</div><a class="link" href="#/messages/${esc(conv?.id ?? '')}" data-action="dismissBanner">Open the conversation ›</a></div></div>`;
}

// the call over the page: ringing in (decline, accept), ringing out (hang up), live (a timer, mute, hang up)
export function renderCall(c, now = Date.now()) {
  const hang = `<button type="button" class="key no big" data-action="hangUp" aria-label="Hang up">${icon('phoneOff', 18, 2.1)}</button>`;
  let label;
  let inner;
  if (c.status === 'live') {
    label = 'Call';
    inner = `${avatar('gravit', 44)}<div class="card-title">Gravit</div><div class="call-timer">${fmtDuration(now - c.since)}</div>` +
      `<div class="call-keys"><button type="button" class="${cls('key', 'big', 'mute', c.muted && 'on')}" data-action="toggleMute" aria-pressed="${c.muted ? 'true' : 'false'}" aria-label="Mute">${icon('mic', 18, 2.1)}</button>${hang}</div>`;
  } else if (c.dir === 'out') {
    label = 'Calling Gravit';
    inner = `${avatar('gravit', 44)}<div class="card-title">Calling Gravit…</div><div class="dim">Ringing</div><div class="call-keys">${hang}</div>`;
  } else {
    label = 'Gravit is calling';
    inner = `${avatar('gravit', 44)}<div class="card-title">Gravit is calling</div><div class="dim">${esc([c.about, c.length].filter(Boolean).join(', '))}</div>` +
      `<div class="call-keys"><button type="button" class="key no big" data-action="answerCall" data-accept="0" aria-label="Decline">${icon('phoneOff', 18, 2.1)}</button>` +
      `<button type="button" class="key yes big" data-action="answerCall" data-accept="1" aria-label="Accept">${icon('phone', 18, 2.1)}</button></div>`;
  }
  const ringing = c.status !== 'live' && c.dir !== 'out';
  return `<div class="call-scrim"><div class="${cls('call', ringing && 'in')}" role="dialog" aria-label="${label}">${inner}</div></div>`;
}
