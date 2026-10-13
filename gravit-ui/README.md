# gravit-ui — Demo v2 · Gravit, the pure front end

The settled design (spec: `../docs/superpowers/specs/2026-10-09-demo-v2-gravit-frontend-design.md`,
with the amendments §13–§16 at its end; the canvas is its picture) as a static site: Messages, Mail,
Discover, Markets, Trade and Account, with scripted data and no back end. Nothing here imports from `../demo/`; the port into
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
  already waiting). **Pelosi** asks for the politician bot or, once it is installed, posts its
  proposal. **0x… / address / scam** runs the fraud check. **limit / cap** asks to raise the limit. Anything else gets two
  grey replies.
  Every product string is English (spec decision 10); the trigger words are English too. Order, ledger and card numbers continue from the seed's counters, and a limit ask reads
  the conversation's real cap.
- The composer's **+** opens a file picker; files sit inside the composer as chips and send with the message, and Gravit says
  it is reading them (only names and sizes are kept). The **mic** turns ink while it listens and fills the
  composer with a sample sentence word by word.
- In a group, a bot named after **@** (`@Buffett`, `@politician`) answers; only Gravit proposes, as a card. In a
  plugin's teaching conversation the plugin answers. New message: **+ Add a bot for a group** opens a picker of
  the installed bots.
- Discover: an installed plugin shows **✓** beside a trash key; **My plugins** filters to yours (Installed in
  install order, then Yours); search is live. Cards carry no author or price line. A card opens the plugin's
  own page (`#/plugin/<id>`): ‹ Discover, the head with its one key, What you sign (the manifest's slug,
  `install kol-bot`), what you can ask it, what it writes, what it needs. Install and Uninstall work there too.
- **Create** opens Discover's own MCP face (Discover is itself an MCP server): its address, its seven tools,
  and the line Claude Code, Cursor or Codex takes to add it. **Copy** copies that line and starts a
  scripted client (no real client connects; the address resolves nowhere): it connects, calls
  `shop.mine`, then asks `shop.publish` with a manifest. You see the manifest, pick Private or Public and
  sign with **Publish**, or **Refuse**. A private plugin is installed at once, opens a conversation that
  teaches its tools and leads its kind's shelf; a public one is reviewed for 5 s behind a clock key, then
  Discover writes to Gravit's mailbox and the plugin can be installed. The uploads come in turn (Moat
  score, then CPI quick read, then the same again with a number). Nothing in the dialog can be typed.
- Details: Change words, Change limit, Top up and Take back edit in place, each box named and the editor
  standing in for the buttons that opened it (✓ or Enter saves, × or Esc cancels); Withdraw, End limit and Stop Gravit ask in place and act on the second press. After Stop or
  Withdraw nothing more lands in that conversation, and Details stops offering them. Top up stops at the
  USDC you hold. Details makes room instead of covering the conversation: below 1400 px the list folds
  away while it is open, and below 1180 px the first level folds to icons by itself. One drawer is open
  at a time.
- The rail's **phone** key rings Gravit: "Ringing", it picks up, the call shows a timer (m:ss), mute and hang
  up, and a call card stays with its topic, time and what was said. Only a call coming in, or a missed one, is
  red. The **mail** key switches to Mail: Gravit's letters in the second level, the open
  letter in the main column (`#/mail/<id>`); opening a letter reads it.
- **Markets** (after Linqi's `ui/markets.js`): tabs for the kinds that have markets (All · Crypto · Stocks ·
  RWAs · Predictions, Watching once something is starred), Most traded · Biggest moves · Closing soonest, one
  table with one key per row (**Trade** where the account trades it, **Connect to trade** at a public venue),
  prediction cards with Yes and No at the ask, and a page per market at `#/markets/<id>` (‹ Markets goes back): price and facts, a
  chart in 5m · 1h · 1d, across venues with the best marked, what you hold and the orders on it, Gravit on it,
  and the statement lines about it. Quotes are stand-ins held still, so what is shown is what fills.
- **Trade** (after Linqi's `ui/trade.js`): the kind seg, a picker (You hold · Recent · Most traded, a search),
  Under way (orders on their way or on a book, and the cards Gravit waits on), and the ticket: Where, Buy or
  Sell, Amount (dollars or units) and Order (Market or Limit), the quote prepared from the fields, What you
  sign, a signature good for ten minutes and **Sign and place**. The press stands in for Linqi's device-key
  signature; a stand-in venue answers 0.9 s later and the fill moves holdings, cash, the Statement and net
  worth. One order is $100 at most. Gravit's orders on a book cancel after asking; **Hand to Gravit instead**
  opens a new message with the ticket in words and the limit set where Gravit may trade.
- Account: Portfolio's **Move** shifts an asset between venues, **Receive** shows the owner's Stand-in Wallet
  address (USDC on Base) with a QR stand-in and copies it, **Statement** lists the activity and exports a CSV; Venues' **Connect an
  account** connects stand-in venues. Memory: add, edit in place, forget, the three switches, Export,
  Forget all. Settings holds the theme (Cream · Black · System) and Reset demo.
- State persists in `localStorage` (`gravit-ui.state`); Reset demo or a new seed version clears it.

## The director (keyboard)

Press **d** (outside an input) for the demo director: Morning brief · Technicals · Breaking · Call · Bot chimes in ·
Monitor · Refusal · Done · Plugin upload · First run · Reset demo. Breaking drops the banner over the conversation
for 5 s, then leaves its red-edged message in the thread; an incoming call can be accepted, then hung up, or
declined; Monitor posts a Telegram monitor signal and Gravit's answer; Plugin upload opens Create on Discover and
starts the scripted client without the clipboard; First run opens the first-run screen with no
conversations. Esc closes editors, confirms, drawers and the director (a plugin's or a market's page stays: its back link
returns). A toast leaves after 6 s; a
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
