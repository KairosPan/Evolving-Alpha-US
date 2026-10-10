# gravit-ui — Demo v2 · Gravit, the pure front end

The settled design (spec: `../docs/superpowers/specs/2026-10-09-demo-v2-gravit-frontend-design.md`,
canvas rows 7–10, with the 2026-10-10 amendments at its end) as a static site: Messages, Mail,
Discover, Account, with scripted data and no back end. Nothing here imports from `../demo/`; the port into
Linqi's page is a mounting job.

## Run

```bash
cd gravit-ui && npm start      # http://127.0.0.1:4830/
npm test                       # node --test tests/*.test.js
```

No dependencies, no build. Any static server works (`python3 -m http.server`); the fonts come from
Google Fonts and fall back to the system.

## The frame

A first level on the left holds Messages · Discover · Markets · Trade, the phone and mail keys and
Account; its chevron collapses it to a strip of icons. Opening Messages shows the second level, the
conversation list with the new-message key; the mail key opens Mail, whose second level lists Gravit's
letters. Markets and Trade follow Linqi's buyer-agent-demo pages. Below 860 px the first level is a bar of
icons on top.

## What is scripted (driver c)

- Send a message: words with **BTC / ETH / SOL** get the F1 story (a reply, then a card to approve for
  that coin; ✓ brings a receipt and a limit request; Grant brings an install request unless one is
  already waiting). **Pelosi / 跟单** asks for the politician bot or, once it is installed, posts its
  proposal. **0x… / 地址** runs the fraud check. **额度** asks to raise the limit. Anything else gets two
  grey replies. Order, ledger and card numbers continue from the seed's counters, and a limit ask reads
  the conversation's real cap.
- The composer's **+** opens a file picker; files sit in a tray and send as chips, and Gravit says it is
  reading them (only names and sizes are kept). The **mic** listens for a moment and writes a sample
  sentence into the composer.
- In a group, a bot named after **@** (`@Buffett`, `@政客`) answers; only Gravit proposes, as a card. In a
  plugin's teaching conversation the plugin answers. New message: **+ 加个 bot** opens a picker of the
  installed bots.
- Discover: an installed plugin shows **✓** beside a trash key; **My plugins** filters to yours; search
  is live. Cards carry no author or price line.
- **Create** opens Discover's own MCP face (Discover is itself an MCP server): its address, its seven tools,
  and the line Claude Code, Cursor or Codex takes to add it. **复制** copies that line and starts a
  scripted client (no real client connects; the address resolves nowhere): it connects, calls
  `shop.mine`, then asks `shop.publish` with a manifest. You see the manifest, pick Private or Public and
  sign with **Publish**, or **拒绝**. A private plugin is installed at once, opens a conversation that
  teaches its tools and leads its kind's shelf; a public one is reviewed for 5 s behind a clock key, then
  Discover writes to Gravit's mailbox and the plugin can be installed. The uploads come in turn (Moat
  score, then CPI 速读, then the same again with a number). Nothing in the dialog can be typed.
- Details: Change words, Change limit, Top up and Take back edit in place (✓ or Enter saves, × or Esc
  cancels); Withdraw, End limit and Stop Gravit ask in place and act on the second press. After Stop or
  Withdraw nothing more lands in that conversation, and Details stops offering them. Top up stops at the
  USDC you hold. Details makes room instead of covering the conversation: below 1400 px the list folds
  away while it is open, and below 1180 px the first level folds to icons by itself. One drawer is open
  at a time.
- The rail's **phone** key rings Gravit: it picks up, the call shows a timer, mute and hang up, and a
  call card stays. The **mail** key switches to Mail: Gravit's letters in the second level, the open
  letter in the main column (`#/mail/<id>`); opening a letter reads it.
- **Markets** (after Linqi's `ui/markets.js`): tabs for the kinds that have markets (All · Crypto · Stocks ·
  RWAs · Predictions, Watching once something is starred), Most traded · Biggest moves · Closing soonest, one
  table with one key per row (**Trade** where the account trades it, **Connect to trade** at a public venue),
  prediction cards with Yes and No at the ask, and a drawer per market at `#/markets/<id>`: price and facts, a
  chart in 5m · 1h · 1d, across venues with the best marked, what you hold and the orders on it, Gravit on it,
  and the statement lines about it. Quotes are stand-ins held still, so what is shown is what fills.
- **Trade** (after Linqi's `ui/trade.js`): the kind seg, a picker (You hold · Recent · Most traded, a search),
  Under way (orders on their way or on a book, and the cards Gravit waits on), and the ticket: Where, Buy or
  Sell, Amount (dollars or units) and Order (Market or Limit), the quote prepared from the fields, What you
  sign, a signature good for ten minutes and **Sign and place**. The press stands in for Linqi's device-key
  signature; a stand-in venue answers 0.9 s later and the fill moves holdings, cash, the Statement and net
  worth. One order is $100 at most. Gravit's orders on a book cancel after asking; **Hand to Gravit instead**
  opens a new message with the ticket in words and the limit set where Gravit may trade.
- Account: Portfolio's **Move** shifts an asset between venues, **Receive** shows the deposit address with
  a QR stand-in and copies it, **Statement** lists the activity and exports a CSV; Venues' **Connect an
  account** connects stand-in venues. Memory: add, edit in place, forget, the three switches, Export,
  Forget all. Settings holds the theme (Cream · Black · System) and Reset demo.
- State persists in `localStorage` (`gravit-ui.state`); Reset demo or a new seed version clears it.

## The director (keyboard)

Press **d** (outside an input) for the demo director: 早报 · 技术分析 · 突发 · 来电 · bot 插话 · 拒单 · 收尾 ·
插件上传 · 空白开始 · 重置 demo. 突发 shows the banner for 5 s, then leaves its red-edged message in the
thread; an incoming call can be accepted, then hung up, or declined; 插件上传 opens Create on Discover and
starts the scripted client without the clipboard; 空白开始 opens the first-run screen with no
conversations. Esc closes editors, confirms, drawers and the director. A toast leaves after 6 s; a
reload starts without banners, calls, drawers or toasts.

## Tests

`npm test` runs the node:test suite: render functions are asserted as strings, and `tests/helpers/fake-dom.js`
runs `boot()` against a fake window to check the composer, scroll, focus, IME handling and the controls.

## Layout of the code

`js/store.js` holds the one state object; `js/reducers/*` change it (`controls.js` holds the editors,
confirms, composer and Account panels; `discover.js` the store and Create); `js/render/*` are pure functions from state to HTML
strings; `js/app.js` wires the hash router, event delegation on `data-action`, the driver's timers and
the director. `css/tokens.css` is Linqi's token sheet plus `--down-edge` and `--on-equity` (the white
words on his equity blue, `--alloc-equity`); `css/app.css` names colours only by token.
