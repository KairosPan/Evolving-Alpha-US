// gravit-ui/tests/css.test.js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { renderRail } from '../js/render/rail.js';
import { renderMessagesScreen, renderBanner, renderCall, renderStub } from '../js/render/messages.js';
import { renderDiscover } from '../js/render/discover.js';
import { renderAccount } from '../js/render/account.js';
import { director } from '../js/driver.js';
import { reducers as R } from '../js/reducers/index.js';
import { seed } from '../js/data/seed.js';

const NOW = new Date(2026, 9, 9, 14, 7).getTime();

function everyState() {
  const s = seed(NOW);
  const withEvents = ['brief', 'ta'].reduce((st, k) => R.append(st, { convId: 'c-1', msg: director[k](NOW), at: NOW }), s);
  const withMore = ['breaking', 'call'].reduce((st, k) => R.append(st, { convId: 'c-1', msg: { from: 'gravit', kind: k, text: 'x', data: k === 'breaking' ? director.breaking(NOW) : { about: 'x' }, answer: k === 'call' ? 'missed' : undefined }, at: NOW }), withEvents);
  return [
    withMore, R.toggleDetails(s), R.nav(s, { screen: 'messages', id: 'c-4' }), R.startDraft(s, { now: NOW }), R.toggleDraftGroup(R.startDraft(s, { now: NOW })), { ...s, conversations: [], route: { screen: 'messages', id: null } },
    R.nav(s, { screen: 'discover', id: null }), R.openPlugin(R.nav(s, { screen: 'discover', id: null }), 'news'), R.openUpload(s), R.toggleInstalledOnly(R.install(s, { id: 'news', now: NOW })), R.setQuery(s, 'bot'), R.nav(s, { screen: 'discover', id: 'bots' }),
    R.nav(s, { screen: 'account', tab: 'portfolio' }), R.nav(s, { screen: 'account', tab: 'venues' }), R.nav(s, { screen: 'account', tab: 'memory' }), R.openSettings(R.nav(s, { screen: 'account', tab: 'portfolio' })),
  ];
}

test('every class the screens emit has a rule in app.css, and app.css names no colour by hex', async () => {
  const css = await readFile(new URL('../css/app.css', import.meta.url), 'utf8');
  assert.doesNotMatch(css, /#[0-9a-fA-F]{3,6}\b/, 'colours come from tokens.css');
  const html = everyState().map(st => renderRail(st, NOW) + (st.route.screen === 'discover' ? renderDiscover(st) : st.route.screen === 'account' ? renderAccount(st) : renderMessagesScreen(st, NOW))).join('')
    + renderBanner(director.breaking(NOW), seed(NOW)) + renderCall(director.call()) + renderStub({ screen: 'markets', id: 'NVDA' });
  const classes = new Set(html.match(/class="([^"]+)"/g).flatMap(m => m.slice(7, -1).split(/\s+/)));
  const missing = [...classes].filter(c => c && !new RegExp(`\\.${c.replace(/[-]/g, '\\-')}(?![\\w-])`).test(css));
  assert.deepEqual(missing, [], 'classes without a rule');
  assert.match(css, /--rail/);
  assert.match(css, /\.key\.yes[^{]*\{[^}]*color: var\(--up\)/);
  assert.match(css, /\.key\.no[^{]*\{[^}]*color: var\(--down\)/);
});
