# Demo v2 · Gravit front end — Design

**Status (2026-10-09):** front end settled. The operator closed the design rounds with *"可以定前端了"*
on canvas version 50. This spec is the written form of the settled boards: what every screen shows,
how it is drawn in Linqi's visual language, and what it expects from the back end. It does not decide
how the back end is built: the architecture boards (canvas rows 5–6, D1–D5: 架构 · 组件 · 数据流 ·
出错与测试 · 十幕) were drafted on 2026-10-08 and parked on the operator's word (*"目前还是专注在前端设计"*);
they get their own spec when the operator returns to them. §9 lists the seams the screens need so that
spec has a checklist.
**Companion:** the design canvas this spec is the written form of —
<https://claude.ai/artifact/XwsiQ4VTqzfGdtzBi2LWgb> (Design type; rows 7–10 are the settled boards,
rows 1–6 the decision history). On a disagreement this spec wins; the canvas is the picture.
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

Two earlier decisions still bind: Venues are never in Discover (they stay in Account), and Serenity
bot's one line is 科技产业链分析.

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
  "你" avatar at the bubble's foot. Every owner message is a signed instruction.
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
"Tell Gravit… 打 @ 点名一个 bot") · a 32 px surface-2 round **mic** · a 36 px equity-blue round **send
arrow** at the far right. Sending signs. The iMessage rule may apply at build time: mic when the input
is empty, send when it has words.

### 5.5 The new-message state (F7)

Pressing + inserts a current row at the top of the list (dashed + avatar, "New message", "now",
"还没发出去"). The head becomes: Cancel at the top-right; a 44 px G avatar; the title as a centred,
borderless 17 px 700 input ("这件事叫什么（不填就用你第一句话）"); a "To:" line with a Gravit chip and a
dashed "+ 加个 bot，就成群聊" key. The thread area is empty. Above the composer a chip row "附一份额度":
每单 $25 ▾ · 总 $100 ▾ · 到 Oct 15 ▾ · 在 Stand-in Exchange ▾ · 不附 — sent together with the first
message as one signature.

### 5.6 Details (F8)

A 400 px drawer from the right (Linqi's `#drawer` look): 这件事 (title; 你委托于 Oct 8 · 到 Oct 15 ·
intent-0003; Change words / Withdraw) · 额度 ($25 an order · $100 in all · $95 left; Change limit /
End limit) · 插件 (what this conversation uses; "Find more in Discover ›") · Gravit 的钱包 ($12.40 USDC ·
Base · address; Top up… / Take back…) · 模式 (Guard | Beast) · Stop Gravit (a down-fill danger pill).

### 5.7 Empty (F6) and Black (F9)

F6: the rail has the Messages header and no rows; the main column centres a 56 px G, "还没有交给
Gravit 的事", one line ("在下面说一句你想让它做的事，或者点左上角的 + 先起个名。") and three surface-2
chips that fill the composer (小仓位买 BTC · 跟单 Pelosi · 查一个地址). F9: F1 with the Black column of
§3.1 and every shadow removed; the ✓ and ✗ keys sit on `#17191c` with a `#2b2e34` hairline.

### 5.8 Group chat (F14)

Gravit plus any installed bots in one conversation: the cluster head, named bubbles, each sender its
own avatar. Gravit alone proposes and signs for; bots argue. A proposal that touches several orders is
one card with a row per order (ticker · reason · venue · type · amount) and one ✗/✓ pair.

## 6. Message kinds and colour levels

Colour is importance, five levels, all from the tokens:

| level | drawing | carries |
|---|---|---|
| 灰 · talk | surface-2 bubble | Gravit thinking, progress, replies |
| 白 · to read | surface bubble, 1 px border | the morning brief, K-line analysis, monitor signals, research |
| 橙边 · needs a decision | surface bubble, warn-edge, a warn-fill chip ("answer by 14:33") | approve an order, grant a limit, install a plugin |
| 红边 · urgent or bad | surface bubble, down-edge, a down-fill chip | breaking news, refusals from the doors, incoming calls |
| 绿底 · done | up-fill bubble, a white chip with up-colour words | filled, paid, report done |

The fifteen kinds (F3 1–10, F15 11–15), who speaks, the level, the keys, and what each is bound to:

| # | kind | who | level | keys | bound to |
|---|---|---|---|---|---|
| 1 | the owner's words | 你 | blue | — | a signed `setIntent` / `say` |
| 2 | Gravit's words | G | 灰 | — | the journal |
| 3 | an order to approve | G | 橙边 | ✗ ✓ | the approval card (`approveCard`), its deadline |
| 4 | a limit request | G | 橙边 | ✓ ✗ | Give a limit (`setPolicy`) |
| 5 | a plugin request | G | 橙边 | + ✗ | the Discover drawer (`shop.get` → `shop.install`) |
| 6 | a bot's proposal that executed inside the limit | bot | 绿底 | — | the order and its ledger row |
| 7 | a monitor's signal | monitor | 白 | — | a plugin message; read-only, never an order |
| 8 | a door's refusal | G | 红边 | — | the error code verbatim (`E_MANDATE_PER_ORDER_CAP`) |
| 9 | a receipt | G | 绿底 | — | a ledger row (fill, payment) |
| 10 | the close | G | 绿底 | — | `agentReport` done |
| 11 | K-line technical analysis | G | 白 | — | a plugin output; the ticker is a link to Linqi's market drawer (`openMarket`) |
| 12 | the morning brief | G | 白 | — | a 7:30 scheduled plugin output with tickers |
| 13 | breaking news | banner | 红边 | × | a banner over the thread for 5 s, then a red-edged message in it |
| 14 | an incoming call | card | 红边 | decline ✗ accept ✓ (44 px phones) | the rail's phone line; a declined call becomes a message |
| 15 | a group-chat message | bot | 灰 | — | the sender's name above the bubble |

## 7. Discover, the store

### 7.1 Header

"Discover" · the 44 × 420 search pill · an **Installed · n** pill (pressed = ink; filters the page to
installed plugins) · an **Upload a plugin** pill with an upload glyph. No sentence under it.

### 7.2 Shelves

Six shelves, each a title (17 px 700) with "See all ›" in equity blue at the right and a horizontal
row of 300 px cards, three in view and the fourth cut at the main column's edge (the row bleeds into
the column's padding): **Like** (recommended from Memory — the user's style: a value investor gets
Buffett bot, 研报, 美国政客 bot, Quant team; a high-frequency trader gets high-frequency strategies and
low-latency data; someone who wants to try quant gets a team to run an idea) · **Data** · **Monitors** ·
**Bots** · **Crypto** · **Quant**. The catalogue on the boards: Price feed, News sentiment, 研报,
On-chain flows · Telegram monitor, X monitor, Whale alerts, Earnings calendar · 美国政客 bot, KOL bot,
Buffett bot, Serenity bot (科技产业链分析) · 地址欺诈检测, 交易所价差, Gas 时机, 合约体检 · Quant team,
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

Linqi's drawer: a 56 px image, the name 17 px 700, "Bots · by Gravit · Free · 1.2k 装了", one line of
what it is; then sections 它能被问什么 · 它会写什么 (what it writes into the conversation, and what it
never does) · 怎么付 · 要你什么 (nothing, a Telegram session, an exchange key…) · **你签的是**, the
signature table inline — What you sign `install buffett-bot` · For `Gravit · 0xec4c…16c1` · May `read
Portfolio · propose in your limit` · May not `pay anyone · move money` · Until `you uninstall` — and a
full-width ink **Install**. No second sheet pops up: the drawer is the signing surface.

### 7.5 Installed (F11) and after install

The Installed pill pressed shows only installed cards in a grid, each with the trash key, plus a
"你上传的" group for the user's own plugins. Right after an install: the new card carries a green
"刚装好" chip and "Open in Messages ›"; a toast "Buffett bot 装好了 · Gravit 开了一个会话教你用 · Open";
and the rail gains an unread conversation opened by the plugin ("Buffett bot：怎么用我") that teaches
its use.

### 7.6 Money

No paid plugins, no per-call or per-minute prices. Revenue is a commission on model calls and on filled
trades. The earlier paid-plugin mechanics (a payees approval per agent, x402 from Gravit's wallet, a
card for the first payment under Guard) are retired for plugins and kept on F16 in case a plugin must
pay an outside data vendor.

### 7.7 Upload a plugin and the shop's MCP face (F12)

The upload drawer: 名字 · 一句话 · 类型 (Data · Monitors · Bots · Crypto · Quant) · 图标 (44 px slot,
initials by default) · 它暴露的工具 (the MCP server's tool names) · 要用户什么 (none · Telegram session ·
exchange key · wallet address) · 放哪 (**只给我自己 · Private** | **放进 Public shop**) · Cancel / Publish.
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

**Memory (F13)** — what Gravit remembers about the user, in a two-column layout. Left, "Gravit 记得的你":
entries grouped 风格 · 规矩 · 场所和人, each with its text, its **source and date** (你说的 · 来自额度 ·
它从你的问题里学的 · 它自己比出来的 · 来自装的 bot), a pencil key and a trash key; an input "加一条它该记住的…"
with an ink Add. Right, "它用在哪": chips naming the places Memory feeds (Discover's Like shelf, the
morning brief, a new conversation's defaults, group chats); "开关": three switches — 让 Gravit 记新东西
(on), 它学到的先问我再记 (off; a new memory then arrives as a card to answer), 群聊里的 bot 也能看 Memory
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
