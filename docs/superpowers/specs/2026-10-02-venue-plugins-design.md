# Venue Plugins — Design

**Status:** design, awaiting operator review on the five decisions in §11. Not built. Extends the
skeleton design (`2026-08-29-market-strategy-account-skeleton-design.md`, the `alpaca_kit` seam) and
the bots design (`2026-09-07-bots-and-rooms-design.md`, the tool mask); it prepares, and does not
itself fire, the charter's real-money and hosted-deployment triggers (§12).
**Companion:** the design canvas this spec is the written form of —
<https://claude.ai/artifact/2aXJoRzTzp5kDhMqCD8fLk> (seven artboards, private to the operator). On a
disagreement the spec wins; the canvas is the picture.
**Pins:** repository `main` @ `a09f217`; dsh `0.1.1-rc.2` (the face's two pins, `face/package.json`).
**Language of citations:** bare paths are this repository; `survey:line` cites the frozen dsh survey
`docs/research/2026-08-22-deepseek-harness-dsh-survey.md`; vendor facts cite the vendor page in §17.
A substrate claim this repository cannot verify offline is marked **[spike Sn]** and listed in §13 —
the plan runs those before code depends on them.

---

## 1. Context and decision history

The operator's request, 2026-10-01, in two parts. First the vision: *"这个市场有很多卖方，比如说
binance / hyperliquid / solana / 纽交所等，但是买方 agent 还未成型 … 我们已经有以 dsh 为基底的 agent，
我们需要给这个 agent 提供多种 plugin（身份和钱包）使其接触到这些资产。"* Then, 2026-10-02, the framing
that this design adopts as its organizing idea: *"把 agent 想象成和人类一样的投资者，需要接触
solana / hyperliquid 这些，那么我就需要 plugin / MCP 去接触这些市场，对吧。"*

The answer to "对吧" is yes with one correction, and the correction is the design: a plugin is not
one thing but three. A human investor walks into any market with an **identity** (the venue knows
who they are), a **wallet** (custody and the power to sign) and a **seat** (a terminal: quotes,
account view, order entry), keeps a **ledger** across venues, and gives their trader a **mandate**
that is bounded and revocable. The trader never holds the owner's seed phrase. Mapping those five
things onto this tree, one at a time, is §2; the rest of the spec is the mechanism each one needs.

Decisions, in the order taken. The first is the operator's; the others are proposed here and are
confirmed or overturned in §11.

1. **A venue is reached through a dsh MCP row** (operator, 2026-10-02). The seat is a
   `@deepseek-ai/dsh-mcp-client` stdio row, exactly the shape `face/src/akshare.ts:13` already
   composes for AKShare, inserted between the bundle layer and the operator's patches
   (`face/src/boot.ts:177-179`).
2. **Identity and wallet are separate objects at every venue.** The read credential and the write
   authority are never the same key. Today they are one key in one file at the repository root
   (`DEVELOPMENT.md` §9 R1); that is acceptable for a paper account with a hostname pin and for
   nothing else.
3. **Identity records live in dsh's credential seam, outside the workspace.** This is charter P1
   applied literally — "wide hands, no self-keys … enforced by placement" (`Kairos-Design.md:54`).
   **[spike S1]** on the mechanism (§13).
4. **The signer is a process or device the agent cannot read.** Where a venue issues a scoped,
   expiring agent key, that key *is* the signer's boundary (Hyperliquid); where it does not, a policy
   signer stands in (Solana), and this design does not build one (§12, §14).
5. **The plugin contract is an allow-list, enforced at mount.** Every tool a venue row registers is
   classified `read` or `write` by a manifest; a write tool's raw name is registered with Gate 2
   when the row mounts; an unclassified tool refuses the whole row. §4.4 says why the current gate
   cannot be extended by adding names.
6. **The market-data Protocol is not generalized.** `MarketDataSource` is US-equity-shaped (daily
   bars, corporate actions, EDGAR). Venue reads are live and unguarded, like AKShare's
   (`AGENTS.md:12`); they never feed `replay_days`. Charter Rule 8.
7. **Everything in this design runs on paper or a testnet.** Mainnet keys come after the next
   charter (§10 step 5, §12).

## 2. The investor model

| The investor carries | At the venue it is | In this tree it lands at |
|---|---|---|
| **Identity** — the venue knows who you are; read and write use different identities | a CEX account with scoped API keys; an on-chain address; a broker account number | dsh's credential seam: a record in `$DSH_HOME/.credentials.yaml`, resolved per operation, never in a `.env` at the repository root (`survey:668`; today's `.env.alpaca` is R1) |
| **Wallet** — custody and signing; the owner keeps it | a hardware wallet, an exchange master account, a bank | a signer the agent cannot read: Hyperliquid's agent wallet, a Binance key with withdrawals off, a Solana policy signer. The agent gets *intent* tools, never the key |
| **Seat** — a terminal into one venue | quotes, account view, order entry; seats do not know each other | one `dsh-mcp-client` row per venue, with a manifest classifying every tool (§4) |
| **Ledger** — positions, cash and open orders across venues | each venue keeps only its own | `/account` becomes a multi-venue read-only aggregation, every row carrying its source and observation time (§8). It replaces no venue's own ledger |
| **Mandate** — what may be traded, how large, until when; revocable | Hyperliquid's `validUntil`; Binance's permission toggles and IP allow-list; CDP's daily caps — enforced by the venue | Gate 2's card above the model (`face/src/orders.ts`); venue-side policy below the code (§5). Both, or the gate is prose |

