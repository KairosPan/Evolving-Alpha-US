// gravit-ui/js/render/controls.js — the small shared controls: segs, key-value rows, drawer sections
import { esc, attrs, cls } from '../html.js';

export function seg(items, pressed, action) {
  return `<div class="seg">${items.map(it => `<button type="button"${attrs({ class: cls('seg-item', it === pressed && 'pressed'), 'aria-pressed': it === pressed ? 'true' : 'false', 'data-action': action, 'data-value': it })}>${esc(it)}</button>`).join('')}</div>`;
}

export function segLinks(items, current) {
  return `<div class="seg">${items.map(([label, href, key]) => `<a${attrs({ class: cls('seg-item', key === current && 'pressed'), 'aria-current': key === current ? 'page' : null, href })}>${esc(label)}</a>`).join('')}</div>`;
}

export function kv(rows) {
  return `<div class="kv-list">${rows.map(([k, v]) => `<div class="kv"><span class="kv-k">${esc(k)}</span><span class="kv-v">${v}</span></div>`).join('')}</div>`;
}

export function sec(label, lines, html = false) {
  return `<div class="dsec"><div class="dsec-label">${esc(label)}</div>${lines.map(l => `<div class="dsec-line">${html ? l : esc(l)}</div>`).join('')}</div>`;
}
