// gravit-ui/js/render/account.js — Account (spec §8): Linqi's Portfolio and Venues, and Memory as the third segment; the Settings drawer
import { esc, attrs, cls, money } from '../html.js';
import { icon } from '../icons.js';
import { fmtDate, fmtClock } from '../time.js';
import { VENUES, CONNECTABLE } from '../data/seed.js';
import { chip, ticker } from './thread.js';
import { seg, segLinks, inlineEdit, confirmPair } from './controls.js';

const box = (inner, extra = '') => `<section class="${cls('cardbox', extra)}">${inner}</section>`;
const panelKey = (panel, label) => `<button type="button" class="btn-sm" data-action="openPanel" data-panel="${panel}">${label}</button>`;
const opt = (v, selected) => `<option${attrs({ value: v, selected: v === selected })}>${esc(v)}</option>`;

// a square of modules derived from the address, with the three corner marks: a stand-in for a real QR code
function qr(text) {
  const n = 21;
  let h = 2166136261;
  const bits = [];
  for (let i = 0; i < n * n; i++) { h ^= text.charCodeAt(i % text.length) + i; h = Math.imul(h, 16777619); bits.push((h >>> 7) & 1); }
  const finder = (x, y) => [[0, 0], [n - 7, 0], [0, n - 7]].some(([fx, fy]) => x >= fx && x < fx + 7 && y >= fy && y < fy + 7);
  const ring = (x, y) => [[0, 0], [n - 7, 0], [0, n - 7]].some(([fx, fy]) => { const dx = x - fx, dy = y - fy; return dx >= 0 && dx < 7 && dy >= 0 && dy < 7 && (dx === 0 || dx === 6 || dy === 0 || dy === 6 || (dx >= 2 && dx <= 4 && dy >= 2 && dy <= 4)); });
  let cells = '';
  for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) if (finder(x, y) ? ring(x, y) : bits[y * n + x]) cells += `<rect x="${x}" y="${y}" width="1" height="1"></rect>`;
  return `<svg class="qr" viewBox="-1 -1 ${n + 2} ${n + 2}" role="img" aria-label="Receive QR code">${cells}</svg>`;
}

// Account's panels as drawers: Move, Receive, Statement, Connect an account
export function renderPanel(state) {
  const a = state.account;
  if (!a.panel) return '';
  const drawer = (label, inner, tag = '') => `<aside class="drawer" aria-label="${label}"><div class="drawer-head">${tag ? `<div class="drawer-title"><h2>${label}</h2>${tag}</div>` : `<h2>${label}</h2>`}<button type="button" class="close-key" data-action="closePanel" aria-label="Close">×</button></div><div class="drawer-body">${inner}</div></aside>`;
  const error = a.panelError ? `<div class="field-error">${esc(a.panelError)}</div>` : '';
  if (a.panel === 'move') {
    const froms = [...new Set(a.holdings.map(h => h.venue))];
    const assets = [...new Set(a.holdings.map(h => h.name))];
    const tos = [...new Set([...VENUES, ...a.venues.filter(v => v.state === 'Healthy').map(v => v.name)])];
    return drawer('Move', `<form class="move-form" data-action="moveFunds">` +
      `<div class="field"><label class="field-label" for="mv-from">From</label><select id="mv-from" class="input" name="from">${froms.map(v => opt(v, 'Stand-in Wallet')).join('')}</select></div>` +
      `<div class="field"><label class="field-label" for="mv-asset">Asset</label><select id="mv-asset" class="input" name="asset">${assets.map(v => opt(v, 'USDC')).join('')}</select></div>` +
      `<div class="field"><label class="field-label" for="mv-to">To</label><select id="mv-to" class="input" name="to">${tos.map(v => opt(v, 'Stand-in Exchange')).join('')}</select></div>` +
      `<div class="field"><label class="field-label" for="mv-amount">Amount ($)</label><input id="mv-amount" class="input" name="amount" type="number" min="0" step="any"></div>${error}` +
      `<div class="btn-row grow"><button type="button" class="btn" data-action="closePanel">Cancel</button><button type="submit" class="btn-primary">Move</button></div></form>`);
  }
  if (a.panel === 'receive') {
    // into the owner's own wallet: the asset in the title, the chain beside it, the QR left of the address
    const r = a.receive;
    return drawer(`Receive · ${esc(r.asset)}`, `<div class="receive">${qr(r.full ?? r.address)}<div class="receive-side"><div><span class="mono">${esc(r.address)}</span><span class="dim"> · ${esc(r.venue)}</span></div>` +
      `<button type="button" class="btn-sm" data-action="copyAddress">${a.copied ? 'Copied' : 'Copy address'}</button></div></div>`, chip(r.chain, 'grey'));
  }
  if (a.panel === 'statement') {
    const rows = a.activity.map(x => `<div class="activity-row"><span class="dim">${fmtDate(x.at)} ${fmtClock(x.at)}</span><span class="activity-text">${esc(x.text)}</span>` +
      `<span class="${cls('num', x.amount > 0 && 'up', x.amount < 0 && 'down')}">${x.amount ? (x.amount > 0 ? '+' : '−') + money(Math.abs(x.amount)) : ''}</span></div>`).join('');
    return drawer('Statement', `<div class="activity">${rows}</div><button type="button" class="btn-sm" data-action="exportStatement">Export CSV</button>`);
  }
  const rows = CONNECTABLE.map(name => {
    const done = a.venues.some(v => v.name === name);
    const busy = a.connecting === name;
    return `<div class="venue"><span><b>${esc(name)}</b></span><button type="button"${attrs({ class: 'btn-sm', 'data-action': 'connectVenue', 'data-name': name, disabled: done || busy })}>${done ? 'Connected' : busy ? 'Connecting…' : 'Connect'}</button></div>`;
  }).join('');
  return drawer('Connect an account', `<div class="venues">${rows}</div>`);
}

