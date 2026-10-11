// gravit-ui/js/render/mail.js — Gravit's own mailbox as a screen: the letters in the second level, the open letter in the main column
import { esc, attrs, cls } from '../html.js';
import { icon } from '../icons.js';
import { rowTime, dayLabel, fmtClock } from '../time.js';
import { avatar, mark } from './avatars.js';

const openLetter = state => (state.route.screen === 'mail' ? state.mail.items.find(m => m.id === state.route.id) ?? null : null);

// a sender's round mark: Gravit's own G, Discover's compass, anyone else their initial
function senderMark(from) {
  if (from === 'Gravit') return avatar('gravit', 36);
  if (from === 'Discover') return mark({ type: 'glyph', icon: 'compass' }, 36, '999px', from);
  return mark({ type: 'letter', text: from.slice(0, 1).toUpperCase(), tone: 'grey' }, 36, '999px', from);
}

function letterRow(m, current, now) {
  return `<a${attrs({ id: `mr-${m.id}`, class: cls('row', current && 'current', !m.read && 'unread'), href: `#/mail/${m.id}`, 'aria-current': current ? 'page' : null })}>` +
    `<span class="${cls('dot', !m.read && 'on')}"></span>${senderMark(m.from)}` +
    `<span class="row-body"><span class="row-top"><span class="row-title">${esc(m.from)}</span><span class="row-time">${rowTime(m.at, now)}</span></span>` +
    `<span class="row-preview">${esc(m.subject)}</span></span></a>`;
}

// the second level on Mail: the title, Gravit's address, the letters newest first
export function renderMailList(state, now) {
  const open = openLetter(state);
  const rows = state.mail.items.map(m => letterRow(m, m === open, now)).join('');
  return `<aside class="list" aria-label="Mail"><div class="list-head"><div><h2 class="list-title">Mail</h2><div class="list-sub mono">${esc(state.mail.address)}</div></div></div>` +
    `${rows ? `<div class="rail-rows">${rows}</div>` : ''}</aside>`;
}

// the main column on Mail: the open letter, or nothing picked yet
export function renderMailScreen(state, now) {
  const m = openLetter(state);
  if (!m) return `<main class="main mail"><div class="mail-none">${icon('mail', 40, 1.8)}<span class="dim">No mail selected</span></div></main>`;
  const files = (m.files ?? []).map(n => `<span class="file-chip">${icon('file', 13, 2)}${esc(n)}</span>`).join('');
  return `<main class="main mail has-letter"><header class="head"><h1 class="head-title">${esc(m.subject)}</h1></header>` +
    `<article class="mail-letter"><div class="mail-meta dim">${esc(m.from)} · ${dayLabel(m.at, now)} ${fmtClock(m.at)}</div>` +
    `${files ? `<div class="files">${files}</div>` : ''}<p class="mail-body">${esc(m.body)}</p></article></main>`;
}
