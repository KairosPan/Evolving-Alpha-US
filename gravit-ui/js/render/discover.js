// gravit-ui/js/render/discover.js — Discover as an App Store (spec §7): shelves, cards with one key, the drawer that signs, Installed, upload
import { esc, attrs, cls } from '../html.js';
import { icon } from '../icons.js';
import { PLUGINS, SHELVES, KINDS, byId, byline, search, likeFor } from '../data/plugins.js';
import { logo } from './avatars.js';
import { chip } from './thread.js';
import { kv, sec } from './controls.js';

export function keyFor(p, state, view = 'shelf') {
  const installed = state.plugins.installed.includes(p.id);
  if (!installed) return `<button type="button"${attrs({ class: 'pkey install', 'data-action': 'install', 'data-id': p.id, 'aria-label': `Install ${p.name}` })}>${icon('plus', 14, 2.4)}</button>`;
  if (view === 'installed' || state.discover.asking === p.id) return `<button type="button"${attrs({ class: 'pkey uninstall', 'data-action': 'uninstall', 'data-id': p.id, 'aria-label': `Uninstall ${p.name}` })}>${icon('trash', 15, 2.1)}</button>`;
  return `<button type="button"${attrs({ class: 'pkey installed', 'data-action': 'uninstallAsk', 'data-id': p.id, 'aria-label': `Installed · uninstall ${p.name}` })}>${icon('check', 13, 2.4)}Installed</button>`;
}

export function card(p, state, { view = 'shelf', pressed = false, openIn = null } = {}) {
  // the link carries its own action so a click opens the conversation, not the card's drawer
  const extra = openIn ? `<div class="pcard-extra">${chip('刚装好', 'up')}<a class="link" data-action="open" data-id="${esc(openIn)}" href="#/messages/${esc(openIn)}">Open in Messages ›</a></div>` : '';
  return `<div${attrs({ class: cls('pcard', pressed && 'pressed', view === 'grid' && 'grid'), 'data-action': 'openPlugin', 'data-id': p.id, role: 'button', tabindex: '0' })}>${logo(p, 44)}` +
    `<div class="pcard-body"><div class="pcard-name">${esc(p.name)}</div><div class="pcard-blurb">${esc(p.blurb)}</div><div class="pcard-by">${esc(byline(p))}</div>${extra}</div>` +
    `<div class="pcard-side"><span class="pcard-kind">${esc(p.kind.toUpperCase())}</span>${keyFor(p, state, view === 'grid' && state.discover.installedOnly ? 'installed' : 'shelf')}</div></div>`;
}

// the plugin whose teaching conversation is still unread, while it stays installed (spec §7.5)
const justInstalled = state => {
  const conv = state.conversations.find(c => c.kind === 'bot' && c.teach && c.unread && state.plugins.installed.includes(c.teach));
  return conv ? { id: conv.teach, convId: conv.id } : null;
};
const openInFor = (p, state) => { const ji = justInstalled(state); return ji && ji.id === p.id ? ji.convId : null; };

// what the signature lets the plugin do: only a bot may propose; the rest read and write (spec §6 kind 7: a monitor never orders)
const MAY = {
  Bots: 'read Portfolio · propose in your limit',
  Monitors: 'read what you point it at · write signals, never orders',
  Data: 'answer when asked · write into the conversation',
  Crypto: 'check what you ask about · write findings, never move money',
  Quant: 'run on your idea · write reports, never orders',
};

function shelf(s, state) {
  const ids = s.id === 'like' ? likeFor(state.memory) : s.ids;
  const cards = ids.map(id => byId(id, state.plugins.uploaded)).filter(Boolean).map(p => card(p, state, { pressed: state.discover.drawer === p.id, openIn: openInFor(p, state) })).join('');
  return `<section class="shelf"><div class="shelf-head"><div class="shelf-title">${esc(s.title)}</div><a class="link" href="#/discover/${s.id}">See all ›</a></div><div class="shelf-row">${cards}</div></section>`;
}

function grid(title, plugins, state, back = false) {
  const cards = plugins.map(p => card(p, state, { view: 'grid', pressed: state.discover.drawer === p.id, openIn: openInFor(p, state) })).join('');
  return `<section class="grid-sec">${back ? '<a class="back-link" href="#/discover">‹ Discover</a>' : ''}<div class="grid-title">${esc(title)}</div><div class="grid">${cards}</div></section>`;
}

function header(state) {
  const on = state.discover.installedOnly;
  return `<div class="disc-head"><h1 class="head-title">Discover</h1>` +
    `<div class="search"><label for="dq" class="sr-only">Search plugins</label>${icon('search', 18, 2)}<input id="dq" type="search" autocomplete="off" placeholder="Search plugins" data-action="query"${attrs({ value: state.discover.query })}></div><span class="spacer"></span>` +
    `<button type="button"${attrs({ class: cls('pill', on && 'pressed'), 'data-action': 'toggleInstalledOnly', 'aria-pressed': on ? 'true' : 'false' })}>Installed · ${state.plugins.installed.length}</button>` +
    `<button type="button" class="pill" data-action="openUpload">${icon('upload', 14, 2.2)}Upload a plugin</button></div>`;
}

// the signature table: installing grants what MAY says until you uninstall; uninstalling signs only what and for
function signRows(p, installed, state) {
  const what = [['What you sign', `<b>${installed ? 'uninstall' : 'install'} ${esc(p.id)}</b>`], ['For', `Gravit · ${esc(state.account.wallet.address)}`]];
  return installed ? what : [...what, ['May', esc(MAY[p.kind] ?? MAY.Data)], ['May not', 'pay anyone · move money'], ['Until', 'you uninstall']];
}

