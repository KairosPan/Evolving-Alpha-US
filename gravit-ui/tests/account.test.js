// gravit-ui/tests/account.test.js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderAccount, renderMemory, renderSettings } from '../js/render/account.js';
import { reducers as R } from '../js/reducers/index.js';
import { seed } from '../js/data/seed.js';

const NOW = new Date(2026, 9, 9, 14, 7).getTime();
const count = (h, re) => (h.match(re) ?? []).length;
const acct = (tab = 'portfolio', s = seed(NOW)) => R.nav(s, { screen: 'account', tab });

test('Portfolio: header with Guard|Beast, Trading on, Settings; the three tabs; net worth, allocation, holdings with tickers', () => {
  const h = renderAccount(acct());
  assert.match(h, /<h1 class="head-title">Account<\/h1>/);
  assert.match(h, /class="seg-item pressed" aria-pressed="true" data-action="setMode" data-value="Guard"/);
  assert.match(h, /Trading on · \$100 a move/);
  assert.match(h, /data-action="openSettings"/);
  assert.match(h, /class="seg-item pressed" aria-current="page" href="#\/account\/portfolio"/);
  assert.match(h, /href="#\/account\/venues"/);
  assert.match(h, /href="#\/account\/memory"/);
  assert.match(h, /class="networth">\$12,480</);
  assert.match(h, /\+\$86 · 0\.7%/);
  assert.equal(count(h, /class="alloc-seg/g), 4);
  assert.equal(count(h, /class="holding"/g), 4);
  assert.match(h, /class="ticker" href="#\/markets\/BTC"/);
  assert.match(h, /class="up">\+1\.2%</);
  assert.match(h, /class="down">−0\.4%</);
  assert.doesNotMatch(h, /embedded same-origin/);
});

test('Venues: four venues with their state chips and Connect an account', () => {
  const h = renderAccount(acct('venues'));
  assert.equal(count(h, /class="venue"/g), 4);
  assert.equal(count(h, /class="chip up">Healthy</g), 3);
  assert.match(h, /class="chip grey">Not served here</);
  assert.match(h, /class="btn-primary" data-action="openPanel" data-panel="connect">Connect an account</);
});

test('Memory: entries grouped with their source and two keys, the add box, where it is used, three switches, Export and Forget all', () => {
  const s = acct('memory');
  const h = renderAccount(s);
  assert.match(h, /class="seg-item pressed" aria-current="page" href="#\/account\/memory"/);
  const m = renderMemory(s);
  assert.deepEqual([...m.matchAll(/class="mem-label">([^<]+)</g)].map(x => x[1]), ['Style', 'Rules', 'Venues and people']);
  assert.equal(count(m, /class="mem-entry"/g), 9);
  assert.match(m, /class="mem-text">Value over hype<\/div><div class="mem-source">You said · Oct 2</);
  assert.equal(count(m, /data-action="editMemory" data-id="mem-\d+"/g), 9);
  assert.equal(count(m, /data-action="forgetMemory" data-id="mem-\d+"/g), 9);
  assert.match(m, /<form class="mem-add" data-action="addMemory">/);
  assert.match(m, /placeholder="Add something it should remember…"/);
  assert.match(m, /class="chip grey">Discover</);
  assert.match(m, /role="switch" aria-checked="true" data-action="memorySwitch" data-key="remember"/);
  assert.match(m, /role="switch" aria-checked="false" data-action="memorySwitch" data-key="askFirst"/);
  assert.match(m, /data-key="botsRead"/);
  assert.match(m, /data-action="exportMemory"/);
  assert.match(m, /class="btn-danger" data-action="forgetAll"/);
  assert.doesNotMatch(m, /no recycle bin/);
  assert.doesNotMatch(m, /switch it off and/);
  const empty = renderMemory(R.forgetAll(s));
  assert.equal(count(empty, /class="mem-entry"/g), 0);
  const added = renderMemory(R.addMemory(s, { text: 'No new positions on Fridays', now: NOW }));
  assert.match(added, /class="mem-label">Added by you</);
});

test('Settings drawer: theme seg and Reset demo', () => {
  const s = R.openSettings(acct());
  const h = renderAccount(s);
  assert.match(h, /<main class="main acct with-drawer">/);
  const d = renderSettings(s);
  assert.match(d, /<aside class="drawer" aria-label="Settings">/);
  assert.match(d, /class="seg-item pressed" aria-pressed="true" data-action="setTheme" data-value="System"/);
  assert.match(d, /data-action="setTheme" data-value="Black"/);
  assert.match(d, /class="btn-danger" data-action="resetDemo"/);
  const black = renderSettings(R.setTheme(s, 'black'));
  assert.match(black, /class="seg-item pressed" aria-pressed="true" data-action="setTheme" data-value="Black"/);
});
