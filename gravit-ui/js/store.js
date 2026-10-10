// gravit-ui/js/store.js — one state object, pure reducers, subscribers, optional persistence
// accept(saved) decides whether a saved state may be used; a refused one boots `initial`.
// persist(state) is what gets written: the app strips what must never reach storage (a typed key, a moment's overlay).
export function createStore({ initial, reducers, storage = null, key = 'gravit-ui.state', accept = () => true, persist = s => s }) {
  let state = load() ?? initial;
  const subs = new Set();

  function load() {
    try {
      const raw = storage?.getItem(key);
      const saved = raw ? JSON.parse(raw) : null;
      return saved && accept(saved) ? saved : null;
    } catch {
      return null;
    }
  }
  function save() {
    try { storage?.setItem(key, JSON.stringify(persist(state))); } catch { /* storage may be unavailable: the demo still runs */ }
  }
  function notify(type) {
    for (const fn of subs) fn(state, type);
  }

  return {
    get: () => state,
    dispatch(type, payload) {
      const reducer = reducers[type];
      if (!reducer) throw new Error('unknown action ' + type);
      const next = reducer(state, payload);
      if (next && next !== state) {
        state = next;
        save();
        notify(type);
      }
      return state;
    },
    subscribe(fn) {
      subs.add(fn);
      return () => subs.delete(fn);
    },
    reset(next) {
      state = next;
      save();
      notify('reset');
    },
  };
}
