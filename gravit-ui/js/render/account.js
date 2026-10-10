// gravit-ui/js/render/account.js — Account (spec §8): Linqi's Portfolio and Venues, and Memory as the third segment; the Settings drawer
import { esc, attrs, cls, money } from '../html.js';
import { icon } from '../icons.js';
import { fmtDate } from '../time.js';
import { chip, ticker } from './thread.js';
import { seg, segLinks, inlineEdit, confirmPair } from './controls.js';

const box = (inner, extra = '') => `<section class="${cls('cardbox', extra)}">${inner}</section>`;

function portfolio(a) {
  const alloc = a.alloc.map(x => `<span class="alloc-seg alloc-${x.token}" style="flex:${x.pct}"></span>`).join('');
  const legend = a.alloc.map(x => `<span>${esc(x.name)} ${x.pct}%</span>`).join('');
  const rows = a.holdings.map(h => `<div class="holding"><span>${ticker(h.name)}<span class="dim"> · ${esc(h.venue)}</span></span><span class="num">${money(h.value)}</span>` +
    `<span class="${h.chg == null ? 'dim' : h.chg >= 0 ? 'up' : 'down'}">${h.chg == null ? '—' : (h.chg >= 0 ? '+' : '−') + Math.abs(h.chg).toFixed(1) + '%'}</span></div>`).join('');
  return `<div class="cards">` + box(`<div class="dim">Net worth</div><div class="networth">${money(a.netWorth)}</div><div class="delta"><span class="up">+${money(a.today)} · ${a.todayPct}%</span><span class="dim">today</span></div>` +
    `<div class="spark"></div><div class="alloc-bar">${alloc}</div><div class="alloc-legend">${legend}</div><div class="holdings">${rows}</div>` +
    `<div class="btn-row"><button type="button" class="btn-sm">Move</button><button type="button" class="btn-sm">Receive</button><button type="button" class="btn-sm">Statement</button></div>`) + `</div>`;
}

function venues(a) {
  const rows = a.venues.map(v => `<div class="venue"><span><b>${esc(v.name)}</b><br><span class="dim">${esc(v.line)}</span></span>${chip(v.state, v.state === 'Healthy' ? 'up' : 'grey')}</div>`).join('');
  return `<div class="cards">` + box(`<div class="card-head"><div class="cardbox-title">Venues</div></div><div class="venues">${rows}</div><button type="button" class="btn-primary">Connect an account</button>`) + `</div>`;
}

const switchRow = (label, key, on) => `<div class="switch-row"><div class="switch-label">${esc(label)}</div>` +
  `<button type="button"${attrs({ class: cls('switch', on && 'on'), role: 'switch', 'aria-checked': on ? 'true' : 'false', 'data-action': 'memorySwitch', 'data-key': key, 'aria-label': label })}><span class="knob"></span></button></div>`;

export function renderMemory(state) {
  const M = state.memory;
  const groups = [...new Set(M.entries.map(e => e.group))];
  const list = groups.map(g => `<div class="mem-group"><div class="mem-label">${esc(g)}</div>` + M.entries.filter(e => e.group === g).map(e =>
    `<div class="mem-entry"><div class="mem-body">${state.edit?.kind === 'memory' && state.edit.id === e.id ? inlineEdit([{ name: 'text', value: e.text, label: '改成' }], state.edit.error) : `<div class="mem-text">${esc(e.text)}</div>`}<div class="mem-source">${esc(e.source)} · ${fmtDate(e.at)}</div></div>` +
    `<div class="mem-keys"><button type="button" class="small-key" data-action="editMemory" data-id="${esc(e.id)}" aria-label="Edit">${icon('pencil', 13, 2.2)}</button>` +
    `<button type="button" class="small-key danger" data-action="forgetMemory" data-id="${esc(e.id)}" aria-label="Forget">${icon('trash', 13, 2.2)}</button></div></div>`).join('') + `</div>`).join('');
  const left = box(`<div class="card-head"><div class="cardbox-title">Gravit 记得的你</div><span class="dim">${M.entries.length} 条 · 只在这台机器上</span></div>${list}` +
    `<form class="mem-add" data-action="addMemory"><label for="mem-new" class="sr-only">加一条</label><input id="mem-new" class="input" name="text" type="text" autocomplete="off" placeholder="加一条它该记住的…"><button type="submit" class="btn-primary small">Add</button></form>`);
  const where = [['Discover', 'Like 货架按风格推：价值 → Buffett、研报、政客 bot'], ['早报', '挑什么给你看，什么时候发'], ['新会话', '默认附的额度、默认的场所'], ['群聊', '谁先说、谁的话该打折']]
    .map(([k, v]) => `<div class="where-row">${chip(k, 'grey')}<span>${esc(v)}</span></div>`).join('');
  const right = box(`<div class="cardbox-title">它用在哪</div><div class="where">${where}</div>`) +
    box(`<div class="cardbox-title">开关</div>${switchRow('让 Gravit 记新东西', 'remember', M.remember)}${switchRow('它学到的先问我再记', 'askFirst', M.askFirst)}${switchRow('群聊里的 bot 也能看 Memory', 'botsRead', M.botsRead)}` +
      `<div class="btn-row"><button type="button" class="btn-sm" data-action="exportMemory">Export</button>${state.confirm?.action === 'forgetAll' ? confirmPair('确认全部忘掉') : '<button type="button" class="btn-danger" data-action="forgetAll">Forget all</button>'}</div>`);
  return `<div class="cards two">${left}<div class="stack">${right}</div></div>`;
}

export function renderSettings(state) {
  const theme = { cream: 'Cream', black: 'Black' }[state.theme] ?? 'System';
  return `<aside class="drawer" aria-label="Settings"><div class="drawer-head"><h2>Settings</h2><button type="button" class="close-key" data-action="closeSettings" aria-label="Close">×</button></div><div class="drawer-body">` +
    `<div class="dsec"><div class="dsec-label">Theme</div>${seg(['Cream', 'Black', 'System'], theme, 'setTheme')}</div>` +
    `<div class="dsec"><div class="dsec-label">Demo</div>${state.confirm?.action === 'resetDemo' ? confirmPair('确认重置') : '<button type="button" class="btn-danger" data-action="resetDemo">Reset demo</button>'}</div></div></aside>`;
}

export function renderAccount(state) {
  const tab = state.route.tab ?? 'portfolio';
  const a = state.account;
  const head = `<div class="acct-head"><h1 class="head-title">Account</h1><span class="spacer"></span>${seg(['Guard', 'Beast'], a.mode === 'beast' ? 'Beast' : 'Guard', 'setMode')}${chip('Trading on · $100 a move', 'up')}<button type="button" class="pill" data-action="openSettings">Settings</button></div>`;
  const tabs = segLinks([['Portfolio', '#/account/portfolio', 'portfolio'], ['Venues', '#/account/venues', 'venues'], ['Memory', '#/account/memory', 'memory']], tab);
  const body = tab === 'venues' ? venues(a) : tab === 'memory' ? renderMemory(state) : portfolio(a);
  return `<main class="${cls('main', 'acct', state.settingsOpen && 'with-drawer')}">${head}${tabs}${body}${state.settingsOpen ? renderSettings(state) : ''}</main>`;
}
