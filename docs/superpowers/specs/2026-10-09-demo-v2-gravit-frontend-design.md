# Demo v2 · Gravit front end — Design

**Status (2026-10-09):** front end settled. The operator closed the design rounds with *"可以定前端了"*
on canvas version 50. This spec is the written form of the settled boards: what every screen shows,
how it is drawn in Linqi's visual language, and what it expects from the back end. It does not decide
how the back end is built: the architecture boards (canvas rows 5–6, D1–D5: 架构 · 组件 · 数据流 ·
出错与测试 · 十幕) were drafted on 2026-10-08 and parked on the operator's word (*"目前还是专注在前端设计"*);
they get their own spec when the operator returns to them. §9 lists the seams the screens need so that
spec has a checklist. **2026-10-11:** the operator asked for the whole front end in English
(*"我要把这个前端全部转成英文"*): every product string in this spec and in `gravit-ui/` is the English copy;
the canvas's own annotations (board titles, specimen labels, stickies, F12/F16 notes) stay Chinese.
**Companion:** the design canvas this spec is the written form of —
<https://claude.ai/artifact/XwsiQ4VTqzfGdtzBi2LWgb> (Design type, re-laid 2026-10-11: rows 1–4 the settled
screens on the §13 rail — Messages, Discover with Create, Account, Mail, Markets and Trade — row 5 the message
specimens and the removed copy, row 6 the parked architecture; the early rounds were removed, their decisions
are §1). On a disagreement this spec wins; the canvas is the picture.
**Pins:** repository `main` @ `69225d8`; `demo/` = `linqizhe07/buyer-agent-demo` @ `0ef5131` (its `main`
after PR #6 and PR #7); the visual tokens are that commit's `demo/src/portfolio/public/ui/tokens.css`
and `shell.css`.
**Language of citations:** bare paths are this repository; `demo/…` is the submodule; `F1`…`F16` name
canvas boards; "Linqi" is the demo's author; "the operator" is this repository's owner.

---

## 1. Context and decision history

The request, 2026-10-08: *"我现在要在linqi这个基础新开一版完整的demo，主题是融入agent"* — a new, complete
demo built on Linqi's account product, with the agent woven in, designed through a Claude Design canvas
one question per round. The decisions, in the order the operator took them:

1. **Purpose A** (round 1): a complete story told to outsiders; stand-in venues only; no real money,
   no `face/`; it hangs on the seam Linqi's COOKBOOK §11b leaves for "our team's" Agent module.
2. **The agent is the main screen; Discover is a second screen full of plugins** (round 2).
3. **One conversation per delegated task, titled by the task; the agent is named Gravit; Account
   collapses to a wallet icon at the bottom-left holding Portfolio and Venues** (round 3).
4. **Markets and Trade leave Account for the rail; the copy-trading roles are "bots" (美国政客, KOL,
   Buffett, Serenity); Discover also carries monitors (Telegram and the like)** (round 4).
5. **Driver c** — scripted by default, `--driver llm` for the live stage — and **approach 2 without a
   reverse proxy**: same repository (the demo, branch `feat/gravit`), same process (round 5).
6. **Front end first**; the five architecture sections wait (round 6).
7. **F1 is the master screen, in the iMessage idiom** (rounds 7–8, twenty comment-driven edits): a
   "Messages" list with conversation rows, bubbles with avatars on both sides, icon-only round keys,
   a pill composer, no status lines, no meta small text, F2 (the dark-rail variant) deleted.
8. **Round 9, the operator's eight points** (2026-10-09): Memory lives in Account; message colour
   encodes importance, ✓ on white in green and ✗ on white in red; more message kinds (K-line
   analysis with a ticker that jumps to Markets, group chats, the morning brief, breaking news,
   incoming calls); Discover becomes an App Store (shelves by kind, a recommended shelf from the
   user's style, cards with a 44 px image, a drawer to read and sign in, an Installed filter, a
   conversation that teaches a plugin after install); the type label moves to the top-right and the
   image to the top-left; Discover is a plugin shop with an MCP face, user-written plugins may be
   public or private; **no paid plugins — revenue is a commission on model calls and filled trades**;
   the conversation head on the new-message screen is the avatar plus the task in one line, a
   cluster of avatars for a group.
9. **Screens carry no explanatory small print** (2026-10-09, three deletion rounds): no helper
   sentences, no shelf subtitles, no notes under switches. Every removed sentence is kept on F16 for
   the onboarding guide and for the back-end spec (§10).
10. **The product speaks English** (2026-10-11): every label, placeholder, message and seed string,
    the example conversations included; the glossary is the boards themselves and §5–§8 below.

Two earlier decisions still bind: Venues are never in Discover (they stay in Account), and Serenity
bot's one line is "Tech supply-chain analysis" (科技产业链分析).

## 2. The screens

| Board | Screen | What it settles |
|---|---|---|
| F1 | Messages, a conversation open | the master: rail, conversation rows, bubbles, cards, keys, composer |
| F6 | Messages, empty | the first-run state: a G mark, one line, three suggestion chips |
| F7 | Messages, after "+" | the new-message state: avatar head, title input, To: row, limit chips |
| F8 | Messages, Details open | the right drawer of one conversation |
| F9 | Messages, Black | the same screen in Linqi's Black tokens |
| F14 | Messages, a group chat | several agents and bots in one conversation |
| F4 | Discover | the store: header, six shelves, card anatomy, three key states |
| F10 | Discover, a card clicked | the plugin drawer with the signature table inside |
| F11 | Discover, Installed | the installed filter, uninstall keys, the after-install conversation |
| F12 | Upload a plugin + the MCP face | a notes board: the upload drawer, the shop's tools, a manifest |
| F5 | Account | Portfolio · Venues · Memory segments; Linqi's Portfolio and Connect an account |
| F13 | Account › Memory | what Gravit remembers, where it is used, three switches |
| F3, F15 | message specimens | the fifteen message kinds and the colour legend |
| F16 | removed copy | sentences kept for the onboarding guide and the back-end spec |

Every screen is 1280 wide in the boards; the page itself is fluid (Linqi's shell wraps the rail under
the main column below ~800 px, and nothing here needs more than his breakpoints).

Added 2026-10-11 for §13–§15, all on the two-level rail: F17 (the first level collapsed), F18 (Mail, a letter
open), F19 and F20 (Create: the Discover MCP dialog waiting for a client, then asked to publish), F21 (Markets),
F22 (the market drawer), F23 (Trade with the ticket), F24 (the controls of §13.5); F8 now shows Details beside the
thread with the second level folded away; F12 (the old upload drawer) is gone with §14.3. Since §16
(2026-10-13) F10 is the KOL bot's page and F22 the BTC market's page, not drawers, and the boards were corrected
against the build (§16.8).

## 3. Visual language

Everything is drawn in Linqi's tokens; no colour or size is invented except the one in §3.4.

### 3.1 Colours (`tokens.css`)

| name | Cream | Black | used for |
|---|---|---|---|
| bg | #f6f4ef | #0e0f11 | the ground |
| surface | #ffffff | #17191c | cards, the rail, white bubbles, the composer |
| surface-2 | #ece8e0 | #212429 | grey bubbles, pressed rows, grey pills, seg containers |
| text / dim | #121417 / #5d5a53 | #f2f3f5 / #a3a9b4 | words / secondary words |
| border / card-border | #e6e1d7 / #ece8e0 | #2b2e34 / #25282d | hairlines / card edges |
| primary / on-primary | #121417 / #ffffff | #f2f3f5 / #0e0f11 | the ink pill (Install, Sign, Add) |
| warn-edge / warn-fill / warn-text | #f3d2b4 / #fdf0e3 / #94480c | #f0a040 / #2b2112 / #f5b866 | the "needs a decision" card and its chip |
| up / up-fill | #0d7a52 / #e4efe6 | #4cc38a / #16301f | ✓ glyph, "filled"/"paid" chips, the green bubble |
| down / down-fill | #b4441c / #f6e6df | #f08a6c / #35201a | ✗ glyph, refusals, the trash key, Forget all |
| equity blue | #3b5bdb | #5c7cfa | the owner's bubbles, the send key, the unread dot, tickers, See all, the "+" Install key |
| rail-bg | #ffffff | #12151b | the rail |
| shadow-card / shadow-lift / shadow | see tokens.css | none / none / black 0.55 | cards / toasts and banners / drawers |

### 3.2 Type, radii, sizes

Manrope throughout (400–800), tabular figures for numbers, IBM Plex Mono only for tool names,
manifests and hashes. Body 15 px / 1.45; conversation titles 14 px 700; row previews and secondary
lines 12 px dim; chips 12 px 600; headings 20–22 px 700–800 with −0.01 em tracking. Radii 10 (rows,
inputs, icons), 16 (cards, bubbles' corners are 18 with one 4 px corner), 20 (drawers), pill.
Controls: rail items 44 px, `.btn` 44 px pill, `.btn-sm` 36 px, `.seg` 38 px segments on a surface-2
pill, search pill 44 × 420, round keys 32 px with 14 px glyphs (44 px for the call keys).

### 3.3 Cards, drawers, toasts

A card is Linqi's `.card`: surface, 1 px card-border, radius 16, padding 18/20, shadow-card. The drawer
is his `#drawer`: fixed to the right edge, width min(460 px, 100 vw), radius 20 0 0 20, 1 px card-border
on the left, his `--shadow`, a sticky head (title 20 px 700, a 36 px round close key, padding
14/14/14/24, hairline below) and a body with padding 20/24/24 and 16 px gaps; sections inside are
separated by hairlines with 14 px above. The page behind a drawer stays usable (no scrim). A toast
is an ink pill at the bottom-centre of the main column with shadow-lift.

### 3.4 One new token

`--down-edge`: the soft red edge of an urgent card, made the way Linqi made `--warn-edge` — the down
colour at about a third on the surface. Cream ≈ `#e8c2b4`; Black uses `--down` itself (`#f08a6c`), as his
Black `--warn-edge` uses `--warn`. It is the only addition to `tokens.css` this design needs.

## 4. The rail

Width 248 px (`--rail`), rail-bg, 1 px border on the right, padding 24/16, 18 px gaps. From the top:

1. **Brand**: a 28 px ink circle with a white G, "Gravit" 22 px 800.
2. **Messages**: a header row — 22 px chat-bubble icon, "Messages" 15 px 500 dim — with two 44 px
   icon keys at its right: **+** (new message) then the collapse chevron. Below it the conversation
   rows; collapsing hides the rows, the header stays. There is no "Done" group and no "New channel" row.
3. **Conversation rows** (iMessage): 64 px min height, padding 8/10, radius 10; an 8 px unread dot
   (equity blue, else transparent) · a 36 px avatar · title 14 px 700 one line with ellipsis · time
   11 px dim at the right, never wrapping · preview 12 px dim one line. The current row has a
   surface-2 ground. The avatar is Gravit's G for its own conversations, a bot's own avatar for a
   conversation that bot opened, a two-circle cluster for a group (F14), a dashed "+" circle for the
   not-yet-sent new message (F7).
4. **Discover · Markets · Trade**: 44 px items with 22 px line icons; the current one has a surface-2
   ground and 700 weight.
5. **Phone · Email**: two bordered 44 px icon keys side by side above Account (the agent's phone and
   mail lines; the research behind them is `docs/research/2026-10-06-agent-phone-and-email.md`).
6. **Account**: a 56 px bordered button pinned to the very bottom — wallet icon, "Account", a 12 px
   line "$12,480 · Guard". When Account is the open screen the button has an ink border and a
   surface-2 ground. No "Trading on · time" line anywhere on the rail.

## 5. Conversations

### 5.1 The head

F1/F8/F9 keep the head settled in round 7: the task title 20 px 700 at the left, a green "Working"
chip, a "Details ›" `.btn-sm`. F7 and F14 use the iMessage head the operator asked for in round 9: a
centred 44 px avatar (for a group, overlapping avatars with a 2 px bg ring, −12 px overlap), the task
in one line (17 px 700), a 12 px dim members line, Working and Details at the top-right. **Whether
F1's head should follow F7/F14 is open** (§11).

### 5.2 Bubbles and cards

- The owner speaks on the right: equity-blue bubble, white words, radius 18 18 4 18, a 28 px outlined
  "You" avatar at the bubble's foot. Every owner message is a signed instruction.
- Gravit speaks on the left: surface-2 bubble, radius 18 18 18 4, its 28 px G avatar at the foot.
  Bots use their own 28 px avatar; in a group the sender's name is written 11 px dim above the bubble.
- Cards are left bubbles on surface with an edge; the edge colour is the importance level (§6).
- Time dividers are centred 11 px dim lines ("Today 14:01", "14:04"); there is no other meta text —
  no "signed · intent-0003", no tool lines, no subtitle under the title. Those fields live in Details.

### 5.3 Keys

Decisions are icon-only 32 px round keys, no words; screen readers still get the name.
✓ = surface ground, 1 px hairline, up-colour glyph (Approve, Grant, Accept). ✗ = surface ground,
hairline, down-colour glyph (Reject, Decline, No). + = equity-blue ground, white glyph (Install). The
keys sit at the bottom-right of a card, left-aligned in a plain bubble. The call keys (§6, kind 14)
are 44 px with phone glyphs in the same two colours.

### 5.4 The composer

A pill on surface with a hairline, padding 4, at the bottom of the main column above an 18 px inset:
a 32 px surface-2 round **+** (attach) at the far left · the input ("Tell Gravit…"; in a group
"Tell Gravit… @ a bot by name") · a 32 px surface-2 round **mic** · a 36 px equity-blue round **send
arrow** at the far right. Sending signs. The iMessage rule may apply at build time: mic when the input
is empty, send when it has words.

### 5.5 The new-message state (F7)

Pressing + inserts a current row at the top of the list (dashed + avatar, "New message", "now",
"Not sent yet"). The head becomes: Cancel at the top-right; a 44 px G avatar; the title as a centred,
borderless 17 px 700 input ("Name this (or your first line is the name)"); a "To:" line with a Gravit chip and a
dashed "+ Add a bot for a group" key. The thread area is empty. Above the composer a chip row "Attach a limit":
$25 an order ▾ · $100 in all ▾ · until Oct 15 ▾ · on Stand-in Exchange ▾ · None — sent together with the first
message as one signature.

### 5.6 Details (F8)

A 400 px drawer from the right (Linqi's `#drawer` look): This task (title; Delegated Oct 8 · until Oct 15 ·
intent-0003; Change words / Withdraw) · Limit ($25 an order · $100 in all · $95 left; Change limit /
End limit) · Plugins (what this conversation uses; "Find more in Discover ›") · Gravit’s wallet ($12.40 USDC ·
Base · address; Top up… / Take back…) · Mode (Guard | Beast) · Stop Gravit (a down-fill danger pill).

### 5.7 Empty (F6) and Black (F9)

F6: the rail has the Messages header and no rows; the main column centres a 56 px G, "Nothing handed to
Gravit yet", one line ("Say what you want done below, or press + at the top-left to name it first.") and three surface-2
chips that fill the composer (Buy a little BTC · Follow Pelosi · Check an address). F9: F1 with the Black column of
§3.1 and every shadow removed; the ✓ and ✗ keys sit on `#17191c` with a `#2b2e34` hairline.

### 5.8 Group chat (F14)

Gravit plus any installed bots in one conversation: the cluster head, named bubbles, each sender its
own avatar. Gravit alone proposes and signs for; bots argue. A proposal that touches several orders is
one card with a row per order (ticker · reason · venue · type · amount) and one ✗/✓ pair.

## 6. Message kinds and colour levels

Colour is importance, five levels, all from the tokens:

| level | drawing | carries |
|---|---|---|
| grey (灰) · talk | surface-2 bubble | Gravit thinking, progress, replies |
| white (白) · to read | surface bubble, 1 px border | the morning brief, K-line analysis, monitor signals, research |
| orange edge (橙边) · needs a decision | surface bubble, warn-edge, a warn-fill chip ("answer by 14:33") | approve an order, grant a limit, install a plugin |
| red edge (红边) · urgent or bad | surface bubble, down-edge, a down-fill chip | breaking news, refusals from the doors, incoming calls |
| green fill (绿底) · done | up-fill bubble, a white chip with up-colour words | filled, paid, report done |

The fifteen kinds (F3 1–10, F15 11–15), who speaks, the level, the keys, and what each is bound to:

| # | kind | who | level | keys | bound to |
|---|---|---|---|---|---|
| 1 | the owner's words | You | blue | — | a signed `setIntent` / `say` |
| 2 | Gravit's words | G | grey | — | the journal |
| 3 | an order to approve | G | orange edge | ✗ ✓ | the approval card (`approveCard`), its deadline |
| 4 | a limit request | G | orange edge | ✓ ✗ | Give a limit (`setPolicy`) |
| 5 | a plugin request | G | orange edge | + ✗ | the Discover drawer (`shop.get` → `shop.install`) |
| 6 | a bot's proposal that executed inside the limit | bot | green fill | — | the order and its ledger row |
| 7 | a monitor's signal | monitor | white | — | a plugin message; read-only, never an order |
| 8 | a door's refusal | G | red edge | — | the error code verbatim (`E_MANDATE_PER_ORDER_CAP`) |
| 9 | a receipt | G | green fill | — | a ledger row (fill, payment) |
| 10 | the close | G | green fill | — | `agentReport` done |
| 11 | K-line technical analysis | G | white | — | a plugin output; the ticker is a link to Linqi's market drawer (`openMarket`) |
| 12 | the morning brief | G | white | — | a 7:30 scheduled plugin output with tickers |
| 13 | breaking news | banner | red edge | × | a banner over the thread for 5 s, then a red-edged message in it |
| 14 | an incoming call | card | red edge | decline ✗ accept ✓ (44 px phones) | the rail's phone line; a declined call becomes a message |
| 15 | a group-chat message | bot | grey | — | the sender's name above the bubble |
| 16 | an alert (§16.3) | G | red edge | — | a check's bad verdict in one sentence |

## 7. Discover, the store

### 7.1 Header

"Discover" · the 44 × 420 search pill · an **Installed · n** pill (pressed = ink; filters the page to
installed plugins) · an **Upload a plugin** pill with an upload glyph. No sentence under it.

### 7.2 Shelves

Six shelves, each a title (17 px 700) with "See all ›" in equity blue at the right and a horizontal
row of 300 px cards, three in view and the fourth cut at the main column's edge (the row bleeds into
the column's padding): **Like** (recommended from Memory — the user's style: a value investor gets
Buffett bot, Broker research, US politician bot, Quant team; a high-frequency trader gets high-frequency strategies and
low-latency data; someone who wants to try quant gets a team to run an idea) · **Data** · **Monitors** ·
**Bots** · **Crypto** · **Quant**. The catalogue on the boards: Price feed, News sentiment, Broker research,
On-chain flows · Telegram monitor, X monitor, Whale alerts, Earnings calendar · US politician bot, KOL bot,
Buffett bot, Serenity bot (Tech supply-chain analysis) · Address fraud check, Exchange spread, Gas timing, Contract check · Quant team,
Backtest, Factor screen, Pairs (the user's own, private).

### 7.3 A card

Surface, card-border, radius 16, padding 16, three columns: a **44 px image** at the top-left (radius
10; a portrait for Buffett and Serenity, a glyph or a letter for the rest) · name 15 px 700, one line
of what it does 13 px, an **author line** 12 px dim ("Free · by Gravit", "Free · by @kol_watch",
"Free · by @you · Private") · at the right, the **type label** 11 px 700 dim at the top and **one key**
at the bottom. The key has three states: **Install** — a 36 px surface-2 round with a + glyph;
**Installed** — dim 13 px "✓ Installed" words, pressing them offers uninstall; **Uninstall** — a 36 px
surface round with a hairline and a down-colour trash glyph (shown in the Installed view and after
pressing "Installed"). The clicked card gets an ink border while its drawer is open. There is no price
line: plugins are free (§7.6).

### 7.4 The drawer (F10)

Linqi's drawer: a 56 px image, the name 17 px 700, "Bots · by Gravit · Free · 1.2k installs", one line of
what it is; then sections What you can ask it · What it writes (what it writes into the conversation, and what it
never does) · How it is paid · What it needs from you (nothing, a Telegram session, an exchange key…) · **What you sign**, the
signature table inline — What you sign `install buffett-bot` · For `Gravit · 0xec4c…16c1` · May `read
Portfolio · propose in your limit` · May not `pay anyone · move money` · Until `you uninstall` — and a
full-width ink **Install**. No second sheet pops up: the drawer is the signing surface.

### 7.5 Installed (F11) and after install

The Installed pill pressed shows only installed cards in a grid, each with the trash key, plus a
"Yours" group for the user's own plugins. Right after an install: the new card carries a green
"Just installed" chip and "Open in Messages ›"; a toast "Buffett bot installed · Gravit opened a conversation to show you how · Open";
and the rail gains an unread conversation opened by the plugin ("Buffett bot: how to use me") that teaches
its use.

### 7.6 Money

No paid plugins, no per-call or per-minute prices. Revenue is a commission on model calls and on filled
trades. The earlier paid-plugin mechanics (a payees approval per agent, x402 from Gravit's wallet, a
card for the first payment under Guard) are retired for plugins and kept on F16 in case a plugin must
pay an outside data vendor.

### 7.7 Upload a plugin and the shop's MCP face (F12)

The upload drawer: Name · One line · Kind (Data · Monitors · Bots · Crypto · Quant) · Icon (44 px slot,
initials if none) · Tools it exposes (the MCP server's tool names) · What it needs from the user (Nothing ·
Telegram session · Exchange key · Wallet address) · Where (**Just me · Private** | **Public shop**) · Cancel / Publish.
A private plugin is visible only to this user's Gravit and usable at once; a public one is reviewed
first (run in a sandbox, its permissions and author read).

The shop is itself an MCP server; the page and Gravit use the same face:

| tool | what it is for |
|---|---|
| `shop.search(q, kind)` | shelves, search and the Like recommendation |
| `shop.get(id)` | the drawer's sections |
| `shop.install(id)` | one owner signature; then the plugin opens its teaching conversation |
| `shop.uninstall(id)` | the trash key |
| `shop.publish(manifest, visibility)` | upload; `visibility` is `public` or `private` |
| `shop.mine()` | what the user uploaded and installed |
| `plugin.call(id, tool, args)` | Gravit calling an installed plugin's tool; every call writes a ledger line |

A plugin is one MCP server plus one manifest: `id`, `name`, `kind`, `blurb`, `icon`, `tools`, `writes`
(`message`, `proposal`…), `needs`, `visibility`, `by`. Message kind 5 (§6) is Gravit using
`shop.search` and `shop.get` itself; installing still needs the owner's signature.

## 8. Account

The wallet button opens Account: "Account" · Guard | Beast · a green "Trading on · $100 a move" chip ·
Settings; a seg **Portfolio · Venues · Memory**. Portfolio and Venues are Linqi's own Portfolio and
Connect an account, embedded same-origin (net worth, allocation bar, holdings, Move / Receive /
Statement; venues with health chips, Connect an account). Markets and Trade are on the rail, not here;
Venues are here and never in Discover.

**Memory (F13)** — what Gravit remembers about the user, in a two-column layout. Left, "What Gravit remembers about you":
entries grouped Style · Rules · Venues and people, each with its text, its **source and date** (You said · From your limit ·
Learned from your questions · Compared on its own · From installed bots), a pencil key and a trash key; an input "Add something it should remember…"
with an ink Add. Right, "Where it is used": chips naming the places Memory feeds (Discover's Like shelf, the
morning brief, a new conversation's defaults, group chats); "Switches": three switches — Let Gravit remember new things
(on), Ask me before it keeps what it learned (off; a new memory then arrives as a card to answer), Bots in group chats can read Memory
(off; only Gravit reads it) — and Export (a JSON file) · Forget all (down-fill danger pill; deletes the
file, no recycle bin). Memory lives on this machine only.

## 9. What the screens expect from the back end

A checklist for the architecture spec, not a design. Each item names the seam the 2026-10-08 code
exploration found (`demo/` @ `0ef5131`), or says that none exists yet.

1. **A Gravit page inside Linqi's account server** — `startPortfolioServer` has no extension point;
   one page route plus read-only JSON routes added behind the local-only guard, `gravit.html` and
   `gravit-*.js|css` under `public/ui`, the page-scripts test taught the second page. Same for the
   stand-in server (it calls the same function).
2. **A conversation journal per task** — the account's words model keeps only the latest report per
   agent and ≤20 open intents of ≤200 characters, so the thread's source of truth must be Gravit's own
   JSONL journal under its home; owner follow-ups go through the signed `say` path; polling, no SSE.
3. **The owner's signed actions the screens press**: setIntent (first message, with its limit),
   say (every later message), approveCard / reject (kind 3), setPolicy / Give a limit (kind 4), Stop,
   Withdraw, Change words (Details).
4. **The plugin shop MCP face** (§7.7) — none exists; `shop.*` and `plugin.call`, the manifest, the
   review path for public plugins, the teaching conversation after install.
5. **Memory** — a file per user with sourced entries, the three switches, export, forget; read by the
   Like shelf, the brief, new-conversation defaults, group chats.
6. **Scheduled and pushed messages** — the 7:30 brief, breaking news with the banner, the phone line
   behind kind 14, bot and monitor senders with their own avatars.
7. **Markets hook** — a ticker in a message opens Linqi's market drawer (`openMarket` by holdings key).
8. **Black** — `html[data-theme]` as Linqi's page already does; the one new token (§3.4).
9. **The stand-in** — purpose A runs on stand-in venues; the stand-in pays no one, so any plugin that
   must pay a vendor needs a stand-in payee (kept on F16; not needed while plugins are free).
10. **The driver** — c: scripted by default, `--driver llm` live, both on the same MCP tool surface;
    no LLM driver exists in the demo today.

## 10. Copy rules and the removed sentences

Screens carry data and controls and do not explain themselves. The sentences taken off the screens on
2026-10-09 are on F16 in two columns — onboarding-guide copy (the empty-state and new-message hints,
the install note, the public/private explanation, the Memory notes and switch notes, the six shelf
subtitles) and back-end rules (money, boundaries, the install signature, the MCP face and manifest,
Memory semantics, Monitors read-only / Bots within limits, the message mechanics, the record fields
moved to Details, the retired payees mechanics). The guide and the architecture spec draw from F16;
nothing on it goes back onto a screen.

## 11. Open

1. Whether F1/F8/F9 adopt the avatar-and-task head of F7/F14 (asked 2026-10-09, unanswered).
2. Where a finished conversation goes once there is no Done group (stays in the list, or an archive
   behind the collapse chevron).
3. Real portraits for Buffett and Serenity; the boards carry silhouette placeholders.
4. The exact `--down-edge` value once it is seen on Linqi's grounds; the 4th-card peek width on
   narrower screens.
5. The architecture itself (rows 5–6, D1–D5): parked, not approved.

## 12. For the implementer

The boards are plain inline-styled HTML (generated for the canvas, not product code); translate them
into Linqi's classes — `.card`, `.btn` / `.btn-sm` / `.btn-primary`, `.seg`, `.chip`, `#drawer` with
`openDrawer`, the rail — rather than copying the inline styles. Use the token names, never the hex
values, so Black comes for free. Keep every number in §3–§5 (rail 248, rows 64, avatars 36/28, keys 32,
composer 36/32, drawer 460) and every state on the boards (current, unread, pressed, installed,
just-installed, collapsed). Nothing in this spec touches Linqi's doors: every order, limit, payment and
install still passes through his signed instructions.

## 13. Amendment, 2026-10-10 (after the first build)

The operator's words, after seeing the pure front end in `gravit-ui/`: keep the branch as it is;
"✓ Installed" becomes a ✓ beside the delete key; "Installed · 6" becomes My plugins; Upload becomes Create,
which pops up an MCP connector; Messages, Discover, Markets and Trade go in a first-level column that
collapses to small icons, and opening Messages shows the second level; and the controls get built.
Where this section and §4, §7.1, §7.3, §7.5, §7.7 or §12 disagree, this section wins. In §7.1 the
header now reads My plugins · n and + Create; in §12 the rail's 248 gives way to the widths in item 1.

1. **Two levels (replaces the single rail of §4).** The first level: the brand with a collapse chevron,
   Messages (with the unread count) · Discover · Markets · Trade, the phone and mail keys, Account at the
   foot. Collapsed, it is a strip of icons; the names stay as titles and for screen readers. The second
   level appears on Messages only: the title "Messages", the new-message +, and the conversation rows of
   §4.3. Messages returns to the last open conversation. The rows' own collapse chevron is gone. Widths:
   the first level 220 px, 68 px collapsed; the second level 300 px. Between 861 and 1180 px the first
   level folds to its icons by itself. Details never lies over the conversation: the thread and the
   composer make room for it, and below 1400 px the second level folds away while Details is open. One
   drawer at a time: opening Details, a plugin, Create, the mailbox, Settings or an Account panel closes
   whichever was open. Below 860 px the first level is a bar of icons on top and the list a block under it.
2. **The installed key (replaces the three states of §7.3).** Not installed: the + key. Installed: a ✓
   mark beside a trash key, in every view; the trash key uninstalls at once. There is no "✓ Installed"
   word key and no ask step.
3. **My plugins (renames the Installed pill of §7.5).** The pill reads My plugins · n; pressed, it shows your
   installed plugins, with Yours for the ones you made.
4. **Create, the MCP connector (replaces the upload drawer of §7.7).** A dialog over a light scrim: Name,
   MCP server address, Auth (None · API key · OAuth, each showing its fields), Icon (initials by default, Choose an image),
   Kind, Where (Private · Public). Connect checks the address, connects, and lists the tools the server
   offers, each with a check; Add makes the server your own installed plugin, with a conversation that
   teaches its tools. A typed key or secret never leaves the page; the front end stores nothing of it.
5. **The controls.** No browser prompt or confirm remains. Editors open in place with ✓ and × (Enter and
   Esc): the draft's limit chips, Change words, Change limit, Top up and Take back (USDC between you and
   Gravit's wallet; Top up stops at the USDC you hold, Take back at what the wallet holds), Memory
   entries. Withdraw, End limit, Stop Gravit, Forget all and Reset demo ask in place and act on the
   second press; a closed conversation offers no Withdraw or Stop, and End limit shows only while a
   limit exists. The composer's + picks files that send as chips; the mic listens and fills the
   composer (scripted here). The phone key calls Gravit: ringing, a live call with a timer,
   mute and hang up, then a call card; an accepted incoming call goes live the same way. The mail key
   opens Gravit's own mailbox. Account's Move, Receive (address, QR, copy), Statement (activity, CSV) and
   Connect an account work as drawers.
6. **Tokens.** The equity blue is Linqi's `--alloc-equity`; the white words on it use `--on-equity`, a
   second addition beside `--down-edge` (his own `--blue` is his orange RWA colour).

## 14. Amendment, 2026-10-10 (round 3)

The operator's words, after round 2: the 我的插件 pill loses its count and takes an English name; "by
MCP I meant wrapping Discover as an MCP, so that plugins users make themselves can be uploaded into
Discover"; no "Free · by …" and no "Just installed" chip, keep Open in Messages; pressing the mail key switches fully to
a mail screen. Where this section and §7.1, §7.3, §7.4, §7.5, §7.7, §12 or §13 disagree, this section
wins.

1. **My plugins.** The pill reads My plugins, with no count; pressed, it shows Installed and Yours as before.
2. **No author or price.** Cards have no author line (§7.3's "Free · by Gravit" is gone) and no "Just installed"
   chip; a just-installed card keeps only "Open in Messages ›", and the install toast stays. The drawer's
   meta line is the kind and, for a catalogue plugin, how many installed it ("Bots · 1.2k installs"); for your
   own plugin, where it stands ("Data · Private", "Data · In review", "Data · Public"). The drawer has no
   How it is paid section. `by` stays in the data, never on screen; the shop stamps the author from the signature.
3. **Create is Discover's own MCP face (replaces §13.4).** Discover is itself an MCP server (§7.7), and
   Create shows it: a dialog titled Discover MCP with the server address, its seven tools as chips
   (`shop.search` · `shop.get` · `shop.install` · `shop.uninstall` · `shop.publish` · `shop.mine` ·
   `plugin.call`), a Client switch (Claude Code · Cursor · Codex) with the line that client takes to add
   Discover and a Copy key, and the status Waiting for a connection. Nothing in the dialog can be typed. When a client
   connects, the status reads "<client> connected" and the client's calls are listed (`shop.mine()` ✓). When it
   asks `shop.publish`, the owner sees the manifest (logo, name, one line, kind, tools, what it needs),
   picks Where (Just me · Private | Public shop) and signs it in the drawer's grammar (What you sign:
   private = publish and install for Gravit, with May, May not and Until; public = publish into the
   Public shop), with Refuse or Publish. Focus never lands on Publish by itself.
   - Private: published and installed at once; the plugin opens its teaching conversation, leads its
     kind's shelf and See all, and sits under Yours; toast "<name> uploaded · Private · Open".
   - Public: reviewed first (a sandbox run, its permissions and author read; 5 s here) behind a clock key
     on its card and a disabled In review in its drawer; toast "<name> uploaded · In review". When the review
     passes, Discover writes to Gravit's mailbox ("<name> passed review"), Discover shows "<name> passed review · Public
     · Open", and the owner installs it with the drawer's usual signature.
   - Here the client is scripted: Copy, or the director's Plugin upload, starts it; it connects after 1.5 s and
     asks to publish 1.5 s later. The uploads come in turn (Moat score, private; CPI quick read, public; then
     the same again with a number). The back end of §9 gains `shop.publish`'s client authorization and
     the real review path.
4. **Mail is a screen (replaces the mailbox drawer of §13.5).** The mail key is a link to `#/mail`; on Mail
   it is current. The second level, which §13.1 kept for Messages, also opens on Mail: the title Mail,
   Gravit's address, and the letters newest first (sender, time, subject; an unread letter has the dot
   and a bold subject). The main column shows the open letter (`#/mail/<id>`: subject, sender and time,
   its files, the body) or, with none open, No mail selected. Opening a letter reads it; an unknown letter opens
   the inbox. Below 860 px the letters stand alone until one is open.
5. **The director** gains Plugin upload and sits above the dialog's scrim.

## 15. Amendment, 2026-10-10 (round 4): Markets and Trade after Linqi's

The operator's words: "Markets和trade的前端借鉴Linqi的buyer-agent-demo" — the Markets and Trade screens follow
Linqi's own pages (buyer-agent-demo @ 0ef5131, `src/portfolio/public/ui/markets.js` and `ui/trade.js`), ported into
gravit-ui's render functions on his tokens, with stand-in data. Nothing is imported from `demo/`.

1. **Markets.** His category tabs, shown only for kinds that have markets (All · Crypto · Stocks · RWAs ·
   Predictions; Watching once something is starred; All results while searching), his sort (Most traded ·
   Biggest moves · Closing soonest), one table with one key per row — Trade where the account trades it,
   Connect to trade at a public venue (the same stand-in connect as Account) — and predictions as cards with
   Yes and No at the ask. The search sits in the head, as on Discover.
2. **The market drawer** is the route `#/markets/<id>` (ids match without case; an unknown one opens Markets):
   price, 24h change and facts (bid, ask, volume; a prediction's close), a chart in 5m · 1h · 1d, Across venues
   with the best price marked and the public listings, You hold with the orders on it (Gravit's cancel after
   an in-place confirm and leave a line in their conversation), Gravit on it (the conversations about it and
   any card it waits on), and On the statement (with Open the Statement). Buy, Sell where it is held, Hand to
   Gravit and Watch. A chat or Portfolio ticker opens it.
3. **Trade.** His kind seg (Crypto · Stocks · RWAs · Predictions), a picker (You hold · Recent · Most traded, a
   search), Under way (orders on their way or on a book, by you or by Gravit, and the cards Gravit waits on),
   and his ticket: Where (the account's venues with the best price and the others' distance; public ones with
   Connect to trade), Buy or Sell, Amount in dollars or units, Market or Limit (cents for a prediction), the
   quote prepared from the fields, What you sign, a signature good for ten minutes, and Sign and place.
4. **The owner trades by hand.** A hand order is the owner's, capped at the account's $100 a move; it never
   draws on a conversation's limit. Here the press stands in for Linqi's device-key signature; a stand-in
   venue answers 0.9 s later. A fill moves the holding (holdings now carry quantities), the cash at the venue
   (the stand-in wallet pays in USDC), the Statement, net worth and the allocation bar (with RWA and Predictions
   in his colours). Hand to Gravit instead opens a new message with the ticket in words and the limit chips set
   where Gravit may trade; only the owner's send gives Gravit room.
5. **Kept out.** Perps and Pre-IPO (no margin model; Memory says No leverage), stop orders, time in force,
   amend, Cancel all, wallet sends, live price ticks (quotes hold still, so a resting limit stays open), his
   top-bar search, lens and statement modal, and his explanatory sentences (kept for F16 and the onboarding
   guide). The back end of §9 gains the venues' real quotes and order endpoints behind the same ticket.

## 16. Amendment, 2026-10-13 (round 5): the re-laid canvas against the build

The operator's words: "画布更新了，你再看看" — compare the re-laid canvas (§2's rows 1–5) with `gravit-ui/`. The
comparison found 132 differences: 30 where the code was wrong, 65 where a board was drawn wrong, 37 for the
operator. The operator answered four: a plugin or a market opens as its own page and Back returns to Discover or
Markets ("点击插件/股票之后就完全是插件和股票的页面，点击退回就回到discover和market的页面"); Details keeps label/value
rows; Venues stay on their own segment; and "改代码那 30 处，改正画布上画错的板，spec 和 ledger 跟着更新". The other
operator items took the defaults announced with the comparison: what is appearance follows the boards, what is
behaviour stays as built. Where this section and §4–§8, §13, §14 or §15 disagree, this section wins.

1. **A plugin and a market are pages (replaces the drawers of §7.4, §14.2 and §15.2).** A card opens
   `#/plugin/<id>`: "‹ Discover" (back to the shelf, See all or search it came from), then the head — the 72 px
   logo, the name 28/800, the meta line of §14.2, and the one key (Install, Uninstall, or a disabled In review)
   at its right — then the blurb, What you sign, What you can ask it, What it writes, its tools and What it needs
   from you. A market opens `#/markets/<id>` as a page: "‹ Markets", the head with the market's name 28/800 and its
   keys (Buy, Sell where held, Hand to Gravit, Watch), price and facts, then Price history and Across venues
   beside You hold, Gravit on it and On the statement (one column on a narrow page). Focus lands on the way
   back; an unknown id opens Discover or Markets; Escape leaves a page alone. Kind 5's + and a toast's Open lead
   to the plugin's page; a ticker leads to the market's page. §13.1's one drawer at a time now covers Details,
   Create, Settings and the Account panels.
2. **The catalogue fills the page.** Every catalogue plugin has What you can ask it, What it writes, an install
   count and what it needs (KOL bot as F10 draws it: "Bots · 640 installs", three questions, two lines it writes,
   "Nothing. Reads Portfolio and Markets."). What you sign names the manifest's slug (`install kol-bot`,
   `install buffett-bot`). The never line reads "Never: moves money, pays anyone, changes a limit". My plugins
   lists Installed in install order. The toast has no ×; it leaves by itself (§14.3).
3. **Conversations.**
   - Plain talk is 66% of the thread wide; every card and green bubble 80%. A chip inside a card hugs its words.
   - An order card's line is venue · type · amount; its card id stays in the record (F16, "record fields moved to
     Details").
   - The quote bar of a signal and the K-line's dashed rules are `--alloc-cash`; the technicals head carries the
     time of the read ("4h · technicals · 14:20").
   - Time dividers stay as built: one only after a 15-minute gap (§5.2's "14:04" is an example of the format).
     The list keeps its order; a new conversation goes on top.
   - Kind 7 now happens: the director's Monitor posts a Telegram monitor signal and Gravit answers "Seen. Not
     chasing." (the seed does not install Telegram monitor; the director is stage machinery).
   - **A sixteenth kind, alert:** Gravit, red edge, one sentence, no keys — the verdict of a check that found
     something bad ("The address is on a scam list. Nothing was sent."). It joins §6's table after kind 15.
   - Kind 13: the banner drops in over the main column (not the window), its head names the conversation the
     message will land in ("14:52 · Small BTC position under $70k"), and its ticker is a link, in the banner and in
     the message that lands.
   - Kind 14: only a call coming in, or one missed, is red-edged; a call that connected, or one you placed, is
     white. Ringing out shows "Calling Gravit…" and "Ringing"; a live call shows Gravit, the timer (m:ss, 20/800),
     mute and hang up, and no transcript line. The card after a call carries its title and chip, the topic with
     its time ("About BTC · 14:52"), and for a call that connected what was said ("Said: Hold until CPI is out;
     raise the order cap to $50 after."). When you ring Gravit, it picks up about BTC.
   - The group head's members line is 12 px (§5.1). Details (§5.6) keeps label/value rows; each plugin row
     carries its kind at the right; Stop Gravit hugs its label.
   - F6 carries no hint line: decision 9 wins over §2's and §5.7's "one line"; the sentence is on F16.
4. **Controls (amends §13.5).** An editor names each box ("an order", "in all"; "Top up" or "Take back"; the
   draft's chips "an order", "in all", "days", "on") and stands in place of the buttons that opened it; boxes are
   36 px, its ✓ and × 32 px round keys with 14 px glyphs. A confirm's two keys share one height. Picked files sit
   inside the composer, above the words, as chips with their names only. The mic, listening, is an ink key named
   "Stop listening", and the words fill the composer as it hears them.
5. **The two levels (amends §13.1).** The list titles (Messages, Mail) are 22/800; the new-message + is a 32 px
   round ink key with an 18 px glyph; a badge is 20 px and hangs over its key's corner; "You" is 10 px in its
   28 px ring; collapsed, the first level is a column of 44 px squares, Account included; the collapse key is a
   28 px round key with a 16 px chevron.
6. **Account, Mail, Create, Trade.**
   - Portfolio is the net-worth card alone; Venues stay on their own segment (§8). "Net worth" is a 12 px 600
     label; a holding's change is coloured at regular weight.
   - **Receive takes money into the owner's own Stand-in Wallet** (`0x9a7c…d41e`), not Gravit's: the drawer is
     titled "Receive · USDC" with a Base chip, an 88 px QR left of the address, and Copy address. Gravit's wallet is
     reached from Details' Top up (§13.5).
   - Memory's entries read as F13 words them ("Value over hype", "No order over $25; real money passes me first",
     "Telegram calls: read, never chase", "Ask before adding; never widen a limit alone", "BTC on the exchange,
     cheaper than the DEX", "Brief at 7:30; hold before CPI"); the sources are §8's, plus "Learned when you
     declined"; Where it is used names Group chats ("Who speaks first, whose word is discounted").
   - An unread letter's subject is 700; a letter's file chip has even padding.
   - Create's Client and Where segments are 38 px like every segment; pill and small-button words are 600.
   - The Trade picker marks the market whose ticket is open; a resting order reads "on Stand-in Broker’s book".
   - The seed moves to version 5 (the owner's wallet, Memory's words), so a saved demo resets once.
7. **Kept as built, the boards follow.** Change limit edits per order and total, not the end date; an order row's
   first press reads Cancel; the Data and Quant shelves keep their fifth card (the HFT-style Like shelf needs
   them); after Refuse, Create keeps the run with a red ✗ on `shop.publish`.
8. **The canvas.** The boards drawn against this spec were corrected on 2026-10-13: the F1 thread (and its
   copies on F17, F8, F9) with the receipt and the two requests as their own messages at their levels and the
   answered card carrying its answer; F8's Details as the 400 px drawer with label/value rows and the seed's facts;
   F6 without the hint; F7 with the group row; F14 in the seed's words; F3 and F15 in the code's sentences, with a
   fill receipt for kind 9 and the alert as specimen 16; F10 redrawn as the KOL bot page and F22 as the BTC page;
   F4, F11, F19 and F20 as Discover and Create render; F5, F13 and F18; F21, F23 and F24. F16 gained the sentences
   taken off in this round and in §15.5 (Linqi's explanatory lines), and its notes now cite F19/F20, My plugins and
   the page.