export function pluginDrawer(p, state) {
  const installed = state.plugins.installed.includes(p.id);
  const meta = [p.kind, `by ${p.by}`, 'Free', p.installs ? `${p.installs} 装了` : null].filter(Boolean).join(' · ');
  const writes = [...p.writes.map(esc), ...(p.never.length ? [`<span class="dim">不会：${esc(p.never.join('、'))}</span>`] : [])];
  return `<aside class="drawer"${attrs({ 'aria-label': p.name })}><div class="drawer-head"><h2>${esc(p.name)}</h2><button type="button" class="close-key" data-action="closeDrawer" aria-label="Close">×</button></div><div class="drawer-body">` +
    `<div class="plug-id">${logo(p, 56)}<div><div class="plug-name">${esc(p.name)}</div><div class="dim">${esc(meta)}</div></div></div><p class="plug-blurb">${esc(p.blurb)}。</p>` +
    (p.asks.length ? sec('它能被问什么', p.asks) : '') + (writes.length ? sec('它会写什么', writes, true) : '') +
    sec('怎么付', ['免费。Gravit 只在模型调用和成交的单上抽成。']) + sec('要你什么', [p.needs]) +
    `<div class="dsec"><div class="dsec-label">你签的是</div>${kv(signRows(p, installed, state))}</div>` +
    `<div class="drawer-foot">${installed ? `<button type="button" class="btn-primary" data-action="uninstall" data-id="${esc(p.id)}">Uninstall</button>` : `<button type="button" class="btn-primary" data-action="install" data-id="${esc(p.id)}">Install</button>`}</div></div></aside>`;
}

const radios = (name, items, checked) => items.map(v => `<label class="radio-item"><input type="radio" name="${name}" value="${esc(v)}"${v === checked ? ' checked' : ''}><span>${esc(v)}</span></label>`).join('');

export function uploadDrawer() {
  return `<aside class="drawer" aria-label="上传一个插件"><div class="drawer-head"><h2>上传一个插件</h2><button type="button" class="close-key" data-action="closeDrawer" aria-label="Close">×</button></div><div class="drawer-body">` +
    `<form class="upload-form" data-action="publish">` +
    `<div class="field"><label class="field-label" for="up-name">名字</label><input id="up-name" class="input" name="name" type="text" required placeholder="Pairs"></div>` +
    `<div class="field"><label class="field-label" for="up-blurb">一句话</label><input id="up-blurb" class="input" name="blurb" type="text" placeholder="两只相关股的价差回归，给出配对信号"></div>` +
    `<div class="field"><span class="field-label">类型</span><div class="radio-seg">${radios('kind', KINDS, 'Quant')}</div></div>` +
    // spec §7.7: a 44 px slot, initials by default (app.js keeps it on the name's first letter)
    `<div class="field"><span class="field-label">图标</span><div class="icon-pick"><span class="icon-slot" id="up-icon">P</span><button type="button" class="btn-sm">换一张图</button></div></div>` +
    `<div class="field"><label class="field-label" for="up-tools">它暴露的工具</label><textarea id="up-tools" class="textarea" name="tools" rows="2" placeholder="pairs.scan(universe)\npairs.signal(a, b)"></textarea></div>` +
    `<div class="field"><span class="field-label">要用户什么</span><div class="picks">${radios('needs', ['没有', 'Telegram 会话', '交易所 key', '钱包地址'], '没有')}</div></div>` +
    `<div class="field"><span class="field-label">放哪</span><div class="radio-seg">${radios('visibility', ['private', 'public'], 'private').replace('>private<', '>只给我自己 · Private<').replace('>public<', '>放进 Public shop<')}</div></div>` +
    `<div class="btn-row grow"><button type="button" class="btn" data-action="closeDrawer">Cancel</button><button type="submit" class="btn-primary">Publish</button></div></form></div></aside>`;
}

export function renderToast(t) {
  const act = t.action ? `<a class="toast-key" href="#/messages/${esc(t.action.route.id)}">${esc(t.action.label)}</a>` : '';
  return `<div class="toast" role="status">${esc(t.text)}${act}<button type="button" class="toast-x" data-action="dismissToast" aria-label="Dismiss">×</button></div>`;
}

export function renderDiscover(state) {
  const d = state.discover;
  const all = [...PLUGINS, ...state.plugins.uploaded];
  let body;
  if (d.query.trim()) {
    const found = search(d.query, state.plugins.uploaded);
    body = grid(`${found.length} 个`, found, state);
  } else if (d.installedOnly) {
    const mine = all.filter(p => state.plugins.mine.includes(p.id));
    const installed = all.filter(p => state.plugins.installed.includes(p.id) && !state.plugins.mine.includes(p.id));
    body = grid('装了的', installed, state) + (mine.length ? grid('你上传的', mine, state) : '');
  } else if (state.route.id) {
    const s = SHELVES.find(x => x.id === state.route.id);
    const ids = s ? (s.id === 'like' ? likeFor(state.memory) : s.ids) : [];
    body = grid(s?.title ?? 'Discover', ids.map(id => byId(id, state.plugins.uploaded)).filter(Boolean), state, true);
  } else {
    body = SHELVES.map(s => shelf(s, state)).join('');
  }
  const drawer = d.upload ? uploadDrawer() : d.drawer ? pluginDrawer(byId(d.drawer, state.plugins.uploaded) ?? { id: d.drawer, name: d.drawer, kind: '', blurb: '', by: '', installs: '', logo: { type: 'letter', text: '?' }, asks: [], writes: [], never: [], needs: '' }, state) : '';
  const toast = d.toast ? renderToast(d.toast) : '';
  return `<main class="${cls('main', 'disc', (d.upload || d.drawer) && 'with-drawer')}">${header(state)}${body}${drawer}${toast}</main>`;
}