## 3. Architecture

The current one-page picture (`Kairos-Design.md` §3) gains one row and one column. The row is
VENUE PLUGINS, between KAIROS and the venues; the column is OUTSIDE THE WORKSPACE, holding the
identity records and the signer. Everything else stays where it is.

```
OPERATOR    holds the master accounts and master keys · answers every card ·
            reviews diffs · [new] an out-of-band approval device before real money
FACE        Gate 2 (one card per write) · /market (three markets today,
            face/src/quote-types.ts:2) · [new] /account as a multi-venue ledger
KAIROS      dsh runtime · tools come from each MCP row · a bot's allow mask
            (mcp__*__<raw>, face/plugins/bot.js:56) decides which venue a voice sees
VENUE       alpaca_kit (US equities + crypto spot, paper, exists) · [new] hyperliquid
PLUGINS     (perps, agent wallet, testnet) · [new] binance (spot, CCXT MCP, testnet) ·
            [later] solana (DEX aggregator, policy signer, devnet)
OUTSIDE     identity records in the credential seam · the signer · venue-side policy
VENUES      NYSE via Alpaca · Hyperliquid · Binance · Solana DEXes
```

What is new is the row, the column, and two rules the row obeys: a plugin's write tools register
with Gate 2 at mount (§4.3), and a plugin's identity is a *reference*, resolved outside the agent's
reach (§4.2). What is not new matters as much: Gate 2 stays the one producer of order cards, tree-wide
(`face/src/boot.ts:332-356`), and a bot's mask stays visibility, not authority (charter D12).

## 4. The venue plugin contract

### 4.1 The manifest

One directory per venue under `venues/`, one `manifest.yml` each. The example is Hyperliquid
because it is the venue where the venue side already enforces the identity split (§6.3).

```yaml
# venues/hyperliquid/manifest.yml
venue: hyperliquid
row:
  id: mcp-hyperliquid            # the cordis row id; composed like mcp-akshare
  plugin: "@deepseek-ai/dsh-mcp-client"
  transport: stdio
  command: ~/.local/bin/hl-mcp   # installed separately; the face never downloads
network: testnet                 # mainnet requires the next charter (§12)
identity:
  ref: HL_AGENT_KEY              # a credential reference; the value never enters the workspace
  kind: agent-wallet             # approved by the master; cannot withdraw; carries validUntil
tools:
  read:  [markets, book, funding, positions, fills]
  write: [place_order, cancel_order]
  # every write raw name is registered with Gate 2 at mount; descriptions carry "(operator-gated)"
  # a tool the row registers that is in neither list refuses the row
pit: none                        # live reads only; never replay evidence
ledger: [positions, fills]       # the two read tools /account aggregates
```

