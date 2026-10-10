// gravit-ui/js/render/discover.js — Discover as an App Store (spec §7): shelves, cards, the drawer that signs, 我的插件, the MCP connector
import { esc, attrs, cls } from '../html.js';
import { icon } from '../icons.js';
import { PLUGINS, SHELVES, KINDS, byId, byline, search, likeFor, ICON_CHOICES, hostOf } from '../data/plugins.js';
import { logo } from './avatars.js';
import { chip } from './thread.js';
import { kv, sec } from './controls.js';

// not installed: the + key; installed: a ✓ beside the trash key, in every view
export function keyFor(p, state) {
  if (!state.plugins.installed.includes(p.id)) return `<button type="button"${attrs({ class: 'pkey install', 'data-action': 'install', 'data-id': p.id, 'aria-label': `Install ${p.name}` })}>${icon('plus', 14, 2.4)}</button>`;
  return `<span class="pkeys"><span class="pkey-done" role="img" aria-label="已安装">${icon('check', 14, 2.4)}</span>` +
    `<button type="button"${attrs({ class: 'pkey uninstall', 'data-action': 'uninstall', 'data-id': p.id, 'aria-label': `Uninstall ${p.name}` })}>${icon('trash', 15, 2.1)}</button></span>`;
}

export function card(p, state, { view = 'shelf', pressed = false, openIn = null } = {}) {
  // the link carries its own action so a click opens the conversation, not the card's drawer
  const extra = openIn ? `<div class="pcard-extra">${chip('刚装好', 'up')}<a class="link" data-action="open" data-id="${esc(openIn)}" href="#/messages/${esc(openIn)}">Open in Messages ›</a></div>` : '';
  return `<div${attrs({ class: cls('pcard', pressed && 'pressed', view === 'grid' && 'grid'), 'data-action': 'openPlugin', 'data-id': p.id, role: 'button', tabindex: '0' })}>${logo(p, 44)}` +
    `<div class="pcard-body"><div class="pcard-name">${esc(p.name)}</div><div class="pcard-blurb">${esc(p.blurb)}</div><div class="pcard-by">${esc(byline(p))}</div>${extra}</div>` +
    `<div class="pcard-side"><span class="pcard-kind">${esc(p.kind.toUpperCase())}</span>${keyFor(p, state)}</div></div>`;
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
    `<button type="button"${attrs({ class: cls('pill', on && 'pressed'), 'data-action': 'toggleInstalledOnly', 'aria-pressed': on ? 'true' : 'false' })}>我的插件 · ${state.plugins.installed.length}</button>` +
    `<button type="button" class="pill" data-action="openCreate">${icon('plus', 14, 2.2)}Create</button></div>`;
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

// radios that write into the connector's form as they change (app.js: data-action mcpField)
const radios = (name, items, checked, labels = {}) => items.map(v => `<label class="radio-item"><input type="radio" name="${name}" value="${esc(v)}" data-action="mcpField"${v === checked ? ' checked' : ''}><span>${esc(labels[v] ?? v)}</span></label>`).join('');
const field = (id, label, input) => `<div class="field"><label class="field-label" for="${id}">${esc(label)}</label>${input}</div>`;
const text = (id, name, value, extra = {}) => `<input${attrs({ id, class: 'input', name, type: extra.type ?? 'text', autocomplete: 'off', 'data-action': 'mcpField', placeholder: extra.placeholder ?? null, value, 'aria-invalid': extra.invalid ? 'true' : null })}>`;

// Create: the MCP connector dialog — a remote MCP server becomes your own plugin (spec §7.7, the shop's MCP face)
export function renderCreate(state) {
  const c = state.discover.create;
  if (!c) return '';
  const f = c.form;
  const head = title => `<div class="modal-head"><h2 class="modal-title">${esc(title)}</h2><button type="button" class="close-key" data-action="closeCreate" aria-label="Close">×</button></div>`;
  let inner;
  if (c.step === 'tools') {
    const rows = c.tools.map((t, i) => `<label class="tool-row"><input type="checkbox" data-action="toggleMcpTool" data-id="${i}"${t.on ? ' checked' : ''}><span class="mono">${esc(t.name)}</span></label>`).join('');
    inner = head(`发现 ${c.tools.length} 个工具`) + `<div class="modal-body"><div class="dim">${esc(f.name.trim() || hostOf(f.url))} · ${esc(hostOf(f.url))}</div><div class="tool-list">${rows}</div>` +
      `<div class="btn-row grow"><button type="button" class="btn" data-action="backToForm">返回</button><button type="button" class="btn-primary" data-action="addMcp">添加</button></div></div>`;
  } else {
    const glyph = ICON_CHOICES[f.icon];
    const slot = glyph ? icon(glyph, 22, 2) : esc((f.name.trim()[0] ?? 'P').toUpperCase());
    const auth = f.auth === 'API key' ? field('mcp-key', 'API key', text('mcp-key', 'key', f.key, { type: 'password', placeholder: 'sk-…' }))
      : f.auth === 'OAuth' ? field('mcp-client-id', 'OAuth Client ID', text('mcp-client-id', 'clientId', f.clientId)) + field('mcp-client-secret', 'OAuth Client Secret', text('mcp-client-secret', 'clientSecret', f.clientSecret, { type: 'password' })) : '';
    const foot = c.step === 'connecting'
      ? `<div class="mcp-status">正在连接 ${esc(hostOf(f.url))}…</div>`
      : `<div class="btn-row grow"><button type="button" class="btn" data-action="closeCreate">取消</button><button type="submit" class="btn-primary">连接</button></div>`;
    inner = `<form class="mcp-form" data-action="connectMcp">${head('添加 MCP 连接器')}<div class="modal-body">` +
      field('mcp-name', '名称', text('mcp-name', 'name', f.name, { placeholder: 'Pairs' })) +
      field('mcp-url', 'MCP 服务器地址', text('mcp-url', 'url', f.url, { type: 'url', placeholder: 'https://example.com/mcp', invalid: !!c.error })) +
      (c.error ? `<div class="field-error">${esc(c.error)}</div>` : '') +
      `<div class="field"><span class="field-label">认证</span><div class="radio-seg">${radios('auth', ['无', 'API key', 'OAuth'], f.auth)}</div></div>` + auth +
      `<div class="field"><span class="field-label">图标</span><div class="icon-pick"><span class="icon-slot" id="mcp-icon">${slot}</span><button type="button" class="btn-sm" data-action="cycleCreateIcon">换一张图</button></div></div>` +
      `<div class="field"><span class="field-label">类型</span><div class="radio-seg">${radios('kind', KINDS, f.kind)}</div></div>` +
      `<div class="field"><span class="field-label">放哪</span><div class="radio-seg">${radios('visibility', ['private', 'public'], f.visibility, { private: '只给我自己 · Private', public: '放进 Public shop' })}</div></div>` +
      foot + `</div></form>`;
  }
  return `<div class="modal-scrim"><div class="modal" role="dialog" aria-label="添加 MCP 连接器">${inner}</div></div>`;
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
    body = grid('装了的', installed, state) + (mine.length ? grid('你创建的', mine, state) : '');
  } else if (state.route.id) {
    const s = SHELVES.find(x => x.id === state.route.id);
    const ids = s ? (s.id === 'like' ? likeFor(state.memory) : s.ids) : [];
    body = grid(s?.title ?? 'Discover', ids.map(id => byId(id, state.plugins.uploaded)).filter(Boolean), state, true);
  } else {
    body = SHELVES.map(s => shelf(s, state)).join('');
  }
  const drawer = d.drawer ? pluginDrawer(byId(d.drawer, state.plugins.uploaded) ?? { id: d.drawer, name: d.drawer, kind: '', blurb: '', by: '', installs: '', logo: { type: 'letter', text: '?' }, asks: [], writes: [], never: [], needs: '' }, state) : '';
  const toast = d.toast ? renderToast(d.toast) : '';
  return `<main class="${cls('main', 'disc', d.drawer && 'with-drawer')}">${header(state)}${body}${drawer}${toast}${renderCreate(state)}</main>`;
}
