# Gravit UI (pure front end) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A runnable, clickable front end of the settled Gravit design — Messages, Discover, Account — with scripted data and no back end, so the design can be felt in a browser before any architecture is decided.

**Architecture:** A static site under `gravit-ui/`: one `index.html` shell, Linqi's tokens copied as CSS custom properties, and vanilla ES modules. All state lives in one store (`js/store.js`) fed by pure reducers; every screen is a pure function `render*(state) → html string`; `js/app.js` wires hash routes, event delegation on `data-action` attributes, and the scripted driver's timers. Nothing imports from `demo/`; the port into Linqi's page later is a mounting job, not a rewrite.

**Tech Stack:** HTML, CSS, JavaScript ES modules (no framework, no bundler, no runtime dependencies); Node ≥ 20 for `node --test` and the zero-dependency static server; Google Fonts for Manrope / Noto Sans SC / IBM Plex Mono (system fallbacks when offline).

**Spec:** `docs/superpowers/specs/2026-10-09-demo-v2-gravit-frontend-design.md` (the written form of canvas rows 7–10, <https://claude.ai/artifact/XwsiQ4VTqzfGdtzBi2LWgb>). Section numbers below (§3.1, §6…) cite that spec.

**Workspace:** create the worktree with `superpowers:using-git-worktrees` first — branch `feat/gravit-ui` under `.claude/worktrees/gravit-ui`; never `git switch` in the primary checkout (other sessions share it).

## Global Constraints

- Directory `gravit-ui/` at the repository root; nothing under `demo/` is read, imported or modified (the operator: *"先不管后端架构和 linqi 的仓库"*).
- No runtime dependencies, no build step: `npm start` serves the folder, `npm test` runs `node --test tests/`. `package.json` has `"type": "module"`; Node `>=20`.
- Colours and sizes only from spec §3: tokens by name (`var(--surface)` never `#ffffff` in `app.css`), rail 248, rows 64, avatars 36/28, round keys 32 (call keys 44), composer keys 32/36, drawer 460, radii 10/16/20/pill. The one new token is `--down-edge` (§3.4).
- Screens carry no explanatory small print (spec §10): no helper sentences, no shelf subtitles, no notes under switches. Copy on screens is data and control labels only.
- The iMessage rules (§4–§5): icon-only 32 px round keys with `aria-label`s; ✓ = surface ground + hairline + `--up` glyph, ✗ = surface ground + hairline + `--down` glyph, Install + = `--blue` ground; owner bubbles right/blue, Gravit left/grey; centred time dividers only; sender names only in group chats.
- Discover is free (§7.6): cards carry an author line, never a price.
- Every owner message, approval, grant and install is "a signature" in copy (send key `aria-label="Sign and send"`), but this prototype signs nothing — it is pure front end.
- Commit messages: plain words, no backticks, no `$(`, no parentheses (they are shell in `-m`); one commit per task, `git add` only the task's files.
- Tests are `node:test` + `node:assert/strict`, no DOM: render functions return strings and are asserted as strings.

## Review Focus

1. **Whitespace-only send** — pressing send with an empty or blank composer must do nothing (no empty bubble, no driver reply). Pinned by Task 6 (`send` ignores blank text) and Task 14 (the submit handler returns before dispatching).
2. **Corrupt or stale saved state** — a `localStorage` value that is not JSON, or saved by another version (`v` mismatch), must boot the seed instead of crashing. Pinned by Task 4 (`createStore` falls back on a parse error) and Task 14 (`initialState` discards a state whose `v` differs from `SEED_VERSION`).
3. **A hash that names a missing conversation** — `#/messages/c-99` after a reset must open the first conversation, not a blank main column. Pinned by Task 10 (`currentConversation` falls back) and Task 14 (`parseHash` sends unknown screens to messages).
4. **Answering a card twice** — a double-click on ✓ must not append two "Approved." bubbles or schedule two receipts. Pinned by Task 6 (`answer` is a no-op when `msg.answer` is set) and Task 7 (`followUp` of an answered message is `[]`).
5. **Timers after a reset** — driver replies scheduled before "Reset demo" must not land in the fresh seed. Pinned by Task 14 (`Timers.clear()` before `store.reset`, tested in `scheduleEvents`).

---

## File structure

```
gravit-ui/
  package.json            scripts start/test, type module, engines node>=20
  serve.js                zero-dep static server (127.0.0.1:4830), exports createApp/contentType
  index.html              the shell: fonts, tokens, app.css, #app, theme-before-paint script, app.js
  README.md               how to run, what is scripted, the director keys
  css/tokens.css          Linqi's Cream/Black values as custom properties + --down-edge + --blue
  css/app.css             every class the render modules emit (rail, rows, bubbles, cards, keys, composer, drawer, store, memory, toast, banner, call)
  js/html.js              esc, attrs, cls, money
  js/icons.js             ICONS paths, icon(name, size, sw)
  js/time.js              fmtClock, rowTime, divider, fmtDate, sameDay, MIN/HOUR/DAY
  js/ids.js               nextId(counters, kind) → { id, counters }
  js/store.js             createStore({ initial, reducers, storage, key })
  js/messages.js          LEVELS, levelOf, needsAnswer, message()
  js/data/plugins.js      PLUGINS catalogue, KINDS, SHELVES, byId, search, likeFor
  js/data/seed.js         seed(now) → the initial state; SEED_VERSION
  js/reducers/messages.js nav, toggleRail, setTheme, drafts, send, append, answer, details, stop/withdraw/changeLimit, banner, call
  js/reducers/discover.js setQuery, toggleInstalledOnly, openPlugin, closeDrawer, install, uninstall, openUpload, publish, dismissToast
  js/reducers/account.js  setMode, addMemory, editMemory, forgetMemory, forgetAll, setMemorySwitch, openSettings, closeSettings
  js/reducers/index.js    reducers = { ...messages, ...discover, ...account }
  js/driver.js            replyTo, followUp, teachScript, director (scripted replies and events)
  js/render/avatars.js    avatar(who, size, state), cluster(members, size, state), plugLogo(plugin, size)
  js/render/rail.js       renderRail(state, now)
  js/render/thread.js     renderThread(conv, state, now), renderMessage
  js/render/messages.js   renderMessagesScreen(state, now), currentConversation(state)
  js/render/discover.js   renderDiscover(state)
  js/render/account.js    renderAccount(state)
  js/router.js            parseHash(hash) → route, toHash(route)
  js/app.js               boot(), Timers, render loop, event delegation, director palette, export
  tests/*.test.js         one file per module
```

Interfaces that every task relies on (defined in Task 4–5, repeated here so a task can be read alone):

```js
// state (seed.js)
{ v: 1, theme: 'system'|'cream'|'black', route: { screen: 'messages'|'discover'|'account', id?: string, tab?: 'portfolio'|'venues'|'memory' },
  railCollapsed: boolean, draft: null | { title, attach, limit: { perOrder, total, until, venue } }, detailsOpen: boolean, settingsOpen: boolean,
  counters: { intent, ord, card, pay, ledger, msg, conv, plugin, mem }, conversations: Conversation[],
  discover: { query, installedOnly, drawer: null | pluginId, upload: boolean, toast: null | { text, action?: { label, route } } },
  plugins: { installed: string[], mine: string[], uploaded: Plugin[] },
  memory: { entries: { id, group, text, source, at }[], remember, askFirst, botsRead },
  account: { mode: 'guard'|'beast', netWorth, today, todayPct, alloc: { name, pct, token }[], holdings: { key, name, venue, value, chg }[], venues: { name, line, state }[], wallet: { usdc, chain, address } },
  banner: null | { id, headline, body, at }, call: null | { from, about } }
// Conversation
{ id, title, kind: 'gravit'|'bot'|'group', members: string[], unread: boolean, status: 'working'|'done'|'stopped'|'withdrawn',
  intent: { id, created, until, limit: null | { perOrder, total, spent, venue } }, plugins: string[], messages: Message[] }
// Message
{ id, at, from: 'you'|'gravit'|pluginId|'system', kind: 'text'|'card'|'limit'|'install'|'proposal'|'signal'|'refusal'|'receipt'|'done'|'ta'|'brief'|'breaking'|'call', text, data, answer? }
// driver event
{ delay: ms, msg: Message-without-id-and-at }
```

---

### Task 1: Scaffold — package, static server, shell, tokens

**Files:**
- Create: `gravit-ui/package.json`, `gravit-ui/serve.js`, `gravit-ui/index.html`, `gravit-ui/css/tokens.css`, `gravit-ui/.gitignore`
- Test: `gravit-ui/tests/serve.test.js`

**Interfaces:**
- Produces: `createApp(root) → http.Server`, `contentType(path) → string` from `serve.js`; the CSS custom properties listed in spec §3.1 plus `--down-edge` and `--blue`.

- [ ] **Step 1: Write the failing test**

```js
// gravit-ui/tests/serve.test.js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createApp, contentType } from '../serve.js';

function listen(app) {
  return new Promise(resolve => app.listen(0, '127.0.0.1', () => resolve(app.address().port)));
}

test('contentType maps the files the shell serves', () => {
  assert.equal(contentType('index.html'), 'text/html; charset=utf-8');
  assert.equal(contentType('js/app.js'), 'text/javascript; charset=utf-8');
  assert.equal(contentType('css/app.css'), 'text/css; charset=utf-8');
  assert.equal(contentType('x.bin'), 'application/octet-stream');
});

test('the server serves index.html at / and 404s a missing file', async () => {
  const app = createApp();
  const port = await listen(app);
  try {
    const home = await fetch(`http://127.0.0.1:${port}/`);
    assert.equal(home.status, 200);
    assert.equal(home.headers.get('content-type'), 'text/html; charset=utf-8');
    const body = await home.text();
    assert.match(body, /<title>Gravit<\/title>/);
    assert.match(body, /css\/tokens\.css/);
    const missing = await fetch(`http://127.0.0.1:${port}/nope.js`);
    assert.equal(missing.status, 404);
  } finally {
    app.close();
  }
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd gravit-ui && node --test tests/serve.test.js`
Expected: FAIL — `Cannot find module '../serve.js'`

- [ ] **Step 3: Write the package, the server, the shell and the tokens**

```json
// gravit-ui/package.json
{
  "name": "gravit-ui",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "description": "Demo v2 · Gravit front end: the settled design as a pure front end, scripted data, no back end",
  "scripts": {
    "start": "node serve.js",
    "test": "node --test tests/"
  },
  "engines": { "node": ">=20" }
}
```

```
# gravit-ui/.gitignore
node_modules/
.playwright-mcp/
```

```js
// gravit-ui/serve.js — a zero-dependency static server: `npm start` → http://127.0.0.1:4830/
import { createServer } from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { extname, join, normalize, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = fileURLToPath(new URL('.', import.meta.url));
export const TYPES = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
  '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png', '.woff2': 'font/woff2', '.md': 'text/markdown; charset=utf-8',
};

export function contentType(path) {
  return TYPES[extname(path).toLowerCase()] ?? 'application/octet-stream';
}

export function createApp(root = ROOT) {
  return createServer(async (req, res) => {
    const url = new URL(req.url, 'http://localhost');
    let path = normalize(decodeURIComponent(url.pathname));
    if (path.endsWith(sep) || path.endsWith('/')) path += 'index.html';
    const file = join(root, path);
    if (!file.startsWith(root)) { res.writeHead(403); return res.end(); }
    try {
      const s = await stat(file);
      if (s.isDirectory()) { res.writeHead(302, { location: url.pathname + '/' }); return res.end(); }
      res.writeHead(200, { 'content-type': contentType(file), 'cache-control': 'no-store' });
      res.end(await readFile(file));
    } catch {
      res.writeHead(404, { 'content-type': 'text/plain; charset=utf-8' });
      res.end('not found');
    }
  });
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const port = Number(process.env.PORT || 4830);
  createApp().listen(port, '127.0.0.1', () => console.log(`gravit-ui at http://127.0.0.1:${port}/`));
}
```

```html
<!-- gravit-ui/index.html -->
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Gravit</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=Noto+Sans+SC:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500&display=swap">
<link rel="stylesheet" href="./css/tokens.css">
<link rel="stylesheet" href="./css/app.css">
<script>
  // the theme before the first paint: the saved choice, else the system's own
  try { const t = localStorage.getItem('gravit-ui.theme'); if (t === 'cream' || t === 'black') document.documentElement.dataset.theme = t; } catch {}