Field by field:

- `row` is rendered into a `FacePatchList` insert exactly as `aksharePatches()` renders AKShare's
  (`face/src/akshare.ts:13-36`): `failOnStartupError: false`, so a missing executable logs and does
  not take down the chat host; `cwd` the repository root; a bounded `toolCallTimeoutMs`.
- `network` is a declared fact the face reads, not a hint: `mainnet` on any manifest refuses the
  row until §12's trigger has been answered in a new charter.
- `identity.ref` names a credential record; the row's `env` block carries the reference, and the
  value reaches the MCP child the way the LLM key reaches the model route today — resolved per
  operation by the credential seam, shadowed by nothing in the workspace (`survey:668-669`).
  **[spike S1]**. `identity.kind` is documentation that the drill checks against the venue (§15).
- `tools.read` / `tools.write` are raw names (`<raw>` in dsh's `mcp__<server>__<raw>` minting,
  `face/plugins/bot.js:52`). The face compares them against the tools the row actually registers.
- `pit` is `none` for every venue in this design (decision 6). A future venue with a captured bed
  would say `guard` and route through `GuardedSource`; nothing here needs that.
- `ledger` names the read tools §8 calls.

### 4.2 Identity: a reference, not a value

Today the broker keys reach the `alpaca_kit` MCP child through the operator's cordis patch, as
`APCA_API_KEY_ID: ${APCA_API_KEY_ID}` in the row's `env` (`dsh/profile/cordis.yml`), from a `.env`
file at the repository root the documented run path sources (`face/README.md` "Run"). R1 records
what that costs: a shell turn reads the file and imports `alpaca_kit.account` directly; the paper
hostname pin (`alpaca_kit/account.py:16,73`) bounds the damage.

This design moves every *new* venue's identity into the credential seam, and proposes moving
Alpaca's with it (§10 step 1). The seam is dsh-base's: records in `$DSH_HOME/.credentials.yaml`,
consumers "re-resolve at each operation and never cache across operations", `describe()` exposes the
source layer and writability without the value, and spawned commands get a scrubbed environment
(`survey:490, 538, 668-669`). What the manifest carries is the reference name. Whether a row's `env`
block can carry a credential *reference* that the MCP client resolves at spawn, rather than a literal
the operator's patch interpolates, is the first spike (§13 S1); if it cannot, the fallback is the
operator's patch interpolating from `$DSH_HOME/.env`, which is still outside the workspace and still
scrubbed from the shell, and still better than R1.

### 4.3 Write tools register with Gate 2 at mount

Gate 2 today matches a constant list — `ORDER_RAW_NAMES = ["place_order", "cancel_order"]`
(`face/src/orders.ts:33`) — plus the literal `(operator-gated)` on an `mcp__` tool's description
(`orders.ts:38, 239`). Boot audits the live registry and refuses to start when a marker-carrying
tool has a name the gate does not match (`orders.ts:270`, `boot.ts:364`).

The contract keeps both anchors and feeds them from manifests instead of a constant: at mount the
face unions every manifest's `tools.write` into the raw-name set the gate matches, and the drill
asserts that each such tool's description carries the marker. A server that ships its own tool names
— CCXT's `createOrder`, say — is covered by its manifest naming them, not by renaming the server.

### 4.4 Why the contract is an allow-list

