# Agent Wallet — Design

**Status:** built 2026-09-21 (face `feat/agent-wallet`; agentpay `agent-surface` @ `73fe702`,
the submodule pin). Designed 2026-09-20 and revised the same day after a three-lens adversarial
pass (charter/security, wallet accounting, face feasibility; the record is in §9). The as-built
truth is consolidated in `DEVELOPMENT.md` (§1 homes, §3.6, §4.2, §4.4–4.7, §6.9, §7.3–7.4, §9
R-W1..R-W7, §10 item 11); one built mechanism differs from §8's note, recorded there. Extends the
bots-and-rooms design (`2026-09-07-bots-and-rooms-design.md`) and amends the charter (§5). The
payment substrate is the `payment/` submodule (agentpay: x402 V2 `exact` / EIP-3009 on the
official `@x402/*` packages, verified on Base Sepolia on 2026-09-19).
**Pins:** face at `feat/payment` @ `acfb0e9` working tree; dsh `0.1.1-rc.2`, cordis `4.0.2` (the
face's two pins); agentpay `main` @ `0028a18` plus the `agent-surface` branch this arc adds.
**Language of citations:** `pkg/…:line` cites the vendored dsh package under
`face/node_modules/@deepseek-ai/`; `pay:…` cites the agentpay repository (the submodule); bare paths
are this repository. Every substrate claim below was read from source on 2026-09-20 by six parallel
readers, a critic and three reviewers; the ones re-verified twice are marked **[verified]**.

---

## 1. Context and decision history

The team's direction (2026-09-20): *start from strategy/trading, then erode outward into
market/exchange and account/payment*. The payment submodule already has a working wallet, a paywall
helper, a facilitator and a CLI, and it has settled real (testnet) USDC — but nothing in `face/` or
`dsh/` calls it (CLAUDE.md map row). This arc is the 0 → 1: Kairos can pay for a resource inside a
budget the operator approved, the operator approves that budget on a card, every payment is
attributed to the strategy and session that made it, Kairos's own child tasks pay only from
sub-budgets it delegated to them, and the operator can see all of it on a wallet page.

Decisions, in the order taken:

1. **In-process tools, not an MCP row.** The face registers the wallet tools on the root context the
   way it registers `dispatch` (`face/src/room.ts` `installRoom`) and `agent_<bin>`
   (`face/src/agents.ts`). Reasons: (a) an MCP child never learns which session called it — the
   wire carries `{name, arguments}` and nothing else **[verified]** — while an in-process
   `execute(args, exec)` receives `exec.agent.session.header.{cwd, agentPreset, parentSession,
   origin, delegationDepth}` and `exec.agent.id` **[verified]**, so attribution is a fact the face
   reads, not a claim the model makes; (b) agentpay's ledger and mandate store have one owning
   process per home (`pay:README.md`), and the face is the only process that must also read them for
   the wallet page; (c) a tool registered after boot is invisible to every bot unless the bot's
   allow list names it **[verified]**, which is the posture the charter wants for anything that
   moves money. The agentpay repository gains a host-agnostic tool table (`pay:packages/cli/src/tools.ts`)
   that the face consumes; no MCP server is built in this arc (charter Rule 6/8: no substrate for
   a user that does not exist yet).
2. **One budget request = one approval card = one mandate.** `wallet_budget_request` is gated
   exactly as `place_order` is (`face/src/orders.ts` + `boot.ts`): a prepended `tools/pre-execute`
   listener answers `ask` with a reason line that names purpose, limit, per-call cap, validity,
   every host in full and the requester; a monotonic guard requires the logged `approval/asked` +
   `approval/decided{allowed-once}` pair for that callId before the body runs. The body then
   creates the mandate in `signed` state — the operator's click is the approval, and the pair in the
   session log is its audit. What holds this: the logged pair, the store's placement outside every
   sandbox write root, and the face being the store's only writer. The EIP-712 signature agentpay
   puts on the mandate is agentpay's own stamp (the payer key signing its own record); nothing
   verifies it at spend time, and this spec does not pretend it does. agentpay's draft →
   `mandate-approve` two-step stays for the CLI.
3. **Paying raises no card.** The mandate is the pre-approval (charter §1: "a budget the human
   approved once"). A payment is recorded as a pay card in the trajectory (a tool result rendered by
   the client) and on the wallet page. Refusals reach the model as agentpay's
   `payment_model_context` hints, unchanged.
4. **Attribution is read from the session header, never from arguments.** Every payment carries
   `context = {channel (workspace id), channelName, session, parentSession, origin, callId}`
   derived in `execute`; agentpay stores it on the ledger row and groups the report by channel and
   session. The face writes nothing into `strategies/<name>/status.yaml` (charter §4: Kairos writes
   strategies, git is the ledger); per-strategy spend reaches the channel landing page through the
   overview payload instead.
5. **Sub-mandates are pass-through, held, and delegated by the principal only — to its own child
   tasks, not to bots.** A sub-mandate is a mandate with a `parentId` and a `holder`; its spend
   counts against itself and every ancestor (a cap on the child, not a reservation from the parent —
   siblings compete for the parent's remaining budget, and the delegate tool says so). Its terms are
   bounded by the parent's at creation (limit ≤ parent's effective remaining, validity ≤ parent's
   and ≤ 24 h, hosts ⊆ parent's, per-call ≤ parent's), and the gate re-checks every ancestor's
   full policy on every payment anyway. It is created in `signed` state without a card, because the
   operator already approved the parent and the child cannot exceed it. `holder` decides who may
   spend: `children:<sessionId>` for the direct child tasks of that session (charter §7.2 temporary
   subagents — they run as Kairos, under approval policy `never`, so they cannot raise a card and
   need a pre-authorized budget) and `session:<id>` for one session. A mandate without a holder is
   the principal's alone. **Bots get no wallet tools in this arc**: the bots design's decision 2
   ("Kairos is the only agent whose composition carries the account tools") and charter §7.1 stand;
   a voice that needs a paid resource says so in its answer and Kairos decides whether to pay. agentpay's
   holder vocabulary keeps `bot:<id>` for hosts that want it; the face never sets or resolves it.
   Giving a bot `wallet_pay` is the existing charter §8 trigger ("a bot's composition is given the
   account tools") and reopens §7.1.
6. **Reclaim is disable + expiry, not lifecycle hooks.** Because a child's spend flows up,
   reclaiming a sub-mandate is `isEnabled=false`; nothing has to be given back. The face subscribes
   to no lifecycle event for it: `subagent/end` fires per residency epoch of a continuable child and
   names no parent (`pkg/dsh-subagent/lib/index.js:199-254`, module note at `:660`), and a
   `children:<parent>` mandate is by definition shared by every sibling. A sub-mandate ends by the
   validity Kairos chose (default 1 h, at most 24 h) or by `wallet_budget_disable`.
7. **The wallet home is the face's metadata directory in the harness home.**
   `$DSH_HOME/face/agentpay/` holds `config.json` (the payer key, 0600, written by the operator with
   `agentpay init --home`), `mandates.json`, `ledger.jsonl`, `wallet.lock` and `face-state.json`.
   The key's placement is the operator's (P1 "placement holds" applies to the key); the mandate and
   ledger files are written by the face on Kairos's card-gated request (roots) or on its ungated
   delegate/disable calls (sub-mandates), never by a file effect or a route. What bounds the key is
   stated plainly in D16: every shell turn can read it (the sandbox denies writes only), and the
   float is the bound, not a pin.
8. **Charter §7.3 "no cryptographic machinery" is not violated.** The wallet signs EIP-3009
   authorizations because that is the payment protocol, not safety machinery the charter refuses
   to build; the face adds no cryptography of its own.
9. **The wallet tools are not a fetch tool.** The charter disables `tool-web`'s page fetch on
   purpose (DEVELOPMENT §3.6). Before any request leaves the face: the URL's host must be one a
   mandate the caller can spend names (agentpay's `requireMandateHost` option makes `fetch()` refuse
   `host_not_allowed` before its first request); loopback, link-local, private-range and `.local`
   hosts are refused outright; `wallet_offer` sends no model-supplied body or headers.
10. **The face is the only process on its home while it runs.** `installWallet` takes
    `wallet.lock` (pid); agentpay's mutating CLI commands refuse a home whose lock names a live pid
    (`mandate-list` and `report` still read). A store loaded once and rewritten from memory would
    otherwise silently drop what another process wrote.
11. **The wallet page and the pay card are the operator's instruments; the intro page is redrawn to
    what is built.** No AEP2 vocabulary survives (deposit, settlement processor, queue, withdraw
    delay, shared `settleBatch` tx).

## 2. What the operator sees

- **A budget card** in the flow, headed `approval · wallet_budget_request`, one line:
  `BUDGET - "market data for AAPL thesis" · limit $5.00 · per call $0.01 · valid 7d · hosts
  api.example.com, data.example.com · from strategies/aapl-momentum by kairos`. Every host is
  printed in full; a request with more than five hosts, or a `*` / `*.<tld>` pattern, is refused
  before any card. Approve → the mandate exists; Deny → the tool returns an error the model reads.
- **A pay card** inside the answer trace for every `wallet_pay`: `$0.001 · GET
  api.example.com/predict · settled · tx 0xe833…c9d`, or `refused before signing ·
  mandate_insufficient_budget`, or `402 · invalid_exact_evm_insufficient_balance`. Refusals render
  in the danger colour even though the tool value is a successful envelope (the model needs the
  hints in it); the raw JSON stays one click away.
- **`/wallet`**, a page like `/account`: address and USDC balance (with a "send test USDC here"
  line; `unavailable` when the RPC does not answer within 3 s), every mandate as a row (purpose ·
  holder · effective remaining / limit · per call · valid until · status), recent payments with tx
  links, spend by strategy and by session, and an alerts block: budget exhausted or under 10 %,
  balance under the sum of root budgets' remaining, `unknown` rows, mandates expiring within a day,
  and **unexplained outflow** (the balance fell by more than the ledger settled since the last
  look — the CLI/raw-key spend D16 admits, made visible). The rail item shows a dot while an alert
  stands. Loading the page runs `reconcile()` when rows are pending (at most once a minute); nothing
  runs on a timer (charter §1: nothing runs unattended).
- **On the channel landing page**, one figure tile per strategy: USDC settled in that channel.
- **The plugin panel** lists the wallet tools by name, so the operator can see that money-moving
  tools are registered (charter Rule 5).
- Bot settings are unchanged; no bot sees a wallet tool.

## 3. What Kairos sees

Eight tools, all registered by the face (names ≤ 64 chars, `[A-Za-z0-9_]`):

| tool | who may call | what it does |
|---|---|---|
| `wallet_offer {url, method?}` | principal, child | Probes once (no body, no model headers) and returns the 402 terms (price, asset, network, payTo, timeout) without paying; a non-402 returns its status only. Refused when no spendable mandate names the host. |
| `wallet_pay {url, method?, body?, headers?, mandate_id?}` | principal; a child with a held sub-mandate | Paid fetch through `MandateWallet.fetch` with the caller's context and holder set; returns `{status, paid, amount_usd, mandate, remaining_usd, tx, ledger_status, body (≤ 8 KB, `body_truncated`)}`; refusals return the `{ok:false, error, payment_model_context}` envelope. |
| `wallet_budget_request {purpose, limit_usd, hosts[], valid_for_hours?, per_call_usd?, category?}` | principal only | Raises the budget card (Gate 3); on approval creates a mandate held by nobody. Denied → error. A child (policy `never`) or a bot preset is refused before any card, in the face's own words. |
| `wallet_budget_delegate {parent_id, limit_usd, for: {children: true} \| {session}, valid_for_hours?, hosts?, per_call_usd?, label?}` | principal only | Creates a sub-mandate within the parent's terms, held for this session's direct children or for one session. No card. |
| `wallet_budget_disable {id}` | principal only | Reclaims a mandate (a root or a sub-mandate). |
| `wallet_budgets {}` | principal, child | The mandates the caller may spend (principal: unheld; child: `children:<parent>` + `session:<self>`), each with effective remaining and validity; plus address, balance when known, and the standing alerts. |
| `wallet_report {}` | principal only | The spend report: totals (over root mandates = the ledger), by strategy / session / host / resource, policy denials. |
| `wallet_reconcile {}` | principal only | Runs `reconcile()` against the chain (needs an RPC); returns what settled, expired or is still pending. |

Amounts cross the tool boundary as **strings** in USD (`"0.25"`), never JSON numbers. The caller
class is derived by one ordered rule (`face/src/wallet.ts` `callerOf`): `origin === 'subagent'` →
child (whatever the preset); otherwise the live preset is the last `agent-preset/selected` event in
the session, else `header.agentPreset`; `undefined` or the default preset → principal (the rule
`dispatch` uses); any other preset → bot (refused by every wallet tool). A fork (`parentSession`
set, no `origin`) is a principal.

Guidance for the model goes into `AGENTS.md` (a wallet paragraph in the register the file already
uses; the rooms sentence "its orders meet the same gate you do" gains "and it has no wallet").

## 4. Substrate and mechanism

### 4.1 agentpay (`pay:packages/wallet`, `pay:packages/cli`) — branch `agent-surface`

- **Context.** `FetchOptions.context?: PaymentContext` — string fields only, each ≤ 256 chars
  (`channel`, `channelName`, `session`, `parentSession`, `origin`, `callId`, `label`), copied onto
  the ledger row as `context` (ledger v2 stays: the field is optional and `parseEntry` tolerates
  it). `report()` adds `byChannel` and `bySession` (settled + unknown rows only, rows lacking the
  key bucketed under `''`), keeps `byHost`/`byResource`, and defines `totals.spent/pending` as the
  sum over **root** mandates (= the ledger sum; a chain must not double-count).
- **Holders and callers.** `IntentMandate` gains `parentId?` and `holder?`, both in the signed
  struct: `INTENT_MANDATE_TYPES` adds `{parentId, string}` and `{holder, string}` (`''` when
  absent), `INTENT_DOMAIN` becomes `{ name: 'agentpay', version: '2' }`, the store file becomes
  `version: 2`, and a v1 or version-less store is refused with a message that says to archive and
  recreate it (mirroring the ledger's v1 message). `FetchOptions.caller?: Caller` = `{kind:
  'principal' | 'child' | 'session' | 'bot', id?, parentSession?}`. Eligibility **filters** the
  store to the caller's set first (principal: no holder; child: `children:<parentSession>` and
  `session:<id>`; session: `session:<id>`; bot: `bot:<id>`); an empty set is the new reason
  `no_held_mandate` (hint: the principal requests a budget; a child asks its parent to delegate one);
  `pickRejection` then runs over the narrowed set only. An explicit `mandateId` outside the set is
  `holder_mismatch`. `createIntentMandate` refuses `parentId`/`holder` in its input; the only
  constructor of a child is `delegateIntentMandate(parentId, input, holder)`, which validates
  against the parent (signed, enabled, unexpired; `limit ≤ effectiveRemaining(parent)`;
  `validUntil ≤ min(parent.validUntil, now + 24 h)`; every child host pattern equals a parent
  pattern, or is a concrete host — with or without a port — matched by one via `matchHost`;
  `perCallMax ≤ parent.perCallMax` when the parent has one; category inherited) and returns the
  mandate in `signed` state.
- **Chain accounting.** `chainOf(id)` walks `parentId` to the root with a visited set (a missing
  parent or a cycle stops the walk and is logged once). `adjustBudget` is the single chain-aware
  mutation site: it patches every member and saves once; `rebuildBudgets` applies each row to its
  chain. `effectiveRemaining(id) = min(remainingOf(m) for m in chainOf(id))` is what `remaining()`,
  `eligibleMandates()`, `report().mandates[].remainingAmount`, `mandate-list`/`-status` and the
  tools return; the raw counters stay on the rows. The gate runs the **full** `mandateRejection`
  on every chain member (hosts, per-call, budget, rate, enabled, window) in its one synchronous
  block, surfaces an ancestor's failure with the existing reason code plus `detail.ancestorId`,
  reserves on every member, and records the attempt in every member's rate window.
- **Reconcile beside a live fetch.** `reconcile()` skips rows whose `error === 'in_flight'` unless
  chain time is past their `validBefore` (a live `fetch()` owns them), and re-reads each row by
  nonce immediately before booking so a row the fetch already settled is only patched
  `verified`/`transaction`, never booked twice.
- **Lock and verification.** `MandateWallet` takes an optional `lock: true` that writes
  `<home>/wallet.lock` (pid, refreshed on save) and releases it on `dispose()`; `lockedBy(home)`
  answers whether a live pid holds it. The CLI's mutating commands (`pay`, `mandate-*`,
  `reconcile`) refuse a locked home with a message naming the pid. `verifyMandates()` (async)
  recovers every signed mandate's signer and returns the ids that do not recover to the payer
  address; the face calls it after registration and disables and alerts on each.
- **Host pre-flight.** `MandateWalletOptions.requireMandateHost?: boolean` (default false): when
  set, `fetch()` refuses `host_not_allowed` before its first request unless a mandate in the
  caller's set names the host.
- CLI: `mandate-delegate --parent <id> --holder <holder> …`, `pay --context k=v` (repeatable) and
  `AGENTPAY_CONTEXT=k=v,…`, `mandate-list`/`-status`/`report` show holder, parent, effective
  remaining and the new groupings; `USAGE`, `SKILL.md`, the README "Budgets" section and
  `docs/technical-report.md` (the domain paragraph) follow.
- `pay:packages/cli/src/tools.ts`: the host-agnostic tool table — `WALLET_TOOLS` (name,
  description, JSON-schema `parameters` with string amounts) and `createWalletToolHandlers(ctx:
  CommandContext, opts)` returning `(name, args, {context, caller, requester}) → CliResult`
  envelopes, reusing the command handlers where they fit (`mandateCreate`, `pay`, `offer`,
  `reconcile`, `report`) and small handlers where they do not (`wallet_budgets` is a projection
  without `signature`/`mandateHash`); exported from the package index together with
  `CommandContext`, `resolveConfig`, `failure` and the handler modules. No wallet-level caps are
  configured in the face: the budgets are the mandates.

### 4.2 Face — branch `feat/agent-wallet` (on top of `feat/payment`)

- **Imports.** `face/src/wallet.ts` imports the submodule by relative path with the `.ts` extension
  (`../../payment/packages/cli/src/index.ts`, `…/wallet/src/index.ts`), the form verified to
  typecheck under the face's NodeNext / `skipLibCheck: false` tsc and to load under tsx — provided
  `payment/node_modules` is installed. The submodule pin is bumped and `npm ci` run in `payment/`
  **before** the face work (§7), and every document that says `git submodule update --init` now
  also says `(cd payment && npm ci)`.
- `face/src/wallet.ts` — `installWallet(deps)`, synchronous through registration and called in
  `main.ts` right after `bootFace` and before the first `await` (so the tools are in the tree before
  any session): resolves the home (`FACE_AGENTPAY_HOME`, else `$DSH_HOME/face/agentpay`); when
  `config.json` is absent, or `resolveConfig({home}, {})` throws (the shell's `AGENTPAY_*` are
  **not** consulted), logs one line naming the path and registers nothing — the page then answers
  `{configured: false, reason}`; otherwise takes the lock, builds ONE `CommandContext` with
  `requireMandateHost: true`, registers the eight tools through `ctx.tools.register` (a structural
  `WalletToolDefinition` with `presentCall` kinds `fetch`/`read`/`other` and `presentResult`
  titles), each `execute` deriving `{context, caller}` from `exec.agent` (`callerOf`, §3) and
  `deps.channelFor(cwd)` (workspace id + basename), refusing bots and the principal-only tools for
  children in words that name the rule, and refusing private/loopback hosts before any request.
  Every promise the face does not await inside a route shell is caught (`main.ts` turns an unhandled
  rejection into a shutdown). Balance is read through a single-flight cache with a 3 s abort and a
  `stale`/`unavailable` field. `verifyMandates()` runs once after registration. Serves
  `/data/wallet.json` (same-origin fenced; never serializes `key`), provides `spendFor(channel)` to
  the channel overview through a new optional `ChannelRouteDeps.spendFor` seam (so `main.ts` builds
  the wallet before `registerChannelRoutes`), adds `walletTools` to the plugin listing, and keeps
  `face-state.json` (last balance, ledger settled at that time) for the outflow alert. Returns a
  disposer that releases the lock.
- `face/src/budgets.ts` — Gate 3, pure: `isBudgetTool`, `requesterOf(session)` (total),
  `describeBudgetRequest` (every host in full; refuses > 5 hosts and `*` / `*.<tld>`),
  `budgetApprovalDecision(name, policy, args, requester)` (bot or child → deny in own words, before
  the `never` and `ask` branches; then `never` → deny; else `ask`), `budgetGuardReason` (via
  `hasApprovalGrant` from `orders.ts`); registered in `bootFace` beside Gate 2 with its own
  prepended listener and its own guard. The body re-derives the mandate's terms from
  `exec.arguments` only.
- Client: `client/wallet.html` (with `<main>` and `</head>`, for `build-static.mjs`) + `wallet.js`
  + `wallet-model.js` (pure, unit-tested) + `wallet-view.js`, mirroring `/account`; `navigation.js`
  gets the item; `static.ts` `PAGES` and `scripts/build-static.mjs` get the page; `render.js`
  `renderResult` checks `name.startsWith('wallet_')` **before** its `ok !== true` return and hands
  `ok:false` envelopes to a `payCard` that carries `data-status="refused"`; `chat.js` `fillResult`
  adds the `pay` class for `wallet_*` tools and toggles `danger` on `isError || refused`;
  `chat.css` gets `.card.pay` and the status badges; `channels.js` renders the `spend` tile; the
  plugin panel renders `walletTools`.
- Tests: `tests/budgets.test.ts` (pure, like `orders.test.ts`: requester classes, host refusals,
  never/ask, guard); `tests/wallet.test.ts` (offline: the tool definitions over a `CommandContext`
  on a temp home with a stub payee, asserting context derivation, caller refusals, the host
  pre-flight, holder routing, envelopes, no unhandled rejection from a rejecting balance/reconcile);
  `FACE_SMOKE=1` `tests/budget-gate.test.ts` (waterfall at `wallet_budget_request` → ask with every
  host on the line; bot preset → deny; agentless → deny; the guard refuses a stand-in without a
  grant); `tests/static.test.ts` route pin; `tests/panels.test.ts` `walletTools`;
  `tests/channels.test.ts` `spendFor`; `tests/wallet-model.test.ts`.
- Docs: this spec; `CLAUDE.md` rows (payment, docs, face, `npm ci`); `DEVELOPMENT.md` (§1 homes
  table, §3.6 beside `tool-web fetch:false`, §4.2 module table, §4.4 routes, §4.5 state, §4.6 env,
  §6 an end-to-end path, §7.3 suites, §7.4 drills, §9 residuals, §10 forward); `Kairos-Design.md`
  (§5 below); `AGENTS.md`; `ROADMAP.md` built log; `face/README.md` (env table, "Agent wallet"
  section with setup, the budget-card drill with automated and manual halves);
  `docs/design/kairos-intro.html` redrawn.

### 4.4 Payload contracts (server ↔ client)

All money crosses as strings in USD (`"0.001000"`), atomic units never reach the client. Times are
ISO-8601 UTC strings.

`GET /data/wallet.json` →
```
{ ok: true, configured: false, reason: string, home: string }                       // not set up
{ ok: true, configured: true, generated_at, home, address, network, token, deployment?,
  balance: { usd, at } | { unavailable: string },
  mandates: [{ id, purpose, holder?, parent_id?, category?, limit_usd, spent_usd, pending_usd,
               remaining_usd /* effective, over the chain */, per_call_usd?, max_calls_per_minute?,
               valid_from, valid_until, status: 'signed'|'draft', enabled: boolean,
               unverified?: true /* signature did not recover to the payer */ }],
  payments: [{ nonce, at, url, host, resource, amount_usd, mandate, status /* settled | rejected |
               unknown | expired-unused */, error?, tx?, http_status,
               context?: { channel?, channelName?, session?, parentSession?, origin?, callId?, label? } }]
               /* newest first, at most 50 */,
  spend: { settled_usd, pending_usd, by_channel: { [workspaceId]: { name, usd } },
           by_session: { [sessionId]: usd }, unattributed_usd },
  reconcile?: { at, settled: number, expired_unused: number, still_pending: number, error?: string },
  alerts: [{ kind: 'budget_exhausted'|'budget_low'|'balance_low'|'unknown_rows'|'expiring'|
             'unexplained_outflow'|'unverified_mandate'|'rpc_unavailable', level: 'warn'|'info',
             text: string, mandate?: string }] }
```
`/data/channels/overview` rows gain `spend?: { settled_usd: string, count: number }` (absent when
the wallet is not configured or the channel has no payments).
`/data/plugins.json` gains `walletTools: [{ name, description }]` (empty when not configured).

`wallet_pay` tool value (what `renderResult` receives as JSON text):
```
{ ok: true, status: number, paid: boolean, amount_usd, mandate, remaining_usd, tx?, ledger_status,
  url, resource /* "GET /predict" */, host, body: string|object, body_truncated?: true }
{ ok: false, error: string /* reason code */, status?: number, detail?: object,
  payment_model_context: { protocol, reason, summary, remediation[], commands? }, url?, host? }
```
`wallet_offer` value: `{ ok: true, status: 402, url, offer: [{ scheme, network, amount_usd, asset,
payTo, maxTimeoutSeconds }], resource?, description? }` or `{ ok: true, status, paid: false, note }`.
`wallet_budgets` value: `{ ok: true, address, network, balance?: {usd}|{unavailable}, caller:
{ kind, id? }, mandates: [as above minus signature/mandateHash], alerts: [as above] }`.
`wallet_budget_request` / `_delegate` value: `{ ok: true, mandate: {as above} }`;
`wallet_budget_disable`: `{ ok: true, id, enabled: false }`; `wallet_report`: `{ ok: true, report }`
(the agentpay `SpendReport` with usd strings added beside atomic ones); `wallet_reconcile`:
`{ ok: true, settled: n, expired_unused: n, still_pending: n, verified: n }`.

### 4.3 What is NOT built here

- No MCP row in the face, no MCP server, no per-bot child.
- No wallet tools for bots; no `bot:` holder resolved by the face; no bot-settings write path.
- No on-chain enforcement of budgets (smart account / session keys): whoever holds the key can move
  all of it.
- No writing to `status.yaml`; no new session-event types; no timer.
- No mainnet record, no funding flow, no facilitator failover (items C of the gap list).
- No change to Gate 1 / Gate 2, to bots' allow lists, or to `bots/*` files.
- Built after this arc, 2026-09-21: the first real payee shape, `wallet_discover`, `wallet_pay
  {save_to}` and the bought-bed path — `2026-09-21-bought-data-design.md`.

## 5. Charter conformance and amendments

- **§1 ACCOUNT bullet** gains: "— and an agent wallet (USDC, x402) behind a third gate: Kairos
  requests a budget, the operator approves it on a card, payments run inside it and are attributed
  to the strategy and session that made them; bots have no wallet."
- **§3 diagram** OPERATOR row gains "payer key (`$DSH_HOME/face/agentpay`)"; FACE row gains "the
  budget card (Gate 3) · /wallet"; KAIROS row gains "pays for resources inside approved budgets".
- **§4 write map** gains the row: `budgets (mandates) | the face, on Kairos's card-gated request
  (roots) or its ungated delegate/disable (sub-budgets for its own child tasks) | approval/asked +
  approval/decided pair in the session log; the ledger; /wallet` — and a fourth honesty note: "Gate
  3 and the holder rule hold the tool surface; the key file is readable from any shell turn; the
  float is the bound."
- **§5 debts** gains **D16**: the payer key in `$DSH_HOME/face/agentpay/config.json` is readable by
  every shell turn (Kairos, any bot, any child) because the sandbox denies writes only; unlike D8
  there is no paper-hostname analogue, so what bounds the wallet is the float the operator keeps
  there; acceptable now because the float is small and testnet; due when a mainnet key is placed
  there. D5 is narrowed to "tool-path on-chain spend is accounted per strategy and session; LLM +
  data-API spend, and CLI/raw-key spend, are not".
- **§7.1** gains one sentence: "A payment meets a mandate, not a card; that is why no bot has a
  wallet tool."
- **§8 triggers** gain: "A mainnet payer key placed in the wallet home → D16 · §4 · the funding and
  custody items of the payment gap list". The existing "a bot's composition is given the account
  tools" row gains "(the wallet tools included)".
- **§7.3** unchanged (decision 8).

## 6. Residuals

- R-W1: the approval answer route is loopback-forgeable (R3a/D10) — a budget card can be answered by
  a shell turn; and a shell turn can mint a principal session over loopback and request from it.
- R-W2: the payer key is readable by every shell turn; a copy of the home under `$TMPDIR` runs the
  CLI with self-approved mandates and no card. The float is the bound; the outflow alert is the
  detection.
- R-W3: attribution is exact for tool calls and absent for a shell turn running the CLI directly.
- R-W4: the hosted facilitator fails 3 of 5 concurrent settlements (measured); the face does not
  queue; several children paying at once will see refusals recorded honestly.
- R-W5: the positive path of the budget card (grant → guard → body) has the same test gap Gate 2's
  order card has; the automated half covers ask/deny/guard, the manual drill covers approve.
- R-W6: the `tools/execute` seam can rename or mutate a call after the guard (R2 class); the card
  describes what the body will create only absent such a wrapper.
- R-W7: the wallet tools are an HTTP client inside the face; the host pre-flight and the
  private-range refusal are what keep them from being the fetch tool the charter disabled.

## 7. Plan decomposition

All seven steps done 2026-09-21.

1. ✓ agentpay `agent-surface`: context, holders/callers, chain accounting, effective remaining,
   reconcile re-check, lock, verification, host pre-flight, tests (pins rewritten as §9 records)
   — `584b60d`.
2. ✓ agentpay: CLI commands, tool table, SKILL/README/technical report — `73fe702`.
3. ✓ Kairos: submodule pin → `73fe702`; `npm ci` in `payment/`; CLAUDE.md row.
4. ✓ Face: `wallet.ts` + `wallet-payload.ts` (the payload split out pure) + `budgets.ts` (Gate 3)
   + boot/main wiring + tests (`budgets`, `wallet`, `budget-gate`, `wallet-smoke`).
5. ✓ Face client: `/wallet` page, pay card, badges, channel spend tile, plugin panel +
   `wallet-model` tests and the `static`/`panels`/`channels` pins.
6. ✓ `docs/design/kairos-intro.html` redrawn for x402 and the surfaces of §2.
7. ✓ Documents: charter, CLAUDE.md, AGENTS.md, DEVELOPMENT.md, ROADMAP.md, face/README.md. The
   manual drill's PASS line is the operator's to record (README, "The budget-card drill").

## 8. Drills

- Automated (`FACE_SMOKE=1`): `budget-gate` (ask with a decidable line; bot preset denied;
  agentless denied; guard refuses without a grant), `wallet-smoke` (the real wallet on a booted
  tree paying a stub payee on the local network through dsh's own registry; the ledger row
  names the gateway session; a bot refused) and `wallet-approve-smoke` (the positive path of
  Gate 3 — a test answerer granting the card, the guard admitting, the body creating the
  mandate; the R-W5 twin the order gate lacks; being written as this status line is set).
- Manual, in a scratch harness home with a local chain (`payment/`'s demo stack: hardhat +
  facilitator + payee): `agentpay init --home <scratch>/face/agentpay --from-deployment localhost
  --key <hardhat #1>`; start the face on that home; ask Kairos for a budget for `127.0.0.1:4021`
  → the card names purpose, limit, hosts; Deny → the tool result says so and nothing is in
  `/wallet`; ask again, Approve → the mandate is on `/wallet`; ask Kairos to fetch
  `http://127.0.0.1:4021/predict` → a pay card with a tx and `/wallet` shows the payment. Note: the
  private-range refusal must be lifted for the drill's loopback payee. **As built** this is not
  an environment variable: `wallet.ts` lifts the refusal when the configured network is the local
  chain `eip155:31337` (`LOCAL_NETWORK`) and on no other — a loopback payee on Base Sepolia is
  refused before any request, whatever mandate names it. No `FACE_AGENTPAY_ALLOW_LOCAL` exists.
  The steps are in `face/README.md`, "The budget-card drill"; not yet run.

## 9. Review record (2026-09-20)

Three reviewers read the first draft against the code. Changes made: bot wallet grants and the
face-side `bot:` holder dropped (blocker: contradicted the bots design, §7.1, the spec's own §4.3,
and had no write path); the `subagent/end` reclaim dropped (fires per epoch, names no parent,
would starve siblings); the caller rule made total and ordered (forks, resumed sessions, switched
presets); host pre-flight and private-range refusal added (the tools were an unrestricted HTTP
client in the face process); the key's exposure restated in D16/R-W2 and a §4 honesty note (the
sandbox denies writes only; the float is the bound); the outflow alert added; the wallet lock and
CLI refusal added (a second process clobbered the store); `effectiveRemaining` and root-only
totals defined (chains double-counted); holder eligibility made a filter with `no_held_mandate`
(the precedence list surfaced the wrong hint); the gate re-checks every ancestor's full policy and
`createIntentMandate` refuses children (a hand-made child could widen the parent's hosts); the
reconcile/in-flight race closed; rate windows recorded on the chain; `chainOf` bounded; the
`h:port`-under-`h` delegation admitted; the two pinned signature/store tests and
`docs/technical-report.md`'s domain paragraph listed as rewritten; the submodule `npm ci` step and
pin-first ordering added (the import did not build at the pinned checkout); the timer replaced by
reconcile-on-load; unhandled rejections named; the `spendFor` seam and workspace-id keying added
(the overview route cannot be extended after registration; basename keying missed the workbench);
the pay-card render path fixed (`renderResult` gated on `ok`); Gate 3 refuses non-principals before
the card; the plugin panel lists the tools; `packages/mcp` dropped from the arc.
