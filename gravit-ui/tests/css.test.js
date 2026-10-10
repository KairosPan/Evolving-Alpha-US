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

const D = { screen: 'discover', id: null };

function everyState() {
  const s = seed(NOW);
  const withEvents = ['brief', 'ta'].reduce((st, k) => R.append(st, { convId: 'c-1', msg: director[k](NOW), at: NOW }), s);
  const withMore = ['breaking', 'call'].reduce((st, k) => R.append(st, { convId: 'c-1', msg: { from: 'gravit', kind: k, text: 'x', data: k === 'breaking' ? director.breaking(NOW) : { about: 'x' }, answer: k === 'call' ? 'missed' : undefined }, at: NOW }), withEvents);
  return [
    withMore, R.toggleDetails(s), R.nav(s, { screen: 'messages', id: 'c-4' }), R.startDraft(s, { now: NOW }), R.toggleDraftGroup(R.startDraft(s, { now: NOW })), { ...s, conversations: [], route: { screen: 'messages', id: null } },
    R.nav(s, { screen: 'discover', id: null }), R.openPlugin(R.nav(s, { screen: 'discover', id: null }), 'news'), R.openCreate(R.nav(s, D)), R.setCreateField(R.openCreate(R.nav(s, D)), { key: 'auth', value: 'OAuth' }), R.connectMcp(R.setCreateField(R.openCreate(R.nav(s, D)), { key: 'url', value: 'bad' })), R.mcpConnected(R.connectMcp(R.setCreateField(R.openCreate(R.nav(s, D)), { key: 'url', value: 'https://a.dev/mcp' })), { tools: ['a.run'] }), R.connectMcp(R.setCreateField(R.openCreate(R.nav(s, D)), { key: 'url', value: 'https://a.dev/mcp' })), R.nav(R.toggleInstalledOnly(R.install(s, { id: 'news', now: NOW })), D), R.nav(R.setQuery(s, 'bot'), D), R.nav(s, { screen: 'discover', id: 'bots' }),
    R.nav(R.showBanner(s, director.breaking(NOW)), { screen: 'markets', id: 'NVDA' }), R.nav(s, { screen: 'trade' }),
    R.toggleDraftBot(R.toggleDraftPicker(R.startDraft(s, { now: NOW })), 'buffett'),
    ['refusal', 'done'].reduce((st, k) => R.append(st, { convId: 'c-1', msg: director[k](NOW), at: NOW }), s),
    R.nav(s, { screen: 'account', tab: 'portfolio' }), R.nav(s, { screen: 'account', tab: 'venues' }), R.nav(s, { screen: 'account', tab: 'memory' }), R.openSettings(R.nav(s, { screen: 'account', tab: 'portfolio' })),
  ];
}

test('every class the screens emit has a rule in app.css, and app.css names no colour by hex', async () => {
  const css = await readFile(new URL('../css/app.css', import.meta.url), 'utf8');
  assert.doesNotMatch(css, /#[0-9a-fA-F]{3,6}\b/, 'colours come from tokens.css');
  const screen = st => st.route.screen === 'discover' ? renderDiscover(st) : st.route.screen === 'account' ? renderAccount(st) : st.route.screen === 'messages' ? renderMessagesScreen(st, NOW) : renderStub(st.route);
  const html = everyState().map(st => renderRail(st, NOW) + screen(st)).join('')
    + renderBanner(director.breaking(NOW), seed(NOW)) + renderCall(director.call()) + renderStub({ screen: 'markets', id: 'NVDA' });
  const classes = new Set(html.match(/class="([^"]+)"/g).flatMap(m => m.slice(7, -1).split(/\s+/)));
  const missing = [...classes].filter(c => c && !new RegExp(`\\.${c.replace(/[-]/g, '\\-')}(?![\\w-])`).test(css));
  assert.deepEqual(missing, [], 'classes without a rule');
  assert.match(css, /--rail/);
  assert.match(css, /\.key\.yes[^{]*\{[^}]*color: var\(--up\)/);
  assert.match(css, /\.key\.no[^{]*\{[^}]*color: var\(--down\)/);
});

test('the layout: one screen tall, the thread scrolls under a pinned composer, the drawer is fixed and the toast sticks to the main column (spec §3.3)', async () => {
  const css = await readFile(new URL('../css/app.css', import.meta.url), 'utf8');
  const rule = sel => css.match(new RegExp(`^${sel.replace(/[.]/g, '\\.')} \\{([^}]*)\\}`, 'm'))?.[1] ?? '';
  assert.match(rule('.main'), /(?:^|;)\s*height: 100vh/, 'a real height, not a minimum');
  assert.match(rule('.thread'), /min-height: 0/);
  assert.match(rule('.rail'), /position: sticky/);
  assert.match(rule('.rail'), /overflow: hidden/, 'the rail never scrolls as a whole: Account stays at the bottom (spec §4)');
  assert.match(rule('.rail-rows'), /overflow-y: auto/);
  assert.match(rule('.director'), /bottom: 88px/, 'the director sits above the composer, clear of the send key');
  assert.match(rule('.drawer'), /position: fixed/);
  assert.match(rule('.toast'), /position: sticky/, 'at the bottom of the main column, whatever the navigation is doing');
  assert.doesNotMatch(css, /\.main\.with-drawer \{ overflow: hidden/, 'the page behind a drawer stays usable');
});

test('narrow windows, the toast under a drawer, and long words that wrap', async () => {
  const css = await readFile(new URL('../css/app.css', import.meta.url), 'utf8');
  const narrow = css.match(/@media \(max-width: 860px\) \{([\s\S]*?)\n\}/)?.[1] ?? '';
  assert.match(narrow, /\.rail, \.rail\.mini \{[^}]*position: static/, 'below 860 px the first level stops being a sticky column, collapsed or not');
  assert.match(narrow, /\.main \{[^}]*height: auto/);
  assert.match(narrow, /\.list \{[^}]*position: static/);
  const z = sel => Number(css.match(new RegExp(`^\\${sel} \\{[^}]*z-index: (\\d+)`, 'm'))?.[1]);
  assert.ok(z('.toast') < z('.drawer'), 'a toast never covers a drawer');
  assert.match(css, /\.bubble, \.card \{[^}]*overflow-wrap: anywhere/, 'a pasted address wraps inside its bubble');
  assert.match(css, /^\.chip \{[^}]*white-space: nowrap/m, 'a chip never breaks one character per line');
  assert.match(css, /^\.pcard-extra \{[^}]*flex-wrap: wrap/m, 'on a narrow shelf card the link drops under the chip');
});

test('the equity blue goes by Linqi\'s own name: no --blue, which his tokens use for the orange RWA colour', async () => {
  const css = await readFile(new URL('../css/app.css', import.meta.url), 'utf8');
  const tokens = await readFile(new URL('../css/tokens.css', import.meta.url), 'utf8');
  assert.doesNotMatch(css, /var\(--blue\)|var\(--on-blue\)/);
  assert.doesNotMatch(tokens, /--blue:|--on-blue:/);
  assert.match(css, /var\(--alloc-equity\)/);
  assert.equal((tokens.match(/--on-equity: #ffffff;/g) ?? []).length, 3, 'white words on the blue, in all three theme blocks');
});