The current gate is a deny-list of two known names. A third-party MCP server mounted as a row
registers a write tool that is neither named `place_order` nor marked `(operator-gated)`; `isGatedTool`
returns false (`orders.ts:239-245`), the boot audit finds nothing to refuse (it only flags
*marked* tools with unknown names, `orders.ts:270-278`), the face comes up healthy, and the tool is
ungated — silently, the exact failure mode `orders.ts`'s own header names as the one it exists to
prevent. Adding names to the constant would not fix this; the next server has other names.

So the rule inverts: a venue row's tools are known or refused. At mount the face lists the row's
registered tools (`ctx.tools.schemas()`, the same call `expandAllow` uses, `bot.js:80`) and compares
them with the manifest; a registered tool in neither list refuses the row and logs the missing names.
Because dsh-mcp-client activates even when its first connection failed and the registry fills in
asynchronously (`orders.ts:224-227` records this), the comparison runs when the row reports its tool
list, not at boot alone — **[spike S2]**.

### 4.5 Read tools and the bot mask

Read tools need no card. Which bot sees which venue is the operator's choice in that bot's allow
list, and the `mcp__*__<raw>` form already resolves against whatever server name the operator gave
the row (`bot.js:56-75`). Nothing in this design changes `bot.js`; it adds venues for the mask to name.

## 5. The write path

```
Kairos proposes an intent   →   Gate 2 card   →   venue-side policy   →   signer   →   venue
(place_order, a write tool)     (face; the        (agent key scope,      (a process the   (fill;
                                operator answers; validUntil, caps;     agent cannot      receipt
                                allowed-once      enforced by the       read)             into the
                                into the log)     venue)                                  session)
```

The two middle-right steps are the new lower layer. Charter Rule 2 — enforce below the layer that
runs arbitrary code, or admit the gate is prose — is why they exist: Gate 2 stops the model's ordinary
tool calls and nothing else (R2), and its answer can be forged from the workspace over loopback (R3a).
For a paper account both are accepted debts (D8, D10). For a venue that can move value they are not,
and this design does not pretend a better card fixes them. What bounds a forged approval on
Hyperliquid is that the agent key cannot withdraw and expires; on Binance, that the key cannot
withdraw and is IP-bound; on Solana, the policy signer's caps. The venue enforces that, not the face.

Two things the path still needs before any non-paper, non-testnet venue, both charter rows rather than
this design's: the human half of the order drill (D3; `DEVELOPMENT.md` §10 item 1) and an
out-of-band answerer for the card (§11 D5), so that R3a's forged answer is no longer a one-shell affair.

Charter Rule 4 applies to the new gate surface as to the old: every venue's write face ships with a
drill, and the drill's first case is the trap in §4.4 — a row registering an undeclared raw name is
refused at mount, not waved through.

## 6. The venues

They are not the same kind of thing, and the identity plugin's shape at each follows from whether the
venue issues a scoped agent key itself.

### 6.1 NYSE, via Alpaca — exists

Not a venue one connects to; reached through a broker. `alpaca_kit` is the plugin already: one row,
Gate 1 by flag and keys (`alpaca_kit/mcp/tools.py:130-132, 298`), Gate 2 in the face. Alpaca's paper
account trades crypto spot on the same key and the same paper host (§17 [A1]), which makes it the
cheapest first multi-asset step. It also exposes the first equity assumption: the MCP `place_order`
tool does not expose `time_in_force` (`tools.py:299-301`), the library defaults it to `day`
(`account.py:85-89`), and Alpaca's crypto orders accept `gtc` and `ioc` only (§17 [A1]) — so the first
paper crypto order through today's tool is rejected. What this plugin needs: a manifest, the
`time_in_force` argument, and its identity moved out of `.env.alpaca` (§10 step 1).

### 6.2 Binance — a centralized exchange

