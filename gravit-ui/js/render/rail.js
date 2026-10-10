// gravit-ui/js/render/rail.js — Linqi's 248 px rail with the iMessage conversation rows (spec §4)
import { esc, attrs, cls } from '../html.js';
import { icon } from '../icons.js';
import { byId } from '../data/plugins.js';
import { rowTime } from '../time.js';
import { avatar, groupMark } from './avatars.js';

const NAME = { you: '你', gravit: 'Gravit', system: '' };
export function senderName(from, state) {
  return NAME[from] ?? byId(from, state?.plugins?.uploaded ?? [])?.name ?? from;
}

export function previewOf(conv, state = null) {
  const m = conv.messages.at(-1);
  if (!m) return '';
  const body = {
    receipt: `${m.data.status} · ${m.text}`, brief: `早报 · ${m.data.date}`, ta: `${m.data.ticker} 技术面`, breaking: m.data.headline ?? m.text, call: 'Gravit 来电',
  }[m.kind] ?? m.text;
  const who = m.from === 'you' ? '' : senderName(m.from, state);
  return conv.kind === 'group' && who ? `${who}：${body}` : body;
}

function rowMark(conv, state) {
  if (conv.kind === 'group') return groupMark(conv.members, 36, state);
  const who = conv.kind === 'bot' ? conv.members.find(x => x !== 'gravit') ?? 'gravit' : 'gravit';
  return avatar(who, 36, state);
}

function row(conv, state, now) {
  const current = state.route.screen === 'messages' && state.route.id === conv.id;
  const last = conv.messages.at(-1);
  return `<a${attrs({ class: cls('row', current && 'current'), 'aria-current': current ? 'page' : null, href: `#/messages/${conv.id}`, 'data-action': 'open', 'data-id': conv.id })}>` +
    `<span class="${cls('dot', conv.unread && 'on')}"></span>${rowMark(conv, state)}` +
    `<span class="row-body"><span class="row-top"><span class="row-title">${esc(conv.title)}</span><span class="row-time">${last ? rowTime(last.at, now) : ''}</span></span>` +
    `<span class="row-preview">${esc(previewOf(conv, state))}</span></span></a>`;
}

function draftRow() {
  return `<a class="row current draft" aria-current="page" href="#/messages/new" data-action="open" data-id="new"><span class="dot"></span><span class="av av-draft">+</span>` +
    `<span class="row-body"><span class="row-top"><span class="row-title">New message</span><span class="row-time">now</span></span><span class="row-preview">还没发出去</span></span></a>`;
}

function navItem(href, name, label, current) {
  return `<a${attrs({ class: cls('nav-item', current && 'current'), 'aria-current': current ? 'page' : null, href })}>${icon(name, 22, current ? 2.1 : 2)}${label}</a>`;
}

export function renderRail(state, now) {
  const { screen } = state.route;
  const rows = state.railCollapsed ? '' : (state.draft ? draftRow() : '') + state.conversations.map(c => row(c, state, now)).join('');
  const accountCurrent = screen === 'account';
  return `<nav class="rail" aria-label="Gravit">
  <div class="brand">${avatar('gravit', 28)}<span class="brand-name">Gravit</span></div>
  <div class="rail-group rail-messages">
    <div class="rail-head">${icon('chat', 22, 2)}<span class="rail-head-label">Messages</span><span class="rail-head-keys">` +
      `<button type="button" class="icon-key" data-action="startDraft" aria-label="New message">${icon('plus', 16, 2.2)}</button>` +
      `<button type="button" class="icon-key" data-action="toggleRail" aria-expanded="${state.railCollapsed ? 'false' : 'true'}" aria-label="Collapse messages">${icon(state.railCollapsed ? 'chevRight' : 'chevDown', 14, 2.2)}</button></span></div>
    ${rows ? `<div class="rail-rows">${rows}</div>` : ''}
  </div>
  <div class="rail-group">
    ${navItem('#/discover', 'compass', 'Discover', screen === 'discover')}
    ${navItem('#/markets', 'markets', 'Markets', screen === 'markets')}
    ${navItem('#/trade', 'trade', 'Trade', screen === 'trade')}
  </div>
  <div class="rail-foot">
    <div class="rail-lines"><button type="button" class="line-key" aria-label="Phone">${icon('phone', 20, 2)}</button><button type="button" class="line-key" aria-label="Email">${icon('mail', 20, 2)}</button></div>
    <a${attrs({ href: '#/account/portfolio', class: cls('account', accountCurrent && 'current'), 'aria-current': accountCurrent ? 'page' : null })}>${icon('wallet', 22, accountCurrent ? 2.1 : 2)}<span class="account-body"><span class="account-title">Account</span><span class="account-line">$${state.account.netWorth.toLocaleString('en-US')} · ${state.account.mode === 'beast' ? 'Beast' : 'Guard'}</span></span></a>
  </div>
</nav>`;
}