function portfolio(a) {
  const alloc = a.alloc.map(x => `<span class="alloc-seg alloc-${x.token}" style="flex:${x.pct}"></span>`).join('');
  const legend = a.alloc.map(x => `<span>${esc(x.name)} ${x.pct}%</span>`).join('');
  const rows = a.holdings.map(h => `<div class="holding"><span>${ticker(h.name)}<span class="dim"> · ${esc(h.venue)}</span></span><span class="num">${money(h.value)}</span>` +
    `<span class="${h.chg == null ? 'dim' : h.chg >= 0 ? 'up' : 'down'}">${h.chg == null ? '—' : (h.chg >= 0 ? '+' : '−') + Math.abs(h.chg).toFixed(1) + '%'}</span></div>`).join('');
  return `<div class="cards">` + box(`<div class="label">Net worth</div><div class="networth">${money(a.netWorth)}</div><div class="delta"><span class="up">+${money(a.today)} · ${a.todayPct}%</span><span class="dim">today</span></div>` +
    `<div class="spark"></div><div class="alloc-bar">${alloc}</div><div class="alloc-legend">${legend}</div><div class="holdings">${rows}</div>` +
    `<div class="btn-row">${panelKey('move', 'Move')}${panelKey('receive', 'Receive')}${panelKey('statement', 'Statement')}</div>`) + `</div>`;
}

function venues(a) {
  const rows = a.venues.map(v => `<div class="venue"><span><b>${esc(v.name)}</b><br><span class="dim">${esc(v.line)}</span></span>${chip(v.state, v.state === 'Healthy' ? 'up' : 'grey')}</div>`).join('');
  return `<div class="cards">` + box(`<div class="card-head"><div class="cardbox-title">Venues</div></div><div class="venues">${rows}</div><button type="button" class="btn-primary" data-action="openPanel" data-panel="connect">Connect an account</button>`) + `</div>`;
}

const switchRow = (label, key, on) => `<div class="switch-row"><div class="switch-label">${esc(label)}</div>` +
  `<button type="button"${attrs({ class: cls('switch', on && 'on'), role: 'switch', 'aria-checked': on ? 'true' : 'false', 'data-action': 'memorySwitch', 'data-key': key, 'aria-label': label })}><span class="knob"></span></button></div>`;