API keys carry separate permissions — reading, spot and margin trading, withdrawals — and can be
restricted to trusted IPs; withdrawals should stay disabled (§17 [B1], [B2]). Identity is one key with
withdrawals off and an IP allow-list; the signer is the exchange's own matching engine acting on that
key. CCXT ships an official MCP server that runs locally over stdio, keeps API keys on the machine and
out of the model, and enables trading only when explicitly turned on (§17 [C1]); it is the candidate
row, pinned by commit the way AKShare is (`face/README.md` "AKShare MCP"). Its tool names are its own,
which is exactly the §4.4 case — **[spike S4]** lists them. First network: the spot testnet.

### 6.3 Hyperliquid — an on-chain perpetuals DEX

The master account approves an agent (API) wallet that can place and cancel orders and cannot
withdraw, transfer, or approve further agents; the approval carries a `validUntil` the venue enforces
(§17 [H1], [H2], [H3]). That is P1's "no self-keys" implemented by the venue, which is why the contract
is prototyped here first (§10 step 2): identity is the agent key's reference, the mandate is the
approval's scope and expiry, and the signer boundary is the venue's. First network: testnet.
**[spike S3]** covers the approval flow.

### 6.4 Solana — a chain, not a venue

The venues are DEX aggregators. A raw keypair is total authority and the chain itself scopes nothing;
delegation comes from a policy layer — Coinbase's agent wallets with allow-listed contracts, per-address
spend caps and daily limits (§17 [S1]); Metaplex's agent registry with an execution delegate (§17
[S2]); session-key schemes. So the "wallet plugin" is a policy-signer plugin, the agent never holds a
keypair, and the row carries only the signer's address. This design does not build the signer: a
policy signer is "cryptographic machinery", which the charter rules out at this scale (§7.3), and the
decision to adopt an external one belongs to the next charter (§12). Devnet experiments against an
external signer are the most this design admits.

## 7. Market reads stay venue-shaped

`MarketDataSource` (`alpaca_kit/source.py`) is daily bars, snapshots, corporate actions keyed on
`announce_date`, EDGAR facts by filing date. Crypto trades around the clock, has funding rates and
perpetuals and no corporate actions; A-shares keep their own calendar. The *guard* transfers — any
captured history would still be read as-of a date through `AsOfGuard` — but the Protocol does not,
and Rule 8 says not to choose the schema before the content exists. So each venue package carries its
own read model; the only things shared are the gate contract (§4) and, where a bed ever exists, the
guard. The face's quote hub is the precedent: three markets, three providers, one shared contract that
keeps provider event time and receipt time apart (`face/src/quote-types.ts`, `face/README.md`
"Market watchlist"). Venue reads are interactive evidence with the same standing as AKShare's: live,
unguarded, never replay input (`AGENTS.md:12-18`); the mechanics skill gains one paragraph saying so.

## 8. The ledger

`/account` today reads one broker through a fixed producer (`face/src/data.ts`; `scripts/face_data.py`).
With a second venue holding positions it becomes an aggregation: one section per venue, each row
carrying the venue, the identity used (its reference name, never its value), the quote currency and the
observation time, and a venue whose read failed showing as unavailable rather than as zero — the posture
the account console already takes for a missing credential (`face/README.md` "Account console"). It
stores nothing (charter §7.3, no memory substrate; Rule 8). Whether this is the right home is §11 D3.

## 9. Substrate — what is used, what is verified, what is not

