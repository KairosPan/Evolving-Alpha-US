// gravit-ui/js/render/discover.js — Discover as an App Store (spec §7): shelves, cards, a page per plugin that signs, My plugins, and Create: Discover's own MCP face
import { esc, attrs, cls } from '../html.js';
import { toHash } from '../router.js';
import { icon } from '../icons.js';
import { PLUGINS, SHELVES, SHOP_MCP, byId, search, likeFor, fromManifest } from '../data/plugins.js';
import { logo } from './avatars.js';
import { kv, sec } from './controls.js';

// not installed: the + key; installed: a ✓ beside the trash key, in every view; your public upload while it is reviewed: a clock
export function keyFor(p, state) {
  const installed = state.plugins.installed.includes(p.id);
  if (!installed && p.review) return `<span class="pkey-wait" role="img" aria-label="In review">${icon('clock', 15, 2.1)}</span>`;
  if (!installed) return `<button type="button"${attrs({ class: 'pkey install', 'data-action': 'install', 'data-id': p.id, 'aria-label': `Install ${p.name}` })}>${icon('plus', 14, 2.4)}</button>`;
  return `<span class="pkeys"><span class="pkey-done" role="img" aria-label="Installed">${icon('check', 14, 2.4)}</span>` +
    `<button type="button"${attrs({ class: 'pkey uninstall', 'data-action': 'uninstall', 'data-id': p.id, 'aria-label': `Uninstall ${p.name}` })}>${icon('trash', 15, 2.1)}</button></span>`;
}

