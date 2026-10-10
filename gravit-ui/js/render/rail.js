// gravit-ui/js/render/rail.js — the two-level navigation: a first level that collapses to icons, and the conversation list as the second level on Messages
import { esc, attrs, cls } from '../html.js';
import { icon } from '../icons.js';
import { byId } from '../data/plugins.js';
import { rowTime } from '../time.js';
import { avatar, groupMark } from './avatars.js';
import { renderMailList } from './mail.js';

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

// a first-level key: an icon and its name; collapsed, the name stays as the title and for screen readers
function navItem(href, name, label, current, mini, badge = 0) {
  return `<a${attrs({ class: cls('nav-item', current && 'current'), 'aria-current': current ? 'page' : null, href, title: mini ? label : null })}>${icon(name, 22, current ? 2.1 : 2)}` +
    `<span class="nav-label">${esc(label)}</span>${badge ? `<span class="nav-badge">${badge}</span>` : ''}</a>`;
}

// the first level: Messages · Discover · Markets · Trade, the phone key and the mail key, Account; it collapses to a strip of icons
export function renderNav(state) {
  const { screen } = state.route;
  const mini = !!state.railCollapsed;
  const unread = state.conversations.filter(c => c.unread).length;
  const messagesHref = `#/messages/${screen === 'messages' && state.route.id && state.route.id !== 'new' ? state.route.id : state.lastConv ?? state.conversations[0]?.id ?? ''}`;
  const mailUnread = (state.mail?.items ?? []).filter(m => !m.read).length;
  const accountCurrent = screen === 'account';
  const mailCurrent = screen === 'mail';
  return `<nav class="${cls('rail', mini && 'mini')}" aria-label="Gravit">
  <div class="brand">${avatar('gravit', 28)}<span class="brand-name">Gravit</span>` +
    `<button type="button" class="icon-key rail-toggle" data-action="toggleRail" aria-expanded="${mini ? 'false' : 'true'}" aria-label="${mini ? '展开导航' : '收起导航'}">${icon(mini ? 'chevRight' : 'chevLeft', 14, 2.2)}</button></div>
  <div class="rail-group">
    ${navItem(messagesHref, 'chat', 'Messages', screen === 'messages', mini, unread)}
    ${navItem('#/discover', 'compass', 'Discover', screen === 'discover', mini)}
    ${navItem('#/markets', 'markets', 'Markets', screen === 'markets', mini)}
    ${navItem('#/trade', 'trade', 'Trade', screen === 'trade', mini)}
  </div>
  <div class="rail-foot">
    <div class="rail-lines"><button type="button" class="${cls('line-key', state.call && 'on')}" data-action="phoneCall" aria-label="Phone">${icon('phone', 20, 2)}</button>` +
      `<a${attrs({ id: 'mail-key', class: cls('line-key', mailCurrent && 'current'), href: '#/mail', 'aria-label': 'Mail', 'aria-current': mailCurrent ? 'page' : null, title: mini ? 'Mail' : null })}>${icon('mail', 20, mailCurrent ? 2.1 : 2)}${mailUnread ? `<span class="nav-badge">${mailUnread}</span>` : ''}</a></div>
    <a${attrs({ href: '#/account/portfolio', class: cls('account', accountCurrent && 'current'), 'aria-current': accountCurrent ? 'page' : null, title: mini ? 'Account' : null })}>${icon('wallet', 22, accountCurrent ? 2.1 : 2)}<span class="account-body"><span class="account-title">Account</span><span class="account-line">$${state.account.netWorth.toLocaleString('en-US')} · ${state.account.mode === 'beast' ? 'Beast' : 'Guard'}</span></span></a>
  </div>
</nav>`;
}

// the second level, open on Messages (the conversations, the new-message key on top) and on Mail (the letters)
export function renderList(state, now) {
  if (state.route.screen === 'mail') return renderMailList(state, now);
  if (state.route.screen !== 'messages') return '';
  const rows = (state.draft ? draftRow() : '') + state.conversations.map(c => row(c, state, now)).join('');
  return `<aside class="list" aria-label="Messages"><div class="list-head"><h2 class="list-title">Messages</h2>` +
    `<button type="button" class="icon-key" data-action="startDraft" aria-label="New message">${icon('plus', 16, 2.2)}</button></div>` +
    `${rows ? `<div class="rail-rows">${rows}</div>` : ''}</aside>`;
}

export function renderRail(state, now) {
  return renderNav(state) + renderList(state, now);
}
