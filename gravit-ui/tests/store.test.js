// gravit-ui/tests/store.test.js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createStore } from '../js/store.js';
import { levelOf, needsAnswer, message, LEVELS } from '../js/messages.js';

function fakeStorage(initial = {}) {
  const m = new Map(Object.entries(initial));
  return { getItem: k => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), map: m };
}

const reducers = {
  inc: (s, n = 1) => ({ ...s, n: s.n + n }),
  same: s => s,
};

test('dispatch runs the reducer, notifies subscribers, persists', () => {
  const storage = fakeStorage();
  const store = createStore({ initial: { n: 0 }, reducers, storage, key: 'k' });
  const seen = [];
  const off = store.subscribe((s, type) => seen.push([s.n, type]));
  store.dispatch('inc', 2);
  assert.equal(store.get().n, 2);
  assert.deepEqual(seen, [[2, 'inc']]);
  assert.equal(storage.getItem('k'), '{"n":2}');
  store.dispatch('same');
  assert.equal(seen.length, 1, 'an unchanged state does not notify');
  off();
  store.dispatch('inc');
  assert.equal(seen.length, 1);
  assert.throws(() => store.dispatch('nope'), /unknown action nope/);
});

test('a saved state is loaded; a corrupt one falls back to the initial', () => {
  const good = createStore({ initial: { n: 0 }, reducers, storage: fakeStorage({ k: '{"n":7}' }), key: 'k' });
  assert.equal(good.get().n, 7);
  const bad = createStore({ initial: { n: 0 }, reducers, storage: fakeStorage({ k: '{not json' }), key: 'k' });
  assert.equal(bad.get().n, 0);
  const none = createStore({ initial: { n: 5 }, reducers });
  assert.equal(none.get().n, 5);
});

test('reset replaces the state and notifies with type reset', () => {
  const store = createStore({ initial: { n: 1 }, reducers });
  let last;
  store.subscribe((s, type) => (last = [s.n, type]));
  store.reset({ n: 9 });
  assert.deepEqual(last, [9, 'reset']);
});

test('the message model: levels by kind, what needs an answer', () => {
  assert.equal(levelOf(message('gravit', 'text', 'hi')), 'grey');
  assert.equal(levelOf(message('gravit', 'card', 'x')), 'orange');
  assert.equal(levelOf(message('gravit', 'refusal', 'x')), 'red');
  assert.equal(levelOf(message('gravit', 'receipt', 'x')), 'green');
  assert.equal(levelOf(message('gravit', 'brief', 'x')), 'white');
  assert.equal(LEVELS.call, 'red');
  assert.equal(needsAnswer(message('gravit', 'card', 'x')), true);
  assert.equal(needsAnswer({ ...message('gravit', 'card', 'x'), answer: 'approved' }), false);
  assert.equal(needsAnswer(message('gravit', 'text', 'x')), false);
  assert.deepEqual(message('you', 'text', 'hi'), { from: 'you', kind: 'text', text: 'hi', data: {} });
});
