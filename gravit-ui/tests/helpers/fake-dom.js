// gravit-ui/tests/helpers/fake-dom.js — just enough of a window and document to run boot() under node:test.
// It does not parse HTML. Elements are registered by id or by selector and persist across renders; each
// innerHTML write behaves like the browser replacing the nodes: scroll positions go to 0, typed values go
// back to what the markup says, and focus falls to <body>. That is what the app has to repair after a render.

export function fakeWindow({ hash = '#/messages/c-1', storage = null, prompt = () => null, confirm = () => true } = {}) {
  const byId = new Map();
  const bySelector = new Map();
  const listeners = { root: {}, doc: {}, win: {} };
  const revoked = [];
  const body = element({ tagName: 'BODY' });
  let writes = 0;
  let html = '';

  function element(props = {}) {
    const el = {
      id: '', tagName: 'DIV', value: '', rendered: '', dataset: {}, attributes: {}, checked: false, name: '',
      scrollTop: 0, scrollLeft: 0, scrollHeight: 1000, clientHeight: 400,
      selectionStart: 0, selectionEnd: 0, textContent: '',
      focus() { doc.activeElement = el; },
      setSelectionRange(a, b) { el.selectionStart = a; el.selectionEnd = b; },
      getAttribute(n) { return el.attributes[n] ?? null; },
      closest(sel) { return el.closestMap?.[sel] ?? null; },
      click() { el.clicks = (el.clicks ?? 0) + 1; },
      ...props,
    };
    return el;
  }

  const root = {
    id: 'app',
    get innerHTML() { return html; },
    set innerHTML(v) {
      html = v;
      writes++;
      for (const el of [...byId.values(), ...[...bySelector.values()].flat()]) {
        el.scrollTop = 0;
        el.scrollLeft = 0;
        el.value = el.rendered;
      }
      doc.activeElement = body;
    },
    querySelectorAll(sel) { return bySelector.get(sel) ?? (sel.includes('input[id]') ? [...byId.values()].filter(e => e.tagName === 'INPUT' || e.tagName === 'TEXTAREA') : []); },
    querySelector(sel) { return (bySelector.get(sel) ?? [])[0] ?? null; },
    addEventListener(type, fn) { (listeners.root[type] ??= []).push(fn); },
  };

  const doc = {
    activeElement: body,
    documentElement: { dataset: {} },
    getElementById(id) { return id === 'app' ? root : byId.get(id) ?? null; },
    addEventListener(type, fn) { (listeners.doc[type] ??= []).push(fn); },
    createElement() { return element({ tagName: 'A' }); },
  };

  let currentHash = hash;
  const win = {
    document: doc,
    localStorage: storage,
    location: {
      get hash() { return currentHash; },
      set hash(v) { currentHash = v; queueMicrotask(() => (listeners.win.hashchange ?? []).forEach(fn => fn())); },
    },
    history: { replaceState(_s, _t, h) { currentHash = h; } },
    addEventListener(type, fn) { (listeners.win[type] ??= []).push(fn); },
    prompt, confirm,
    Blob: class { constructor(parts, opts) { this.parts = parts; this.type = opts?.type; } },
    URL: { createObjectURL: () => 'blob:fake', revokeObjectURL: url => revoked.push(url) },
    FormData: class { constructor(form) { this.form = form; } get(k) { return this.form.fields?.[k] ?? null; } },
  };

  return {
    win, doc, root, body, revoked,
    get writes() { return writes; },
    element,
    // register an element the app will look up by id, or by an exact selector
    withId(id, props = {}) { const el = element({ id, ...props }); byId.set(id, el); return el; },
    withSelector(sel, props = {}) { const el = element(props); bySelector.set(sel, [...(bySelector.get(sel) ?? []), el]); return el; },
    fire(target, type, event = {}) { for (const fn of listeners[target][type] ?? []) fn({ preventDefault() {}, ...event }); },
    // a click on an element carrying data-action, the way delegation finds it
    click(el) { this.fire('root', 'click', { target: { closest: () => el } }); },
    tick: () => new Promise(r => setTimeout(r, 0)),
  };
}