</script>
</head>
<body>
<div id="app" class="app"></div>
<script type="module" src="./js/app.js"></script>
</body>
</html>
```

```css
/* gravit-ui/css/tokens.css — Linqi's tokens.css values (demo @ 0ef5131), Cream and Black, plus the one new edge and a name for his equity blue */
:root,
:root[data-theme="cream"] {
  color-scheme: light;
  --bg: #f6f4ef; --surface: #ffffff; --surface-2: #ece8e0; --text: #121417; --dim: #5d5a53;
  --border: #e6e1d7; --card-border: #ece8e0; --rule: #121417; --primary: #121417; --on-primary: #ffffff;
  --warn: #d9741e; --warn-text: #94480c; --warn-fill: #fdf0e3; --warn-edge: #f3d2b4;
  --up: #0d7a52; --up-fill: #e4efe6; --down: #b4441c; --down-fill: #f6e6df;
  /* new: the soft red edge of an urgent card, down at a third on the surface (spec §3.4) */
  --down-edge: #e8c2b4;
  --blue: #3b5bdb; --on-blue: #ffffff;
  --hover: rgba(18, 20, 23, 0.05); --scrim: rgba(18, 20, 23, 0.32);
  --shadow-card: 0 1px 2px rgba(16, 24, 40, 0.06), 0 1px 3px rgba(16, 24, 40, 0.05);
  --shadow-lift: 0 8px 30px rgba(16, 24, 40, 0.1);
  --shadow: 0 16px 48px rgba(16, 24, 40, 0.16);
  --rail-bg: #ffffff;
  --alloc-cash: #c9c3b7; --alloc-stable: #5d5a53; --alloc-crypto: #121417; --alloc-equity: #3b5bdb;
}
:root[data-theme="black"] {
  color-scheme: dark;
  --bg: #0e0f11; --surface: #17191c; --surface-2: #212429; --text: #f2f3f5; --dim: #a3a9b4;
  --border: #2b2e34; --card-border: #25282d; --rule: #f2f3f5; --primary: #f2f3f5; --on-primary: #0e0f11;
  --warn: #f0a040; --warn-text: #f5b866; --warn-fill: #2b2112; --warn-edge: #f0a040;
  --up: #4cc38a; --up-fill: #16301f; --down: #f08a6c; --down-fill: #35201a;
  --down-edge: #f08a6c;
  --blue: #5c7cfa; --on-blue: #ffffff;
  --hover: rgba(242, 243, 245, 0.06); --scrim: rgba(0, 0, 0, 0.6);
  --shadow-card: none; --shadow-lift: none; --shadow: 0 16px 48px rgba(0, 0, 0, 0.55);
  --rail-bg: #12151b;
  --alloc-cash: #4a4e56; --alloc-stable: #a3a9b4; --alloc-crypto: #f2f3f5; --alloc-equity: #5c7cfa;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme]) {
    color-scheme: dark;
    --bg: #0e0f11; --surface: #17191c; --surface-2: #212429; --text: #f2f3f5; --dim: #a3a9b4;
    --border: #2b2e34; --card-border: #25282d; --rule: #f2f3f5; --primary: #f2f3f5; --on-primary: #0e0f11;
    --warn: #f0a040; --warn-text: #f5b866; --warn-fill: #2b2112; --warn-edge: #f0a040;
    --up: #4cc38a; --up-fill: #16301f; --down: #f08a6c; --down-fill: #35201a;
    --down-edge: #f08a6c;
    --blue: #5c7cfa; --on-blue: #ffffff;
    --hover: rgba(242, 243, 245, 0.06); --scrim: rgba(0, 0, 0, 0.6);
    --shadow-card: none; --shadow-lift: none; --shadow: 0 16px 48px rgba(0, 0, 0, 0.55);
    --rail-bg: #12151b;
    --alloc-cash: #4a4e56; --alloc-stable: #a3a9b4; --alloc-crypto: #f2f3f5; --alloc-equity: #5c7cfa;
  }
}
:root {
  --font-sans: "Manrope", "Noto Sans SC", "PingFang SC", "Hiragino Sans GB", "Segoe UI", system-ui, sans-serif;
  --font-mono: "IBM Plex Mono", "SF Mono", Menlo, Consolas, monospace;
  --radius-s: 10px; --radius-m: 16px; --radius-l: 20px; --radius-pill: 999px;
  --rail: 248px;
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd gravit-ui && node --test tests/serve.test.js`
Expected: PASS (2 tests). `app.css` does not exist yet; the shell links it anyway and the test only reads `index.html`.

- [ ] **Step 5: Commit**

```bash
git add gravit-ui/package.json gravit-ui/serve.js gravit-ui/index.html gravit-ui/css/tokens.css gravit-ui/.gitignore gravit-ui/tests/serve.test.js
git commit -m "gravit-ui: scaffold the static shell, the server and the tokens"
```

---

### Task 2: HTML helpers and icons

**Files:**
- Create: `gravit-ui/js/html.js`, `gravit-ui/js/icons.js`
- Test: `gravit-ui/tests/html.test.js`

**Interfaces:**
- Produces: `esc(s)`, `attrs(obj)`, `cls(...names)`, `money(n)` from `html.js`; `ICONS` and `icon(name, size = 22, sw = 2)` from `icons.js`. Every render module uses these and nothing else for markup.

- [ ] **Step 1: Write the failing test**

```js
// gravit-ui/tests/html.test.js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { esc, attrs, cls, money } from '../js/html.js';
import { icon, ICONS } from '../js/icons.js';

test('esc neutralises the five HTML characters', () => {
  assert.equal(esc(`<a href="x">it's & more</a>`), '&lt;a href=&quot;x&quot;&gt;it&#39;s &amp; more&lt;/a&gt;');
  assert.equal(esc(null), '');
  assert.equal(esc(12), '12');
});

test('attrs writes string and boolean attributes and skips null/false', () => {
  assert.equal(attrs({ id: 'say', disabled: true, hidden: false, title: null, 'data-n': 3 }), ' id="say" disabled data-n="3"');
  assert.equal(attrs({ 'aria-label': 'Sign & send' }), ' aria-label="Sign &amp; send"');
});

test('cls joins truthy names', () => {
  assert.equal(cls('row', false, 'current', null, ''), 'row current');
});

test('money formats dollars with grouping and up to two decimals', () => {
  assert.equal(money(12480), '$12,480');
  assert.equal(money(0.1), '$0.10');
  assert.equal(money(3740.5), '$3,740.50');
});

test('icon returns an inline svg, aria-hidden, sized as asked', () => {
  const s = icon('check', 14, 2.4);
  assert.match(s, /^<svg width="14" height="14" viewBox="0 0 24 24"/);
  assert.match(s, /stroke-width="2.4"/);
  assert.match(s, /aria-hidden="true"/);
  assert.match(s, /<path d="M5 12l5 5 9-10">/);
  assert.throws(() => icon('nope'), /unknown icon/);
  for (const name of ['chat', 'plus', 'chevDown', 'chevRight', 'compass', 'markets', 'trade', 'phone', 'phoneOff', 'mail', 'wallet', 'search', 'mic', 'send', 'check', 'x', 'trash', 'shield', 'bars', 'book', 'link', 'plane', 'wave', 'calendar', 'columns', 'arrows', 'flame', 'fileCheck', 'team', 'rewind', 'filter', 'pairs', 'upload', 'pencil', 'bell', 'sigma', 'clock', 'bolt']) {
    assert.ok(ICONS[name], name);
  }
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd gravit-ui && node --test tests/html.test.js`
Expected: FAIL — `Cannot find module '../js/html.js'`

- [ ] **Step 3: Write the helpers**

```js
// gravit-ui/js/html.js — the four helpers every render module uses; render functions return strings
const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

export function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ESC[c]);
}

export function attrs(obj) {
  return Object.entries(obj)
    .filter(([, v]) => v !== false && v != null)
    .map(([k, v]) => (v === true ? ` ${k}` : ` ${k}="${esc(v)}"`))
    .join('');
}

export function cls(...names) {
  return names.filter(Boolean).join(' ');
}

export function money(n) {
  const v = Number(n);
  const fixed = Number.isInteger(v) ? v.toLocaleString('en-US') : v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return '$' + fixed;
}
```

```js
// gravit-ui/js/icons.js — 24-box line icons, the same paths the design boards used
export const ICONS = {
  chat: '<path d="M21 12a8 8 0 0 1-8 8H8l-5 3 1.5-4.5A8 8 0 1 1 21 12z"></path>',
  plus: '<path d="M12 5v14M5 12h14"></path>',
  chevDown: '<path d="M6 9l6 6 6-6"></path>',
  chevRight: '<path d="M9 6l6 6-6 6"></path>',
  compass: '<circle cx="12" cy="12" r="9"></circle><path d="M15.5 8.5l-2 5-5 2 2-5z"></path>',
  markets: '<path d="M4 18l5-6 4 3 7-9"></path>',
  trade: '<path d="M7 7h10M7 12h10M7 17h6"></path>',
  phone: '<path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2"></path>',
  phoneOff: '<path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2"></path><path d="M3 3l18 18"></path>',
  mail: '<rect x="3" y="5" width="18" height="14" rx="2"></rect><path d="M3 7l9 6 9-6"></path>',
  wallet: '<path d="M3 7h15a3 3 0 0 1 3 3v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path><path d="M3 7V6a2 2 0 0 1 2-2h11v3"></path><circle cx="17" cy="14" r="1.2"></circle>',
  search: '<circle cx="11" cy="11" r="7"></circle><path d="M20 20l-3.5-3.5"></path>',
  mic: '<rect x="9" y="3" width="6" height="11" rx="3"></rect><path d="M5 11a7 7 0 0 0 14 0M12 18v3"></path>',
  send: '<path d="M12 19V5M5 12l7-7 7 7"></path>',
  check: '<path d="M5 12l5 5 9-10"></path>',
  x: '<path d="M6 6l12 12M18 6L6 18"></path>',
  trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"></path>',
  shield: '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"></path><path d="M9 12l2 2 4-4"></path>',
  bars: '<path d="M5 20V10M12 20V4M19 20v-7"></path>',
  book: '<path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z"></path><path d="M4 19a2 2 0 0 1 2-2h13"></path>',
  link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"></path><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"></path>',
  plane: '<path d="M21 3L3 10l7 3 3 7z"></path><path d="M10 13l11-10"></path>',
  wave: '<path d="M3 12c2-3 4-3 6 0s4 3 6 0 4-3 6 0"></path><path d="M3 17c2-3 4-3 6 0s4 3 6 0 4-3 6 0"></path>',
  calendar: '<rect x="3" y="5" width="18" height="16" rx="2"></rect><path d="M3 10h18M8 3v4M16 3v4"></path>',
  columns: '<path d="M3 21h18M5 21V10M9 21V10M15 21V10M19 21V10M3 10l9-6 9 6z"></path>',
  arrows: '<path d="M4 8h14l-3-3M20 16H6l3 3"></path>',
  flame: '<path d="M12 3c1 4 5 5 5 10a5 5 0 0 1-10 0c0-2 1-3 2-4 0 2 1 3 2 3 0-3-1-6 1-9z"></path>',
  fileCheck: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"></path><path d="M14 3v5h5M9 14l2 2 4-4"></path>',
  team: '<circle cx="8" cy="9" r="3"></circle><circle cx="16" cy="9" r="3"></circle><path d="M2 20a6 6 0 0 1 12 0M10 20a6 6 0 0 1 12 0"></path>',
  rewind: '<path d="M19 5l-9 7 9 7zM10 5l-9 7 9 7z"></path>',
  filter: '<path d="M3 5h18l-7 8v6l-4-2v-4z"></path>',
  pairs: '<path d="M4 9h16M4 15h16"></path><circle cx="8" cy="9" r="2" fill="currentColor"></circle><circle cx="16" cy="15" r="2" fill="currentColor"></circle>',
  upload: '<path d="M12 16V4M6 10l6-6 6 6"></path><path d="M4 20h16"></path>',
  pencil: '<path d="M4 20l4-1 11-11-3-3L5 16z"></path>',
  bell: '<path d="M6 16V11a6 6 0 0 1 12 0v5l2 2H4z"></path><path d="M10 21h4"></path>',
  sigma: '<path d="M18 5H6l6 7-6 7h12"></path>',
  clock: '<circle cx="12" cy="12" r="9"></circle><path d="M12 7v5l3 2"></path>',
  bolt: '<path d="M13 2L4 14h7l-1 8 9-12h-7z"></path>',
};

export function icon(name, size = 22, sw = 2) {
  const path = ICONS[name];
  if (!path) throw new Error('unknown icon ' + name);
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${sw}" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${path}</svg>`;
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd gravit-ui && node --test tests/html.test.js`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add gravit-ui/js/html.js gravit-ui/js/icons.js gravit-ui/tests/html.test.js
git commit -m "gravit-ui: html helpers and the icon set"
```

---

### Task 3: Time and ids

**Files:**
- Create: `gravit-ui/js/time.js`, `gravit-ui/js/ids.js`
- Test: `gravit-ui/tests/time.test.js`

**Interfaces:**
- Produces: `MIN, HOUR, DAY, fmtClock(ts), sameDay(a, b), dayLabel(ts, now), rowTime(ts, now), divider(ts, prev, now), fmtDate(ts)` from `time.js`; `nextId(counters, kind) → { id, counters }` from `ids.js` with kinds `intent, ord, card, pay, ledger, msg, conv, plugin, mem`.

- [ ] **Step 1: Write the failing test**

```js
// gravit-ui/tests/time.test.js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { MIN, HOUR, DAY, fmtClock, rowTime, divider, fmtDate, sameDay } from '../js/time.js';
import { nextId } from '../js/ids.js';

const NOW = new Date(2026, 9, 9, 14, 7).getTime(); // Oct 9 2026 14:07 local

test('fmtClock is zero-padded 24h', () => {
  assert.equal(fmtClock(new Date(2026, 9, 9, 9, 5).getTime()), '09:05');
  assert.equal(fmtClock(NOW), '14:07');
});

test('rowTime is the clock today, 昨天 yesterday, M/D before', () => {
  assert.equal(rowTime(NOW - 6 * MIN, NOW), '14:01');
  assert.equal(rowTime(NOW - DAY, NOW), '昨天');
  assert.equal(rowTime(NOW - 3 * DAY, NOW), '10/6');
});

test('divider: first of the day carries the day, later ones the clock, none inside 15 minutes', () => {
  const first = NOW - 6 * MIN;
  assert.equal(divider(first, null, NOW), 'Today 14:01');
  assert.equal(divider(first + 3 * MIN, first, NOW), null);
  assert.equal(divider(first + 20 * MIN, first, NOW), '14:21');
  assert.equal(divider(NOW - DAY, null, NOW), '昨天 14:07');
  assert.equal(divider(NOW, NOW - DAY, NOW), 'Today 14:07');
  assert.equal(sameDay(NOW, NOW - DAY), false);
});

test('fmtDate is Mon D', () => {
  assert.equal(fmtDate(NOW), 'Oct 9');
  assert.equal(fmtDate(NOW + 6 * DAY), 'Oct 15');
});

test('nextId formats by kind and never mutates the counters it was given', () => {
  const c0 = { intent: 3 };
  const a = nextId(c0, 'intent');
  assert.equal(a.id, 'intent-0004');
  assert.deepEqual(c0, { intent: 3 });
  const b = nextId(a.counters, 'ord');
  assert.equal(b.id, 'ord-0001');
  assert.equal(nextId(b.counters, 'ledger').id, '#1');
  assert.equal(nextId({ ledger: 41 }, 'ledger').id, '#42');
  assert.equal(nextId({}, 'msg').id, 'm-1');
  assert.equal(nextId({ conv: 4 }, 'conv').id, 'c-5');
  assert.equal(HOUR, 60 * MIN);
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd gravit-ui && node --test tests/time.test.js`
Expected: FAIL — `Cannot find module '../js/time.js'`

- [ ] **Step 3: Write time.js and ids.js**

```js
// gravit-ui/js/time.js — clocks, row times and the centred dividers (spec §5.2)
export const MIN = 60_000;
export const HOUR = 60 * MIN;
export const DAY = 24 * HOUR;
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const pad = n => String(n).padStart(2, '0');

export function fmtClock(ts) {
  const d = new Date(ts);
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function sameDay(a, b) {
  const x = new Date(a), y = new Date(b);
  return x.getFullYear() === y.getFullYear() && x.getMonth() === y.getMonth() && x.getDate() === y.getDate();
}

export function dayLabel(ts, now) {
  if (sameDay(ts, now)) return 'Today';
  if (sameDay(ts, now - DAY)) return '昨天';
  const d = new Date(ts);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

export function rowTime(ts, now) {
  return sameDay(ts, now) ? fmtClock(ts) : dayLabel(ts, now);
}

export function divider(ts, prev, now) {
  if (prev != null && ts - prev < 15 * MIN) return null;
  if (prev == null || !sameDay(ts, prev)) return `${dayLabel(ts, now)} ${fmtClock(ts)}`;
  return fmtClock(ts);
}

export function fmtDate(ts) {
  const d = new Date(ts);
  return `${MONTHS[d.getMonth()]} ${d.getDate()}`;
}
```

```js
// gravit-ui/js/ids.js — the ids the screens show (intent-0003, ord-0001, card-0001, 账本 #41); counters live in state
const FORMATS = {
  intent: ['intent-', 4], ord: ['ord-', 4], card: ['card-', 4], pay: ['pay-', 4],
  ledger: ['#', 0], msg: ['m-', 0], conv: ['c-', 0], plugin: ['p-', 0], mem: ['mem-', 0],
};

export function nextId(counters, kind) {
  const [prefix, width] = FORMATS[kind] ?? [kind + '-', 0];
  const n = (counters[kind] ?? 0) + 1;
  const id = prefix + (width ? String(n).padStart(width, '0') : String(n));
  return { id, counters: { ...counters, [kind]: n } };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd gravit-ui && node --test tests/time.test.js`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add gravit-ui/js/time.js gravit-ui/js/ids.js gravit-ui/tests/time.test.js
git commit -m "gravit-ui: time formatting and id counters"
```

---

### Task 4: The store and the message model

**Files:**
- Create: `gravit-ui/js/store.js`, `gravit-ui/js/messages.js`
- Test: `gravit-ui/tests/store.test.js`

**Interfaces:**
- Produces: `createStore({ initial, reducers, storage = null, key = 'gravit-ui.state' }) → { get(), dispatch(type, payload), subscribe(fn) → unsubscribe, reset(next) }`; reducers are `(state, payload) → state` and must return the same object to signal "nothing changed". From `messages.js`: `LEVELS`, `levelOf(msg)`, `needsAnswer(msg)`, `message(from, kind, text, data)`.

- [ ] **Step 1: Write the failing test**

```js
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd gravit-ui && node --test tests/store.test.js`
Expected: FAIL — `Cannot find module '../js/store.js'`

- [ ] **Step 3: Write store.js and messages.js**

```js
// gravit-ui/js/store.js — one state object, pure reducers, subscribers, optional persistence
export function createStore({ initial, reducers, storage = null, key = 'gravit-ui.state' }) {
  let state = load() ?? initial;
  const subs = new Set();

  function load() {
    try {
      const raw = storage?.getItem(key);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  }
  function save() {
    try { storage?.setItem(key, JSON.stringify(state)); } catch { /* storage may be unavailable: the demo still runs */ }
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
```

```js
// gravit-ui/js/messages.js — the message model: colour is importance (spec §6)
export const LEVELS = {
  text: 'grey', proposal: 'green', signal: 'white', ta: 'white', brief: 'white',
  card: 'orange', limit: 'orange', install: 'orange',
  refusal: 'red', breaking: 'red', call: 'red',
  receipt: 'green', done: 'green',
};

export const levelOf = m => LEVELS[m.kind] ?? 'grey';

export const needsAnswer = m => ['card', 'limit', 'install', 'call'].includes(m.kind) && !m.answer;

export function message(from, kind, text, data = {}) {
  return { from, kind, text, data };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd gravit-ui && node --test tests/store.test.js`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add gravit-ui/js/store.js gravit-ui/js/messages.js gravit-ui/tests/store.test.js
git commit -m "gravit-ui: the store and the message model"
```

---

### Task 5: The data — plugin catalogue and the seed state

**Files:**
- Create: `gravit-ui/js/data/plugins.js`, `gravit-ui/js/data/seed.js`
- Test: `gravit-ui/tests/data.test.js`

**Interfaces:**
- Produces: `PLUGINS`, `KINDS`, `SHELVES`, `byId(id, extra = [])`, `byline(p)`, `search(q, extra = [])`, `likeFor(memory)` from `plugins.js`; `seed(now) → state`, `SEED_VERSION` from `seed.js`. A plugin is `{ id, kind, name, blurb, by, visibility, installs, logo: { type: 'letter'|'glyph'|'portrait', text?, icon?, initials?, tone? }, avatar: null | same shape, asks: string[], writes: string[], never: string[], needs: string, teach: string }`.

- [ ] **Step 1: Write the failing test**

```js
// gravit-ui/tests/data.test.js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { PLUGINS, KINDS, SHELVES, byId, byline, search, likeFor } from '../js/data/plugins.js';
import { seed, SEED_VERSION } from '../js/data/seed.js';
import { MIN, DAY } from '../js/time.js';

test('the catalogue: unique ids, known kinds, every shelf id resolves, Serenity has her line', () => {
  const ids = PLUGINS.map(p => p.id);
  assert.equal(new Set(ids).size, ids.length);
  for (const p of PLUGINS) {
    assert.ok(KINDS.includes(p.kind), p.id);
    assert.ok(['letter', 'glyph', 'portrait'].includes(p.logo.type), p.id);
    assert.ok(p.teach.length > 0, p.id);
  }
  for (const s of SHELVES.filter(s => s.id !== 'like')) for (const id of s.ids) assert.ok(byId(id), id);
  assert.equal(byId('serenity').blurb, '科技产业链分析');
  assert.equal(byline(byId('buffett')), 'Free · by Gravit');
  assert.equal(byline(byId('pairs')), 'Free · by @you · Private');
  assert.equal(byId('nope'), null);
  assert.equal(byId('p-1', [{ id: 'p-1', name: 'Mine' }]).name, 'Mine');
});

test('search matches name, blurb and kind, case-insensitively; blank query is empty', () => {
  assert.deepEqual(search('buffett').map(p => p.id), ['buffett']);
  assert.ok(search('骗子').some(p => p.id === 'fraud'));
  assert.ok(search('quant').length >= 3);
  assert.deepEqual(search('   '), []);
});

test('likeFor reads the style out of Memory', () => {
  assert.deepEqual(likeFor({ entries: [{ text: '偏价值，不追热点' }] }), ['buffett', 'research', 'politician', 'quantteam']);
  assert.equal(likeFor({ entries: [{ text: '我做高频' }] })[0], 'hft');
  assert.equal(likeFor({ entries: [{ text: '想试试量化' }] })[0], 'quantteam');
  assert.equal(likeFor({ entries: [] })[0], 'buffett');
});

test('seed: four conversations shaped as the boards, memory, account, counters', () => {
  const now = new Date(2026, 9, 9, 14, 7).getTime();
  const s = seed(now);
  assert.equal(s.v, SEED_VERSION);
  assert.equal(s.conversations.length, 4);
  const [btc, pelosi, addr, group] = s.conversations;
  assert.equal(btc.id, 'c-1');
  assert.equal(btc.title, '小仓位 BTC，$70k 以下');
  assert.equal(btc.intent.id, 'intent-0003');
  assert.deepEqual(btc.intent.limit, { perOrder: 25, total: 100, spent: 5, venue: 'Stand-in Exchange' });
  assert.equal(btc.messages[0].from, 'you');
  assert.equal(btc.messages[0].at, now - 6 * MIN);
  assert.equal(btc.messages.at(-1).at, now);
  assert.equal(btc.messages.find(m => m.kind === 'card').answer, 'approved');
  assert.equal(btc.messages.at(-1).kind, 'install');
  assert.equal(pelosi.kind, 'bot');
  assert.equal(pelosi.unread, true);
  assert.equal(pelosi.messages.at(-1).from, 'politician');
  assert.ok(addr.messages[0].at < now - DAY + 60 * MIN);
  assert.equal(group.kind, 'group');
  assert.deepEqual(group.members, ['gravit', 'politician', 'buffett']);
  const ids = s.conversations.flatMap(c => c.messages.map(m => m.id));
  assert.equal(new Set(ids).size, ids.length, 'message ids are unique');
  assert.ok(ids.every(id => /^m-\d+$/.test(id)));
  assert.equal(s.counters.msg, ids.length);
  assert.equal(s.counters.conv, 4);
  assert.equal(s.memory.entries.length, 9);
  assert.deepEqual(s.memory.entries.map(e => e.group).filter((g, i, a) => a.indexOf(g) === i), ['风格', '规矩', '场所和人']);
  assert.deepEqual(s.plugins.installed, ['pricefeed', 'fraud', 'politician', 'buffett', 'pairs']);
  assert.deepEqual(s.plugins.mine, ['pairs']);
  assert.equal(s.account.netWorth, 12480);
  assert.equal(s.account.holdings.length, 3);
  assert.equal(s.route.id, 'c-1');
  assert.equal(s.draft, null);
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd gravit-ui && node --test tests/data.test.js`
Expected: FAIL — `Cannot find module '../js/data/plugins.js'`

- [ ] **Step 3: Write the catalogue and the seed**

```js
// gravit-ui/js/data/plugins.js — the catalogue Discover sells (all free, spec §7) and its shelves
export const KINDS = ['Data', 'Monitors', 'Bots', 'Crypto', 'Quant'];

const P = (id, kind, name, blurb, extra = {}) => ({
  id, kind, name, blurb, by: 'Gravit', visibility: 'public', installs: '',
  logo: { type: 'letter', text: name[0].toUpperCase() }, avatar: null,
  asks: [], writes: [], never: ['动钱', '付人', '改额度'], needs: '没有。',
  teach: `你好，我是 ${name}。${blurb}。`,
  ...extra,
});

export const PLUGINS = [
  P('buffett', 'Bots', 'Buffett bot', '只买看得懂的、便宜的，拿很久', {
    logo: { type: 'portrait', initials: 'WB', tone: 'warm' }, avatar: { type: 'portrait', initials: 'WB', tone: 'warm' }, installs: '1.2k',
    asks: ['「这只股便宜吗」', '「巴菲特会买它吗」', '「我仓里哪只不像他会拿的」'],
    writes: ['提议：在你额度里的直接成交，超出的发一张要你答的卡', '每周一一份持仓点评，发进这个会话'],
    needs: '没有。只读 Portfolio 和 Markets。',
    teach: '你好，我是 Buffett bot。三件我会做的事：看一只股贵不贵；每周一点评你的仓；在你额度里替你买便宜的好公司。先问你一个问题：你能拿多久？' }),
  P('research', 'Data', '研报', '券商研报摘成三句，按 ticker 问', { logo: { type: 'glyph', icon: 'book' }, asks: ['「NVDA 最近的研报怎么说」', '「谁在看多 KO」'], writes: ['三句摘要和出处，发进会话'] }),
  P('politician', 'Bots', '美国政客 bot', '跟公开披露的国会交易，一笔披露一笔单', {
    logo: { type: 'glyph', icon: 'columns' }, avatar: { type: 'letter', text: 'P', tone: 'blue' }, installs: '3.4k',
    asks: ['「Pelosi 最近买了什么」', '「跟谁的披露」'], writes: ['每条披露一条消息；在你额度里的直接下单，超出的发一张卡'],
    teach: '你好，我是美国政客 bot。国会议员的交易披露一出来我就告诉你，跟不跟按你的额度。先选要跟的人：Pelosi？' }),
  P('quantteam', 'Quant', 'Quant team', '给它一个想法，组一队 agent 回测、挑参数、给结论', { logo: { type: 'glyph', icon: 'team' }, asks: ['「动量在美股过去两年行不行」'], writes: ['一份回测报告发进会话；不下单'] }),
  P('pricefeed', 'Data', 'Price feed', '各场所的 K 线和报价', { logo: { type: 'glyph', icon: 'bars' }, installs: '8.1k', writes: ['K 线和报价，给 Gravit 和技术分析用'] }),
  P('news', 'Data', 'News sentiment', '每个 ticker 一个情绪分', { logo: { type: 'letter', text: 'N' }, asks: ['「BTC 现在情绪怎么样」'], writes: ['一个分数和三条标题'] }),
  P('onchain', 'Data', 'On-chain flows', '大额转账、交易所进出', { by: 'community', logo: { type: 'glyph', icon: 'link' } }),
  P('telegram', 'Monitors', 'Telegram monitor', '盯你指定的群聊，摘成信号发进会话', { logo: { type: 'glyph', icon: 'plane' }, avatar: { type: 'letter', text: 'TG', tone: 'grey' }, installs: '2.0k', writes: ['只读的信号消息；不下单'], needs: '你的 Telegram 会话。' }),
  P('xmon', 'Monitors', 'X monitor', '盯几个账号的发帖，摘成一句', { by: '@kol_watch', logo: { type: 'letter', text: 'X' }, writes: ['只读的信号消息；不下单'] }),
  P('whale', 'Monitors', 'Whale alerts', '链上大户动了就说一声', { by: 'community', logo: { type: 'glyph', icon: 'wave' } }),
  P('earnings', 'Monitors', 'Earnings calendar', '你持仓的财报日，提前一天提醒', { logo: { type: 'glyph', icon: 'calendar' } }),
  P('kol', 'Bots', 'KOL bot', '跟一个 KOL 的链上钱包或喊单', { logo: { type: 'letter', text: 'K' }, avatar: { type: 'letter', text: 'K', tone: 'grey' } }),
  P('serenity', 'Bots', 'Serenity bot', '科技产业链分析', { logo: { type: 'portrait', initials: 'S', tone: 'green' }, avatar: { type: 'portrait', initials: 'S', tone: 'green' }, asks: ['「英伟达的上游是谁」'], writes: ['一条产业链图谱和三个结论'] }),
  P('fraud', 'Crypto', '地址欺诈检测', '转账前查收款地址：骗子名单、合约陷阱', { logo: { type: 'glyph', icon: 'shield' }, avatar: { type: 'glyph', icon: 'shield' }, installs: '5.6k', asks: ['「这个地址安全吗」'], writes: ['一条结论：名单、合约、历史'] }),
  P('spread', 'Crypto', '交易所价差', '同一个币在几家的价，差多少', { logo: { type: 'glyph', icon: 'arrows' } }),
  P('gas', 'Crypto', 'Gas 时机', '链上手续费低的时候再动', { by: 'community', logo: { type: 'glyph', icon: 'flame' } }),
  P('audit', 'Crypto', '合约体检', '买之前看合约：能不能卖、税多少', { by: 'community', logo: { type: 'glyph', icon: 'fileCheck' } }),
  P('backtest', 'Quant', 'Backtest', '一个想法在过去两年跑一遍', { logo: { type: 'glyph', icon: 'rewind' } }),
  P('factor', 'Quant', 'Factor screen', '按因子筛一遍股票池', { by: 'community', logo: { type: 'glyph', icon: 'filter' } }),
  P('pairs', 'Quant', 'Pairs', '两只相关股的价差回归，配对信号', { by: '@you', visibility: 'private', logo: { type: 'glyph', icon: 'pairs' } }),
  P('latency', 'Data', 'Low-latency feed', '毫秒级的报价流，给高频用', { logo: { type: 'glyph', icon: 'bolt' } }),
  P('hft', 'Quant', 'HFT strategies', '几套做市和套利的模板，自己调参', { by: 'community', logo: { type: 'glyph', icon: 'sigma' } }),
];

export const SHELVES = [
  { id: 'like', title: 'Like' },
  { id: 'data', title: 'Data', ids: ['pricefeed', 'news', 'research', 'onchain', 'latency'] },
  { id: 'monitors', title: 'Monitors', ids: ['telegram', 'xmon', 'whale', 'earnings'] },
  { id: 'bots', title: 'Bots', ids: ['politician', 'kol', 'buffett', 'serenity'] },
  { id: 'crypto', title: 'Crypto', ids: ['fraud', 'spread', 'gas', 'audit'] },
  { id: 'quant', title: 'Quant', ids: ['quantteam', 'backtest', 'factor', 'pairs', 'hft'] },
];

export function byId(id, extra = []) {
  return PLUGINS.find(p => p.id === id) ?? extra.find(p => p.id === id) ?? null;
}

export function byline(p) {
  return `Free · by ${p.by}` + (p.visibility === 'private' ? ' · Private' : '');
}

export function search(q, extra = []) {
  const s = (q ?? '').trim().toLowerCase();
  if (!s) return [];
  return [...PLUGINS, ...extra].filter(p => `${p.name} ${p.blurb} ${p.kind}`.toLowerCase().includes(s));
}

// the Like shelf: the user's style, read out of Memory (spec §7.2)
export function likeFor(memory) {
  const text = (memory?.entries ?? []).map(e => e.text).join(' ');
  if (/高频/.test(text)) return ['hft', 'latency', 'spread', 'backtest'];
  if (/量化/.test(text)) return ['quantteam', 'backtest', 'factor', 'pairs'];
  return ['buffett', 'research', 'politician', 'quantteam'];
}
```

```js
// gravit-ui/js/data/seed.js — the state the demo boots into: the four conversations of the boards, Memory, the account numbers
import { MIN, DAY } from '../time.js';

export const SEED_VERSION = 1;

const msg = (from, kind, text, data = {}, extra = {}) => ({ from, kind, text, data, ...extra });

export function seed(now = Date.now()) {
  const ago = min => now - min * MIN;
  let n = 0;
  const stamp = (at, m) => ({ id: `m-${++n}`, at, ...m });

  const btc = {
    id: 'c-1', title: '小仓位 BTC，$70k 以下', kind: 'gravit', members: ['gravit'], unread: false, status: 'working',
    intent: { id: 'intent-0003', created: ago(6), until: now + 6 * DAY, limit: { perOrder: 25, total: 100, spent: 5, venue: 'Stand-in Exchange' } },
    plugins: ['pricefeed', 'fraud'],
    messages: [
      stamp(ago(6), msg('you', 'text', '小仓位买 BTC，$70k 以下，一次别超过 $25。')),
      stamp(ago(5.5), msg('gravit', 'text', '收到。看了 Stand-in Exchange 和 Stand-in Wallet 的 DEX，交易所便宜。先建 $5 试水。')),
      stamp(ago(5), msg('gravit', 'card', '要你答：买 0.00008 BTC', { title: '要你答：买 0.00008 BTC', venue: 'Stand-in Exchange', type: 'market', about: 'about $5.00', cardId: 'card-0001', by: now + 26 * MIN }, { answer: 'approved' })),
      stamp(ago(3), msg('you', 'text', 'Approved.')),
      stamp(ago(2.5), msg('gravit', 'receipt', '0.00008 BTC @ 62,500 · ord-0001 · 账本 #41', { status: 'filled' })),
      stamp(ago(2.4), msg('gravit', 'limit', '想再加 $30，但你的每单上限是 $25。改到 $50？', { from: 25, to: 50 })),
      stamp(ago(0), msg('gravit', 'install', 'Discover 里有个 News sentiment。装上我就能看情绪再加仓。', { plugin: 'news' })),
    ],
  };

  const pelosi = {
    id: 'c-2', title: '跟单 Pelosi 的交易', kind: 'bot', members: ['gravit', 'politician'], unread: true, status: 'working',
    intent: { id: 'intent-0002', created: ago(27), until: now + 6 * DAY, limit: { perOrder: 20, total: 100, spent: 20, venue: 'Stand-in Broker' } },
    plugins: ['politician'],
    messages: [
      stamp(ago(27), msg('you', 'text', '跟单 Pelosi 的交易，每笔 $20 以内。')),
      stamp(ago(26.5), msg('gravit', 'text', '好。美国政客 bot 在，披露一出来我就跟，在额度里的直接下单。')),
      stamp(ago(26), msg('politician', 'proposal', '披露：Pelosi 买 NVDA。照它买 $20，在额度里，直接成交。', { status: 'filled', ord: 'ord-0004', venue: 'Stand-in Broker' })),
    ],
  };

  const addr = {
    id: 'c-3', title: '查这个地址是不是骗子', kind: 'gravit', members: ['gravit'], unread: false, status: 'done',
    intent: { id: 'intent-0001', created: now - DAY - 40 * MIN, until: now + 5 * DAY, limit: null },
    plugins: ['fraud'],
    messages: [
      stamp(now - DAY - 40 * MIN, msg('you', 'text', '查这个地址是不是骗子：0x9f3a…c21e')),
      stamp(now - DAY - 39 * MIN, msg('fraud', 'signal', '0x9f3a…c21e · 在 3 份骗子名单里 · 合约可暂停转出', { source: '地址欺诈检测' })),
      stamp(now - DAY - 38 * MIN, msg('gravit', 'alert', '这个地址在骗子名单里，没有转。')),
    ],
  };

  const group = {
    id: 'c-4', title: '跟 Pelosi 和 Buffett 挑股', kind: 'group', members: ['gravit', 'politician', 'buffett'], unread: false, status: 'working',
    intent: { id: 'intent-0004', created: ago(27), until: now + 6 * DAY, limit: { perOrder: 25, total: 50, spent: 25, venue: 'Stand-in Broker' } },
    plugins: ['politician', 'buffett'],
    messages: [
      stamp(ago(27), msg('you', 'text', '两位，$50 以内，今天有什么值得买的？')),
      stamp(ago(26), msg('politician', 'text', '披露：Pelosi 10/7 买 NVDA $1–5M，今天公开。照我的规矩是跟 $25。')),
      stamp(ago(25), msg('buffett', 'text', 'NVDA 市盈率 55，不是我会出的价。KO 更像我的：看得懂、便宜、拿得住。')),
      stamp(ago(24), msg('gravit', 'card', '要你答：两笔，各 $25', { title: '要你答：两笔，各 $25', by: now + 20 * MIN, rows: [{ t: 'NVDA', why: '跟披露 · Stand-in Broker · market', amt: '$25' }, { t: 'KO', why: '照 Buffett · Stand-in Broker · limit 58.20', amt: '$25' }], note: '两条都在额度里。要只要一笔，回我一句就行。' }, { answer: 'approved' })),
      stamp(ago(21), msg('you', 'text', '两笔都要。')),
      stamp(ago(20.5), msg('gravit', 'receipt', 'NVDA $25 @ 187.40 · ord-0009 · 账本 #58', { status: 'filled', more: 'KO 挂着，58.20 还没到。到了我说一声。' })),
    ],
  };

  const mem = (id, group, text, source, daysAgo) => ({ id: `mem-${id}`, group, text, source, at: now - daysAgo * DAY });

  return {
    v: SEED_VERSION,
    theme: 'system',
    route: { screen: 'messages', id: 'c-1' },
    railCollapsed: false,
    draft: null,
    detailsOpen: false,
    settingsOpen: false,
    counters: { intent: 4, ord: 9, card: 1, pay: 7, ledger: 58, msg: n, conv: 4, plugin: 0, mem: 9 },
    conversations: [btc, pelosi, addr, group],
    discover: { query: '', installedOnly: false, drawer: null, upload: false, toast: null },
    plugins: { installed: ['pricefeed', 'fraud', 'politician', 'buffett', 'pairs'], mine: ['pairs'], uploaded: [] },
    memory: {
      entries: [
        mem(1, '风格', '偏价值，不追热点', '你说的', 7), mem(2, '风格', '不碰杠杆', '你说的', 7), mem(3, '风格', '盯科技产业链', '它从你的问题里学的', 3),
        mem(4, '规矩', '每单不超过 $25，真钱先过我', '来自额度', 1), mem(5, '规矩', 'Telegram 群的喊单只看不追', '你说的', 1), mem(6, '规矩', '加仓先问，别自己扩额度', '它从你拒掉的那次学的', 0),
        mem(7, '场所和人', 'BTC 去交易所，比 DEX 便宜', '它自己比出来的', 1), mem(8, '场所和人', '跟 Pelosi 的披露，用 Buffett 的挑法', '来自装的 bot', 0), mem(9, '场所和人', '早报 7:30，CPI 前不动', '你说的', 0),
      ],
      remember: true, askFirst: false, botsRead: false,
    },
    account: {
      mode: 'guard', netWorth: 12480, today: 86, todayPct: 0.7,
      alloc: [{ name: 'Cash', pct: 30, token: 'cash' }, { name: 'Stablecoins', pct: 20, token: 'stable' }, { name: 'Crypto', pct: 30, token: 'crypto' }, { name: 'Stocks', pct: 20, token: 'equity' }],
      holdings: [{ key: 'crypto:BTC', name: 'BTC', venue: 'Stand-in Exchange', value: 3740, chg: 1.2 }, { key: 'equity:AAPL', name: 'AAPL', venue: 'Stand-in Broker', value: 2510, chg: -0.4 }, { key: 'stable:USDC', name: 'USDC', venue: 'Stand-in Wallet', value: 2490, chg: null }],
      venues: [
        { name: 'Stand-in Exchange', line: 'Connected · key file · Gravit may trade', state: 'Healthy' },
        { name: 'Stand-in Broker', line: 'Connected · key file · Gravit may trade', state: 'Healthy' },
        { name: 'Stand-in Wallet', line: 'Connected · address proved · Gravit: read only', state: 'Healthy' },
        { name: 'Kalshi', line: 'Asked it first, without a key', state: 'Not served here' },
      ],
      wallet: { usdc: 12.4, chain: 'Base', address: '0xec4c…16c1' },
    },
    banner: null,
    call: null,
  };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd gravit-ui && node --test tests/data.test.js`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add gravit-ui/js/data/plugins.js gravit-ui/js/data/seed.js gravit-ui/tests/data.test.js
git commit -m "gravit-ui: the plugin catalogue and the seed state"
```

---

### Task 6: The reducers

**Files:**
- Create: `gravit-ui/js/reducers/messages.js`, `gravit-ui/js/reducers/discover.js`, `gravit-ui/js/reducers/account.js`, `gravit-ui/js/reducers/index.js`
- Test: `gravit-ui/tests/reducers.test.js`

**Interfaces:**
- Consumes: `nextId`, `seed`, `byId`, `DAY`.
- Produces: `reducers` (one object, action name → `(state, payload) → state`) and `stampMessage(state, msg, at) → { state, msg }` from `reducers/messages.js`. Actions: `nav(route)`, `toggleRail()`, `setTheme(theme)`, `startDraft({ now })`, `cancelDraft()`, `setDraftTitle(title)`, `setDraftLimit({ key, value })`, `toggleDraftAttach()`, `send({ text, now })`, `append({ convId, msg, at })`, `answer({ convId, msgId, answer, now })`, `toggleDetails()`, `stopGravit({ convId, now })`, `withdraw({ convId, now })`, `changeLimit({ convId, limit })`, `showBanner(banner)`, `dismissBanner()`, `incomingCall(call)`, `answerCall({ accept, now })`, `setQuery(q)`, `toggleInstalledOnly()`, `openPlugin(id)`, `closeDrawer()`, `openUpload()`, `dismissToast()`, `install({ id, now })`, `uninstall(id)`, `publish({ manifest, now })`, `setMode(mode)`, `openSettings()`, `closeSettings()`, `addMemory({ text, now })`, `editMemory({ id, text })`, `forgetMemory(id)`, `forgetAll()`, `setMemorySwitch({ key, value })`.

- [ ] **Step 1: Write the failing test**

```js
// gravit-ui/tests/reducers.test.js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { reducers as R } from '../js/reducers/index.js';
import { seed } from '../js/data/seed.js';
import { MIN } from '../js/time.js';

const NOW = new Date(2026, 9, 9, 14, 7).getTime();
const fresh = () => seed(NOW);
const conv = (s, id) => s.conversations.find(c => c.id === id);

test('nav opens a conversation, clears its unread dot, closes drawers and drops a draft', () => {
  let s = R.startDraft(fresh(), { now: NOW });
  assert.ok(s.draft);
  s = R.nav(s, { screen: 'messages', id: 'c-2' });
  assert.equal(conv(s, 'c-2').unread, false);
  assert.equal(s.draft, null);
  assert.equal(s.detailsOpen, false);
  const same = R.nav(s, { screen: 'discover' });
  assert.equal(same.route.screen, 'discover');
});

test('send: blank text is ignored; otherwise an owner bubble joins the open conversation', () => {
  const s0 = fresh();
  assert.equal(R.send(s0, { text: '   ', now: NOW }), s0);
  const s1 = R.send(s0, { text: ' 再看看 ETH ', now: NOW + MIN });
  const last = conv(s1, 'c-1').messages.at(-1);
  assert.equal(last.from, 'you');
  assert.equal(last.text, '再看看 ETH');
  assert.equal(last.at, NOW + MIN);
  assert.equal(last.id, 'm-' + (s0.counters.msg + 1));
});

test('send from a draft creates the conversation, titled by the draft or the first words, with the attached limit', () => {
  let s = R.startDraft(fresh(), { now: NOW });
  s = R.setDraftTitle(s, '买一点 SOL');
  s = R.setDraftLimit(s, { key: 'perOrder', value: 30 });
  s = R.send(s, { text: '小仓位买 SOL，别超过 $30 一次', now: NOW });
  assert.equal(s.draft, null);
  assert.equal(s.route.id, 'c-5');
  const c = conv(s, 'c-5');
  assert.equal(c.title, '买一点 SOL');
  assert.equal(c.intent.id, 'intent-0005');
  assert.equal(c.intent.limit.perOrder, 30);
  assert.equal(c.messages[0].text, '小仓位买 SOL，别超过 $30 一次');
  assert.equal(s.conversations[0].id, 'c-5', 'the new conversation is first in the list');

  let t = R.startDraft(fresh(), { now: NOW });
  t = R.toggleDraftAttach(t);
  t = R.send(t, { text: '帮我盯一下这个很长很长很长很长很长很长很长很长的事情', now: NOW });
  assert.equal(conv(t, 'c-5').intent.limit, null);
  assert.equal(conv(t, 'c-5').title.length, 25);
  assert.ok(conv(t, 'c-5').title.endsWith('…'));
});

test('append stamps id and time and marks unread only when the conversation is not open', () => {
  const s0 = fresh();
  const s1 = R.append(s0, { convId: 'c-3', msg: { from: 'gravit', kind: 'text', text: 'x', data: {} }, at: NOW });
  assert.equal(conv(s1, 'c-3').unread, true);
  assert.equal(conv(s1, 'c-3').messages.at(-1).at, NOW);
  const s2 = R.append(s0, { convId: 'c-1', msg: { from: 'gravit', kind: 'text', text: 'x', data: {} }, at: NOW });
  assert.equal(conv(s2, 'c-1').unread, false);
  assert.equal(R.append(s0, { convId: 'c-99', msg: { from: 'gravit', kind: 'text', text: 'x', data: {} }, at: NOW }), s0);
});

test('answer records the answer once, adds the owner word, and a grant raises the limit', () => {
  const s0 = fresh();
  const limitMsg = conv(s0, 'c-1').messages.find(m => m.kind === 'limit');
  const s1 = R.answer(s0, { convId: 'c-1', msgId: limitMsg.id, answer: 'granted', now: NOW });
  assert.equal(conv(s1, 'c-1').messages.find(m => m.id === limitMsg.id).answer, 'granted');
  assert.equal(conv(s1, 'c-1').messages.at(-1).text, 'Granted.');
  assert.equal(conv(s1, 'c-1').intent.limit.perOrder, 50);
  assert.equal(R.answer(s1, { convId: 'c-1', msgId: limitMsg.id, answer: 'granted', now: NOW }), s1, 'a second answer is a no-op');
  const installMsg = conv(s0, 'c-1').messages.find(m => m.kind === 'install');
  const s2 = R.answer(s0, { convId: 'c-1', msgId: installMsg.id, answer: 'installed', now: NOW });
  assert.equal(conv(s2, 'c-1').messages.at(-1).kind, 'install', 'installing adds no owner bubble');
});

test('details, stop, withdraw, banner, call', () => {
  let s = R.toggleDetails(fresh());
  assert.equal(s.detailsOpen, true);
  s = R.stopGravit(s, { convId: 'c-1', now: NOW });
  assert.equal(conv(s, 'c-1').status, 'stopped');
  assert.equal(conv(s, 'c-1').messages.at(-1).from, 'system');
  s = R.withdraw(s, { convId: 'c-2', now: NOW });
  assert.equal(conv(s, 'c-2').status, 'withdrawn');
  s = R.changeLimit(s, { convId: 'c-1', limit: { total: 200 } });
  assert.equal(conv(s, 'c-1').intent.limit.total, 200);
  assert.equal(conv(s, 'c-1').intent.limit.perOrder, 25);
  s = R.showBanner(s, { id: 'b1', headline: 'h', body: 'b', at: NOW });
  assert.equal(s.banner.id, 'b1');
  s = R.dismissBanner(s);
  assert.equal(s.banner, null);
  s = R.incomingCall(s, { from: 'gravit', about: '想说 BTC 的事' });
  s = R.answerCall(s, { accept: false, now: NOW });
  assert.equal(s.call, null);
  assert.match(s.conversations[0].messages.at(-1).text, /没接/);
});

test('discover: install adds the plugin, a teaching conversation and a toast; uninstall removes; publish adds a private plugin of yours', () => {
  const s0 = R.openPlugin(fresh(), 'news');
  assert.equal(s0.discover.drawer, 'news');
  const s1 = R.install(s0, { id: 'news', now: NOW });
  assert.ok(s1.plugins.installed.includes('news'));
  assert.equal(s1.discover.drawer, null);
  assert.match(s1.discover.toast.text, /News sentiment 装好了/);
  assert.equal(s1.conversations[0].title, 'News sentiment：怎么用我');
  assert.equal(s1.conversations[0].unread, true);
  assert.equal(s1.conversations[0].members[1], 'news');
  assert.equal(s1.discover.toast.action.route.id, s1.conversations[0].id);
  assert.equal(R.install(s1, { id: 'news', now: NOW }), s1, 'installing twice is a no-op');
  const s2 = R.uninstall(s1, 'news');
  assert.ok(!s2.plugins.installed.includes('news'));
  assert.equal(s2.conversations[0].title, 'News sentiment：怎么用我', 'the conversation stays');
  const s3 = R.publish(R.openUpload(s2), { manifest: { name: 'Pairs 2', blurb: '价差', kind: 'Quant', tools: 'pairs2.scan', needs: '没有。', visibility: 'private' }, now: NOW });
  assert.equal(s3.discover.upload, false);
  assert.equal(s3.plugins.uploaded[0].id, 'p-1');
  assert.ok(s3.plugins.mine.includes('p-1'));
  assert.ok(s3.plugins.installed.includes('p-1'));
  assert.equal(R.publish(s3, { manifest: { name: '  ', blurb: '', kind: 'Quant', tools: '', needs: '', visibility: 'private' }, now: NOW }), s3);
  const s4 = R.setQuery(R.toggleInstalledOnly(s3), 'bot');
  assert.equal(s4.discover.installedOnly, true);
  assert.equal(s4.discover.query, 'bot');
  assert.equal(R.dismissToast(s4).discover.toast, null);
});

test('account: mode, memory add/edit/forget/forget all, switches, settings', () => {
  let s = R.setMode(fresh(), 'beast');
  assert.equal(s.account.mode, 'beast');
  assert.equal(R.addMemory(s, { text: '  ', now: NOW }), s);
  s = R.addMemory(s, { text: '周五不开新仓', now: NOW });
  const added = s.memory.entries.at(-1);
  assert.equal(added.id, 'mem-10');
  assert.equal(added.source, '你说的');
  s = R.editMemory(s, { id: 'mem-10', text: '周五不开新仓，周一也不' });
  assert.equal(s.memory.entries.at(-1).text, '周五不开新仓，周一也不');
  s = R.forgetMemory(s, 'mem-1');
  assert.equal(s.memory.entries.length, 9);
  s = R.setMemorySwitch(s, { key: 'askFirst', value: true });
  assert.equal(s.memory.askFirst, true);
  s = R.forgetAll(s);
  assert.deepEqual(s.memory.entries, []);
  s = R.openSettings(s);
  assert.equal(s.settingsOpen, true);
  assert.equal(R.closeSettings(s).settingsOpen, false);
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd gravit-ui && node --test tests/reducers.test.js`
Expected: FAIL — `Cannot find module '../js/reducers/index.js'`

- [ ] **Step 3: Write the reducers**

```js
// gravit-ui/js/reducers/messages.js — the conversation side: routes, drafts, sending, answering, details, banners, calls
import { nextId } from '../ids.js';
import { DAY } from '../time.js';

const upd = (state, id, fn) => ({ ...state, conversations: state.conversations.map(c => (c.id === id ? fn(c) : c)) });
const push = (state, convId, msg) => upd(state, convId, c => ({ ...c, messages: [...c.messages, msg] }));

export function stampMessage(state, msg, at) {
  const { id, counters } = nextId(state.counters, 'msg');
  return { state: { ...state, counters }, msg: { ...msg, id, at } };
}

function newConversation(state, { title, kind, members, intentLimit, until, plugins, now }) {
  const c1 = nextId(state.counters, 'conv');
  const c2 = nextId(c1.counters, 'intent');
  const conv = {
    id: c1.id, title, kind, members, unread: false, status: 'working',
    intent: { id: c2.id, created: now, until, limit: intentLimit }, plugins, messages: [],
  };
  return { state: { ...state, counters: c2.counters, conversations: [conv, ...state.conversations] }, conv };
}

export const reducers = {
  nav(state, route) {
    let s = { ...state, route, detailsOpen: false, settingsOpen: false };
    if (route.screen === 'messages' && route.id && route.id !== 'new') s = upd(s, route.id, c => (c.unread ? { ...c, unread: false } : c));
    if (!(route.screen === 'messages' && route.id === 'new')) s.draft = null;
    return s;
  },
  toggleRail: s => ({ ...s, railCollapsed: !s.railCollapsed }),
  setTheme: (s, theme) => ({ ...s, theme }),

  startDraft(s, { now }) {
    return { ...s, draft: { title: '', attach: true, limit: { perOrder: 25, total: 100, until: now + 6 * DAY, venue: 'Stand-in Exchange' } }, route: { screen: 'messages', id: 'new' }, detailsOpen: false };
  },
  cancelDraft: s => ({ ...s, draft: null, route: { screen: 'messages', id: s.conversations[0]?.id } }),
  setDraftTitle: (s, title) => (s.draft ? { ...s, draft: { ...s.draft, title } } : s),
  setDraftLimit: (s, { key, value }) => (s.draft ? { ...s, draft: { ...s.draft, limit: { ...s.draft.limit, [key]: value } } } : s),
  toggleDraftAttach: s => (s.draft ? { ...s, draft: { ...s.draft, attach: !s.draft.attach } } : s),

  send(state, { text, now }) {
    const clean = (text ?? '').trim();
    if (!clean) return state;
    let s = state;
    let convId = s.route.screen === 'messages' ? s.route.id : null;
    if (s.draft || !s.conversations.some(c => c.id === convId)) {
      const d = s.draft ?? { title: '', attach: false, limit: null };
      const made = newConversation(s, {
        title: d.title.trim() || (clean.length > 24 ? clean.slice(0, 24) + '…' : clean),
        kind: 'gravit', members: ['gravit'], plugins: [], now,
        until: d.limit?.until ?? now + 6 * DAY,
        intentLimit: d.attach && d.limit ? { perOrder: d.limit.perOrder, total: d.limit.total, spent: 0, venue: d.limit.venue } : null,
      });
      s = { ...made.state, draft: null, route: { screen: 'messages', id: made.conv.id } };
      convId = made.conv.id;
    }
    const st = stampMessage(s, { from: 'you', kind: 'text', text: clean, data: {} }, now);
    return push(st.state, convId, st.msg);
  },

  append(state, { convId, msg, at }) {
    if (!state.conversations.some(c => c.id === convId)) return state;
    const st = stampMessage(state, msg, at);
    const open = state.route.screen === 'messages' && state.route.id === convId;
    return upd(st.state, convId, c => ({ ...c, unread: c.unread || (!open && msg.from !== 'you'), messages: [...c.messages, st.msg] }));
  },

  answer(state, { convId, msgId, answer, now }) {
    const conv = state.conversations.find(c => c.id === convId);
    const msg = conv?.messages.find(m => m.id === msgId);
    if (!msg || msg.answer) return state;
    const word = { approved: 'Approved.', rejected: 'Rejected.', granted: 'Granted.', declined: 'Declined.', no: 'No.' }[answer];
    let s = upd(state, convId, c => ({ ...c, messages: c.messages.map(m => (m.id === msgId ? { ...m, answer } : m)) }));
    if (word) {
      const st = stampMessage(s, { from: 'you', kind: 'text', text: word, data: {} }, now);
      s = push(st.state, convId, st.msg);
    }
    if (answer === 'granted' && msg.kind === 'limit') {
      s = upd(s, convId, c => ({ ...c, intent: { ...c.intent, limit: { ...(c.intent.limit ?? { total: 100, spent: 0, venue: 'Stand-in Exchange' }), perOrder: msg.data.to } } }));
    }
    return s;
  },

  toggleDetails: s => ({ ...s, detailsOpen: !s.detailsOpen }),
  stopGravit(s, { convId, now }) {
    const st = stampMessage(s, { from: 'system', kind: 'text', text: 'Gravit 停了，这件事不再动。', data: {} }, now);
    return upd(push(st.state, convId, st.msg), convId, c => ({ ...c, status: 'stopped' }));
  },
  withdraw(s, { convId, now }) {
    const st = stampMessage(s, { from: 'system', kind: 'text', text: '委托撤了。', data: {} }, now);
    return upd(push(st.state, convId, st.msg), convId, c => ({ ...c, status: 'withdrawn' }));
  },
  changeLimit: (s, { convId, limit }) => upd(s, convId, c => ({ ...c, intent: { ...c.intent, limit: { ...(c.intent.limit ?? { perOrder: 25, total: 100, spent: 0, venue: 'Stand-in Exchange' }), ...limit } } })),

  showBanner: (s, banner) => ({ ...s, banner }),
  dismissBanner: s => (s.banner ? { ...s, banner: null } : s),
  incomingCall: (s, call) => ({ ...s, call }),
  answerCall(s, { accept, now }) {
    if (!s.call) return s;
    const convId = s.conversations[0]?.id;
    const text = accept ? `接了 Gravit 的电话：${s.call.about}。` : `没接。它想说：${s.call.about}。`;
    let st = { ...s, call: null };
    if (convId) {
      const r = stampMessage(st, { from: 'gravit', kind: 'text', text, data: {} }, now);
      st = push(r.state, convId, r.msg);
    }
    return st;
  },
};
```

```js
// gravit-ui/js/reducers/discover.js — the store: search, the Installed filter, the drawer, install/uninstall, upload
import { nextId } from '../ids.js';
import { DAY } from '../time.js';
import { byId } from '../data/plugins.js';
import { stampMessage } from './messages.js';

const disc = (s, patch) => ({ ...s, discover: { ...s.discover, ...patch } });

export const reducers = {
  setQuery: (s, query) => disc(s, { query: query ?? '' }),
  toggleInstalledOnly: s => disc(s, { installedOnly: !s.discover.installedOnly }),
  openPlugin: (s, id) => disc(s, { drawer: id, upload: false }),
  closeDrawer: s => disc(s, { drawer: null, upload: false }),
  openUpload: s => disc(s, { upload: true, drawer: null }),
  dismissToast: s => (s.discover.toast ? disc(s, { toast: null }) : s),

  install(state, { id, now }) {
    const p = byId(id, state.plugins.uploaded);
    if (!p || state.plugins.installed.includes(id)) return state;
    const c1 = nextId(state.counters, 'conv');
    const c2 = nextId(c1.counters, 'intent');
    let s = { ...state, counters: c2.counters, plugins: { ...state.plugins, installed: [...state.plugins.installed, id] } };
    // the plugin opens a conversation that teaches its use (spec §7.5)
    const st = stampMessage(s, { from: id, kind: 'text', text: p.teach, data: {} }, now);
    const conv = {
      id: c1.id, title: `${p.name}：怎么用我`, kind: 'bot', members: ['gravit', id], unread: true, status: 'working',
      intent: { id: c2.id, created: now, until: now + 6 * DAY, limit: null }, plugins: [id], messages: [st.msg],
    };
    s = { ...st.state, conversations: [conv, ...st.state.conversations] };
    return disc(s, { drawer: null, toast: { text: `${p.name} 装好了 · Gravit 开了一个会话教你用`, action: { label: 'Open', route: { screen: 'messages', id: conv.id } } } });
  },

  uninstall(s, id) {
    if (!s.plugins.installed.includes(id)) return s;
    const next = { ...s, plugins: { ...s.plugins, installed: s.plugins.installed.filter(x => x !== id) } };
    return next.discover.drawer === id ? disc(next, { drawer: null }) : next;
  },

  publish(state, { manifest, now }) {
    const name = (manifest.name ?? '').trim();
    if (!name) return state;
    const { id, counters } = nextId(state.counters, 'plugin');
    const p = {
      id, kind: manifest.kind, name, blurb: (manifest.blurb ?? '').trim(), by: '@you', visibility: manifest.visibility === 'public' ? 'public' : 'private', installs: '',
      logo: { type: 'letter', text: name[0].toUpperCase() }, avatar: null, asks: [], writes: ['你写的工具的输出'], never: ['动钱', '付人', '改额度'],
      needs: manifest.needs || '没有。', tools: manifest.tools ?? '', teach: `你好，这是你自己写的 ${name}。工具：${manifest.tools || '（没写）'}。`, at: now,
    };
    const s = { ...state, counters, plugins: { ...state.plugins, uploaded: [...state.plugins.uploaded, p], mine: [...state.plugins.mine, id], installed: [...state.plugins.installed, id] } };
    return disc(s, { upload: false, toast: { text: `${name} 发布了 · ${p.visibility === 'private' ? '只有你的 Gravit 看得见' : '等过审'}`, action: null } });
  },
};
```

```js
// gravit-ui/js/reducers/account.js — Account: mode, Memory, settings
import { nextId } from '../ids.js';

const mem = (s, patch) => ({ ...s, memory: { ...s.memory, ...patch } });

export const reducers = {
  setMode: (s, mode) => ({ ...s, account: { ...s.account, mode } }),
  openSettings: s => ({ ...s, settingsOpen: true }),
  closeSettings: s => ({ ...s, settingsOpen: false }),
  addMemory(s, { text, now }) {
    const t = (text ?? '').trim();
    if (!t) return s;
    const { id, counters } = nextId(s.counters, 'mem');
    return { ...mem(s, { entries: [...s.memory.entries, { id, group: '你加的', text: t, source: '你说的', at: now }] }), counters };
  },
  editMemory: (s, { id, text }) => mem(s, { entries: s.memory.entries.map(e => (e.id === id ? { ...e, text: (text ?? '').trim() || e.text } : e)) }),
  forgetMemory: (s, id) => mem(s, { entries: s.memory.entries.filter(e => e.id !== id) }),
  forgetAll: s => mem(s, { entries: [] }),
  setMemorySwitch: (s, { key, value }) => (['remember', 'askFirst', 'botsRead'].includes(key) ? mem(s, { [key]: !!value }) : s),
};
```

```js
// gravit-ui/js/reducers/index.js
import { reducers as messages } from './messages.js';
import { reducers as discover } from './discover.js';
import { reducers as account } from './account.js';

export const reducers = { ...messages, ...discover, ...account };
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd gravit-ui && node --test tests/reducers.test.js`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add gravit-ui/js/reducers gravit-ui/tests/reducers.test.js
git commit -m "gravit-ui: reducers for messages, discover and account"
```

---

### Task 7: The scripted driver

**Files:**
- Create: `gravit-ui/js/driver.js`
- Test: `gravit-ui/tests/driver.test.js`

**Interfaces:**
- Consumes: `message` from `messages.js`, `MIN`, `fmtDate`.
- Produces: `replyTo(text, ctx) → event[]`, `followUp(msg, answer, ctx) → event[]`, `director` with `brief(now)`, `ta(now)`, `breaking(now)`, `call()`, `bot()`; `CANDLES`. An event is `{ delay: ms, msg }` where `msg` has no id and no `at`. `ctx = { installed: string[], now: ms }`. Driver c, scripted: the same table a later `--driver llm` would replace.

- [ ] **Step 1: Write the failing test**

```js
// gravit-ui/tests/driver.test.js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { replyTo, followUp, director, CANDLES } from '../js/driver.js';
import { message } from '../js/messages.js';

const NOW = new Date(2026, 9, 9, 14, 7).getTime();
const ctx = { installed: ['pricefeed', 'fraud'], now: NOW };

test('replyTo scripts by what the owner said', () => {
  const btc = replyTo('小仓位买 BTC，$70k 以下', ctx);
  assert.equal(btc.length, 2);
  assert.equal(btc[0].msg.kind, 'text');
  assert.equal(btc[1].msg.kind, 'card');
  assert.equal(btc[1].msg.data.by, NOW + 26 * 60_000);
  assert.ok(btc[1].delay > btc[0].delay);
  const askInstall = replyTo('跟单 Pelosi', ctx);
  assert.equal(askInstall[0].msg.kind, 'install');
  assert.equal(askInstall[0].msg.data.plugin, 'politician');
  const withBot = replyTo('跟单 Pelosi', { ...ctx, installed: ['politician'] });
  assert.equal(withBot.at(-1).msg.from, 'politician');
  assert.equal(withBot.at(-1).msg.kind, 'proposal');
  const addr = replyTo('查 0x9f3a1234 是不是骗子', ctx);
  assert.equal(addr[1].msg.from, 'fraud');
  assert.equal(addr[1].msg.kind, 'signal');
  assert.equal(addr[2].msg.kind, 'alert');
  const limit = replyTo('额度不够', ctx);
  assert.equal(limit[0].msg.kind, 'limit');
  const other = replyTo('今天天气', ctx);
  assert.equal(other.length, 2);
  assert.ok(other.every(e => e.msg.from === 'gravit' && e.msg.kind === 'text'));
  for (const e of [...btc, ...askInstall, ...addr, ...other]) {
    assert.equal(e.msg.id, undefined);
    assert.equal(e.msg.at, undefined);
    assert.equal(typeof e.delay, 'number');
  }
});

test('followUp continues the scripted story and never answers twice', () => {
  const card = message('gravit', 'card', '要你答', { title: 'x' });
  const ok = followUp(card, 'approved', ctx);
  assert.equal(ok[0].msg.kind, 'receipt');
  assert.equal(ok[1].msg.kind, 'limit');
  assert.equal(followUp(card, 'rejected', ctx)[0].msg.kind, 'text');
  assert.deepEqual(followUp({ ...card, answer: 'approved' }, 'approved', ctx), []);
  const limit = message('gravit', 'limit', 'x', { from: 25, to: 50 });
  const granted = followUp(limit, 'granted', ctx);
  assert.match(granted[0].msg.text, /\$50/);
  assert.equal(granted[1].msg.kind, 'install');
  assert.match(followUp(limit, 'declined', ctx)[0].msg.text, /\$25/);
  const install = message('gravit', 'install', 'x', { plugin: 'news' });
  assert.equal(followUp(install, 'no', ctx)[0].msg.kind, 'text');
  assert.deepEqual(followUp(install, 'installed', ctx), []);
  assert.deepEqual(followUp(null, 'approved', ctx), []);
});

test('the director hands out the brief, a K-line card, a breaking banner, a call and a bot line', () => {
  const brief = director.brief(NOW);
  assert.equal(brief.kind, 'brief');
  assert.equal(brief.data.date, 'Oct 9');
  assert.ok(brief.data.lines.some(l => l.includes('{{BTC}}')));
  const ta = director.ta(NOW);
  assert.equal(ta.kind, 'ta');
  assert.equal(ta.data.ticker, 'NVDA');
  assert.equal(ta.data.candles.length, 14);
  assert.equal(CANDLES.length, 14);
  for (const [o, c, l, h] of CANDLES) assert.ok(h <= Math.min(o, c) && l >= Math.max(o, c), 'y grows downward: high is the smallest');
  const b = director.breaking(NOW);
  assert.equal(b.at, NOW);
  assert.match(b.headline, /Stand-in Exchange/);
  assert.equal(director.call().from, 'gravit');
  assert.equal(director.bot().from, 'buffett');
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd gravit-ui && node --test tests/driver.test.js`
Expected: FAIL — `Cannot find module '../js/driver.js'`

- [ ] **Step 3: Write the driver**

```js
// gravit-ui/js/driver.js — driver c, scripted: what Gravit says back, and the events a demo director can fire
import { message } from './messages.js';
import { MIN, fmtDate } from './time.js';

const G = (kind, text, data = {}) => message('gravit', kind, text, data);
const ev = (delay, msg) => ({ delay, msg });

// fourteen 4h candles as [open, close, low, high] in SVG y (0 = top of a 68 px box); close < open = up
export const CANDLES = [
  [50, 42, 56, 38], [42, 46, 50, 38], [46, 36, 50, 30], [36, 30, 40, 24], [30, 35, 40, 26], [35, 28, 38, 22], [28, 33, 36, 24],
  [33, 26, 36, 20], [26, 20, 30, 14], [20, 25, 28, 16], [25, 18, 28, 12], [18, 22, 26, 14], [22, 16, 26, 10], [16, 20, 24, 12],
];

export function replyTo(text, ctx = {}) {
  const t = (text ?? '').toLowerCase();
  const installed = ctx.installed ?? [];
  const now = ctx.now ?? Date.now();
  if (/btc|比特币|eth|以太|sol\b/.test(t)) {
    return [
      ev(1200, G('text', '收到。看了 Stand-in Exchange 和 Stand-in Wallet 的 DEX，交易所便宜。先建 $5 试水。')),
      ev(2800, G('card', '要你答：买 0.00008 BTC', { title: '要你答：买 0.00008 BTC', venue: 'Stand-in Exchange', type: 'market', about: 'about $5.00', by: now + 26 * MIN })),
    ];
  }
  if (/pelosi|跟单|政客/.test(t)) {
    if (!installed.includes('politician')) return [ev(1200, G('install', '跟单要装 美国政客 bot，Discover 里有。', { plugin: 'politician' }))];
    return [
      ev(1200, G('text', '好。美国政客 bot 在，披露一出来我就跟，在额度里的直接下单。')),
      ev(3200, message('politician', 'proposal', '披露：Pelosi 买 NVDA。照它买 $20，在额度里，直接成交。', { status: 'filled', ord: 'ord-0004', venue: 'Stand-in Broker' })),
    ];
  }
  if (/0x[0-9a-f]{4,}|地址|骗子/.test(t)) {
    return [
      ev(1000, G('text', '查了。')),
      ev(1900, message('fraud', 'signal', '0x9f3a…c21e · 在 3 份骗子名单里 · 合约可暂停转出', { source: '地址欺诈检测' })),
      ev(2800, G('alert', '这个地址在骗子名单里，没有转。')),
    ];
  }
  if (/额度|上限/.test(t)) return [ev(1000, G('limit', '每单上限 $25 不够，改到 $50？', { from: 25, to: 50 }))];
  return [ev(1000, G('text', '收到，我先看看。')), ev(2800, G('text', '看了，没有要动的。有事我说。'))];
}

export function followUp(msg, answer, ctx = {}) {
  if (!msg || msg.answer) return [];
  if (msg.kind === 'card') {
    return answer === 'approved'
      ? [ev(1500, G('receipt', '0.00008 BTC @ 62,500 · ord-0001 · 账本 #41', { status: 'filled' })), ev(3400, G('limit', '想再加 $30，但你的每单上限是 $25。改到 $50？', { from: 25, to: 50 }))]
      : [ev(1200, G('text', '好，不买。有变化我再问。'))];
  }
  if (msg.kind === 'limit') {
    return answer === 'granted'
      ? [ev(1200, G('text', `改到 $${msg.data.to} 了。`)), ev(2800, G('install', 'Discover 里有个 News sentiment。装上我就能看情绪再加仓。', { plugin: 'news' }))]
      : [ev(1200, G('text', `那就还是 $${msg.data.from}。`))];
  }
  if (msg.kind === 'install') return answer === 'no' ? [ev(1000, G('text', '好，不装。'))] : [];
  return [];
}

export const director = {
  brief: now => G('brief', '早报', { date: fmtDate(now), time: '7:30', lines: [
    '隔夜：纳指 +0.8%，{{BTC}} 63.1k（+1.4%）',
    '今天：CPI 8:30 · {{NVDA}} 财报后第一天',
    '你的仓：{{BTC}} $3,740 · {{AAPL}} $2,510，没有要到期的额度',
    '我的建议：CPI 出来前不动。',
  ] }),
  ta: () => G('ta', 'NVDA 技术面', { ticker: 'NVDA', tf: '4h', support: 178, resistance: 192, candles: CANDLES, lines: ['区间上沿，量在放。支撑 178，压力 192。', '结论：要追等回踩 182，别在上沿接。'] }),
  breaking: now => ({ id: 'b-' + now, headline: 'SEC 起诉 Stand-in Exchange（替身新闻）', body: '你在那儿有 BTC $3,740。Gravit 已经停了这家的单，等你一句。', at: now }),
  call: () => ({ from: 'gravit', about: '想说 BTC 的事，30 秒' }),
  bot: () => message('buffett', 'text', '补一句：KO 这个价我会买。'),
};
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd gravit-ui && node --test tests/driver.test.js`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add gravit-ui/js/driver.js gravit-ui/tests/driver.test.js
git commit -m "gravit-ui: the scripted driver and the demo director"
```

---

### Task 8: Avatars and the rail

**Files:**
- Create: `gravit-ui/js/render/avatars.js`, `gravit-ui/js/render/rail.js`
- Test: `gravit-ui/tests/rail.test.js`

**Interfaces:**
- Consumes: `esc, attrs, cls`, `icon`, `byId`, `rowTime`.
- Produces: `avatar(who, size = 28, state = null)`, `mark(spec, size, radius, name)`, `logo(plugin, size = 44)`, `cluster(members, size, state)`, `groupMark(members, size, state)` from `avatars.js`; `renderRail(state, now)`, `previewOf(conv, state)` from `rail.js`. Row actions: `data-action="open"` with `data-id`, `data-action="startDraft"`, `data-action="toggleRail"`; nav links are `href="#/discover"`, `#/markets`, `#/trade`, `#/account/portfolio`.

- [ ] **Step 1: Write the failing test**

```js
// gravit-ui/tests/rail.test.js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { avatar, logo, cluster, groupMark } from '../js/render/avatars.js';
import { renderRail, previewOf } from '../js/render/rail.js';
import { seed } from '../js/data/seed.js';
import { byId } from '../js/data/plugins.js';
import { reducers as R } from '../js/reducers/index.js';

const NOW = new Date(2026, 9, 9, 14, 7).getTime();
const count = (h, re) => (h.match(re) ?? []).length;

test('avatars: you, Gravit, a bot letter, a portrait slot, a glyph; logos are rounded squares', () => {
  assert.match(avatar('you', 28), /class="av av-you"[^>]*>你</);
  assert.match(avatar('gravit', 36), /class="av av-g" style="width:36px;height:36px/);
  assert.match(avatar('politician', 28), /av-letter tone-blue[^>]*>P</);
  assert.match(avatar('buffett', 28), /av-portrait tone-warm/);
  assert.match(avatar('buffett', 28), /aria-label="Buffett bot 的头像图"/);
  assert.match(avatar('fraud', 28), /av-glyph/);
  assert.match(avatar('p-1', 28, { plugins: { uploaded: [{ id: 'p-1', name: 'Zed', logo: { type: 'letter', text: 'Z' } }] } }), />Z</);
  assert.match(avatar('ghost', 28), />G</, 'an unknown sender gets its first letter');
  assert.match(logo(byId('telegram')), /border-radius:10px/);
  assert.equal(count(cluster(['gravit', 'politician', 'buffett'], 44), /class="cluster-item"/g), 3);
  assert.equal(count(groupMark(['gravit', 'politician', 'buffett'], 36), /class="av /g), 2);
});

test('previewOf: the last message in words, with the sender in a group', () => {
  const s = seed(NOW);
  assert.equal(previewOf(s.conversations[0]), 'Discover 里有个 News sentiment。装上我就能看情绪再加仓。');
  assert.equal(previewOf(s.conversations[1]), '披露：Pelosi 买 NVDA。照它买 $20，在额度里，直接成交。');
  assert.equal(previewOf(s.conversations[3]), 'Gravit：filled · NVDA $25 @ 187.40 · ord-0009 · 账本 #58');
  assert.equal(previewOf({ kind: 'gravit', messages: [] }), '');
});

test('renderRail: brand, Messages header with + and chevron, four rows, the current one, the unread dot, nav, phone/mail, Account', () => {
  const s = seed(NOW);
  const h = renderRail(s, NOW);
  assert.match(h, /<nav class="rail"/);
  assert.match(h, /Messages/);
  assert.match(h, /data-action="startDraft"[^>]*aria-label="New message"/);
  assert.match(h, /data-action="toggleRail"[^>]*aria-expanded="true"/);
  assert.equal(count(h, /class="row(?: current)?"/g), 4);
  assert.equal(count(h, /class="row current" aria-current="page" href="#\/messages\/c-1"/g), 1);
  assert.equal(count(h, /class="dot on"/g), 1, 'one unread conversation');
  assert.match(h, /row-time">14:07</);
  assert.match(h, /row-time">昨天</);
  assert.match(h, /href="#\/discover"/);
  assert.match(h, /href="#\/markets"/);
  assert.match(h, /href="#\/trade"/);
  assert.match(h, /aria-label="Phone"/);
  assert.match(h, /aria-label="Email"/);
  assert.match(h, /href="#\/account\/portfolio"[^>]*class="account"/);
  assert.match(h, /\$12,480 · Guard/);
  assert.doesNotMatch(h, /Trading on/);
});

test('renderRail: a draft row leads the list; the discover nav is current on that screen; collapsed hides the rows', () => {
  const d = R.startDraft(seed(NOW), { now: NOW });
  const h = renderRail(d, NOW);
  assert.match(h, /class="row current draft"/);
  assert.match(h, /New message/);
  assert.equal(count(h, /class="row(?: current)?(?: draft)?"/g), 5);
  const disc = renderRail(R.nav(seed(NOW), { screen: 'discover' }), NOW);
  assert.match(disc, /class="nav-item current" aria-current="page" href="#\/discover"/);
  const acct = renderRail(R.nav(seed(NOW), { screen: 'account', tab: 'memory' }), NOW);
  assert.match(acct, /class="account current" aria-current="page"/);
  const collapsed = renderRail(R.toggleRail(seed(NOW)), NOW);
  assert.match(collapsed, /aria-expanded="false"/);
  assert.equal(count(collapsed, /class="row/g), 0);
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd gravit-ui && node --test tests/rail.test.js`
Expected: FAIL — `Cannot find module '../js/render/avatars.js'`

- [ ] **Step 3: Write avatars.js and rail.js**

```js
// gravit-ui/js/render/avatars.js — the round marks: 你, G, a bot's letter, a portrait slot, a glyph; logos are the 44 px rounded squares of Discover
import { esc } from '../html.js';
import { icon } from '../icons.js';
import { byId } from '../data/plugins.js';

const SILHOUETTE = '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="12" cy="9" r="4.2"></circle><path d="M3.5 24a8.5 8.5 0 0 1 17 0z"></path></svg>';

export function mark(spec, size, radius, name) {
  const box = `width:${size}px;height:${size}px;border-radius:${radius}`;
  if (spec.type === 'portrait') return `<span class="av av-portrait tone-${spec.tone ?? 'warm'}" role="img" aria-label="${esc(name)} 的头像图" style="${box}">${SILHOUETTE}</span>`;
  if (spec.type === 'glyph') return `<span class="av av-glyph" style="${box}">${icon(spec.icon, Math.round(size / 2), 2)}</span>`;
  return `<span class="av av-letter tone-${spec.tone ?? 'grey'}" style="${box};font-size:${Math.round(size * 0.42)}px">${esc(spec.text)}</span>`;
}

export function avatar(who, size = 28, state = null) {
  if (who === 'you') return `<span class="av av-you" style="width:${size}px;height:${size}px;font-size:${Math.round(size * 0.43)}px">你</span>`;
  if (who === 'gravit') return `<span class="av av-g" style="width:${size}px;height:${size}px;font-size:${Math.round(size * 0.46)}px">G</span>`;
  const p = byId(who, state?.plugins?.uploaded ?? []);
  const spec = p?.avatar ?? (p?.logo?.type === 'portrait' ? p.logo : null) ?? { type: 'letter', text: (p?.name ?? who).slice(0, 1).toUpperCase(), tone: 'grey' };
  return mark(spec, size, '999px', p?.name ?? who);
}

export function logo(plugin, size = 44) {
  return mark(plugin.logo, size, '10px', plugin.name);
}

// the group head: overlapping avatars (spec §5.1)
export function cluster(members, size = 44, state = null) {
  return `<span class="cluster">${members.map(m => `<span class="cluster-item">${avatar(m, size, state)}</span>`).join('')}</span>`;
}

// the group row mark: two small circles in one slot (spec §4.3)
export function groupMark(members, size = 36, state = null) {
  const small = Math.round(size * 0.62);
  const [a, b] = members;
  return `<span class="group-mark" style="width:${size}px;height:${size}px"><span class="group-a">${avatar(a, small, state)}</span><span class="group-b">${avatar(b ?? a, small, state)}</span></span>`;
}
```

```js
// gravit-ui/js/render/rail.js — Linqi's 248 px rail with the iMessage conversation rows (spec §4)
import { esc, attrs, cls } from '../html.js';
import { icon } from '../icons.js';
import { byId } from '../data/plugins.js';
import { rowTime } from '../time.js';
import { avatar, groupMark } from './avatars.js';

const NAME = { you: '你', gravit: 'Gravit', system: '' };
export function senderName(from, state) {
  return NAME[from] ?? byId(from, state?.plugins?.uploaded ?? [])?.name ?? from;
}

export function previewOf(conv, state = null) {
  const m = conv.messages.at(-1);
  if (!m) return '';
  const body = {
    receipt: `${m.data.status} · ${m.text}`, brief: `早报 · ${m.data.date}`, ta: `${m.data.ticker} 技术面`, breaking: m.data.headline ?? m.text, call: 'Gravit 来电',
  }[m.kind] ?? m.text;
  return conv.kind === 'group' && m.from !== 'you' ? `${senderName(m.from, state)}：${body}` : body;
}

function rowMark(conv, state) {
  if (conv.kind === 'group') return groupMark(conv.members, 36, state);
  const who = conv.kind === 'bot' ? conv.members.find(x => x !== 'gravit') ?? 'gravit' : 'gravit';
  return avatar(who, 36, state);
}

function row(conv, state, now) {
  const current = state.route.screen === 'messages' && state.route.id === conv.id;
  const last = conv.messages.at(-1);
  return `<a${attrs({ class: cls('row', current && 'current'), 'aria-current': current ? 'page' : null, href: `#/messages/${conv.id}`, 'data-action': 'open', 'data-id': conv.id })}>` +
    `<span class="${cls('dot', conv.unread && 'on')}"></span>${rowMark(conv, state)}` +
    `<span class="row-body"><span class="row-top"><span class="row-title">${esc(conv.title)}</span><span class="row-time">${last ? rowTime(last.at, now) : ''}</span></span>` +
    `<span class="row-preview">${esc(previewOf(conv, state))}</span></span></a>`;
}

function draftRow() {
  return `<a class="row current draft" aria-current="page" href="#/messages/new" data-action="open" data-id="new"><span class="dot"></span><span class="av av-draft">+</span>` +
    `<span class="row-body"><span class="row-top"><span class="row-title">New message</span><span class="row-time">now</span></span><span class="row-preview">还没发出去</span></span></a>`;
}

function navItem(href, name, label, current) {
  return `<a${attrs({ class: cls('nav-item', current && 'current'), 'aria-current': current ? 'page' : null, href })}>${icon(name, 22, current ? 2.1 : 2)}${label}</a>`;
}

export function renderRail(state, now) {
  const { screen } = state.route;
  const rows = state.railCollapsed ? '' : (state.draft ? draftRow() : '') + state.conversations.map(c => row(c, state, now)).join('');
  const accountCurrent = screen === 'account';
  return `<nav class="rail" aria-label="Gravit">
  <div class="brand">${avatar('gravit', 28)}<span class="brand-name">Gravit</span></div>
  <div class="rail-group">
    <div class="rail-head">${icon('chat', 22, 2)}<span class="rail-head-label">Messages</span><span class="rail-head-keys">` +
      `<button type="button" class="icon-key" data-action="startDraft" aria-label="New message">${icon('plus', 16, 2.2)}</button>` +
      `<button type="button" class="icon-key" data-action="toggleRail" aria-expanded="${state.railCollapsed ? 'false' : 'true'}" aria-label="Collapse messages">${icon(state.railCollapsed ? 'chevRight' : 'chevDown', 14, 2.2)}</button></span></div>
    ${rows}
  </div>
  <div class="rail-group">
    ${navItem('#/discover', 'compass', 'Discover', screen === 'discover')}
    ${navItem('#/markets', 'markets', 'Markets', screen === 'markets')}
    ${navItem('#/trade', 'trade', 'Trade', screen === 'trade')}
  </div>
  <div class="rail-foot">
    <div class="rail-lines"><button type="button" class="line-key" aria-label="Phone">${icon('phone', 20, 2)}</button><button type="button" class="line-key" aria-label="Email">${icon('mail', 20, 2)}</button></div>
    <a${attrs({ href: '#/account/portfolio', class: cls('account', accountCurrent && 'current'), 'aria-current': accountCurrent ? 'page' : null })}>${icon('wallet', 22, accountCurrent ? 2.1 : 2)}<span class="account-body"><span class="account-title">Account</span><span class="account-line">$${state.account.netWorth.toLocaleString('en-US')} · ${state.account.mode === 'beast' ? 'Beast' : 'Guard'}</span></span></a>
  </div>
</nav>`;
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd gravit-ui && node --test tests/rail.test.js`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add gravit-ui/js/render/avatars.js gravit-ui/js/render/rail.js gravit-ui/tests/rail.test.js
git commit -m "gravit-ui: avatars and the rail"
```

---

### Task 9: The thread — bubbles, cards, keys, dividers

**Files:**
- Create: `gravit-ui/js/render/thread.js`
- Test: `gravit-ui/tests/thread.test.js`

**Interfaces:**
- Consumes: `esc, attrs, cls`, `icon`, `divider, fmtClock`, `levelOf, needsAnswer`, `avatar`, `senderName`.
- Produces: `renderThread(conv, state, now)`, `renderMessage(m, conv, state)`, `key(type, label, data)`, `chip(text, tone)`, `ticker(t)`, `candles(data)`. Keys carry `data-action="answer" data-conv data-msg data-answer`; the install key carries `data-action="installAsk" data-plugin`; a ticker is `<a class="ticker" href="#/markets/NVDA">`.

- [ ] **Step 1: Write the failing test**

```js
// gravit-ui/tests/thread.test.js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderThread, renderMessage, chip, key, ticker, candles } from '../js/render/thread.js';
import { seed } from '../js/data/seed.js';
import { director, CANDLES } from '../js/driver.js';
import { message } from '../js/messages.js';

const NOW = new Date(2026, 9, 9, 14, 7).getTime();
const count = (h, re) => (h.match(re) ?? []).length;
const s = seed(NOW);
const btc = s.conversations[0];
const group = s.conversations[3];
const ctx = { id: 'c-1', kind: 'gravit' };

test('the BTC thread: dividers, owner bubbles right, Gravit left, an answered card without keys, a live limit with ✓ ✗, an install with + ✗', () => {
  const h = renderThread(btc, s, NOW);
  assert.match(h, /class="divider">Today 14:01</);
  assert.equal(count(h, /class="divider"/g), 1, 'messages inside 15 minutes share one divider');
  assert.equal(count(h, /class="msg you"/g), 2);
  assert.equal(count(h, /class="msg left"/g), 5);
  assert.match(h, /class="bubble you">小仓位买 BTC/);
  assert.match(h, /class="card orange"/);
  assert.match(h, /answer by 14:33/);
  const cardPart = h.slice(h.indexOf('card orange'), h.indexOf('class="msg you">', h.indexOf('card orange')));
  assert.doesNotMatch(cardPart, /class="key/, 'an answered card has no keys');
  assert.match(h, /class="bubble green"[\s\S]*?filled/);
  assert.match(h, /class="key no"[^>]*aria-label="Decline"[^>]*data-action="answer"[^>]*data-answer="declined"/);
  assert.match(h, /class="key yes"[^>]*aria-label="Grant"[^>]*data-answer="granted"/);
  assert.match(h, /class="key plus"[^>]*aria-label="Install"[^>]*data-action="installAsk"[^>]*data-plugin="news"/);
  assert.match(h, /class="key no"[^>]*aria-label="No"[^>]*data-answer="no"/);
  assert.doesNotMatch(h, /intent-0003/, 'no meta text in bubbles');
  assert.doesNotMatch(h, /sender-name/, 'no sender names outside groups');
});

test('a group thread writes the sender over bot bubbles and draws the two-order card', () => {
  const h = renderThread(group, s, NOW);
  assert.match(h, /class="sender-name">美国政客 bot</);
  assert.match(h, /class="sender-name">Buffett bot</);
  assert.match(h, /class="sender-name">Gravit</);
  assert.equal(count(h, /class="order-row"/g), 2);
  assert.match(h, /KO 挂着/);
});

test('every kind renders at its level', () => {
  const r = m => renderMessage({ id: 'm-x', at: NOW, ...m }, ctx, s);
  assert.match(r(message('gravit', 'text', 'hi')), /class="bubble grey">hi</);
  assert.match(r(message('fraud', 'signal', 'q', { source: '地址欺诈检测' })), /class="card white"[\s\S]*地址欺诈检测[\s\S]*class="quote">q</);
  assert.match(r(message('gravit', 'refusal', '$30 is above', { code: 'E_MANDATE_PER_ORDER_CAP' })), /class="card red"[\s\S]*E_MANDATE_PER_ORDER_CAP/);
  assert.match(r(message('gravit', 'alert', 'bad')), /class="card red">[\s\S]*bad/);
  assert.match(r(message('gravit', 'receipt', 'x', { status: 'paid' })), /class="bubble green"[\s\S]*>paid</);
  assert.match(r(message('gravit', 'done', 'x', { foot: '账本对上' })), /class="bubble green"[\s\S]*class="foot">账本对上/);
  assert.match(r(message('politician', 'proposal', 'x', { status: 'filled', ord: 'ord-0004', venue: 'Stand-in Broker' })), /class="bubble green"[\s\S]*ord-0004 · Stand-in Broker/);
  const brief = r(director.brief(NOW));
  assert.match(brief, /class="card white"/);
  assert.match(brief, /早报 · Oct 9/);
  assert.equal(count(brief, /class="ticker" href="#\/markets\/BTC"/g), 2);
  const ta = r(director.ta(NOW));
  assert.match(ta, /class="ticker" href="#\/markets\/NVDA"/);
  assert.equal(count(ta, /<rect /g), 14);
  assert.match(ta, /压力 192/);
  assert.match(r(message('gravit', 'breaking', 'x', { headline: 'H', body: 'B' })), /class="card red"[\s\S]*>突发<[\s\S]*H/);
  const call = r({ ...message('gravit', 'call', '来电', { about: '想说 BTC 的事' }), answer: 'missed' });
  assert.match(call, /class="card red"[\s\S]*没接/);
  assert.match(r({ from: 'system', kind: 'text', text: '委托撤了。', data: {} }), /class="sysline">委托撤了。</);
});

test('helpers: chip, key, ticker, candles', () => {
  assert.equal(chip('filled', 'up'), '<span class="chip up">filled</span>');
  assert.match(key('yes', 'Approve', { 'data-answer': 'approved' }), /^<button type="button" class="key yes" aria-label="Approve" data-answer="approved">/);
  assert.equal(ticker('KO'), `<a class="ticker" href="#/markets/KO">KO<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 6l6 6-6 6"></path></svg></a>`);
  const svg = candles({ candles: CANDLES, support: 178, resistance: 192, ticker: 'NVDA', tf: '4h' });
  assert.match(svg, /^<svg class="kline" viewBox="0 0 300 68"/);
  assert.match(svg, /stroke="var\(--up\)"/);
  assert.match(svg, /fill="var\(--down\)"/);
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd gravit-ui && node --test tests/thread.test.js`
Expected: FAIL — `Cannot find module '../js/render/thread.js'`

- [ ] **Step 3: Write thread.js**

```js
// gravit-ui/js/render/thread.js — the conversation body: bubbles, cards by level, icon-only keys, centred dividers (spec §5.2–5.3, §6)
import { esc, attrs, cls } from '../html.js';
import { icon } from '../icons.js';
import { divider, fmtClock } from '../time.js';
import { levelOf, needsAnswer } from '../messages.js';
import { avatar } from './avatars.js';
import { senderName } from './rail.js';

export const chip = (text, tone = 'grey') => `<span class="${cls('chip', tone)}">${esc(text)}</span>`;

export function key(type, label, data = {}) {
  const glyph = { yes: 'check', no: 'x', plus: 'plus' }[type];
  return `<button type="button"${attrs({ class: `key ${type}`, 'aria-label': label, ...data })}>${icon(glyph, 14, 2.4)}</button>`;
}

export const ticker = t => `<a class="ticker" href="#/markets/${esc(t)}">${esc(t)}${icon('chevRight', 12, 2.4)}</a>`;

const withTickers = text => esc(text).replace(/\{\{([A-Z]+)\}\}/g, (_, t) => ticker(t));

export function candles(data) {
  const bars = data.candles.map(([o, c, l, h], i) => {
    const x = 12 + i * 21;
    const tone = c < o ? 'var(--up)' : 'var(--down)';
    return `<line x1="${x}" y1="${h}" x2="${x}" y2="${l}" stroke="${tone}" stroke-width="1.5"></line><rect x="${x - 5}" y="${Math.min(o, c)}" width="10" height="${Math.max(Math.abs(o - c), 2)}" fill="${tone}" rx="1"></rect>`;
  }).join('');
  return `<svg class="kline" viewBox="0 0 300 68" role="img" aria-label="${esc(data.ticker)} ${esc(data.tf)} K 线">` +
    `<line x1="0" y1="12" x2="300" y2="12" class="kline-rule"></line><text x="298" y="9" class="kline-label" text-anchor="end">压力 ${esc(data.resistance)}</text>` +
    `<line x1="0" y1="56" x2="300" y2="56" class="kline-rule"></line><text x="298" y="66" class="kline-label" text-anchor="end">支撑 ${esc(data.support)}</text>${bars}</svg>`;
}

const keysFor = (m, convId) => {
  if (!needsAnswer(m)) return '';
  const d = { 'data-action': 'answer', 'data-conv': convId, 'data-msg': m.id };
  if (m.kind === 'card') return `<div class="keys right">${key('no', 'Reject', { ...d, 'data-answer': 'rejected' })}${key('yes', 'Approve', { ...d, 'data-answer': 'approved' })}</div>`;
  if (m.kind === 'limit') return `<div class="keys">${key('yes', 'Grant', { ...d, 'data-answer': 'granted' })}${key('no', 'Decline', { ...d, 'data-answer': 'declined' })}</div>`;
  if (m.kind === 'install') return `<div class="keys">${key('plus', 'Install', { 'data-action': 'installAsk', 'data-conv': convId, 'data-msg': m.id, 'data-plugin': m.data.plugin })}${key('no', 'No', { ...d, 'data-answer': 'no' })}</div>`;
  return '';
};

function body(m, convId) {
  const d = m.data ?? {};
  switch (m.kind) {
    case 'card':
      return `<div class="card orange"><div class="card-head"><div class="card-title">${esc(d.title ?? m.text)}</div>${d.by ? chip(`answer by ${fmtClock(d.by)}`, 'warn') : ''}</div>` +
        (d.venue ? `<div class="dim">${esc([d.venue, d.type, d.about, d.cardId].filter(Boolean).join(' · '))}</div>` : '') +
        (d.rows ? `<div class="orders">${d.rows.map(r => `<div class="order-row"><span class="order-t">${esc(r.t)}</span><span class="dim">${esc(r.why)}</span><span class="num">${esc(r.amt)}</span></div>`).join('')}</div>` : '') +
        (d.note ? `<div class="dim">${esc(d.note)}</div>` : '') + keysFor(m, convId) + `</div>`;
    case 'limit':
    case 'install':
      return `<div class="card orange"><div>${esc(m.text)}</div>${keysFor(m, convId)}</div>`;
    case 'signal':
      return `<div class="card white"><div class="dim">${esc(d.source ?? '')}</div><div class="quote">${esc(m.text)}</div></div>`;
    case 'ta':
      return `<div class="card white"><div class="card-head"><span class="ticker-lead">${ticker(d.ticker)}</span><span class="dim">${esc(d.tf)} · 技术面</span></div>${candles(d)}` +
        (d.lines ?? []).map((l, i) => `<div${i ? ' class="dim"' : ''}>${esc(l)}</div>`).join('') + `<a class="link" href="#/markets/${esc(d.ticker)}">在 Markets 里看 ›</a></div>`;
    case 'brief':
      return `<div class="card white"><div class="card-head"><div class="card-title">早报 · ${esc(d.date)}</div><span class="dim">${esc(d.time)} · 每天</span></div>` +
        (d.lines ?? []).map((l, i, a) => `<div${i === a.length - 1 ? ' class="dim"' : ''}>${withTickers(l)}</div>`).join('') + `</div>`;
    case 'refusal':
      return `<div class="card red">${chip(`✗ ${d.code ?? ''}`, 'down')}<div>${esc(m.text)}</div></div>`;
    case 'alert':
      return `<div class="card red">${esc(m.text)}</div>`;
    case 'breaking':
      return `<div class="card red"><div class="card-head">${chip('突发', 'down')}<span class="dim">${fmtClock(m.at)}</span></div><div class="card-title">${esc(d.headline ?? m.text)}</div>${d.body ? `<div class="dim">${withTickers(d.body)}</div>` : ''}</div>`;
    case 'call':
      return `<div class="card red"><div class="card-head"><div class="card-title">Gravit 来电</div>${chip(m.answer === 'accepted' ? '接了' : '没接', m.answer === 'accepted' ? 'up' : 'down')}</div><div class="dim">${esc(d.about ?? m.text)}</div></div>`;
    case 'receipt':
      return `<div class="bubble green"><div class="line">${chip(d.status ?? 'filled', 'up')}<span>${esc(m.text)}</span></div>${d.more ? `<div>${esc(d.more)}</div>` : ''}</div>`;
    case 'proposal':
      return `<div class="bubble green"><div>${esc(m.text)}</div><div class="line">${chip(d.status ?? 'filled', 'up')}<span class="dim">${esc([d.ord, d.venue].filter(Boolean).join(' · '))}</span></div></div>`;
    case 'done':
      return `<div class="bubble green"><div>${esc(m.text)}</div>${d.foot ? `<div class="foot">${esc(d.foot)}</div>` : ''}</div>`;
    default:
      return `<div class="bubble ${levelOf(m)}">${esc(m.text)}</div>`;
  }
}

export function renderMessage(m, conv, state) {
  if (m.from === 'system') return `<div class="sysline">${esc(m.text)}</div>`;
  if (m.from === 'you') return `<div class="msg you"><div class="bubble you">${esc(m.text)}</div>${avatar('you', 28)}</div>`;
  const name = conv.kind === 'group' ? `<div class="sender-name">${esc(senderName(m.from, state))}</div>` : '';
  const wide = ['card', 'ta', 'brief', 'breaking', 'signal'].includes(m.kind);
  return `<div class="msg left">${name}<div class="msg-row">${avatar(m.from, 28, state)}<div class="${cls('msg-body', wide && 'wide')}">${body(m, conv.id)}</div></div></div>`;
}

export function renderThread(conv, state, now) {
  let prev = null;
  const out = [];
  for (const m of conv.messages) {
    const d = divider(m.at, prev, now);
    if (d) out.push(`<div class="divider">${esc(d)}</div>`);
    out.push(renderMessage(m, conv, state));
    prev = m.at;
  }
  return out.join('');
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd gravit-ui && node --test tests/thread.test.js`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add gravit-ui/js/render/thread.js gravit-ui/tests/thread.test.js
git commit -m "gravit-ui: the thread renderer with cards by level and icon keys"
```

---

### Task 10: The Messages screen — heads, composer, new message, empty, Details, banner, call

**Files:**
- Create: `gravit-ui/js/render/controls.js`, `gravit-ui/js/render/messages.js`
- Modify: `gravit-ui/js/reducers/messages.js` (add `toggleDraftGroup`, `rename`; `send` builds a group from a group draft)
- Test: `gravit-ui/tests/messages-screen.test.js`

**Interfaces:**
- Consumes: `esc, attrs, cls, money`, `icon`, `fmtDate, fmtClock`, `byId`, `avatar, cluster`, `renderThread, chip`, `senderName`.
- Produces: from `controls.js` — `seg(items, pressed, action)`, `segLinks(items, current)` (items are `[label, href, key]`), `kv(rows)` (values are HTML), `sec(label, lines, html = false)`; from `messages.js` — `currentConversation(state)`, `renderMessagesScreen(state, now)`, `renderHead(conv, state)`, `renderComposer({ placeholder, above })`, `renderDetails(conv, state)`, `renderBanner(banner, state)`, `renderCall(call)`, `renderStub(route)`. New actions: `toggleDraftGroup()`, `rename({ convId, title })`. Data actions emitted: `send` (form submit), `toggleDetails`, `cancelDraft`, `draftTitle` (input), `draftLimit` (`data-key`), `toggleDraftAttach`, `toggleDraftGroup`, `suggest` (`data-text`), `withdraw`, `changeWords`, `changeLimit`, `endLimit`, `stopGravit`, `setMode` (`data-value`), `dismissBanner`, `answerCall` (`data-accept`).

- [ ] **Step 1: Write the failing test**

```js
// gravit-ui/tests/messages-screen.test.js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { currentConversation, renderMessagesScreen, renderHead, renderComposer, renderDetails, renderBanner, renderCall, renderStub } from '../js/render/messages.js';
import { seg, segLinks, kv, sec } from '../js/render/controls.js';
import { reducers as R } from '../js/reducers/index.js';
import { seed } from '../js/data/seed.js';

const NOW = new Date(2026, 9, 9, 14, 7).getTime();
const count = (h, re) => (h.match(re) ?? []).length;

test('currentConversation falls back to the first when the route names nothing or a missing id', () => {
  const s = seed(NOW);
  assert.equal(currentConversation(s).id, 'c-1');
  assert.equal(currentConversation({ ...s, route: { screen: 'messages', id: 'c-99' } }).id, 'c-1');
  assert.equal(currentConversation({ ...s, route: { screen: 'messages', id: 'c-3' } }).id, 'c-3');
  assert.equal(currentConversation({ ...s, conversations: [] }), null);
});

test('F1: the head is title + Working + Details; the thread and the composer follow; no small print', () => {
  const s = seed(NOW);
  const h = renderMessagesScreen(s, NOW);
  assert.match(h, /<main class="main">/);
  assert.match(h, /<h1 class="head-title">小仓位 BTC，\$70k 以下<\/h1>/);
  assert.match(h, /class="status up"[^>]*>[\s\S]*?Working/);
  assert.match(h, /data-action="toggleDetails" aria-expanded="false"/);
  assert.match(h, /class="thread" id="thread"/);
  assert.match(h, /<form class="composer" data-action="send">/);
  assert.match(h, /aria-label="Add a file"/);
  assert.match(h, /aria-label="Voice input"/);
  assert.match(h, /type="submit" class="send-key" aria-label="Sign and send"/);
  assert.match(h, /placeholder="Tell Gravit…"/);
  assert.doesNotMatch(h, /发出去就是/);
  assert.doesNotMatch(h, /class="drawer/);
});

test('F14: a group gets the cluster head with the members line and the @ placeholder', () => {
  const s = R.nav(seed(NOW), { screen: 'messages', id: 'c-4' });
  const h = renderMessagesScreen(s, NOW);
  assert.match(h, /<header class="head centered">/);
  assert.equal(count(h, /class="cluster-item"/g), 3);
  assert.match(h, /class="head-task">跟 Pelosi 和 Buffett 挑股</);
  assert.match(h, /Gravit · 美国政客 bot · Buffett bot · 3 位/);
  assert.match(h, /placeholder="Tell Gravit… 打 @ 点名一个 bot"/);
});

test('F7: the draft head is avatar + title input + To line; the limit chips sit over the composer; a group draft shows the cluster', () => {
  let s = R.startDraft(seed(NOW), { now: NOW });
  s = R.setDraftTitle(s, '买一点 SOL');
  const h = renderMessagesScreen(s, NOW);
  assert.match(h, /<header class="head centered draft">/);
  assert.match(h, /data-action="cancelDraft"/);
  assert.match(h, /id="nm-title"[^>]*data-action="draftTitle"[^>]*value="买一点 SOL"/);
  assert.match(h, /class="to-label">To:</);
  assert.match(h, /class="to-chip">[\s\S]*Gravit</);
  assert.match(h, /data-action="toggleDraftGroup"/);
  assert.match(h, /class="limit-label">附一份额度</);
  assert.match(h, /data-action="draftLimit" data-key="perOrder">每单 \$25/);
  assert.match(h, /data-key="until">到 Oct 15/);
  assert.match(h, /data-key="venue">在 Stand-in Exchange/);
  assert.match(h, /data-action="toggleDraftAttach">不附</);
  const off = renderMessagesScreen(R.toggleDraftAttach(s), NOW);
  assert.doesNotMatch(off, /data-key="perOrder"/);
  assert.match(off, /data-action="toggleDraftAttach">附上</);
  const g = R.toggleDraftGroup(s);
  assert.equal(g.draft.group, true);
  const gh = renderMessagesScreen(g, NOW);
  assert.equal(count(gh, /class="cluster-item"/g), 3, 'Gravit plus the two installed bots');
  const sent = R.send(g, { text: '两位看看 KO', now: NOW });
  assert.equal(sent.conversations[0].kind, 'group');
  assert.deepEqual(sent.conversations[0].members, ['gravit', 'politician', 'buffett']);
});

test('F6: no conversations → the empty state with three suggestion chips', () => {
  const s = { ...seed(NOW), conversations: [], route: { screen: 'messages', id: null } };
  const h = renderMessagesScreen(s, NOW);
  assert.match(h, /class="empty-title">还没有交给 Gravit 的事</);
  assert.equal(count(h, /data-action="suggest"/g), 3);
  assert.match(h, /data-text="跟单 Pelosi"/);
  assert.match(h, /<form class="composer"/);
});

test('F8: Details drawer sections and keys', () => {
  const s = R.toggleDetails(seed(NOW));
  const h = renderMessagesScreen(s, NOW);
  assert.match(h, /<main class="main with-drawer">/);
  assert.match(h, /<aside class="drawer details" aria-label="Details">/);
  assert.match(h, /data-action="toggleDetails" aria-expanded="true"/);
  const d = renderDetails(s.conversations[0], s);
  assert.match(d, /你委托于 Oct 9 · 到 Oct 15 · intent-0003/);
  assert.match(d, /data-action="withdraw" data-conv="c-1"/);
  assert.match(d, /data-action="changeWords" data-conv="c-1"/);
  assert.match(d, /\$95/, 'what is left of the limit');
  assert.match(d, /data-action="endLimit" data-conv="c-1"/);
  assert.match(d, /Price feed/);
  assert.match(d, /href="#\/discover"/);
  assert.match(d, /0xec4c…16c1/);
  assert.match(d, /class="seg-item pressed" aria-pressed="true" data-action="setMode" data-value="Guard"/);
  assert.match(d, /class="btn-danger" data-action="stopGravit" data-conv="c-1"/);
  const none = renderDetails({ ...s.conversations[2] }, s);
  assert.match(none, /没附额度/);
  const renamed = R.rename(s, { convId: 'c-1', title: '  BTC 小仓  ' });
  assert.equal(renamed.conversations[0].title, 'BTC 小仓');
  assert.equal(R.rename(s, { convId: 'c-1', title: '  ' }), s);
});

test('banner, call, stub and the controls', () => {
  const s = seed(NOW);
  const b = renderBanner({ id: 'b', headline: 'H', body: 'B', at: NOW }, s);
  assert.match(b, /class="banner" role="status"/);
  assert.match(b, />突发</);
  assert.match(b, /14:07/);
  assert.match(b, /data-action="dismissBanner" aria-label="Dismiss"/);
  assert.match(b, /href="#\/messages\/c-1"/);
  const c = renderCall({ from: 'gravit', about: '想说 BTC 的事' });
  assert.match(c, /class="call-scrim"/);
  assert.match(c, /class="key no big" data-action="answerCall" data-accept="0" aria-label="Decline"/);
  assert.match(c, /class="key yes big" data-action="answerCall" data-accept="1" aria-label="Accept"/);
  assert.match(renderStub({ screen: 'markets', id: 'NVDA' }), /Markets › NVDA/);
  assert.match(renderStub({ screen: 'trade' }), /<h1 class="head-title">Trade<\/h1>/);
  assert.equal(seg(['A', 'B'], 'B', 'pick'), '<div class="seg"><button type="button" class="seg-item" aria-pressed="false" data-action="pick" data-value="A">A</button><button type="button" class="seg-item pressed" aria-pressed="true" data-action="pick" data-value="B">B</button></div>');
  assert.match(segLinks([['Portfolio', '#/account/portfolio', 'portfolio'], ['Memory', '#/account/memory', 'memory']], 'memory'), /class="seg-item pressed" aria-current="page" href="#\/account\/memory"/);
  assert.equal(kv([['For', '<b>x</b>']]), '<div class="kv-list"><div class="kv"><span class="kv-k">For</span><span class="kv-v"><b>x</b></span></div></div>');
  assert.equal(sec('怎么付', ['<免费>']), '<div class="dsec"><div class="dsec-label">怎么付</div><div class="dsec-line">&lt;免费&gt;</div></div>');
  assert.match(renderComposer({ placeholder: 'x', above: '<i>a</i>' }), /<form class="composer" data-action="send"><i>a<\/i>/);
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd gravit-ui && node --test tests/messages-screen.test.js`
Expected: FAIL — `Cannot find module '../js/render/messages.js'`

- [ ] **Step 3: Add the two reducers and the group draft to `js/reducers/messages.js`**

In `reducers/messages.js` add the import and the two actions, and change the `send` branch that builds a conversation:

```js
// at the top, with the other imports
import { byId } from '../data/plugins.js';
```

```js
// inside `export const reducers = {` after toggleDraftAttach:
  toggleDraftGroup: s => (s.draft ? { ...s, draft: { ...s.draft, group: !s.draft.group } } : s),
  rename(s, { convId, title }) {
    const t = (title ?? '').trim();
    if (!t) return s;
    return upd(s, convId, c => ({ ...c, title: t }));
  },
```

```js
// inside send(): replace the `const made = newConversation(s, { ... })` call with
      const bots = d.group ? s.plugins.installed.filter(id => byId(id, s.plugins.uploaded)?.kind === 'Bots') : [];
      const members = ['gravit', ...bots];
      const made = newConversation(s, {
        title: d.title.trim() || (clean.length > 24 ? clean.slice(0, 24) + '…' : clean),
        kind: members.length > 1 ? 'group' : 'gravit', members, plugins: bots, now,
        until: d.limit?.until ?? now + 6 * DAY,
        intentLimit: d.attach && d.limit ? { perOrder: d.limit.perOrder, total: d.limit.total, spent: 0, venue: d.limit.venue } : null,
      });
```

- [ ] **Step 4: Write controls.js and messages.js**

```js
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
```

```js
// gravit-ui/js/render/messages.js — the Messages screen in its states: a conversation (F1/F14), new (F7), empty (F6), Details (F8); the banner and the call
import { esc, attrs, cls, money } from '../html.js';
import { icon } from '../icons.js';
import { fmtDate, fmtClock } from '../time.js';
import { byId } from '../data/plugins.js';
import { avatar, cluster } from './avatars.js';
import { renderThread, chip } from './thread.js';
import { senderName } from './rail.js';
import { seg, kv } from './controls.js';

export function currentConversation(state) {
  const id = state.route.screen === 'messages' ? state.route.id : null;
  return state.conversations.find(c => c.id === id) ?? state.conversations[0] ?? null;
}

export function renderComposer({ placeholder = 'Tell Gravit…', above = '' } = {}) {
  return `<form class="composer" data-action="send">${above}<div class="composer-pill">` +
    `<button type="button" class="round-key" aria-label="Add a file">${icon('plus', 14, 2.4)}</button>` +
    `<label for="say" class="sr-only">Tell Gravit</label><input id="say" class="composer-input" type="text" autocomplete="off"${attrs({ placeholder })}>` +
    `<button type="button" class="round-key" aria-label="Voice input">${icon('mic', 14, 2.2)}</button>` +
    `<button type="submit" class="send-key" aria-label="Sign and send">${icon('send', 18, 2.4)}</button></div></form>`;
}

const STATUS = { working: ['Working', 'up'], done: ['Done', 'grey'], stopped: ['Stopped', 'down'], withdrawn: ['Withdrawn', 'grey'] };

function headRight(conv, state) {
  const [label, tone] = STATUS[conv.status] ?? STATUS.working;
  return `<span class="status ${tone}"><span class="status-dot"></span>${label}</span>` +
    `<button type="button"${attrs({ class: cls('btn-sm', state.detailsOpen && 'pressed'), 'data-action': 'toggleDetails', 'aria-expanded': state.detailsOpen ? 'true' : 'false' })}>Details${icon('chevRight', 14, 2.2)}</button>`;
}

export function renderHead(conv, state) {
  if (conv.kind !== 'group') return `<header class="head"><h1 class="head-title">${esc(conv.title)}</h1>${headRight(conv, state)}</header>`;
  const names = conv.members.map(m => senderName(m, state)).join(' · ');
  return `<header class="head centered"><div class="head-right">${headRight(conv, state)}</div>${cluster(conv.members, 44, state)}` +
    `<div class="head-task">${esc(conv.title)}</div><div class="dim">${esc(names)} · ${conv.members.length} 位</div></header>`;
}

function draftHead(state) {
  const d = state.draft;
  const bots = d.group ? state.plugins.installed.filter(id => byId(id, state.plugins.uploaded)?.kind === 'Bots') : [];
  const who = d.group && bots.length ? cluster(['gravit', ...bots], 44, state) : avatar('gravit', 44);
  const toChips = ['gravit', ...bots].map(m => `<span class="to-chip">${avatar(m, 20, state)}${esc(senderName(m, state))}</span>`).join('');
  return `<header class="head centered draft"><button type="button" class="btn-sm head-cancel" data-action="cancelDraft">Cancel</button>${who}` +
    `<label for="nm-title" class="sr-only">这件事叫什么</label><input id="nm-title" class="title-input" type="text" autocomplete="off" placeholder="这件事叫什么（不填就用你第一句话）" data-action="draftTitle"${attrs({ value: d.title })}>` +
    `<div class="to-line"><span class="to-label">To:</span>${toChips}<button type="button" class="to-add" data-action="toggleDraftGroup" aria-pressed="${d.group ? 'true' : 'false'}">${icon('plus', 11, 2.4)}${d.group ? '只跟 Gravit' : '加个 bot，就成群聊'}</button></div></header>`;
}

function limitRow(d) {
  const chips = [['perOrder', `每单 $${d.limit.perOrder}`], ['total', `总 $${d.limit.total}`], ['until', `到 ${fmtDate(d.limit.until)}`], ['venue', `在 ${d.limit.venue}`]];
  return `<div class="limit-row"><span class="limit-label">附一份额度</span>` +
    (d.attach ? chips.map(([k, t]) => `<button type="button" class="chip white" data-action="draftLimit" data-key="${k}">${esc(t)} ▾</button>`).join('') : '') +
    `<button type="button" class="limit-off" data-action="toggleDraftAttach">${d.attach ? '不附' : '附上'}</button></div>`;
}

function draftScreen(state) {
  return `<main class="main">${draftHead(state)}<div class="thread" id="thread"></div>${renderComposer({ above: limitRow(state.draft) })}</main>`;
}

function emptyScreen() {
  const chips = ['小仓位买 BTC', '跟单 Pelosi', '查一个地址'].map(t => `<button type="button" class="btn-sm" data-action="suggest"${attrs({ 'data-text': t })}>${esc(t)}</button>`).join('');
  return `<main class="main"><header class="head"><h1 class="head-title">Gravit</h1></header><div class="empty">${avatar('gravit', 56)}` +
    `<div class="empty-title">还没有交给 Gravit 的事</div><div class="empty-line">在下面说一句你想让它做的事，或者点左上角的 + 先起个名。</div><div class="suggest">${chips}</div></div>${renderComposer()}</main>`;
}

export function renderDetails(conv, state) {
  const L = conv.intent.limit;
  const plugs = conv.plugins.map(id => byId(id, state.plugins.uploaded)?.name ?? id);
  const w = state.account.wallet;
  const limit = L
    ? kv([['每单', money(L.perOrder)], ['总额', money(L.total)], ['剩余', money(L.total - L.spent)], ['在', esc(L.venue)]])
    : '<div class="dim">没附额度</div>';
  return `<aside class="drawer details" aria-label="Details">
  <div class="drawer-head"><h2>Details</h2><button type="button" class="close-key" data-action="toggleDetails" aria-label="Close">×</button></div>
  <div class="drawer-body">
    <section class="dsec"><div class="dsec-label">这件事</div><div class="dsec-title">${esc(conv.title)}</div><div class="dim">你委托于 ${fmtDate(conv.intent.created)} · 到 ${fmtDate(conv.intent.until)} · ${esc(conv.intent.id)}</div>
      <div class="btn-row"><button type="button" class="btn-sm" data-action="changeWords" data-conv="${conv.id}">Change words</button><button type="button" class="btn-sm" data-action="withdraw" data-conv="${conv.id}">Withdraw</button></div></section>
    <section class="dsec"><div class="dsec-label">额度</div>${limit}
      <div class="btn-row"><button type="button" class="btn-sm" data-action="changeLimit" data-conv="${conv.id}">Change limit</button><button type="button" class="btn-sm" data-action="endLimit" data-conv="${conv.id}">End limit</button></div></section>
    <section class="dsec"><div class="dsec-label">插件</div>${plugs.length ? plugs.map(n => `<div class="dsec-line">${esc(n)}</div>`).join('') : '<div class="dim">没有</div>'}<a class="link" href="#/discover">Find more in Discover ›</a></section>
    <section class="dsec"><div class="dsec-label">Gravit 的钱包</div>${kv([['USDC', money(w.usdc)], ['链', esc(w.chain)], ['地址', `<span class="mono">${esc(w.address)}</span>`]])}
      <div class="btn-row"><button type="button" class="btn-sm">Top up…</button><button type="button" class="btn-sm">Take back…</button></div></section>
    <section class="dsec"><div class="dsec-label">模式</div>${seg(['Guard', 'Beast'], state.account.mode === 'beast' ? 'Beast' : 'Guard', 'setMode')}</section>
    <section class="dsec"><button type="button" class="btn-danger" data-action="stopGravit" data-conv="${conv.id}">Stop Gravit</button></section>
  </div>
</aside>`;
}

export function renderMessagesScreen(state, now) {
  if (state.draft) return draftScreen(state);
  const conv = currentConversation(state);
  if (!conv) return emptyScreen();
  const placeholder = conv.kind === 'group' ? 'Tell Gravit… 打 @ 点名一个 bot' : 'Tell Gravit…';
  return `<main class="${cls('main', state.detailsOpen && 'with-drawer')}">${renderHead(conv, state)}<div class="thread" id="thread">${renderThread(conv, state, now)}</div>${renderComposer({ placeholder })}${state.detailsOpen ? renderDetails(conv, state) : ''}</main>`;
}

export function renderBanner(b, state) {
  const first = state.conversations[0]?.id ?? '';
  return `<div class="banner" role="status"><div class="banner-head">${chip('突发', 'down')}<span class="dim">${fmtClock(b.at)}</span><span class="spacer"></span><button type="button" class="close-key small" data-action="dismissBanner" aria-label="Dismiss">×</button></div>` +
    `<div class="card-title">${esc(b.headline)}</div><div class="dim">${esc(b.body)}</div><a class="link" href="#/messages/${esc(first)}" data-action="dismissBanner">去会话 ›</a></div>`;
}

export function renderCall(c) {
  return `<div class="call-scrim"><div class="call" role="dialog" aria-label="Gravit 来电">${avatar('gravit', 44)}<div class="card-title">Gravit 来电</div><div class="dim">${esc(c.about)}</div>` +
    `<div class="call-keys"><button type="button" class="key no big" data-action="answerCall" data-accept="0" aria-label="Decline">${icon('phoneOff', 18, 2.1)}</button>` +
    `<button type="button" class="key yes big" data-action="answerCall" data-accept="1" aria-label="Accept">${icon('phone', 18, 2.1)}</button></div></div></div>`;
}

// Markets and Trade are Linqi's pages; this pure front end only shows where a ticker would land
export function renderStub(route) {
  const title = route.screen === 'markets' ? 'Markets' : 'Trade';
  const sub = route.screen === 'markets' && route.id ? `Markets › ${esc(route.id)}` : '';
  return `<main class="main"><header class="head"><h1 class="head-title">${title}</h1></header><div class="stub">${sub ? `<div class="head-task">${sub}</div>` : ''}<div class="dim">Linqi 的页面</div></div></main>`;
}
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd gravit-ui && node --test tests/messages-screen.test.js tests/reducers.test.js`
Expected: PASS (7 + 8 tests)

- [ ] **Step 6: Commit**

```bash
git add gravit-ui/js/render/controls.js gravit-ui/js/render/messages.js gravit-ui/js/reducers/messages.js gravit-ui/tests/messages-screen.test.js
git commit -m "gravit-ui: the Messages screen in its states"
```

---

### Task 11: Discover — shelves, cards, the drawer, Installed, upload, toast

**Files:**
- Create: `gravit-ui/js/render/discover.js`
- Test: `gravit-ui/tests/discover.test.js`

**Interfaces:**
- Consumes: `esc, attrs, cls`, `icon`, `PLUGINS, SHELVES, KINDS, byId, byline, search, likeFor`, `logo`, `chip`, `kv, sec`.
- Produces: `renderDiscover(state)`, `card(p, state, opts)`, `keyFor(p, state, view)`, `pluginDrawer(p, state)`, `uploadDrawer()`, `renderToast(toast)`. Data actions: `openPlugin` (`data-id`), `install`, `uninstall`, `uninstallAsk`, `toggleInstalledOnly`, `openUpload`, `closeDrawer`, `publish` (form submit), `dismissToast`, `query` (input). Routes: `#/discover` (shelves), `#/discover/<shelfId>` (one shelf as a grid).

- [ ] **Step 1: Write the failing test**

```js
// gravit-ui/tests/discover.test.js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderDiscover, card, keyFor, pluginDrawer, uploadDrawer, renderToast } from '../js/render/discover.js';
import { byId, SHELVES } from '../js/data/plugins.js';
import { reducers as R } from '../js/reducers/index.js';
import { seed } from '../js/data/seed.js';

const NOW = new Date(2026, 9, 9, 14, 7).getTime();
const count = (h, re) => (h.match(re) ?? []).length;
const disc = (s = seed(NOW)) => R.nav(s, { screen: 'discover', id: null });

test('the store page: header with search, Installed · n, Upload; six shelves, each with See all and its cards; no price, no subtitle', () => {
  const h = renderDiscover(disc());
  assert.match(h, /<h1 class="head-title">Discover<\/h1>/);
  assert.match(h, /id="dq"[^>]*placeholder="Search plugins"[^>]*data-action="query"/);
  assert.match(h, /data-action="toggleInstalledOnly" aria-pressed="false">Installed · 5</);
  assert.match(h, /data-action="openUpload"[^>]*>[\s\S]*Upload a plugin/);
  assert.equal(count(h, /class="shelf"/g), 6);
  assert.equal(count(h, /See all ›/g), 6);
  assert.match(h, /class="shelf-title">Like</);
  assert.match(h, /href="#\/discover\/bots"/);
  assert.doesNotMatch(h, /a call|a minute|\$0\.10/);
  assert.doesNotMatch(h, /shelf-sub/);
  const like = h.slice(h.indexOf('shelf-title">Like'), h.indexOf('shelf-title">Data'));
  assert.equal(count(like, /class="pcard"/g), 4);
  assert.match(like, /Buffett bot/);
});

test('a card: 44 px logo top-left, kind top-right, name, one line, author line, one key in three states', () => {
  const s = disc();
  const h = card(byId('buffett'), s);
  assert.match(h, /^<div class="pcard" data-action="openPlugin" data-id="buffett" role="button" tabindex="0">/);
  assert.match(h, /av-portrait tone-warm/);
  assert.match(h, /class="pcard-kind">BOTS</);
  assert.match(h, /class="pcard-name">Buffett bot</);
  assert.match(h, /class="pcard-by">Free · by Gravit</);
  assert.match(keyFor(byId('buffett'), s), /class="pkey installed" data-action="uninstallAsk" data-id="buffett" aria-label="Installed · uninstall Buffett bot"/);
  assert.match(keyFor(byId('news'), s), /class="pkey install" data-action="install" data-id="news" aria-label="Install News sentiment"/);
  assert.match(keyFor(byId('buffett'), s, 'installed'), /class="pkey uninstall" data-action="uninstall" data-id="buffett"/);
  assert.match(card(byId('pairs'), s), /Free · by @you · Private/);
  assert.match(card(byId('news'), s, { pressed: true }), /class="pcard pressed"/);
});

test('the drawer: sections, the signature table inline, Install at the foot; installed shows Uninstall', () => {
  const s = R.openPlugin(disc(), 'news');
  const h = renderDiscover(s);
  assert.match(h, /<aside class="drawer" aria-label="News sentiment">/);
  assert.match(h, /class="pcard pressed" data-action="openPlugin" data-id="news"/);
  const d = pluginDrawer(byId('news'), s);
  assert.match(d, /class="dsec-label">它能被问什么</);
  assert.match(d, /class="dsec-label">它会写什么</);
  assert.match(d, /不会：动钱、付人、改额度/);
  assert.match(d, /class="dsec-label">怎么付</);
  assert.match(d, /免费。Gravit 只在模型调用和成交的单上抽成。/);
  assert.match(d, /class="dsec-label">要你什么</);
  assert.match(d, /class="dsec-label">你签的是</);
  assert.match(d, /install news/);
  assert.match(d, /Gravit · 0xec4c…16c1/);
  assert.match(d, /you uninstall/);
  assert.match(d, /class="btn-primary" data-action="install" data-id="news">Install</);
  assert.doesNotMatch(d, /签这一下/);
  const inst = pluginDrawer(byId('buffett'), s);
  assert.match(inst, /uninstall buffett/);
  assert.match(inst, /class="btn-primary" data-action="uninstall" data-id="buffett">Uninstall</);
});

test('Installed view: the pill pressed, every card with the trash key, 你上传的 for your own, the just-installed card links to its conversation', () => {
  let s = R.install(disc(), { id: 'news', now: NOW });
  s = R.toggleInstalledOnly(s);
  const h = renderDiscover(s);
  assert.match(h, /aria-pressed="true">Installed · 6</);
  assert.equal(count(h, /class="shelf"/g), 0);
  assert.equal(count(h, /class="pkey uninstall"/g), 6, 'five installed that are not yours plus the private Pairs you uploaded');
  assert.match(h, /class="grid-title">你上传的</);
  assert.match(h, /刚装好/);
  assert.match(h, /href="#\/messages\/c-5">Open in Messages ›/);
  assert.match(h, /class="toast" role="status">News sentiment 装好了/);
  assert.match(h, /class="toast-key" href="#\/messages\/c-5">Open</);
});

test('search shows a results grid; a shelf route shows that shelf as a grid with a way back', () => {
  const h = renderDiscover(R.setQuery(disc(), 'bot'));
  assert.equal(count(h, /class="shelf"/g), 0);
  assert.match(h, /class="grid-title">4 个</);
  const none = renderDiscover(R.setQuery(disc(), 'zzz'));
  assert.match(none, /class="grid-title">0 个</);
  const bots = renderDiscover(R.nav(seed(NOW), { screen: 'discover', id: 'bots' }));
  assert.match(bots, /class="grid-title">Bots</);
  assert.equal(count(bots, /class="pcard grid"/g), 4);
  assert.match(bots, /class="back-link" href="#\/discover"/);
});

test('the upload drawer is a form with the fields of the spec and the private default', () => {
  const h = renderDiscover(R.openUpload(disc()));
  assert.match(h, /<aside class="drawer" aria-label="上传一个插件">/);
  const u = uploadDrawer();
  assert.match(u, /<form class="upload-form" data-action="publish">/);
  assert.match(u, /name="name"/);
  assert.match(u, /name="blurb"/);
  assert.equal(count(u, /name="kind"/g), 5);
  assert.match(u, /name="tools"/);
  assert.equal(count(u, /name="needs"/g), 4);
  assert.match(u, /type="radio" name="visibility" value="private" checked/);
  assert.match(u, /type="radio" name="visibility" value="public"/);
  assert.match(u, /type="submit" class="btn-primary">Publish</);
  assert.doesNotMatch(u, /先过一次审/);
  assert.equal(renderToast({ text: 'x', action: null }), '<div class="toast" role="status">x<button type="button" class="toast-x" data-action="dismissToast" aria-label="Dismiss">×</button></div>');
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd gravit-ui && node --test tests/discover.test.js`
Expected: FAIL — `Cannot find module '../js/render/discover.js'`

- [ ] **Step 3: Write discover.js**

```js
// gravit-ui/js/render/discover.js — Discover as an App Store (spec §7): shelves, cards with one key, the drawer that signs, Installed, upload
import { esc, attrs, cls } from '../html.js';
import { icon } from '../icons.js';
import { PLUGINS, SHELVES, KINDS, byId, byline, search, likeFor } from '../data/plugins.js';
import { logo } from './avatars.js';
import { chip } from './thread.js';
import { kv, sec } from './controls.js';

export function keyFor(p, state, view = 'shelf') {
  const installed = state.plugins.installed.includes(p.id);
  if (!installed) return `<button type="button"${attrs({ class: 'pkey install', 'data-action': 'install', 'data-id': p.id, 'aria-label': `Install ${p.name}` })}>${icon('plus', 14, 2.4)}</button>`;
  if (view === 'installed') return `<button type="button"${attrs({ class: 'pkey uninstall', 'data-action': 'uninstall', 'data-id': p.id, 'aria-label': `Uninstall ${p.name}` })}>${icon('trash', 15, 2.1)}</button>`;
  return `<button type="button"${attrs({ class: 'pkey installed', 'data-action': 'uninstallAsk', 'data-id': p.id, 'aria-label': `Installed · uninstall ${p.name}` })}>${icon('check', 13, 2.4)}Installed</button>`;
}

export function card(p, state, { view = 'shelf', pressed = false, openIn = null } = {}) {
  const extra = openIn ? `<div class="pcard-extra">${chip('刚装好', 'up')}<a class="link" href="#/messages/${esc(openIn)}">Open in Messages ›</a></div>` : '';
  return `<div${attrs({ class: cls('pcard', pressed && 'pressed', view === 'grid' && 'grid'), 'data-action': 'openPlugin', 'data-id': p.id, role: 'button', tabindex: '0' })}>${logo(p, 44)}` +
    `<div class="pcard-body"><div class="pcard-name">${esc(p.name)}</div><div class="pcard-blurb">${esc(p.blurb)}</div><div class="pcard-by">${esc(byline(p))}</div>${extra}</div>` +
    `<div class="pcard-side"><span class="pcard-kind">${esc(p.kind.toUpperCase())}</span>${keyFor(p, state, view === 'grid' && state.discover.installedOnly ? 'installed' : 'shelf')}</div></div>`;
}

const justInstalled = state => {
  const conv = state.conversations.find(c => c.kind === 'bot' && c.title.endsWith('：怎么用我') && c.unread);
  return conv ? { id: conv.members[1], convId: conv.id } : null;
};

function shelf(s, state) {
  const ids = s.id === 'like' ? likeFor(state.memory) : s.ids;
  const cards = ids.map(id => byId(id, state.plugins.uploaded)).filter(Boolean).map(p => card(p, state, { pressed: state.discover.drawer === p.id })).join('');
  return `<section class="shelf"><div class="shelf-head"><div class="shelf-title">${esc(s.title)}</div><a class="link" href="#/discover/${s.id}">See all ›</a></div><div class="shelf-row">${cards}</div></section>`;
}

function grid(title, plugins, state, back = false) {
  const ji = justInstalled(state);
  const cards = plugins.map(p => card(p, state, { view: 'grid', pressed: state.discover.drawer === p.id, openIn: ji && ji.id === p.id ? ji.convId : null })).join('');
  return `<section class="grid-sec">${back ? '<a class="back-link" href="#/discover">‹ Discover</a>' : ''}<div class="grid-title">${esc(title)}</div><div class="grid">${cards}</div></section>`;
}

function header(state) {
  const on = state.discover.installedOnly;
  return `<div class="disc-head"><h1 class="head-title">Discover</h1>` +
    `<div class="search"><label for="dq" class="sr-only">Search plugins</label>${icon('search', 18, 2)}<input id="dq" type="search" autocomplete="off" placeholder="Search plugins" data-action="query"${attrs({ value: state.discover.query })}></div><span class="spacer"></span>` +
    `<button type="button"${attrs({ class: cls('pill', on && 'pressed'), 'data-action': 'toggleInstalledOnly', 'aria-pressed': on ? 'true' : 'false' })}>Installed · ${state.plugins.installed.length}</button>` +
    `<button type="button" class="pill" data-action="openUpload">${icon('upload', 14, 2.2)}Upload a plugin</button></div>`;
}

export function pluginDrawer(p, state) {
  const installed = state.plugins.installed.includes(p.id);
  const meta = [p.kind, `by ${p.by}`, 'Free', p.installs ? `${p.installs} 装了` : null].filter(Boolean).join(' · ');
  const writes = [...p.writes.map(esc), ...(p.never.length ? [`<span class="dim">不会：${esc(p.never.join('、'))}</span>`] : [])];
  return `<aside class="drawer"${attrs({ 'aria-label': p.name })}><div class="drawer-head"><h2>${esc(p.name)}</h2><button type="button" class="close-key" data-action="closeDrawer" aria-label="Close">×</button></div><div class="drawer-body">` +
    `<div class="plug-id">${logo(p, 56)}<div><div class="plug-name">${esc(p.name)}</div><div class="dim">${esc(meta)}</div></div></div><p class="plug-blurb">${esc(p.blurb)}。</p>` +
    sec('它能被问什么', p.asks.length ? p.asks : ['（它还没写）']) + sec('它会写什么', writes.length ? writes : ['（它还没写）'], true) +
    sec('怎么付', ['免费。Gravit 只在模型调用和成交的单上抽成。']) + sec('要你什么', [p.needs]) +
    `<div class="dsec"><div class="dsec-label">你签的是</div>${kv([['What you sign', `<b>${installed ? 'uninstall' : 'install'} ${esc(p.id)}</b>`], ['For', `Gravit · ${esc(state.account.wallet.address)}`], ['May', 'read Portfolio · propose in your limit'], ['May not', 'pay anyone · move money'], ['Until', 'you uninstall']])}</div>` +
    `<div class="drawer-foot">${installed ? `<button type="button" class="btn-primary" data-action="uninstall" data-id="${esc(p.id)}">Uninstall</button>` : `<button type="button" class="btn-primary" data-action="install" data-id="${esc(p.id)}">Install</button>`}</div></div></aside>`;
}

const radios = (name, items, checked) => items.map(v => `<label class="radio-item"><input type="radio" name="${name}" value="${esc(v)}"${v === checked ? ' checked' : ''}><span>${esc(v)}</span></label>`).join('');

export function uploadDrawer() {
  return `<aside class="drawer" aria-label="上传一个插件"><div class="drawer-head"><h2>上传一个插件</h2><button type="button" class="close-key" data-action="closeDrawer" aria-label="Close">×</button></div><div class="drawer-body">` +
    `<form class="upload-form" data-action="publish">` +
    `<div class="field"><label class="field-label" for="up-name">名字</label><input id="up-name" class="input" name="name" type="text" required placeholder="Pairs"></div>` +
    `<div class="field"><label class="field-label" for="up-blurb">一句话</label><input id="up-blurb" class="input" name="blurb" type="text" placeholder="两只相关股的价差回归，给出配对信号"></div>` +
    `<div class="field"><span class="field-label">类型</span><div class="radio-seg">${radios('kind', KINDS, 'Quant')}</div></div>` +
    `<div class="field"><label class="field-label" for="up-tools">它暴露的工具 · 一个 MCP server</label><textarea id="up-tools" class="textarea" name="tools" rows="2" placeholder="pairs.scan(universe)\npairs.signal(a, b)"></textarea></div>` +
    `<div class="field"><span class="field-label">要用户什么</span><div class="picks">${radios('needs', ['没有', 'Telegram 会话', '交易所 key', '钱包地址'], '没有')}</div></div>` +
    `<div class="field"><span class="field-label">放哪</span><div class="radio-seg">${radios('visibility', ['private', 'public'], 'private').replace('>private<', '>只给我自己 · Private<').replace('>public<', '>放进 Public shop<')}</div></div>` +
    `<div class="btn-row grow"><button type="button" class="btn" data-action="closeDrawer">Cancel</button><button type="submit" class="btn-primary">Publish</button></div></form></div></aside>`;
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
    body = grid('装了的', installed, state) + (mine.length ? grid('你上传的', mine, state) : '');
  } else if (state.route.id) {
    const s = SHELVES.find(x => x.id === state.route.id);
    const ids = s ? (s.id === 'like' ? likeFor(state.memory) : s.ids) : [];
    body = grid(s?.title ?? 'Discover', ids.map(id => byId(id, state.plugins.uploaded)).filter(Boolean), state, true);
  } else {
    body = SHELVES.map(s => shelf(s, state)).join('');
  }
  const drawer = d.upload ? uploadDrawer() : d.drawer ? pluginDrawer(byId(d.drawer, state.plugins.uploaded) ?? { id: d.drawer, name: d.drawer, kind: '', blurb: '', by: '', installs: '', logo: { type: 'letter', text: '?' }, asks: [], writes: [], never: [], needs: '' }, state) : '';
  const toast = d.toast ? renderToast(d.toast) : '';
  return `<main class="${cls('main', 'disc', (d.upload || d.drawer) && 'with-drawer')}">${header(state)}${body}${drawer}${toast}</main>`;
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd gravit-ui && node --test tests/discover.test.js`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add gravit-ui/js/render/discover.js gravit-ui/tests/discover.test.js
git commit -m "gravit-ui: Discover as a store with its drawer, Installed and upload"
```

---

### Task 12: Account — Portfolio, Venues, Memory, Settings

**Files:**
- Create: `gravit-ui/js/render/account.js`
- Test: `gravit-ui/tests/account.test.js`

**Interfaces:**
- Consumes: `esc, attrs, cls, money`, `icon`, `fmtDate`, `chip, ticker`, `seg, segLinks, kv`.
- Produces: `renderAccount(state)`, `renderMemory(state)`, `renderSettings(state)`. Data actions: `setMode` (`data-value`), `openSettings`, `closeSettings`, `setTheme` (`data-value`), `resetDemo`, `addMemory` (form submit), `editMemory` (`data-id`), `forgetMemory` (`data-id`), `forgetAll`, `memorySwitch` (`data-key`, `aria-checked`), `exportMemory`.

- [ ] **Step 1: Write the failing test**

```js
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
  assert.equal(count(h, /class="holding"/g), 3);
  assert.match(h, /class="ticker" href="#\/markets\/BTC"/);
  assert.match(h, /class="up">\+1\.2%</);
  assert.match(h, /class="down">−0\.4%</);
  assert.doesNotMatch(h, /同源嵌进来/);
});

test('Venues: four venues with their state chips and Connect an account', () => {
  const h = renderAccount(acct('venues'));
  assert.equal(count(h, /class="venue"/g), 4);
  assert.equal(count(h, /class="chip up">Healthy</g), 3);
  assert.match(h, /class="chip grey">Not served here</);
  assert.match(h, /class="btn-primary">Connect an account</);
});

test('Memory: entries grouped with their source and two keys, the add box, where it is used, three switches, Export and Forget all', () => {
  const s = acct('memory');
  const h = renderAccount(s);
  assert.match(h, /class="seg-item pressed" aria-current="page" href="#\/account\/memory"/);
  const m = renderMemory(s);
  assert.deepEqual([...m.matchAll(/class="mem-label">([^<]+)</g)].map(x => x[1]), ['风格', '规矩', '场所和人']);
  assert.equal(count(m, /class="mem-entry"/g), 9);
  assert.match(m, /class="mem-text">偏价值，不追热点<\/div><div class="mem-source">你说的 · Oct 2</);
  assert.equal(count(m, /data-action="editMemory" data-id="mem-\d+"/g), 9);
  assert.equal(count(m, /data-action="forgetMemory" data-id="mem-\d+"/g), 9);
  assert.match(m, /<form class="mem-add" data-action="addMemory">/);
  assert.match(m, /placeholder="加一条它该记住的…"/);
  assert.match(m, /class="chip grey">Discover</);
  assert.match(m, /role="switch" aria-checked="true" data-action="memorySwitch" data-key="remember"/);
  assert.match(m, /role="switch" aria-checked="false" data-action="memorySwitch" data-key="askFirst"/);
  assert.match(m, /data-key="botsRead"/);
  assert.match(m, /data-action="exportMemory"/);
  assert.match(m, /class="btn-danger" data-action="forgetAll"/);
  assert.doesNotMatch(m, /没有回收站/);
  assert.doesNotMatch(m, /关了它就只用/);
  const empty = renderMemory(R.forgetAll(s));
  assert.equal(count(empty, /class="mem-entry"/g), 0);
  const added = renderMemory(R.addMemory(s, { text: '周五不开新仓', now: NOW }));
  assert.match(added, /class="mem-label">你加的</);
});

test('Settings drawer: theme seg and Reset demo', () => {
  const s = R.openSettings(acct());
  const h = renderAccount(s);
  assert.match(h, /<main class="main with-drawer">/);
  const d = renderSettings(s);
  assert.match(d, /<aside class="drawer" aria-label="Settings">/);
  assert.match(d, /class="seg-item pressed" aria-pressed="true" data-action="setTheme" data-value="System"/);
  assert.match(d, /data-action="setTheme" data-value="Black"/);
  assert.match(d, /class="btn-danger" data-action="resetDemo"/);
  const black = renderSettings(R.setTheme(s, 'black'));
  assert.match(black, /class="seg-item pressed" aria-pressed="true" data-action="setTheme" data-value="Black"/);
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd gravit-ui && node --test tests/account.test.js`
Expected: FAIL — `Cannot find module '../js/render/account.js'`

- [ ] **Step 3: Write account.js**

```js
// gravit-ui/js/render/account.js — Account (spec §8): Linqi's Portfolio and Venues, and Memory as the third segment; the Settings drawer
import { esc, attrs, cls, money } from '../html.js';
import { icon } from '../icons.js';
import { fmtDate } from '../time.js';
import { chip, ticker } from './thread.js';
import { seg, segLinks } from './controls.js';

const box = (inner, extra = '') => `<section class="${cls('cardbox', extra)}">${inner}</section>`;

function portfolio(a) {
  const alloc = a.alloc.map(x => `<span class="alloc-seg alloc-${x.token}" style="flex:${x.pct}"></span>`).join('');
  const legend = a.alloc.map(x => `<span>${esc(x.name)} ${x.pct}%</span>`).join('');
  const rows = a.holdings.map(h => `<div class="holding"><span>${ticker(h.name)}<span class="dim"> · ${esc(h.venue)}</span></span><span class="num">${money(h.value)}</span>` +
    `<span class="${h.chg == null ? 'dim' : h.chg >= 0 ? 'up' : 'down'}">${h.chg == null ? '—' : (h.chg >= 0 ? '+' : '−') + Math.abs(h.chg).toFixed(1) + '%'}</span></div>`).join('');
  return `<div class="cards">` + box(`<div class="dim">Net worth</div><div class="networth">${money(a.netWorth)}</div><div class="delta"><span class="up">+${money(a.today)} · ${a.todayPct}%</span><span class="dim">today</span></div>` +
    `<div class="spark"></div><div class="alloc-bar">${alloc}</div><div class="alloc-legend">${legend}</div><div class="holdings">${rows}</div>` +
    `<div class="btn-row"><button type="button" class="btn-sm">Move</button><button type="button" class="btn-sm">Receive</button><button type="button" class="btn-sm">Statement</button></div>`) + `</div>`;
}

function venues(a) {
  const rows = a.venues.map(v => `<div class="venue"><span><b>${esc(v.name)}</b><br><span class="dim">${esc(v.line)}</span></span>${chip(v.state, v.state === 'Healthy' ? 'up' : 'grey')}</div>`).join('');
  return `<div class="cards">` + box(`<div class="card-head"><div class="cardbox-title">Venues</div></div><div class="venues">${rows}</div><button type="button" class="btn-primary">Connect an account</button>`) + `</div>`;
}

const switchRow = (label, key, on) => `<div class="switch-row"><div class="switch-label">${esc(label)}</div>` +
  `<button type="button"${attrs({ class: cls('switch', on && 'on'), role: 'switch', 'aria-checked': on ? 'true' : 'false', 'aria-label': label, 'data-action': 'memorySwitch', 'data-key': key })}><span class="knob"></span></button></div>`;

export function renderMemory(state) {
  const M = state.memory;
  const groups = [...new Set(M.entries.map(e => e.group))];
  const list = groups.map(g => `<div class="mem-group"><div class="mem-label">${esc(g)}</div>` + M.entries.filter(e => e.group === g).map(e =>
    `<div class="mem-entry"><div class="mem-body"><div class="mem-text">${esc(e.text)}</div><div class="mem-source">${esc(e.source)} · ${fmtDate(e.at)}</div></div>` +
    `<div class="mem-keys"><button type="button" class="small-key" data-action="editMemory" data-id="${esc(e.id)}" aria-label="Edit">${icon('pencil', 13, 2.2)}</button>` +
    `<button type="button" class="small-key danger" data-action="forgetMemory" data-id="${esc(e.id)}" aria-label="Forget">${icon('trash', 13, 2.2)}</button></div></div>`).join('') + `</div>`).join('');
  const left = box(`<div class="card-head"><div class="cardbox-title">Gravit 记得的你</div><span class="dim">${M.entries.length} 条 · 只在这台机器上</span></div>${list}` +
    `<form class="mem-add" data-action="addMemory"><label for="mem-new" class="sr-only">加一条</label><input id="mem-new" class="input" name="text" type="text" autocomplete="off" placeholder="加一条它该记住的…"><button type="submit" class="btn-primary small">Add</button></form>`);
  const where = [['Discover', 'Like 货架按风格推：价值 → Buffett、研报、政客 bot'], ['早报', '挑什么给你看，什么时候发'], ['新会话', '默认附的额度、默认的场所'], ['群聊', '谁先说、谁的话该打折']]
    .map(([k, v]) => `<div class="where-row">${chip(k, 'grey')}<span>${esc(v)}</span></div>`).join('');
  const right = box(`<div class="cardbox-title">它用在哪</div><div class="where">${where}</div>`) +
    box(`<div class="cardbox-title">开关</div>${switchRow('让 Gravit 记新东西', 'remember', M.remember)}${switchRow('它学到的先问我再记', 'askFirst', M.askFirst)}${switchRow('群聊里的 bot 也能看 Memory', 'botsRead', M.botsRead)}` +
      `<div class="btn-row"><button type="button" class="btn-sm" data-action="exportMemory">Export</button><button type="button" class="btn-danger" data-action="forgetAll">Forget all</button></div>`);
  return `<div class="cards two">${left}<div class="stack">${right}</div></div>`;
}

export function renderSettings(state) {
  const theme = { cream: 'Cream', black: 'Black' }[state.theme] ?? 'System';
  return `<aside class="drawer" aria-label="Settings"><div class="drawer-head"><h2>Settings</h2><button type="button" class="close-key" data-action="closeSettings" aria-label="Close">×</button></div><div class="drawer-body">` +
    `<div class="dsec"><div class="dsec-label">Theme</div>${seg(['Cream', 'Black', 'System'], theme, 'setTheme')}</div>` +
    `<div class="dsec"><div class="dsec-label">Demo</div><button type="button" class="btn-danger" data-action="resetDemo">Reset demo</button></div></div></aside>`;
}

export function renderAccount(state) {
  const tab = state.route.tab ?? 'portfolio';
  const a = state.account;
  const head = `<div class="acct-head"><h1 class="head-title">Account</h1><span class="spacer"></span>${seg(['Guard', 'Beast'], a.mode === 'beast' ? 'Beast' : 'Guard', 'setMode')}${chip('Trading on · $100 a move', 'up')}<button type="button" class="pill" data-action="openSettings">Settings</button></div>`;
  const tabs = segLinks([['Portfolio', '#/account/portfolio', 'portfolio'], ['Venues', '#/account/venues', 'venues'], ['Memory', '#/account/memory', 'memory']], tab);
  const body = tab === 'venues' ? venues(a) : tab === 'memory' ? renderMemory(state) : portfolio(a);
  return `<main class="${cls('main', 'acct', state.settingsOpen && 'with-drawer')}">${head}${tabs}${body}${state.settingsOpen ? renderSettings(state) : ''}</main>`;
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd gravit-ui && node --test tests/account.test.js`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add gravit-ui/js/render/account.js gravit-ui/tests/account.test.js
git commit -m "gravit-ui: Account with Portfolio, Venues, Memory and Settings"
```

---

### Task 13: The stylesheet

**Files:**
- Create: `gravit-ui/css/app.css`
- Test: `gravit-ui/tests/css.test.js` (every class a render module emits has a rule)

**Interfaces:**
- Consumes: the class names emitted by Tasks 8–12 and the `data-theme` tokens of Task 1.
- Produces: `css/app.css`, the only stylesheet besides tokens; no hex colours, only `var(--…)`.

- [ ] **Step 1: Write the failing test**

```js
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd gravit-ui && node --test tests/css.test.js`
Expected: FAIL — `ENOENT … css/app.css`

- [ ] **Step 3: Write app.css**

```css
/* gravit-ui/css/app.css — every class the render modules emit; numbers from the spec (§3–§8), colours only by token */
*, *::before, *::after { box-sizing: border-box; }
html, body { margin: 0; background: var(--bg); color: var(--text); font: 15px/1.45 var(--font-sans); }
body { min-height: 100vh; -webkit-font-smoothing: antialiased; }
button, input, textarea { font: inherit; color: inherit; }
button { cursor: pointer; }
a { color: inherit; text-decoration: none; }
h1, h2 { margin: 0; font-weight: 700; letter-spacing: -0.01em; }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
.dim { color: var(--dim); font-size: 13px; }
.num { font-variant-numeric: tabular-nums; }
.mono { font-family: var(--font-mono); font-size: 13px; }
.up { color: var(--up); font-weight: 700; }
.down { color: var(--down); font-weight: 700; }
.spacer { flex: 1 1 auto; }
.link { color: var(--blue); font-size: 13px; font-weight: 600; }
.ticker { display: inline-flex; align-items: center; gap: 2px; color: var(--blue); font-weight: 700; }
.ticker-lead { font-size: 15px; }

/* ---- the app frame: rail + main ---- */
.app { display: flex; flex-wrap: wrap; min-height: 100vh; }
.rail { flex: 0 0 var(--rail); min-width: 0; max-width: 100%; display: flex; flex-direction: column; gap: 18px; padding: 24px 16px; background: var(--rail-bg); border-right: 1px solid var(--border); }
.main { flex: 999 1 560px; min-width: 0; position: relative; display: flex; flex-direction: column; min-height: 100vh; }
.main.with-drawer { overflow: hidden; }
.brand { display: flex; align-items: center; gap: 10px; padding: 0 12px; }
.brand-name { font-size: 22px; font-weight: 800; letter-spacing: -0.02em; }
.rail-group { display: flex; flex-direction: column; gap: 4px; }
.rail-head { display: flex; align-items: center; min-height: 44px; padding: 0 0 0 12px; gap: 12px; font-weight: 500; color: var(--dim); }
.rail-head-label { flex: 1 1 auto; }
.rail-head-keys { display: inline-flex; gap: 2px; }
.icon-key { display: inline-flex; align-items: center; justify-content: center; width: 44px; min-height: 44px; border: 0; background: transparent; border-radius: var(--radius-s); color: var(--dim); }
.icon-key:hover { background: var(--hover); }
.row { display: flex; align-items: center; gap: 10px; min-height: 64px; padding: 8px 10px; border-radius: var(--radius-s); color: var(--text); }
.row:hover { background: var(--hover); }
.row.current { background: var(--surface-2); }
.dot { flex: 0 0 8px; width: 8px; height: 8px; border-radius: var(--radius-pill); background: transparent; }
.dot.on { background: var(--blue); }
.row-body { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.row-top { display: flex; align-items: baseline; gap: 8px; }
.row-title { flex: 1 1 auto; min-width: 0; font-size: 14px; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.row-time { font-size: 11px; color: var(--dim); white-space: nowrap; font-variant-numeric: tabular-nums; }
.row-preview { font-size: 12px; color: var(--dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.nav-item { display: flex; align-items: center; gap: 12px; min-height: 44px; padding: 0 12px; border-radius: var(--radius-s); color: var(--dim); font-weight: 500; }
.nav-item:hover { background: var(--hover); }
.nav-item.current { background: var(--surface-2); color: var(--text); font-weight: 700; }
.rail-foot { margin-top: auto; display: flex; flex-direction: column; gap: 14px; }
.rail-lines { display: flex; gap: 8px; }
.line-key { flex: 1 1 0; display: inline-flex; align-items: center; justify-content: center; min-height: 44px; border: 1px solid var(--border); border-radius: var(--radius-s); background: var(--surface); color: var(--dim); }
.account { display: flex; align-items: center; gap: 12px; min-height: 56px; padding: 8px 12px; border: 1px solid var(--border); border-radius: var(--radius-s); background: var(--surface); color: var(--text); }
.account.current { border-color: var(--rule); background: var(--surface-2); }
.account-body { display: flex; flex-direction: column; line-height: 1.25; }
.account-title { font-size: 14px; font-weight: 600; }
.account.current .account-title { font-weight: 700; }
.account-line { font-size: 12px; color: var(--dim); font-variant-numeric: tabular-nums; }

/* ---- avatars ---- */
.av { flex: 0 0 auto; display: inline-flex; align-items: center; justify-content: center; border-radius: var(--radius-pill); font-weight: 800; overflow: hidden; }
.av-you { border: 1.5px solid var(--text); font-weight: 700; }
.av-g { background: var(--primary); color: var(--on-primary); }
.av-letter.tone-grey { background: var(--surface-2); color: var(--text); }
.av-letter.tone-blue { background: var(--blue); color: var(--on-blue); }
.av-letter.tone-ink { background: var(--primary); color: var(--on-primary); }
.av-portrait { align-items: flex-end; }
.av-portrait svg { width: 100%; height: 100%; }
.av-portrait.tone-warm { background: var(--warn-fill); color: var(--warn-text); }
.av-portrait.tone-green { background: var(--up-fill); color: var(--up); }
.av-glyph { background: var(--surface-2); color: var(--text); }
.av-draft { width: 36px; height: 36px; border: 1.5px dashed var(--dim); color: var(--dim); font-size: 18px; font-weight: 700; }
.cluster { display: inline-flex; align-items: center; }
.cluster-item { display: inline-flex; border: 2px solid var(--bg); border-radius: var(--radius-pill); }
.cluster-item + .cluster-item { margin-left: -12px; }
.group-mark { flex: 0 0 auto; position: relative; display: inline-block; }
.group-a { position: absolute; left: 0; top: 0; }
.group-b { position: absolute; right: 0; bottom: 0; border: 2px solid var(--rail-bg); border-radius: var(--radius-pill); display: inline-flex; }

/* ---- heads ---- */
.head { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; padding: 22px 28px 16px; border-bottom: 1px solid var(--border); }
.head-title { font-size: 20px; flex: 1 1 320px; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.head.centered { position: relative; flex-direction: column; gap: 4px; padding: 16px 28px 12px; }
.head.centered .head-title { flex: none; }
.head-right { position: absolute; right: 28px; top: 16px; display: flex; align-items: center; gap: 8px; }
.head-task { font-size: 17px; font-weight: 700; letter-spacing: -0.01em; margin-top: 2px; }
.head.draft { padding-top: 18px; }
.head-cancel { position: absolute; right: 28px; top: 18px; }
.title-input { width: min(560px, 100%); height: 36px; border: 0; background: transparent; text-align: center; font-size: 17px; font-weight: 700; letter-spacing: -0.01em; outline: none; }
.title-input::placeholder { color: var(--dim); }
.to-line { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; justify-content: center; font-size: 12px; color: var(--dim); }
.to-label { font-weight: 600; }
.to-chip { display: inline-flex; align-items: center; gap: 6px; padding: 2px 10px 2px 3px; border-radius: var(--radius-pill); background: var(--surface-2); color: var(--text); font-weight: 600; }
.to-add { display: inline-flex; align-items: center; gap: 4px; min-height: 26px; padding: 0 10px; border: 1px dashed var(--dim); border-radius: var(--radius-pill); background: transparent; color: var(--dim); font-size: 12px; }
.status { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 600; border: 1px solid var(--card-border); border-radius: var(--radius-pill); padding: 2px 10px; }
.status.up { background: var(--up-fill); color: var(--up); }
.status.grey { background: var(--surface-2); color: var(--dim); }
.status.down { background: var(--down-fill); color: var(--down); }
.status-dot { width: 7px; height: 7px; border-radius: var(--radius-pill); background: currentColor; }

/* ---- buttons, pills, chips, segs ---- */
.btn, .btn-sm, .btn-primary, .btn-danger, .pill { display: inline-flex; align-items: center; justify-content: center; gap: 6px; border: 0; border-radius: var(--radius-pill); font-size: 13px; white-space: nowrap; }
.btn { min-height: 44px; padding: 0 18px; background: var(--surface-2); color: var(--text); font-size: 15px; }
.btn-sm, .pill { min-height: 36px; padding: 0 14px; background: var(--surface-2); color: var(--text); }
.btn-sm.pressed, .pill.pressed { background: var(--primary); color: var(--on-primary); }
.btn-primary { min-height: 44px; padding: 0 18px; background: var(--primary); color: var(--on-primary); font-size: 15px; font-weight: 600; }
.btn-primary.small { min-height: 40px; padding: 0 16px; font-size: 14px; }
.btn-danger { min-height: 36px; padding: 0 14px; background: var(--down-fill); color: var(--down); font-weight: 600; }
.btn-row { display: flex; gap: 8px; flex-wrap: wrap; }
.btn-row.grow > * { flex: 1 1 0; }
.chip { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 600; border-radius: var(--radius-pill); padding: 2px 10px; }
.chip.grey { background: var(--surface-2); color: var(--dim); }
.chip.up { background: var(--up-fill); color: var(--up); }
.chip.down { background: var(--down-fill); color: var(--down); }
.chip.warn { background: var(--warn-fill); color: var(--warn-text); }
.chip.white { background: var(--surface); color: var(--text); border: 1px solid var(--card-border); }
.bubble.green .chip.up { background: var(--surface); }
.seg { display: inline-flex; gap: 2px; padding: 3px; border-radius: var(--radius-pill); background: var(--surface-2); align-self: flex-start; }
.seg-item { display: inline-flex; align-items: center; min-height: 38px; padding: 0 14px; border: 0; border-radius: var(--radius-pill); background: transparent; color: var(--dim); font-size: 13px; font-weight: 600; }
.seg-item.pressed { background: var(--surface); color: var(--text); font-weight: 700; box-shadow: var(--shadow-card); }

/* ---- the thread ---- */
.thread { flex: 1 1 auto; display: flex; flex-direction: column; gap: 6px; padding: 18px 28px 22px; overflow-y: auto; }
.divider { text-align: center; font-size: 11px; font-weight: 600; color: var(--dim); padding: 4px 0 8px; }
.sysline { text-align: center; font-size: 11px; color: var(--dim); padding: 4px 0; }
.msg { display: flex; align-items: flex-end; gap: 8px; }
.msg.you { justify-content: flex-end; }
.msg.left { flex-direction: column; align-items: stretch; gap: 2px; }
.msg-row { display: flex; align-items: flex-end; gap: 8px; }
.msg-body { max-width: 66%; min-width: 0; }
.msg-body.wide { max-width: 86%; }
.sender-name { font-size: 11px; font-weight: 600; color: var(--dim); padding-left: 36px; }
.bubble { padding: 10px 14px; border-radius: 18px 18px 18px 4px; }
.bubble.you { max-width: 66%; background: var(--blue); color: var(--on-blue); border-radius: 18px 18px 4px 18px; }
.bubble.grey { background: var(--surface-2); }
.bubble.green { background: var(--up-fill); display: flex; flex-direction: column; gap: 8px; }
.bubble .line { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.bubble .foot { font-size: 13px; color: var(--dim); border-top: 1px solid var(--border); padding-top: 8px; }
.card { display: flex; flex-direction: column; gap: 10px; padding: 14px 16px; border-radius: 18px 18px 18px 4px; background: var(--surface); border: 1px solid var(--border); box-shadow: var(--shadow-card); }
.card.orange { border-color: var(--warn-edge); }
.card.red { border-color: var(--down-edge); }
.card-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.card-title { font-weight: 700; }
.quote { font-size: 14px; border-left: 2px solid var(--border); padding-left: 10px; }
.orders { display: flex; flex-direction: column; border-top: 1px solid var(--border); }
.order-row { display: grid; grid-template-columns: auto 1fr auto; gap: 12px; padding: 8px 0; border-bottom: 1px solid var(--border); font-size: 14px; }
.order-t { font-weight: 700; }
.keys { display: flex; gap: 8px; }
.keys.right { justify-content: flex-end; }
.key { display: inline-flex; align-items: center; justify-content: center; width: 32px; height: 32px; border: 1px solid var(--border); border-radius: var(--radius-pill); background: var(--surface); }
.key.yes { color: var(--up); }
.key.no { color: var(--down); }
.key.plus { border: 0; background: var(--blue); color: var(--on-blue); }
.key.big { width: 44px; height: 44px; }
.kline { display: block; width: 100%; height: 68px; }
.kline-rule { stroke: var(--border); stroke-dasharray: 3 3; }
.kline-label { font-size: 9px; fill: var(--dim); }

/* ---- the composer ---- */
.composer { display: flex; flex-direction: column; gap: 6px; padding: 12px 28px 18px; border-top: 1px solid var(--border); margin: 0; }
.composer-pill { display: flex; align-items: center; gap: 8px; padding: 4px; border: 1px solid var(--border); border-radius: var(--radius-pill); background: var(--surface); }
.composer-input { flex: 1 1 auto; min-width: 0; height: 36px; border: 0; background: transparent; font-size: 14px; outline: none; }
.round-key { display: inline-flex; align-items: center; justify-content: center; width: 32px; height: 32px; border: 0; border-radius: var(--radius-pill); background: var(--surface-2); color: var(--text); }
.send-key { display: inline-flex; align-items: center; justify-content: center; width: 36px; height: 36px; border: 0; border-radius: var(--radius-pill); background: var(--blue); color: var(--on-blue); }
.limit-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding: 2px 0 4px; }
.limit-label { font-size: 12px; font-weight: 600; color: var(--dim); }
.limit-off { min-height: 28px; padding: 0 10px; border: 0; border-radius: var(--radius-pill); background: transparent; color: var(--dim); font-size: 12px; }
.empty { flex: 1 1 auto; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 14px; padding: 40px 28px; text-align: center; }
.empty-title { font-size: 20px; font-weight: 700; letter-spacing: -0.01em; }
.empty-line { max-width: 440px; color: var(--dim); }
.suggest { display: flex; gap: 8px; flex-wrap: wrap; justify-content: center; margin-top: 6px; }
.stub { flex: 1 1 auto; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; }

/* ---- drawers (Linqi's #drawer): right edge, 460, radius 20 0 0 20 ---- */
.drawer { position: absolute; top: 0; right: 0; bottom: 0; width: min(460px, 100%); display: flex; flex-direction: column; background: var(--surface); border-left: 1px solid var(--card-border); border-radius: var(--radius-l) 0 0 var(--radius-l); box-shadow: var(--shadow); overflow: hidden; z-index: 30; }
.drawer.details { width: min(400px, 100%); }
.drawer-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px 14px 14px 24px; border-bottom: 1px solid var(--border); }
.drawer-head h2 { font-size: 20px; }
.drawer-body { flex: 1 1 auto; display: flex; flex-direction: column; gap: 16px; padding: 20px 24px 24px; overflow-y: auto; }
.drawer-foot { margin-top: auto; display: flex; flex-direction: column; gap: 8px; }
.drawer-foot .btn-primary { width: 100%; }
.close-key { width: 36px; height: 36px; border: 0; border-radius: var(--radius-pill); background: var(--surface-2); font-size: 18px; }
.close-key.small { width: 24px; height: 24px; font-size: 13px; }
.dsec { display: flex; flex-direction: column; gap: 8px; padding-top: 14px; border-top: 1px solid var(--border); }
.drawer-body > .dsec:first-child, .drawer-body > .plug-id + .plug-blurb + .dsec { border-top: 0; padding-top: 0; }
.dsec-label { font-size: 12px; font-weight: 600; color: var(--dim); }
.dsec-title { font-size: 15px; font-weight: 700; }
.dsec-line { font-size: 14px; line-height: 1.4; }
.kv-list { display: flex; flex-direction: column; }
.kv { display: flex; justify-content: space-between; gap: 12px; padding: 8px 0; border-bottom: 1px solid var(--border); font-size: 14px; }
.kv:last-child { border-bottom: 0; }
.kv-k { color: var(--dim); white-space: nowrap; }
.kv-v { text-align: right; }

/* ---- banner, call, toast ---- */
.banner { position: fixed; top: 16px; left: 50%; transform: translateX(-50%); width: min(560px, calc(100vw - 32px)); display: flex; flex-direction: column; gap: 8px; padding: 12px 14px; border-radius: var(--radius-m); background: var(--surface); border: 1px solid var(--down-edge); box-shadow: var(--shadow-lift); z-index: 40; }
.banner-head { display: flex; align-items: center; gap: 8px; }
.call-scrim { position: fixed; inset: 0; display: flex; align-items: center; justify-content: center; background: var(--scrim); z-index: 50; }
.call { display: flex; flex-direction: column; align-items: center; gap: 10px; width: min(320px, calc(100vw - 32px)); padding: 22px 18px; border-radius: var(--radius-l); background: var(--surface); border: 1px solid var(--down-edge); box-shadow: var(--shadow); text-align: center; }
.call-keys { display: flex; gap: 16px; margin-top: 4px; }
.toast { position: absolute; left: 50%; bottom: 28px; transform: translateX(-50%); display: inline-flex; align-items: center; gap: 12px; padding: 8px 8px 8px 18px; border-radius: var(--radius-pill); background: var(--primary); color: var(--on-primary); font-size: 13px; white-space: nowrap; box-shadow: var(--shadow-lift); z-index: 35; }
.toast-key { min-height: 32px; padding: 0 14px; display: inline-flex; align-items: center; border-radius: var(--radius-pill); background: var(--surface); color: var(--text); font-weight: 600; }
.toast-x { width: 28px; height: 28px; border: 0; border-radius: var(--radius-pill); background: transparent; color: var(--on-primary); font-size: 14px; }

/* ---- Discover ---- */
.disc, .acct { gap: 22px; padding: 24px 28px 28px; }
.disc-head, .acct-head { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
.disc-head .head-title, .acct-head .head-title { flex: none; }
.search { display: flex; align-items: center; gap: 10px; height: 44px; width: 420px; max-width: 100%; padding: 0 14px; border-radius: var(--radius-pill); border: 1px solid var(--border); background: var(--surface); color: var(--dim); }
.search input { flex: 1 1 auto; min-width: 0; width: 0; border: 0; background: transparent; font-size: 14px; outline: none; color: var(--text); }
.shelf { display: flex; flex-direction: column; gap: 10px; min-width: 0; }
.shelf-head { display: flex; align-items: baseline; gap: 12px; }
.shelf-title { flex: 1 1 auto; font-size: 17px; font-weight: 700; letter-spacing: -0.01em; }
.shelf-row { display: flex; gap: 12px; overflow-x: auto; margin: 0 -28px; padding: 2px 28px 6px; scrollbar-width: none; }
.shelf-row::-webkit-scrollbar { display: none; }
.pcard { flex: 0 0 300px; display: grid; grid-template-columns: 44px minmax(0, 1fr) auto; column-gap: 12px; align-items: start; background: var(--surface); border: 1px solid var(--card-border); border-radius: var(--radius-m); padding: 16px; box-shadow: var(--shadow-card); cursor: pointer; }
.pcard.pressed { border-color: var(--rule); }
.pcard.grid { flex: none; }
.pcard-body { min-width: 0; display: flex; flex-direction: column; gap: 3px; }
.pcard-name { font-size: 15px; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pcard-blurb { font-size: 13px; line-height: 1.35; }
.pcard-by { font-size: 12px; color: var(--dim); }
.pcard-extra { display: flex; align-items: center; gap: 8px; margin-top: 4px; }
.pcard-side { display: flex; flex-direction: column; align-items: flex-end; justify-content: space-between; gap: 10px; align-self: stretch; }
.pcard-kind { font-size: 11px; font-weight: 700; color: var(--dim); letter-spacing: 0.04em; }
.pkey { display: inline-flex; align-items: center; justify-content: center; gap: 4px; border: 0; border-radius: var(--radius-pill); }
.pkey.install { width: 36px; height: 36px; background: var(--surface-2); color: var(--text); }
.pkey.installed { min-height: 36px; padding: 0 4px; background: transparent; color: var(--dim); font-size: 13px; font-weight: 600; }
.pkey.uninstall { width: 36px; height: 36px; border: 1px solid var(--border); background: var(--surface); color: var(--down); }
.grid-sec { display: flex; flex-direction: column; gap: 10px; }
.grid-title { font-size: 17px; font-weight: 700; letter-spacing: -0.01em; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(300px, 100%), 1fr)); gap: 12px; }
.back-link { color: var(--dim); font-size: 13px; font-weight: 600; }
.plug-id { display: flex; align-items: center; gap: 14px; }
.plug-name { font-size: 17px; font-weight: 700; }
.plug-blurb { margin: 0; font-size: 14px; color: var(--dim); }
.upload-form { display: flex; flex-direction: column; gap: 14px; flex: 1 1 auto; }
.field { display: flex; flex-direction: column; gap: 6px; }
.field-label { font-size: 12px; font-weight: 600; color: var(--dim); }
.input, .textarea { width: 100%; padding: 0 12px; border: 1px solid var(--border); border-radius: var(--radius-s); background: var(--surface); font-size: 14px; outline: none; }
.input { height: 40px; }
.textarea { padding: 10px 12px; resize: vertical; font-family: var(--font-mono); font-size: 12px; }
.input:focus, .textarea:focus { border-color: var(--rule); }
.radio-seg { display: inline-flex; gap: 2px; padding: 3px; border-radius: var(--radius-pill); background: var(--surface-2); flex-wrap: wrap; }
.radio-item { display: inline-flex; }
.radio-item input { position: absolute; opacity: 0; width: 1px; height: 1px; }
.radio-item span { display: inline-flex; align-items: center; min-height: 32px; padding: 0 12px; border-radius: var(--radius-pill); color: var(--dim); font-size: 13px; font-weight: 600; cursor: pointer; }
.radio-item input:checked + span { background: var(--surface); color: var(--text); font-weight: 700; box-shadow: var(--shadow-card); }
.picks { display: flex; gap: 8px; flex-wrap: wrap; }
.picks .radio-item span { border: 1px solid var(--border); background: var(--surface); }
.picks .radio-item input:checked + span { border-color: var(--rule); box-shadow: none; }

/* ---- Account ---- */
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(360px, 100%), 1fr)); gap: 16px; align-items: start; }
.cards.two { grid-template-columns: repeat(auto-fit, minmax(min(380px, 100%), 1fr)); }
.stack { display: flex; flex-direction: column; gap: 16px; }
.cardbox { display: flex; flex-direction: column; gap: 12px; background: var(--surface); border: 1px solid var(--card-border); border-radius: var(--radius-m); padding: 18px 20px; box-shadow: var(--shadow-card); min-width: 0; }
.cardbox-title { font-size: 20px; font-weight: 700; letter-spacing: -0.01em; }
.networth { font-size: 52px; font-weight: 800; letter-spacing: -0.02em; line-height: 1.05; font-variant-numeric: tabular-nums; }
.delta { display: flex; align-items: center; gap: 8px; font-size: 13px; }
.spark { height: 56px; border-radius: var(--radius-s); background: var(--surface-2); }
.alloc-bar { display: flex; height: 8px; border-radius: var(--radius-pill); overflow: hidden; }
.alloc-seg { display: block; }
.alloc-cash { background: var(--alloc-cash); } .alloc-stable { background: var(--alloc-stable); } .alloc-crypto { background: var(--alloc-crypto); } .alloc-equity { background: var(--alloc-equity); }
.alloc-legend { display: flex; gap: 14px; flex-wrap: wrap; font-size: 12px; color: var(--dim); }
.holdings { display: flex; flex-direction: column; border-top: 1px solid var(--border); }
.holding { display: grid; grid-template-columns: 1fr auto auto; gap: 12px; padding: 10px 0; border-bottom: 1px solid var(--border); font-size: 14px; }
.venues { display: flex; flex-direction: column; gap: 10px; }
.venue { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 12px 14px; border: 1px solid var(--border); border-radius: var(--radius-s); }
.mem-group { display: flex; flex-direction: column; }
.mem-label { font-size: 12px; font-weight: 700; color: var(--dim); padding: 12px 0 4px; }
.mem-entry { display: flex; align-items: center; gap: 10px; padding: 9px 0; border-bottom: 1px solid var(--border); }
.mem-body { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
.mem-text { font-size: 14px; }
.mem-source { font-size: 12px; color: var(--dim); }
.mem-keys { display: flex; gap: 6px; }
.small-key { display: inline-flex; align-items: center; justify-content: center; width: 28px; height: 28px; border: 1px solid var(--border); border-radius: var(--radius-pill); background: var(--surface); color: var(--dim); }
.small-key.danger { color: var(--down); }
.mem-add { display: flex; gap: 8px; margin: 6px 0 0; }
.where { display: flex; flex-direction: column; gap: 8px; font-size: 14px; }
.where-row { display: flex; align-items: center; gap: 10px; }
.switch-row { display: flex; justify-content: space-between; align-items: center; gap: 16px; padding: 12px 0; border-top: 1px solid var(--border); }
.switch-label { font-size: 14px; font-weight: 600; }
.switch { position: relative; width: 40px; height: 24px; border: 0; border-radius: var(--radius-pill); background: var(--alloc-cash); padding: 0; }
.switch.on { background: var(--primary); }
.knob { position: absolute; left: 2px; top: 2px; width: 20px; height: 20px; border-radius: var(--radius-pill); background: var(--surface); transition: left 120ms; }
.switch.on .knob { left: 18px; }

/* ---- the demo director (keyboard d) ---- */
.director { position: fixed; right: 16px; bottom: 16px; display: flex; flex-direction: column; gap: 6px; padding: 10px; border-radius: var(--radius-m); background: var(--surface); border: 1px solid var(--card-border); box-shadow: var(--shadow-lift); z-index: 45; }
.director-key { min-height: 32px; padding: 0 12px; border: 0; border-radius: var(--radius-pill); background: var(--surface-2); color: var(--text); font-size: 13px; text-align: left; }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd gravit-ui && node --test tests/css.test.js`
Expected: PASS. If `missing` lists a class, add its rule (the list is the to-do); do not delete the class from the renderer.

- [ ] **Step 5: Commit**

```bash
git add gravit-ui/css/app.css gravit-ui/tests/css.test.js
git commit -m "gravit-ui: the stylesheet from the spec numbers and tokens"
```

---

### Task 14: Router and the app — boot, events, timers, director, theme

**Files:**
- Create: `gravit-ui/js/router.js`, `gravit-ui/js/app.js`
- Test: `gravit-ui/tests/app.test.js`

**Interfaces:**
- Consumes: everything above.
- Produces: `parseHash(hash) → route`, `toHash(route) → string` from `router.js`; `Timers`, `initialState(storage, now)`, `scheduleEvents(store, timers, convId, events, now)`, `boot(win)` from `app.js`. `boot` is only called in the browser (`if (typeof window !== 'undefined' && window.document) boot(window)`), so the module imports cleanly under node.

- [ ] **Step 1: Write the failing test**

```js
// gravit-ui/tests/app.test.js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseHash, toHash } from '../js/router.js';
import { Timers, initialState, scheduleEvents } from '../js/app.js';
import { createStore } from '../js/store.js';
import { reducers } from '../js/reducers/index.js';
import { seed, SEED_VERSION } from '../js/data/seed.js';

const NOW = new Date(2026, 9, 9, 14, 7).getTime();
const sleep = ms => new Promise(r => setTimeout(r, ms));

test('parseHash and toHash round-trip, unknown screens fall back to messages', () => {
  assert.deepEqual(parseHash('#/messages/c-2'), { screen: 'messages', id: 'c-2' });
  assert.deepEqual(parseHash('#/messages/new'), { screen: 'messages', id: 'new' });
  assert.deepEqual(parseHash('#/discover'), { screen: 'discover', id: null });
  assert.deepEqual(parseHash('#/discover/bots'), { screen: 'discover', id: 'bots' });
  assert.deepEqual(parseHash('#/account'), { screen: 'account', tab: 'portfolio' });
  assert.deepEqual(parseHash('#/account/memory'), { screen: 'account', tab: 'memory' });
  assert.deepEqual(parseHash('#/account/nope'), { screen: 'account', tab: 'portfolio' });
  assert.deepEqual(parseHash('#/markets/NVDA'), { screen: 'markets', id: 'NVDA' });
  assert.deepEqual(parseHash('#/trade'), { screen: 'trade' });
  assert.deepEqual(parseHash(''), { screen: 'messages', id: null });
  assert.deepEqual(parseHash('#/whatever'), { screen: 'messages', id: null });
  assert.equal(toHash({ screen: 'messages', id: 'c-1' }), '#/messages/c-1');
  assert.equal(toHash({ screen: 'account', tab: 'memory' }), '#/account/memory');
  assert.equal(toHash({ screen: 'discover', id: null }), '#/discover');
});

test('initialState: a saved state of the same version is kept; another version or garbage boots the seed', () => {
  const saved = { ...seed(NOW), theme: 'black' };
  const storage = { getItem: () => JSON.stringify(saved), setItem() {} };
  assert.equal(initialState(storage, NOW).theme, 'black');
  const old = { getItem: () => JSON.stringify({ ...saved, v: SEED_VERSION + 1 }), setItem() {} };
  assert.equal(initialState(old, NOW).theme, 'system');
  const junk = { getItem: () => '{nope', setItem() {} };
  assert.equal(initialState(junk, NOW).v, SEED_VERSION);
  assert.equal(initialState(null, NOW).conversations.length, 4);
});

test('Timers tracks pending timers and clear() cancels them', async () => {
  const t = new Timers();
  let fired = 0;
  t.after(5, () => fired++);
  t.after(5, () => fired++);
  assert.equal(t.size, 2);
  t.clear();
  assert.equal(t.size, 0);
  await sleep(15);
  assert.equal(fired, 0);
  t.after(5, () => fired++);
  await sleep(15);
  assert.equal(fired, 1);
  assert.equal(t.size, 0, 'a fired timer leaves the set');
});

test('scheduleEvents appends each event after its delay; a reset in between drops the rest', async () => {
  const store = createStore({ initial: seed(NOW), reducers });
  const timers = new Timers();
  const events = [{ delay: 5, msg: { from: 'gravit', kind: 'text', text: 'one', data: {} } }, { delay: 30, msg: { from: 'gravit', kind: 'text', text: 'two', data: {} } }];
  scheduleEvents(store, timers, 'c-1', events, () => NOW);
  await sleep(15);
  assert.equal(store.get().conversations[0].messages.at(-1).text, 'one');
  timers.clear();
  store.reset(seed(NOW));
  await sleep(40);
  assert.equal(store.get().conversations[0].messages.at(-1).kind, 'install', 'the fresh seed never saw "two"');
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd gravit-ui && node --test tests/app.test.js`
Expected: FAIL — `Cannot find module '../js/router.js'`

- [ ] **Step 3: Write router.js and app.js**

```js
// gravit-ui/js/router.js — hash routes: #/messages/<id> · #/discover[/<shelf>] · #/account/<tab> · #/markets[/<ticker>] · #/trade
const TABS = ['portfolio', 'venues', 'memory'];

export function parseHash(hash) {
  const [screen, a] = (hash ?? '').replace(/^#\/?/, '').split('/').filter(Boolean);
  switch (screen) {
    case 'discover': return { screen: 'discover', id: a ?? null };
    case 'account': return { screen: 'account', tab: TABS.includes(a) ? a : 'portfolio' };
    case 'markets': return { screen: 'markets', id: a ?? null };
    case 'trade': return { screen: 'trade' };
    case 'messages': return { screen: 'messages', id: a ?? null };
    default: return { screen: 'messages', id: null };
  }
}

export function toHash(route) {
  if (route.screen === 'account') return `#/account/${route.tab ?? 'portfolio'}`;
  if (route.screen === 'trade') return '#/trade';
  return route.id ? `#/${route.screen}/${route.id}` : `#/${route.screen}`;
}
```

```js
// gravit-ui/js/app.js — boot: the store, the hash router, one render per change, event delegation on data-action, the driver's timers, the director
import { createStore } from './store.js';
import { reducers } from './reducers/index.js';
import { seed, SEED_VERSION } from './data/seed.js';
import { byId } from './data/plugins.js';
import { parseHash, toHash } from './router.js';
import { renderRail } from './render/rail.js';
import { renderMessagesScreen, renderBanner, renderCall, renderStub, currentConversation } from './render/messages.js';
import { renderDiscover } from './render/discover.js';
import { renderAccount } from './render/account.js';
import { replyTo, followUp, director } from './driver.js';
import { DAY } from './time.js';

export class Timers {
  constructor() { this.set = new Set(); }
  after(ms, fn) {
    const t = setTimeout(() => { this.set.delete(t); fn(); }, ms);
    this.set.add(t);
    return t;
  }
  clear() { for (const t of this.set) clearTimeout(t); this.set.clear(); }
  get size() { return this.set.size; }
}

const KEY = 'gravit-ui.state';

export function initialState(storage, now = Date.now()) {
  try {
    const raw = storage?.getItem(KEY);
    const saved = raw ? JSON.parse(raw) : null;
    if (saved && saved.v === SEED_VERSION && Array.isArray(saved.conversations)) return saved;
  } catch { /* fall through to the seed */ }
  return seed(now);
}

export function scheduleEvents(store, timers, convId, events, now = () => Date.now()) {
  for (const e of events) timers.after(e.delay, () => store.dispatch('append', { convId, msg: e.msg, at: now() }));
}

const DIRECTOR = [['早报', 'brief'], ['技术分析', 'ta'], ['突发', 'breaking'], ['来电', 'call'], ['bot 插话', 'bot'], ['重置 demo', 'reset']];

export function boot(win) {
  const doc = win.document;
  const storage = (() => { try { return win.localStorage; } catch { return null; } })();
  const store = createStore({ initial: initialState(storage), reducers, storage, key: KEY });
  const timers = new Timers();
  const root = doc.getElementById('app');
  const now = () => Date.now();
  let directorOpen = false;
  let composerText = '';

  function applyTheme(theme) {
    if (theme === 'cream' || theme === 'black') doc.documentElement.dataset.theme = theme; else delete doc.documentElement.dataset.theme;
    try { if (theme === 'cream' || theme === 'black') storage?.setItem('gravit-ui.theme', theme); else storage?.removeItem('gravit-ui.theme'); } catch { /* ignore */ }
  }

  function render() {
    const s = store.get();
    const active = doc.activeElement?.id;
    const screen = s.route.screen === 'discover' ? renderDiscover(s) : s.route.screen === 'account' ? renderAccount(s) : (s.route.screen === 'markets' || s.route.screen === 'trade') ? renderStub(s.route) : renderMessagesScreen(s, now());
    const overlays = (s.banner ? renderBanner(s.banner, s) : '') + (s.call ? renderCall(s.call) : '') +
      (directorOpen ? `<div class="director" role="menu">${DIRECTOR.map(([l, k]) => `<button type="button" class="director-key" data-action="director" data-key="${k}">${l}</button>`).join('')}</div>` : '');
    root.innerHTML = renderRail(s, now()) + screen + overlays;
    const say = doc.getElementById('say');
    if (say) { say.value = composerText; if (active === 'say') say.focus(); }
    const title = doc.getElementById('nm-title');
    if (title && active === 'nm-title') { title.focus(); title.setSelectionRange(title.value.length, title.value.length); }
    const dq = doc.getElementById('dq');
    if (dq && active === 'dq') { dq.focus(); dq.setSelectionRange(dq.value.length, dq.value.length); }
    const thread = doc.getElementById('thread');
    if (thread) thread.scrollTop = thread.scrollHeight;
  }

  function go(route) {
    const h = toHash(route);
    if (win.location.hash !== h) win.location.hash = h; else store.dispatch('nav', route);
  }

  function reply(convId, text) {
    const s = store.get();
    scheduleEvents(store, timers, convId, replyTo(text, { installed: s.plugins.installed, now: now() }), now);
  }

  function reset() {
    timers.clear();
    store.reset(seed(now()));
    composerText = '';
    go({ screen: 'messages', id: 'c-1' });
  }

  const actions = {
    open: el => go({ screen: 'messages', id: el.dataset.id }),
    startDraft: () => { store.dispatch('startDraft', { now: now() }); go({ screen: 'messages', id: 'new' }); },
    cancelDraft: () => { store.dispatch('cancelDraft'); go(store.get().route); },
    toggleRail: () => store.dispatch('toggleRail'),
    toggleDraftAttach: () => store.dispatch('toggleDraftAttach'),
    toggleDraftGroup: () => store.dispatch('toggleDraftGroup'),
    draftLimit: el => {
      const key = el.dataset.key;
      const d = store.get().draft;
      if (!d) return;
      if (key === 'venue') {
        const venues = ['Stand-in Exchange', 'Stand-in Broker', 'Stand-in Wallet'];
        store.dispatch('setDraftLimit', { key, value: venues[(venues.indexOf(d.limit.venue) + 1) % venues.length] });
      } else if (key === 'until') {
        const days = Number(win.prompt('几天后到期？', '6'));
        if (days > 0) store.dispatch('setDraftLimit', { key, value: now() + days * DAY });
      } else {
        const v = Number(win.prompt(key === 'perOrder' ? '每单上限（$）' : '总额（$）', String(d.limit[key])));
        if (v > 0) store.dispatch('setDraftLimit', { key, value: v });
      }
    },
    suggest: el => { composerText = el.dataset.text; render(); doc.getElementById('say')?.focus(); },
    answer: el => {
      const { conv, msg, answer } = el.dataset;
      const before = store.get().conversations.find(c => c.id === conv)?.messages.find(m => m.id === msg);
      const events = followUp(before, answer, { now: now() });
      const after = store.dispatch('answer', { convId: conv, msgId: msg, answer, now: now() });
      if (after !== store.get() || before?.answer) return;
      scheduleEvents(store, timers, conv, events, now);
    },
    installAsk: el => {
      const { conv, msg, plugin } = el.dataset;
      store.dispatch('answer', { convId: conv, msgId: msg, answer: 'installed', now: now() });
      store.dispatch('openPlugin', plugin);
      go({ screen: 'discover', id: null });
    },
    toggleDetails: () => store.dispatch('toggleDetails'),
    changeWords: el => {
      const c = store.get().conversations.find(x => x.id === el.dataset.conv);
      const title = win.prompt('这件事叫什么', c?.title ?? '');
      if (title != null) store.dispatch('rename', { convId: el.dataset.conv, title });
    },
    withdraw: el => { if (win.confirm('撤回这条委托？')) store.dispatch('withdraw', { convId: el.dataset.conv, now: now() }); },
    changeLimit: el => {
      const c = store.get().conversations.find(x => x.id === el.dataset.conv);
      const L = c?.intent.limit ?? { perOrder: 25, total: 100 };
      const perOrder = Number(win.prompt('每单上限（$）', String(L.perOrder)));
      const total = Number(win.prompt('总额（$）', String(L.total)));
      if (perOrder > 0 && total > 0) store.dispatch('changeLimit', { convId: el.dataset.conv, limit: { perOrder, total } });
    },
    endLimit: el => {
      const c = store.get().conversations.find(x => x.id === el.dataset.conv);
      if (c?.intent.limit) store.dispatch('changeLimit', { convId: el.dataset.conv, limit: { total: c.intent.limit.spent } });
    },
    stopGravit: el => { if (win.confirm('停掉 Gravit？这件事不再动。')) store.dispatch('stopGravit', { convId: el.dataset.conv, now: now() }); },
    setMode: el => store.dispatch('setMode', el.dataset.value === 'Beast' ? 'beast' : 'guard'),
    dismissBanner: () => store.dispatch('dismissBanner'),
    answerCall: el => store.dispatch('answerCall', { accept: el.dataset.accept === '1', now: now() }),
    // Discover
    openPlugin: el => store.dispatch('openPlugin', el.dataset.id),
    closeDrawer: () => store.dispatch('closeDrawer'),
    install: el => store.dispatch('install', { id: el.dataset.id, now: now() }),
    uninstall: el => store.dispatch('uninstall', el.dataset.id),
    uninstallAsk: el => { const p = byId(el.dataset.id, store.get().plugins.uploaded); if (win.confirm(`卸载 ${p?.name ?? el.dataset.id}？`)) store.dispatch('uninstall', el.dataset.id); },
    toggleInstalledOnly: () => store.dispatch('toggleInstalledOnly'),
    openUpload: () => store.dispatch('openUpload'),
    dismissToast: () => store.dispatch('dismissToast'),
    // Account
    openSettings: () => store.dispatch('openSettings'),
    closeSettings: () => store.dispatch('closeSettings'),
    setTheme: el => { const t = el.dataset.value.toLowerCase(); store.dispatch('setTheme', t); applyTheme(t); },
    resetDemo: () => { if (win.confirm('回到最初的样子？')) reset(); },
    editMemory: el => {
      const e = store.get().memory.entries.find(x => x.id === el.dataset.id);
      const text = win.prompt('改成', e?.text ?? '');
      if (text != null) store.dispatch('editMemory', { id: el.dataset.id, text });
    },
    forgetMemory: el => store.dispatch('forgetMemory', el.dataset.id),
    forgetAll: () => { if (win.confirm('全部忘掉？没有回收站。')) store.dispatch('forgetAll'); },
    memorySwitch: el => store.dispatch('setMemorySwitch', { key: el.dataset.key, value: el.getAttribute('aria-checked') !== 'true' }),
    exportMemory: () => {
      const blob = new win.Blob([JSON.stringify(store.get().memory, null, 2)], { type: 'application/json' });
      const a = doc.createElement('a');
      a.href = win.URL.createObjectURL(blob);
      a.download = 'gravit-memory.json';
      a.click();
      win.URL.revokeObjectURL(a.href);
    },
    // the director
    director: el => {
      const k = el.dataset.key;
      const s = store.get();
      const convId = currentConversation(s)?.id ?? s.conversations[0]?.id;
      if (k === 'reset') return reset();
      if (k === 'breaking') return store.dispatch('showBanner', director.breaking(now()));
      if (k === 'call') return store.dispatch('incomingCall', director.call());
      if (convId) store.dispatch('append', { convId, msg: director[k](now()), at: now() });
    },
  };

  root.addEventListener('click', ev => {
    const el = ev.target.closest('[data-action]');
    if (!el || el.tagName === 'FORM' || el.tagName === 'INPUT') return;
    const fn = actions[el.dataset.action];
    if (!fn) return;
    if (el.tagName === 'A' && el.dataset.action !== 'open' && el.dataset.action !== 'dismissBanner') return;
    if (el.tagName === 'A') { ev.preventDefault(); }
    fn(el);
  });

  root.addEventListener('submit', ev => {
    const form = ev.target.closest('form[data-action]');
    if (!form) return;
    ev.preventDefault();
    const action = form.dataset.action;
    if (action === 'send') {
      const text = composerText.trim();
      if (!text) return;
      const before = store.get();
      const after = store.dispatch('send', { text, now: now() });
      if (after === before) return;
      composerText = '';
      const convId = after.route.id;
      if (before.draft) win.location.hash = toHash(after.route);
      reply(convId, text);
    } else if (action === 'publish') {
      const f = new win.FormData(form);
      store.dispatch('publish', { manifest: { name: f.get('name'), blurb: f.get('blurb'), kind: f.get('kind'), tools: f.get('tools'), needs: f.get('needs') === '没有' ? '没有。' : `你的${f.get('needs')}。`, visibility: f.get('visibility') }, now: now() });
    } else if (action === 'addMemory') {
      const f = new win.FormData(form);
      store.dispatch('addMemory', { text: f.get('text'), now: now() });
    }
  });

  root.addEventListener('input', ev => {
    const el = ev.target;
    if (el.id === 'say') composerText = el.value;
    else if (el.dataset.action === 'draftTitle') store.dispatch('setDraftTitle', el.value);
    else if (el.dataset.action === 'query') store.dispatch('setQuery', el.value);
  });

  doc.addEventListener('keydown', ev => {
    if (ev.key === 'Escape') {
      const s = store.get();
      if (s.call) return;
      if (s.discover.drawer || s.discover.upload) store.dispatch('closeDrawer');
      else if (s.detailsOpen) store.dispatch('toggleDetails');
      else if (s.settingsOpen) store.dispatch('closeSettings');
      else if (directorOpen) { directorOpen = false; render(); }
      return;
    }
    const typing = ['INPUT', 'TEXTAREA'].includes(doc.activeElement?.tagName);
    if (ev.key === 'd' && !typing && !ev.metaKey && !ev.ctrlKey) { directorOpen = !directorOpen; render(); }
  });

  win.addEventListener('hashchange', () => store.dispatch('nav', parseHash(win.location.hash)));
  store.subscribe(render);
  applyTheme(store.get().theme);
  const first = parseHash(win.location.hash);
  if (!win.location.hash) win.location.hash = toHash(store.get().route);
  else store.dispatch('nav', first);
  render();
  return store;
}

if (typeof window !== 'undefined' && window.document) boot(window);
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd gravit-ui && node --test tests/app.test.js`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add gravit-ui/js/router.js gravit-ui/js/app.js gravit-ui/tests/app.test.js
git commit -m "gravit-ui: router and app wiring with the driver timers and the director"
```

---

### Task 15: README, the map row, and the smoke run in a browser

**Files:**
- Create: `gravit-ui/README.md`
- Modify: `CLAUDE.md` (the Map table: one row for `gravit-ui/`)
- Test: the whole suite plus a browser pass

- [ ] **Step 1: Run the whole suite**

Run: `cd gravit-ui && npm test`
Expected: every file passes; the count is 14 files, 0 failures.

- [ ] **Step 2: Write the README**

```markdown
# gravit-ui — Demo v2 · Gravit, the pure front end

The settled design (spec: `../docs/superpowers/specs/2026-10-09-demo-v2-gravit-frontend-design.md`,
canvas rows 7–10) as a static site: Messages, Discover, Account, with scripted data and no back end.
Nothing here imports from `../demo/`; the port into Linqi's page is a mounting job.

## Run

```bash
cd gravit-ui && npm start      # http://127.0.0.1:4830/
npm test                       # node --test tests/
```

No dependencies, no build. Any static server works (`python3 -m http.server`), the fonts come from
Google Fonts and fall back to the system.

## What is scripted (driver c)

- Send a message: words with **BTC / ETH / SOL** get the F1 story (a reply, then a card to approve;
  ✓ brings a receipt and a limit request; Grant brings an install request). **Pelosi / 跟单** asks for
  the politician bot or, once it is installed, posts its proposal. **0x… / 地址** runs the fraud check.
  **额度** asks to raise the limit. Anything else gets two grey replies.
- Discover: Install opens the plugin's teaching conversation and a toast; Installed · n filters;
  Upload a plugin publishes a private plugin of yours; search is live.
- Account › Memory: add, edit, forget, the three switches, Export (a JSON download), Forget all;
  Settings holds the theme (Cream · Black · System) and Reset demo.
- State persists in `localStorage` (`gravit-ui.state`); Reset demo or a new seed version clears it.

## The director (keyboard)

Press **d** (outside an input) for the demo director: 早报 · 技术分析 · 突发 · 来电 · bot 插话 · 重置 demo.
Esc closes drawers and the director.

## Layout of the code

`js/store.js` holds the one state object; `js/reducers/*` change it; `js/render/*` are pure
functions from state to HTML strings; `js/app.js` wires the hash router, event delegation on
`data-action`, the driver's timers and the director. `css/tokens.css` is Linqi's token sheet plus
`--down-edge`; `css/app.css` names colours only by token.
```

- [ ] **Step 3: Add the map row to `CLAUDE.md`**

In the Map table, after the `demo/` row, add:

```markdown
| `gravit-ui/` | Demo v2 · Gravit, the pure front end of the settled design (`docs/superpowers/specs/2026-10-09-demo-v2-gravit-frontend-design.md`): a static site, vanilla ES modules, scripted data, no back end, nothing imported from `demo/`; `npm start` serves 127.0.0.1:4830, `npm test` is `node --test`; press `d` for the demo director |
```

- [ ] **Step 4: Smoke it in a browser**

Run: `cd gravit-ui && npm start` then open <http://127.0.0.1:4830/> (the Playwright plugin or the built-in browser). Walk:
1. Messages opens on 小仓位 BTC; the rail shows four rows, one unread dot; press ✓ Grant on the limit card → "Granted." and, after ~1 s, "改到 $50 了。", then the install request.
2. Press + on the install request → Discover opens with the News sentiment drawer; press Install → the toast, a new unread "News sentiment：怎么用我" row; press Open → the teaching conversation.
3. Rail +: type a title and "小仓位买 SOL", press send → a new conversation, Gravit's reply and a card; ✗ it → "Rejected." and the grey reply.
4. Press `d` → 早报, 技术分析 (tickers are blue; one click goes to the Markets stub), 突发 (the banner), 来电 (decline → a line in the conversation).
5. Account › Memory: add a line, flip a switch, Export; Settings → Black (every colour changes, no shadows), Reset demo.
Expected: no console errors; every step as described. If a step fails, fix it in the owning module and add the case to that module's test before continuing.

- [ ] **Step 5: Commit**

```bash
git add gravit-ui/README.md CLAUDE.md
git commit -m "gravit-ui: README and the map row"
```

---

## Self-review notes

- **Spec coverage:** §3 tokens → Task 1 + 13; §4 rail → 8; §5.1 heads → 10; §5.2–5.3 bubbles and keys → 9; §5.4 composer → 10; §5.5 new message → 10 (+ group draft); §5.6 Details → 10; §5.7 empty/Black → 10 + 1/13; §5.8 group → 5, 9, 10; §6 kinds and levels → 4, 7, 9; §7 store → 5, 6, 11; §8 Account and Memory → 6, 12; §10 copy rules → every render test's `doesNotMatch`; §11.1 (F1 head) stays as settled; §9 is out of scope by the operator's word.
- **Not built, on purpose:** Markets and Trade (Linqi's pages; a stub names the ticker), real signatures, Top up / Take back, Move / Receive / Statement, Connect an account (buttons without handlers), real portraits.
- **Type consistency checked:** `message(from, kind, text, data)`; events `{ delay, msg }`; `append({ convId, msg, at })`; `answer({ convId, msgId, answer, now })`; `install({ id, now })`; `publish({ manifest, now })`; `seg(items, pressed, action)`; `card(p, state, { view, pressed, openIn })`; `keyFor(p, state, view)`; `renderDetails(conv, state)`; `renderBanner(b, state)`; `scheduleEvents(store, timers, convId, events, now)`.
