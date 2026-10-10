// gravit-ui/js/render/thread.js — the conversation body: bubbles, cards by level, icon-only keys, centred dividers (spec §5.2–5.3, §6)
import { esc, attrs, cls } from '../html.js';
import { icon } from '../icons.js';
import { divider, fmtClock, fmtDuration } from '../time.js';
import { levelOf, needsAnswer, isClosed } from '../messages.js';
import { avatar } from './avatars.js';
import { senderName } from './rail.js';

export const chip = (text, tone = 'grey') => `<span class="${cls('chip', tone)}">${esc(text)}</span>`;

export function key(type, label, data = {}) {
  const glyph = { yes: 'check', no: 'x', plus: 'plus' }[type];
  return `<button type="button"${attrs({ class: `key ${type}`, 'aria-label': label, ...data })}>${icon(glyph, 14, 2.4)}</button>`;
}

export const ticker = t => `<a class="ticker" href="#/markets/${esc(t)}">${esc(t)}${icon('chevRight', 12, 2.4)}</a>`;

const withTickers = text => esc(text).replace(/\{\{([A-Z]+)\}\}/g, (_, t) => ticker(t));

export function candles(data) {
  const bars = data.candles.map(([o, c, l, h], i) => {
    const x = 12 + i * 21;
    const tone = c < o ? 'var(--up)' : 'var(--down)';
    return `<line x1="${x}" y1="${h}" x2="${x}" y2="${l}" stroke="${tone}" stroke-width="1.5"></line><rect x="${x - 5}" y="${Math.min(o, c)}" width="10" height="${Math.max(Math.abs(o - c), 2)}" fill="${tone}" rx="1"></rect>`;
  }).join('');
  return `<svg class="kline" viewBox="0 0 300 68" role="img" aria-label="${esc(data.ticker)} ${esc(data.tf)} K 线">` +
    `<line x1="0" y1="12" x2="300" y2="12" class="kline-rule"></line><text x="298" y="9" class="kline-label" text-anchor="end">压力 ${esc(data.resistance)}</text>` +
    `<line x1="0" y1="56" x2="300" y2="56" class="kline-rule"></line><text x="298" y="66" class="kline-label" text-anchor="end">支撑 ${esc(data.support)}</text>${bars}</svg>`;
}

const keysFor = (m, conv) => {
  // a stopped or withdrawn conversation takes no answers, so its cards show no keys
  if (!needsAnswer(m) || isClosed(conv)) return '';
  const convId = conv.id;
  const d = { 'data-action': 'answer', 'data-conv': convId, 'data-msg': m.id };
  if (m.kind === 'card') return `<div class="keys right">${key('no', 'Reject', { ...d, 'data-answer': 'rejected' })}${key('yes', 'Approve', { ...d, 'data-answer': 'approved' })}</div>`;
  if (m.kind === 'limit') return `<div class="keys">${key('yes', 'Grant', { ...d, 'data-answer': 'granted' })}${key('no', 'Decline', { ...d, 'data-answer': 'declined' })}</div>`;
  if (m.kind === 'install') return `<div class="keys">${key('plus', 'Install', { 'data-action': 'installAsk', 'data-conv': convId, 'data-msg': m.id, 'data-plugin': m.data.plugin })}${key('no', 'No', { ...d, 'data-answer': 'no' })}</div>`;
  return '';
};

// a card still waiting carries its deadline (spec §6, warn-fill); once answered it carries the answer instead
const ANSWERED = { approved: ['Approved', 'up'], rejected: ['Rejected', 'grey'] };
function cardChip(m) {
  if (m.answer) { const [label, tone] = ANSWERED[m.answer] ?? [m.answer, 'grey']; return chip(label, tone); }
  return m.data?.by ? chip(`answer by ${fmtClock(m.data.by)}`, 'warn') : '';
}

