# gravit-ui — Demo v2 · Gravit, the pure front end

The settled design (spec: `../docs/superpowers/specs/2026-10-09-demo-v2-gravit-frontend-design.md`,
canvas rows 7–10) as a static site: Messages, Discover, Account, with scripted data and no back end.
Nothing here imports from `../demo/`; the port into Linqi's page is a mounting job.

## Run

```bash
cd gravit-ui && npm start      # http://127.0.0.1:4830/
npm test                       # node --test tests/*.test.js
```

No dependencies, no build. Any static server works (`python3 -m http.server`); the fonts come from
Google Fonts and fall back to the system.

## What is scripted (driver c)

- Send a message: words with **BTC / ETH / SOL** get the F1 story (a reply, then a card to approve for
  that coin; ✓ brings a receipt and a limit request; Grant brings an install request unless one is
  already waiting). **Pelosi / 跟单** asks for the politician bot or, once it is installed, posts its
  proposal. **0x… / 地址** runs the fraud check. **额度** asks to raise the limit. Anything else gets two
  grey replies. Order, ledger and card numbers continue from the seed's counters, and a limit ask reads
  the conversation's real cap.
- In a group, a bot named after **@** (`@Buffett`, `@政客`) answers; only Gravit proposes, as a card. In a
  plugin's teaching conversation the plugin answers. New message: **+ 加个 bot** opens a picker of the
  installed bots.
- Discover: Install opens the plugin's teaching conversation and a toast; pressing "✓ Installed"
  turns that key into the trash key; Installed · n filters; Upload a plugin publishes a private plugin
  of yours; search is live.
- Account › Memory: add, edit, forget, the three switches, Export (a JSON download), Forget all;
  Settings holds the theme (Cream · Black · System) and Reset demo.
- Stop Gravit or Withdraw in Details: nothing more lands in that conversation.
- State persists in `localStorage` (`gravit-ui.state`); Reset demo or a new seed version clears it.

## The director (keyboard)

Press **d** (outside an input) for the demo director: 早报 · 技术分析 · 突发 · 来电 · bot 插话 · 拒单 · 收尾 ·
空白开始 · 重置 demo. 突发 shows the banner for 5 s, then leaves its red-edged message in the thread; a
declined call leaves a call card; 空白开始 opens the first-run screen with no conversations. Esc closes
drawers and the director.

Below 860 px the rail sits above the page. A toast leaves after 6 s; a reload starts without banners,
calls, drawers or toasts.

## Tests

`npm test` runs the node:test suite: render functions are asserted as strings, and `tests/helpers/fake-dom.js`
runs `boot()` against a fake window to check the composer, scroll, focus and IME handling.

## Layout of the code

`js/store.js` holds the one state object; `js/reducers/*` change it; `js/render/*` are pure
functions from state to HTML strings; `js/app.js` wires the hash router, event delegation on
`data-action`, the driver's timers and the director. `css/tokens.css` is Linqi's token sheet plus
`--down-edge` and `--on-equity` (the white words on his equity blue, `--alloc-equity`); `css/app.css`
names colours only by token.