| Claim | Status |
|---|---|
| A project-owned MCP row composes below the operator's patches and can be disabled by one | verified in code: `boot.ts:177-179`; documented `face/README.md` "AKShare MCP" |
| Gate 2 matches raw-name suffixes and the `(operator-gated)` marker; boot refuses an unmatched marked tool | verified: `orders.ts:33-62, 239-283`; `boot.ts:364` |
| An unmarked, unknown-named write tool from a mounted row is ungated | verified by reading `orders.ts:239-245`; drilled nowhere yet — the §15 drill's first case |
| `mcp__*__<raw>` masks resolve against the live registry | verified: `bot.js:56-75` |
| dsh credentials: records outside the workspace, per-operation resolution, scrubbed spawn env | survey only (`survey:490, 538, 668-669`); the vendored package is not in this checkout — **[spike S1]** |
| The registry fills asynchronously after a row activates | recorded in `orders.ts:224-227`; the mount-time comparison must subscribe, not poll once — **[spike S2]** |
| Hyperliquid agent wallets: orders yes, withdrawals no, `validUntil` enforced | vendor docs §17 [H1]–[H3]; the testnet approval flow through the SDK — **[spike S3]** |
| CCXT MCP: local stdio, keys stay local, trading opt-in; its write tool names | vendor docs §17 [C1]; the names and the per-account opt-in — **[spike S4]** |
| Alpaca paper trades crypto spot; `gtc`/`ioc` only | vendor docs §17 [A1]; the first rejected order is the proof — **[spike S5]** |

## 10. Sequence

In order; each names what "done" is. All of it runs on paper or a testnet.

1. **Alpaca, crypto spot on paper.** Two halves. (1a) Read side: a `venues/alpaca/manifest.yml`,
   the row mounted through the manifest path instead of the operator's hand-written patch, the
   identity reference resolved by the seam (S1), crypto positions on `/account`. Done when the face
   boots with the manifest-mounted row and the operator's patch row disabled, and the offline suite
   pins the manifest. (1b) The first paper crypto order through Gate 2: needs the `time_in_force`
   argument (§6.1) and, because it arms `ALPACA_KIT_ENABLE_ORDERS` in the real harness home for the
   first time, needs `DEVELOPMENT.md` §10 item 1 — the manual half of the order drill — run first
   (charter §8, first row). Done when a crypto order's card is seen, answered, and the fill is on
   `/account`.
2. **Hyperliquid testnet with an agent wallet.** The contract is defined on this venue: manifest
   schema, mount-time classification, Gate 2 fed from manifests, the drill. Done when a testnet
   order raises a card, an undeclared tool refuses the row in the drill, and the agent key's
   `validUntil` is visible on the card's reason line.
3. **Binance spot testnet through CCXT MCP.** Proves a third-party server mounts as a plugin and is
   gated by its manifest, not by its names. Done when the §4.4 trap is reproduced on the unmodified
   server (ungated) and closed by the manifest (refused until classified, gated once classified).
4. **Solana on devnet, only against an external policy signer.** Not before one is adopted (§12).
5. **The next charter**, before any mainnet key: custody model, who answers the card, whether the
   face is ever hosted. The §12 rows are its agenda.

## 11. Open decisions (awaiting the operator)

Each carries the recommendation drawn on the canvas; a reply of the form `D1-A` settles it.

| # | Decision | Options | Recommended |
|---|---|---|---|
| D1 | Custody | **A** non-custodial: the operator holds the master accounts; the agent holds only venue-issued, scoped, expiring, non-withdrawing keys · **B** custodial: a platform holds keys behind one policy signer | **A**. It is the safer path and the lighter regulatory one, and it is the shape Hyperliquid and CDP already offer |
| D2 | Code shape | **A** one package per venue, copying `alpaca_kit`'s shape; shared pieces are the guard and the gate contract · **B** a venue-neutral core now | **A** (Rule 8: a Protocol chosen before the second venue exists is chosen blind) |
| D3 | The ledger | **A** `/account` aggregates read-only, no store · **B** a ledger service with its own storage and reconciliation · **C** none yet; each venue's own view | **A**; B only when content demands a store (§7.3) |
| D4 | First new venue | **A** Hyperliquid testnet · **B** Binance testnet · **C** Alpaca crypto first, zero new credentials | **A**, with **C** in parallel (step 1 costs almost nothing) |
| D5 | Who answers the card before real money | **A** an out-of-band device (phone confirmation, a hardware button) · **B** a second person · **C** the face's card as today | **A**; B fires the charter's last trigger by itself; C is paper-and-testnet only |