function body(m, conv) {
  const d = m.data ?? {};
  switch (m.kind) {
    case 'card':
      return `<div class="card orange"><div class="card-head"><div class="card-title">${esc(d.title ?? m.text)}</div>${cardChip(m)}</div>` +
        (d.venue ? `<div class="dim">${esc([d.venue, d.type, d.about, d.cardId].filter(Boolean).join(' · '))}</div>` : '') +
        (d.rows ? `<div class="orders">${d.rows.map(r => `<div class="order-row"><span class="order-t">${esc(r.t)}</span><span class="dim">${esc(r.why)}</span><span class="num">${esc(r.amt)}</span></div>`).join('')}</div>` : '') +
        (d.note ? `<div class="dim">${esc(d.note)}</div>` : '') + keysFor(m, conv) + `</div>`;
    case 'limit':
    case 'install':
      return `<div class="card orange"><div>${esc(m.text)}</div>${keysFor(m, conv)}</div>`;
    case 'signal':
      return `<div class="card white"><div class="dim">${esc(d.source ?? '')}</div><div class="quote">${esc(m.text)}</div></div>`;
    case 'ta':
      return `<div class="card white"><div class="card-head"><span class="ticker-lead">${ticker(d.ticker)}</span><span class="dim">${esc(d.tf)} · 技术面</span></div>${candles(d)}` +
        (d.lines ?? []).map((l, i) => `<div${i ? ' class="dim"' : ''}>${esc(l)}</div>`).join('') + `<a class="link" href="#/markets/${esc(d.ticker)}">在 Markets 里看 ›</a></div>`;
    case 'brief':
      return `<div class="card white"><div class="card-head"><div class="card-title">早报 · ${esc(d.date)}</div><span class="dim">${esc(d.time)} · 每天</span></div>` +
        (d.lines ?? []).map((l, i, a) => `<div${i === a.length - 1 ? ' class="dim"' : ''}>${withTickers(l)}</div>`).join('') + `</div>`;
    case 'refusal':
      return `<div class="card red">${chip(`✗ ${d.code ?? ''}`, 'down')}<div>${esc(m.text)}</div></div>`;
    case 'alert':
      return `<div class="card red">${esc(m.text)}</div>`;
    case 'breaking':
      return `<div class="card red"><div class="card-head">${chip('突发', 'down')}<span class="dim">${fmtClock(m.at)}</span></div><div class="card-title">${esc(d.headline ?? m.text)}</div>${d.body ? `<div class="dim">${withTickers(d.body)}</div>` : ''}</div>`;
    case 'call': {
      // how the call went: connected and for how long, missed, or never got through
      const title = d.dir === 'out' ? '打给 Gravit' : 'Gravit 来电';
      const [label, tone] = { accepted: [`接通 · ${fmtDuration(d.duration ?? 0)}`, 'up'], cancelled: ['没打通', 'grey'] }[m.answer] ?? ['没接', 'down'];
      return `<div class="card red"><div class="card-head"><div class="card-title">${title}</div>${chip(label, tone)}</div>${d.about ? `<div class="dim">${esc(d.about)}</div>` : ''}</div>`;
    }
    case 'receipt':
      return `<div class="bubble green"><div class="line">${chip(d.status ?? 'filled', 'up')}<span>${esc(m.text)}</span></div>${d.more ? `<div>${esc(d.more)}</div>` : ''}</div>`;
    case 'proposal':
      return `<div class="bubble green"><div>${esc(m.text)}</div><div class="line">${chip(d.status ?? 'filled', 'up')}<span class="dim">${esc([d.ord, d.venue].filter(Boolean).join(' · '))}</span></div></div>`;
    case 'done':
      return `<div class="bubble green"><div>${esc(m.text)}</div>${d.foot ? `<div class="foot">${esc(d.foot)}</div>` : ''}</div>`;
    default:
      return `<div class="bubble ${levelOf(m)}">${esc(m.text)}</div>`;
  }
}

export function renderMessage(m, conv, state) {
  if (m.from === 'system') return `<div class="sysline">${esc(m.text)}</div>`;
  if (m.from === 'you') {
    const files = (m.data?.files ?? []).map(n => `<span class="file-chip">${icon('file', 13, 2)}${esc(n)}</span>`).join('');
    return `<div class="msg you"><div class="bubble you">${files}${m.text ? esc(m.text) : ''}</div>${avatar('you', 28)}</div>`;
  }
  const name = conv.kind === 'group' ? `<div class="sender-name">${esc(senderName(m.from, state))}</div>` : '';
  const wide = ['card', 'ta', 'brief', 'breaking', 'signal'].includes(m.kind);
  return `<div class="msg left">${name}<div class="msg-row">${avatar(m.from, 28, state)}<div class="${cls('msg-body', wide && 'wide')}">${body(m, conv)}</div></div></div>`;
}

export function renderThread(conv, state, now) {
  let prev = null;
  const out = [];
  for (const m of conv.messages) {
    const d = divider(m.at, prev, now);
    if (d) out.push(`<div class="divider">${esc(d)}</div>`);
    out.push(renderMessage(m, conv, state));
    prev = m.at;
  }
  return out.join('');
}