export function renderMemory(state) {
  const M = state.memory;
  const groups = [...new Set(M.entries.map(e => e.group))];
  const list = groups.map(g => `<div class="mem-group"><div class="mem-label">${esc(g)}</div>` + M.entries.filter(e => e.group === g).map(e =>
    `<div class="mem-entry"><div class="mem-body">${state.edit?.kind === 'memory' && state.edit.id === e.id ? inlineEdit([{ name: 'text', value: e.text, label: 'Change to' }], state.edit.error) : `<div class="mem-text">${esc(e.text)}</div>`}<div class="mem-source">${esc(e.source)} · ${fmtDate(e.at)}</div></div>` +
    `<div class="mem-keys"><button type="button" class="small-key" data-action="editMemory" data-id="${esc(e.id)}" aria-label="Edit">${icon('pencil', 13, 2.2)}</button>` +
    `<button type="button" class="small-key danger" data-action="forgetMemory" data-id="${esc(e.id)}" aria-label="Forget">${icon('trash', 13, 2.2)}</button></div></div>`).join('') + `</div>`).join('');
  const left = box(`<div class="card-head"><div class="cardbox-title">What Gravit remembers about you</div><span class="dim">${M.entries.length} ${M.entries.length === 1 ? 'entry' : 'entries'}</span></div>${list}` +
    `<form class="mem-add" data-action="addMemory"><label for="mem-new" class="sr-only">Add one</label><input id="mem-new" class="input" name="text" type="text" autocomplete="off" placeholder="Add something it should remember…"><button type="submit" class="btn-primary small">Add</button></form>`);
  const where = [['Discover', 'The Like shelf follows your style: value → Buffett, Broker research, US politician bot'], ['Morning brief', 'What to show you, and when'], ['New message', 'The default limit and venue'], ['Group chats', 'Who speaks first, whose word is discounted']]
    .map(([k, v]) => `<div class="where-row">${chip(k, 'grey')}<span>${esc(v)}</span></div>`).join('');
  const right = box(`<div class="cardbox-title">Where it is used</div><div class="where">${where}</div>`) +
    box(`<div class="cardbox-title">Switches</div>${switchRow('Let Gravit remember new things', 'remember', M.remember)}${switchRow('Ask me before it keeps what it learned', 'askFirst', M.askFirst)}${switchRow('Bots in group chats can read Memory', 'botsRead', M.botsRead)}` +
      `<div class="btn-row"><button type="button" class="btn-sm" data-action="exportMemory">Export</button>${state.confirm?.action === 'forgetAll' ? confirmPair('Yes, forget all') : '<button type="button" class="btn-danger" data-action="forgetAll">Forget all</button>'}</div>`);
  return `<div class="cards two">${left}<div class="stack">${right}</div></div>`;
}

export function renderSettings(state) {
  const theme = { cream: 'Cream', black: 'Black' }[state.theme] ?? 'System';
  return `<aside class="drawer" aria-label="Settings"><div class="drawer-head"><h2>Settings</h2><button type="button" class="close-key" data-action="closeSettings" aria-label="Close">×</button></div><div class="drawer-body">` +
    `<div class="dsec"><div class="dsec-label">Theme</div>${seg(['Cream', 'Black', 'System'], theme, 'setTheme')}</div>` +
    `<div class="dsec"><div class="dsec-label">Demo</div>${state.confirm?.action === 'resetDemo' ? confirmPair('Yes, reset') : '<button type="button" class="btn-danger" data-action="resetDemo">Reset demo</button>'}</div></div></aside>`;
}

export function renderAccount(state) {
  const tab = state.route.tab ?? 'portfolio';
  const a = state.account;
  const head = `<div class="acct-head"><h1 class="head-title">Account</h1><span class="spacer"></span>${seg(['Guard', 'Beast'], a.mode === 'beast' ? 'Beast' : 'Guard', 'setMode')}${chip('Trading on · $100 a move', 'up')}<button type="button" class="pill" data-action="openSettings">Settings</button></div>`;
  const tabs = segLinks([['Portfolio', '#/account/portfolio', 'portfolio'], ['Venues', '#/account/venues', 'venues'], ['Memory', '#/account/memory', 'memory']], tab);
  const body = tab === 'venues' ? venues(a) : tab === 'memory' ? renderMemory(state) : portfolio(a);
  return `<main class="${cls('main', 'acct', (state.settingsOpen || a.panel) && 'with-drawer')}">${head}${tabs}${body}${state.settingsOpen ? renderSettings(state) : renderPanel(state)}</main>`;
}