## 12. Charter conformance — what this reopens, and what it does not

- **P1 (wide hands, no self-keys).** Served by decisions 3 and 4: placement, not prose, for every
  new venue's identity; the signer outside the agent's reach.
- **P3 (PIT honesty in code).** Untouched: venue reads join AKShare's category, live and unguarded,
  outside both sanctioned replay channels. The backtest rules do not change.
- **P5 (the human is the steady state).** Every write still stops for a card. Nothing here runs
  unattended; the daily-cadence item (`DEVELOPMENT.md` §10 item 5) stays deferred.
- **Rule 2.** The reason the venue-side policy and the signer are in the path at all.
- **Rule 4.** The §15 drill ships with the gate change, in the same change.
- **Rules 6 and 8.** No venue-neutral Protocol, no ledger store, no manifest fields beyond what
  three venues need.
- **§7.3 "no cryptographic machinery", "no hosted face", "no multi-tenant".** Honored by deferring
  the Solana signer and the product form of the operator's vision to the next charter. A buy-side
  assistant for many users is a hosted, multi-user deployment, and the charter's last trigger says
  what that means: *"this charter is the wrong document; write the next one"* (`Kairos-Design.md:292`).
  This design is that charter's input, done on one operator's machine with fake money.
- **§8 rows this design walks up to.** *Arming `ALPACA_KIT_ENABLE_ORDERS` in the real harness home*
  (step 1b): D3 first, then D8. *Real-money intent*: not fired by anything here; the `network:
  mainnet` refusal in §4.1 is the fence. *A second human or any hosted deployment*: D5-B would fire
  it; the recommendation avoids that until the next charter.
- **D8, D10, D12.** Unchanged in substance; §14 adds the venue-shaped residuals beside them.

## 13. Spikes the plan runs first

- **S1 — credential reference into an MCP row's env.** Can a `dsh-mcp-client` row's `env` carry a
  credential reference the seam resolves at spawn, or only a literal from the patch layer? Read the
  vendored `dsh-credentials` and `dsh-mcp-client` packages; measure with a fake record. The
  fallback is §4.2's.
- **S2 — when a row's tool list is known.** Subscribe to the registry change the client emits after
  connection rather than reading `schemas()` once at boot; confirm the refusal can unmount or
  disable the row after activation.
- **S3 — Hyperliquid testnet agent approval.** Approve an agent with `validUntil` from a testnet
  master, place and cancel one order with it, confirm a withdrawal attempt is refused by the venue.
- **S4 — CCXT MCP write tool names and trading opt-in.** List the server's tools on the spot
  testnet; record every mutating name for the manifest; confirm trading is off by default.
- **S5 — Alpaca paper crypto order.** Reproduce the `day` rejection, then a `gtc` fill, on paper.

## 14. Residuals (Rule 3)

- **R-V1 — Placement holds against file reads, not against `/proc`.** A same-user shell can read
  another process's environment on Linux unless the sandbox forbids it; the MCP child's environment
  holds the resolved value even when the workspace never does. What bounds it is the venue: a key that
  cannot withdraw and expires. The same shape as R1's paper pin, and named for the same reason.
- **R-V2 — A third-party MCP server is third-party code holding the credential.** Pin by commit,
  review on upgrade, keep withdrawals off at the venue. The face cannot audit the server's conduct.
- **R-V3 — The manifest is enforced by the face, above the arbitrary-code layer.** A shell turn that
  launches its own MCP server, or imports a venue SDK directly, meets no manifest. R2's statement,
  extended to venues; the venue-side scoping is the answer, as in R-V1.
- **R-V4 — `(operator-gated)` is still a string on a description.** A server that drops it is caught
  only because the manifest names its write tools; the marker becomes the cross-check, not the anchor.
- **R-V5 — Testnet behaviour is not mainnet behaviour.** Venue-side limits, fee schedules and rate
  limits differ; the drills prove the gate, not the venue.