// a card opens its plugin's page; its key installs or uninstalls in place
export function card(p, state, { view = 'shelf', openIn = null } = {}) {
  // the link carries its own action so a click opens the conversation, not the plugin's page
  const extra = openIn ? `<div class="pcard-extra"><a class="link" data-action="open" data-id="${esc(openIn)}" href="#/messages/${esc(openIn)}">Open in Messages ›</a></div>` : '';
  return `<div${attrs({ class: cls('pcard', view === 'grid' && 'in-grid'), 'data-action': 'openPlugin', 'data-id': p.id, role: 'button', tabindex: '0' })}>${logo(p, 44)}` +
    `<div class="pcard-body"><div class="pcard-name">${esc(p.name)}</div><div class="pcard-blurb">${esc(p.blurb)}</div>${extra}</div>` +
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

// a shelf's cards: your own uploads of its kind first, newest first, then the catalogue's
const shelfIds = (s, state) => (s.id === 'like' ? likeFor(state.memory) : [...state.plugins.uploaded.filter(p => p.kind === s.kind).map(p => p.id).reverse(), ...s.ids]);

function shelf(s, state) {
  const cards = shelfIds(s, state).map(id => byId(id, state.plugins.uploaded)).filter(Boolean).map(p => card(p, state, { openIn: openInFor(p, state) })).join('');
  return `<section class="shelf"><div class="shelf-head"><div class="shelf-title">${esc(s.title)}</div><a class="link" href="#/discover/${s.id}">See all ›</a></div><div class="shelf-row">${cards}</div></section>`;
}

function grid(title, plugins, state, back = false) {
  const cards = plugins.map(p => card(p, state, { view: 'grid', openIn: openInFor(p, state) })).join('');
  return `<section class="grid-sec">${back ? '<a class="back-link" href="#/discover">‹ Discover</a>' : ''}<div class="grid-title">${esc(title)}</div><div class="grid">${cards}</div></section>`;
}

function header(state) {
  const on = state.discover.installedOnly;
  return `<div class="disc-head"><h1 class="head-title">Discover</h1>` +
    `<div class="search"><label for="dq" class="sr-only">Search plugins</label>${icon('search', 18, 2)}<input id="dq" type="search" autocomplete="off" placeholder="Search plugins" data-action="query"${attrs({ value: state.discover.query })}></div><span class="spacer"></span>` +
    `<button type="button"${attrs({ class: cls('pill', on && 'pressed'), 'data-action': 'toggleInstalledOnly', 'aria-pressed': on ? 'true' : 'false' })}>My plugins</button>` +
    `<button type="button" class="pill" data-action="openCreate">${icon('plus', 14, 2.2)}Create</button></div>`;
}

// the signature table: installing grants what MAY says until you uninstall; uninstalling signs only what and for
function signRows(p, installed, state) {
  const what = [['What you sign', `<b>${installed ? 'uninstall' : 'install'} ${esc(p.id)}</b>`], ['For', `Gravit · ${esc(state.account.wallet.address)}`]];
  return installed ? what : [...what, ['May', esc(MAY[p.kind] ?? MAY.Data)], ['May not', 'pay anyone · move money'], ['Until', 'you uninstall']];
}

// a plugin's own page: the way back, its head with the one key, what you sign under it, then what it does
export function pluginPage(p, state) {
  const installed = state.plugins.installed.includes(p.id);
  // your own plugin says where it stands; a catalogue plugin, how many installed it
  const meta = state.plugins.mine.includes(p.id)
    ? `${p.kind} · ${p.review ? 'In review' : p.visibility === 'private' ? 'Private' : 'Public'}`
    : [p.kind, p.installs ? `${p.installs} installs` : null].filter(Boolean).join(' · ');
  const writes = [...p.writes.map(esc), ...(p.never.length ? [`<span class="dim">Never: ${esc(p.never.join(', '))}</span>`] : [])];
  const tools = Array.isArray(p.tools) && p.tools.length ? sec('Tools', p.tools.map(t => `<span class="mono">${esc(t)}</span>`), true) : '';
  // while it is reviewed there is nothing to sign yet
  const pending = p.review && !installed;
  const key = pending ? '<button type="button" class="btn-primary" disabled>In review</button>'
    : installed ? `<button type="button" class="btn-primary" data-action="uninstall" data-id="${esc(p.id)}">Uninstall</button>` : `<button type="button" class="btn-primary" data-action="install" data-id="${esc(p.id)}">Install</button>`;
  const back = toHash(state.lastDiscover ?? { screen: 'discover', id: null });
  return `<main class="main disc plugin-page"><a class="back-link page-back" href="${esc(back)}">‹ Discover</a>` +
    `<header class="plug-head">${logo(p, 72)}<div class="plug-title"><h1 class="plug-name">${esc(p.name)}</h1><div class="dim">${esc(meta)}</div></div><div class="plug-key">${key}</div></header>` +
    `<div class="plug-body"><p class="plug-blurb">${esc(p.blurb)}.</p>` +
    (pending ? '' : `<div class="dsec"><div class="dsec-label">What you sign</div>${kv(signRows(p, installed, state))}</div>`) +
    (p.asks.length ? sec('What you can ask it', p.asks) : '') + (writes.length ? sec('What it writes', writes, true) : '') + tools + sec('What it needs from you', [p.needs]) +
    `</div>${state.discover.toast ? renderToast(state.discover.toast) : ''}</main>`;
}

// the plugin page the route names (nav sends an unknown one back to Discover)
export function renderPlugin(state) {
  return pluginPage(byId(state.route.id, state.plugins.uploaded), state);
}

const radio = (name, action, value, checked, label = value) => `<label class="radio-item"><input type="radio" name="${name}" value="${esc(value)}" data-action="${action}"${checked ? ' checked' : ''}><span>${esc(label)}</span></label>`;
const field = (label, body) => `<div class="field"><span class="field-label">${esc(label)}</span>${body}</div>`;
// one line of the client's calls on Discover: done, waiting on you, or refused
const callRow = (call, state) => `<div class="tool-row"><span class="mono">${esc(call)}</span><span class="spacer"></span><span class="tool-state ${state}">${state === 'ok' ? icon('check', 14, 2.4) : state === 'no' ? icon('x', 14, 2.4) : '…'}</span></div>`;

// what the owner signs for shop.publish, in the drawer's grammar: private = publish and install for Gravit; public = publish into the shop
function publishRows(m, visibility, state) {
  const what = ['What you sign', `<b>publish ${esc(m.id)} · ${visibility}</b>`];
  if (visibility === 'public') return [what, ['For', 'Public shop']];
  return [what, ['For', `Gravit · ${esc(state.account.wallet.address)}`], ['May', esc(MAY[m.kind] ?? MAY.Data)], ['May not', 'pay anyone · move money'], ['Until', 'you uninstall']];
}

// Create: Discover's own MCP face (spec §7.7) — its address and tools, the line a client takes, then the client's calls and the owner's signature
export function renderCreate(state) {
  const c = state.discover.create;
  if (!c) return '';
  const head = '<div class="modal-head"><h2 class="modal-title">Discover MCP</h2><button type="button" class="close-key" data-action="closeCreate" aria-label="Close">×</button></div>';
  const face = field('Address', `<span class="mono">${esc(SHOP_MCP.url)}</span>`) + field('Tools', `<div class="tool-chips">${SHOP_MCP.tools.map(t => `<span class="chip grey mono">${esc(t)}</span>`).join('')}</div>`);
  const status = c.step === 'wait' ? '<span class="status grey"><span class="status-dot"></span>Waiting for a connection</span>' : `<span class="status up"><span class="status-dot"></span>${esc(c.client)} connected</span>`;
  const publishCall = c.manifest ? `shop.publish(${c.manifest.id}, ${c.visibility})` : '';
  let body;
  if (c.step === 'wait') {
    const line = SHOP_MCP.clients[c.client];
    body = face + field('Client', `<div class="radio-seg">${Object.keys(SHOP_MCP.clients).map(n => radio('client', 'mcpClient', n, n === c.client)).join('')}</div>`) +
      `<div class="snippet">${line.file ? `<div class="snippet-file mono">${esc(line.file)}</div>` : ''}<pre class="snippet-code mono">${esc(line.code)}</pre>` +
      `<button type="button" id="mcp-copy" class="btn-sm" data-action="copyMcp">${c.copied ? 'Copied' : 'Copy'}</button></div>` + status;
  } else if (c.step === 'connected') {
    body = face + status + `<div class="tool-list">${callRow('shop.mine()', 'ok')}</div>`;
  } else if (c.step === 'refused') {
    body = face + status + `<div class="tool-list">${callRow('shop.mine()', 'ok')}${callRow(publishCall, 'no')}</div>`;
  } else {
    const p = fromManifest(c.manifest, c.visibility, 0);
    body = status + `<div class="tool-list">${callRow('shop.mine()', 'ok')}${callRow(publishCall, 'wait')}</div>` +
      `<div class="manifest"><div class="manifest-top">${logo(p, 44)}<div class="manifest-body"><div class="pcard-name">${esc(p.name)}</div><div class="pcard-blurb">${esc(p.blurb)}</div></div><span class="pcard-kind">${esc(p.kind.toUpperCase())}</span></div>` +
      kv([['Tools', `<span class="mono">${p.tools.map(esc).join(' · ')}</span>`], ['What it needs from you', esc(p.needs)]]) + '</div>' +
      field('Where', `<div class="radio-seg">${radio('visibility', 'uploadVisibility', 'private', c.visibility === 'private', 'Just me · Private')}${radio('visibility', 'uploadVisibility', 'public', c.visibility === 'public', 'Public shop')}</div>`) +
      `<div class="dsec"><div class="dsec-label">What you sign</div>${kv(publishRows(c.manifest, c.visibility, state))}</div>` +
      '<div class="btn-row grow"><button type="button" class="btn" data-action="rejectUpload">Refuse</button><button type="button" class="btn-primary" data-action="publishUpload">Publish</button></div>';
  }
  return `<div class="modal-scrim"><div class="modal wide" role="dialog" aria-label="Discover MCP">${head}<div class="modal-body">${body}</div></div></div>`;
}

// a toast's key opens a conversation or a plugin's page
export function renderToast(t) {
  const a = t.action;
  const act = !a ? '' : `<a class="toast-key" href="${a.plugin ? `#/plugin/${esc(a.plugin)}` : `#/messages/${esc(a.route.id)}`}">${esc(a.label)}</a>`;
  return `<div class="toast" role="status">${esc(t.text)}${act}<button type="button" class="toast-x" data-action="dismissToast" aria-label="Dismiss">×</button></div>`;
}

export function renderDiscover(state) {
  const d = state.discover;
  const all = [...PLUGINS, ...state.plugins.uploaded];
  let body;
  if (d.query.trim()) {
    const found = search(d.query, state.plugins.uploaded);
    body = grid(`${found.length} result${found.length === 1 ? '' : 's'}`, found, state);
  } else if (d.installedOnly) {
    const mine = all.filter(p => state.plugins.mine.includes(p.id));
    const installed = all.filter(p => state.plugins.installed.includes(p.id) && !state.plugins.mine.includes(p.id));
    body = grid('Installed', installed, state) + (mine.length ? grid('Yours', mine, state) : '');
  } else if (state.route.id) {
    const s = SHELVES.find(x => x.id === state.route.id);
    body = grid(s?.title ?? 'Discover', (s ? shelfIds(s, state) : []).map(id => byId(id, state.plugins.uploaded)).filter(Boolean), state, true);
  } else {
    body = SHELVES.map(s => shelf(s, state)).join('');
  }
  const toast = d.toast ? renderToast(d.toast) : '';
  return `<main class="main disc">${header(state)}${body}${toast}${renderCreate(state)}</main>`;
}
