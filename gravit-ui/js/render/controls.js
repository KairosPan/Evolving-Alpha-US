// gravit-ui/js/render/controls.js — the small shared controls: segs, key-value rows, drawer sections, inline editors, two-step confirms
import { esc, attrs, cls } from '../html.js';
import { icon } from '../icons.js';

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

// an inline editor: its inputs, a ✓ that commits and a × that cancels (app.js reads every [name] inside .inline-edit)
// fields: { name, value, type = 'text' | 'number', label, word?, options? } — a word is the box's visible name, the label its full
// accessible name (it contains the word); options make a pick list
export function inlineEdit(fields, error = null) {
  const input = f => {
    const named = { 'aria-label': f.label };
    const box = f.options
      ? `<select${attrs({ id: `edit-${f.name}`, class: 'input small', name: f.name, ...named })}>${f.options.map(o => `<option${attrs({ value: o, selected: o === f.value })}>${esc(o)}</option>`).join('')}</select>`
      : `<input${attrs({ id: `edit-${f.name}`, class: 'input small', name: f.name, type: f.type ?? 'text', value: f.value, ...named })}>`;
    return (f.word ? `<label class="edit-word" for="edit-${esc(f.name)}">${esc(f.word)}</label>` : '') + box;
  };
  return `<span class="inline-edit">${fields.map(input).join('')}` +
    `<button type="button" class="key yes" data-action="commitEdit" aria-label="Save">${icon('check', 14, 2.4)}</button>` +
    `<button type="button" class="key no" data-action="cancelEdit" aria-label="Cancel">${icon('x', 14, 2.4)}</button>` +
    `${error ? `<span class="field-error">${esc(error)}</span>` : ''}</span>`;
}

// the second step of a confirm, in place of the button that asked
export function confirmPair(label) {
  return `<span class="confirm"><button type="button" class="btn-danger" data-action="confirmYes">${esc(label)}</button><button type="button" class="btn-sm" data-action="cancelConfirm">No</button></span>`;
}