## 15. Testing and drills

- **Offline (face suite).** Manifest parsing and refusal cases: an unclassified tool refuses the row;
  a `write` tool without the marker is reported; `network: mainnet` refuses; the union of manifests
  feeds `isOrderTool`'s raw-name set and `auditOrderTools` keeps both directions.
- **Offline (Python suite).** `alpaca_kit`'s manifest pins its tool classification against
  `READ_ONLY_TOOLS` (`tools.py:41`) and the two order tools; `time_in_force` threads through
  `place_order`.
- **The venue drill** (added beside the Gate-2 and order-approval drills in `face/README.md`): mount a
  fixture row registering `createOrder` with no manifest — assert ungated today, refused under the
  contract; add the manifest — assert a card is raised and the admit path logs `allowed-once`. This is
  also the home for the admit-path test `DEVELOPMENT.md` §10 item 3 still owes.
- **Smoke, behind `FACE_SMOKE=1`.** One Hyperliquid testnet boot with a real agent key, one CCXT spot
  testnet boot; both skip without their credential.

## 16. Code changes (sketch, for the plan)

- `venues/<id>/manifest.yml` — the contract; `venues/alpaca/` first.
- `face/src/venues.ts` — manifest loader, row rendering (modeled on `akshare.ts`), mount-time
  classification, the write-name union handed to `orders.ts`.
- `face/src/orders.ts` — `ORDER_RAW_NAMES` becomes a set fed at boot; the audit's unknown-name branch
  gains the manifest's names; the card's reason line renders the venue and network.
- `face/src/boot.ts` — venue patches composed beside `marketPatches` (line 177).
- `alpaca_kit/mcp/tools.py`, `alpaca_kit/account.py` — `time_in_force` exposed; nothing else.
- `face/src/data.ts`, `scripts/face_data.py` — `/account` sections per venue (D3-A).
- Documents: `CLAUDE.md` map row for `venues/`; `DEVELOPMENT.md` §2.7, §3.6, §4.7, §9, §10; `AGENTS.md`
  one paragraph on venue tools as unguarded live reads; `dsh/skills/mechanics` the same paragraph;
  `face/README.md` the venue drill.

## 17. Verification record and sources

Repository citations were read at `main` @ `a09f217` on 2026-10-02. Vendor facts:

- [A1] Alpaca, crypto spot trading on paper accounts; crypto orders accept `gtc` and `ioc` —
  <https://docs.alpaca.markets/us/docs/crypto-trading>,
  <https://alpaca.markets/learn/getting-started-with-alpaca-crypto-api>
- [B1] Binance API key permissions (reading, spot and margin trading, withdrawals) —
  <https://developers.binance.com/docs/wallet/account/api-key-permission>
- [B2] Binance.US, creating an API key with IP restriction; keep withdrawals disabled —
  <https://support.binance.us/en/articles/9842800-how-to-create-an-api-key-on-binance-us>
- [C1] CCXT MCP server: local stdio, keys stay local, trading enabled explicitly —
  <https://docs.ccxt.com/docs/mcp>
- [H1] Hyperliquid `approveAgent` — <https://www.dwellir.com/docs/hyperliquid/approveAgent>
- [H2] Hyperliquid exchange approve agent — <https://docs.chainstack.com/reference/hyperliquid-exchange-approve-agent>
- [H3] Hyperliquid agent wallets, `valid_until` convention — <https://www.dynamic.xyz/docs/recipes/integrations/hyperliquid-agent-wallets>
- [S1] Coinbase CDP wallet policies — <https://www.coinbase.com/developer-platform/discover/launches/policy-engine>;
  agentic wallets explained — <https://eco.com/support/en/articles/14845485-coinbase-agentic-wallets-explained>
- [S2] Metaplex, what an agent is (asset signer, execution delegate) — <https://www.metaplex.com/docs/agents/what-is-an-agent>
