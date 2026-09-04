# Channels — Design

**Date:** 2026-09-03 · **Status:** approved in brainstorming, pending user review of this spec ·
**Supersedes:** the strategy-as-directory arena surface described in
`docs/superpowers/specs/2026-08-29-market-strategy-account-skeleton-design.md` §"STRATEGY" and
in `face/README.md` (the session-per-strategy workspace model). The *directory* contract is
unchanged; what changes is identity, navigation, and the pre-entry view.

---

## 1. Context and decision history

The operator wants the strategy layer reshaped along a Grok-bot / Slack model: **channels** that
may host discussion of a strategy, a single ticker, a sector, quant work, or news — with a
per-channel agent roster, and with a channel's **artifact** visible before entering it.

An 8-reader survey plus a completeness critic (2026-09-03) established the load-bearing fact
that reshapes the design: **dsh already ships the channel object, and the face declines it.**
`@deepseek-ai/dsh-workspace` is mounted at `face/src/overlay.ts:52` and its state is live at
`~/.dsh/storages/workspace.json`, but the face never uses its capability — the client sends
`session.create({cwd})` (pre-channels `face/client/chat.js:1319`), so every face-created session
was permanently **Ungrouped** in the host's own registry. The registry offers exactly the four
things the current model lacks: a stable UUID decoupled from the path, a display `title`
decoupled from the directory name, a durable `sessionIds` membership index, and manual order.

Decisions fixed during brainstorming (each confirmed by the operator):

| # | Question | Decision |
|---|---|---|
| 1 | What is an agent inside a channel? | **A tool of Kairos.** The channel's member list is that channel's `agent_<bin>` whitelist. Only Kairos speaks; delegated CLI output stays a folded tool result. No multi-party posting. |
| 2 | Are channels typed? | **No kinds, but the card is structured.** One channel shape; an all-optional structured header supplies what cannot be derived. |
| 3 | Where does the artifact sit? | **A channel landing page (three-tier).** Sidebar lists channels → the channel page shows the artifact plus that channel's sessions → a session (or "new round") opens the conversation. |
| 4 | Where does the artifact's content come from? | **Derived-first, plus one optional headline block.** No new producer, no new file; `status.yaml` gains optional keys. |
| A | Channel identity | **Approach A: channel = dsh workspace.** Rejected: (B) keep cwd-prefix grouping and only add a landing page — no stable id, no rename, no order, and it continues re-implementing what dsh has, against charter §7.3; (C) a new face-side channel store — against §7.5 and Rule 8, and it duplicates the registry. |
| B | Rename `strategies/` → `channels/`? | **No.** With `workspace.title` decoupling the display name, renaming buys only cosmetics, while it dangles the `cwd` of the three existing sessions under `strategies/` (`status() → missing-dir`) and turns `python -m pytest` red at **collection** time — `tests/strategies/test_market_sentiment.py` loads `strategies/市场情绪/sentiment.py` by absolute path at module scope. |

---

## 2. What a channel is

A channel is one directory, given an identity by the host and a roster by the operator. The
three layers are split by *who may write them*, which the charter already decides:

| Layer | Lives in | Writer | Contents |
|---|---|---|---|
| **Body** (content) | `strategies/<dir>/` in the repo | **Kairos, freely** (write map row 1, `Kairos-Design.md:87`) | `THESIS.md` · `status.yaml` · `journal.md` · `screen.py` · `backtest.py` · `backtests/` · optional `AGENTS.md` |
| **Identity** (container) | dsh workspace registry → `~/.dsh/storages/workspace.json` | **host-owned; mutated only through `/api/workspace.*`** | `workspaceId` (UUID) · `title` · `sessionIds[]` · durable order · timestamps |
| **Roster** (runtime) | `$DSH_HOME/face/channels.json` (new) | **operator only**, through the face UI | the channel's `agent_<bin>` whitelist |

Kairos may rewrite a channel's *content* freely and cannot **write** its *identity* or its
*roster*: both sit outside the workspace, behind the sandbox's file-write fence. This is a
placement of concerns in the spirit of P1, but **it is not structural unreachability** — see
§5 limit 3, which names the loopback path that reaches them anyway. It is also why the roster
cannot live in the channel's own `AGENTS.md`: that file is Kairos's.

`@deepseek-ai/dsh-workspace` "registers no tools, injects no prompts, and writes no session
events" (its README, "Model Experience"), so nothing about the registry enters a request prefix.
The separation is a **write** separation, not confidentiality: `dsh-fs-sandbox` fences
`writeText`/`editText` only — "Reads always pass through — every mode permits reading" (its
README:5) — and `dsh-shell-env` hands every shell call `DSH_HOME`, so Kairos can read both files
if it looks. Nothing in this design depends on it not looking.

### Existence rule

**The directory is the truth of existence; the workspace is an identity record, created lazily.**

`listChannels()` = `readdir(strategies/)`, **skipping `_template` and any name starting `.` or
`__`** — the filter carried verbatim from the pre-rename `face/src/strategies.ts:66`, because the copy source
must never become a channel — **plus the repo root itself** → for each such directory
`workspaceRegistry.create(path)` → merge the registry's `title` / `sessionIds` / order. `create` is idempotent: it canonicalizes
via `fs.realpath`, keeps at most one record per canonical path, and "repeated calls for that
path return the existing workspace without changing its title." A channel Kairos creates with a
plain `mkdir` therefore becomes a channel on the next listing, and "git history is the ledger"
still holds.

The repo root is itself already a workspace (`title: "evolving-alpha-us"`, live on disk) and is
**not** under `strategies/`, which is why the rule above adds it explicitly. It stays the
*workbench* entry — a channel like any other whose landing page simply skips the blocks it has
no files for, and which owns the repo-root sessions that would otherwise fall into the ungrouped
bucket.

---

## 3. The host substrate — what is used, and what is not on RPC

Verified at pin `0.1.1-rc.2` (`face/src/version.ts:3-9`).

**Exposed over RPC** (`workspaceViewSchema` = `{workspaceId, path, title, sessionIds[], createdAt, updatedAt}`;
note `workspace.list` returns `{items, archivedSessionIds}` — a registry-global archive set, not
only the per-workspace views):
`workspace.list` · `workspace.create` (payload is `{path}` only — no title) · `workspace.rename`
· `workspace.delete` · `workspace.insertBefore` · `workspace.insertSessionBefore` ·
`workspace.archiveSession`. Plus `session.create`, which "accepts workspaceId or cwd, not both"
and auto-attaches on the `workspaceId` branch.

**NOT exposed over RPC:** `attachSession`, `detachSession`, `resolveByPath`, and the `title`
argument of `create`. These exist only on the service interface.

**Consequence, and the mechanism the migration depends on:** the face hosts dsh *in-process* —
`bootFace` returns `{ ctx, dispose }` (`face/src/boot.ts:211`) and `main.ts:102-117` already
threads `booted.ctx` into the route modules. So `channels.ts` takes `ctx.workspaceRegistry` and
calls the service directly, including the four members RPC does not carry. **The browser cannot
attach an existing session to a workspace; only the face host can.** `session.create({workspaceId})`
covers new sessions only.

Division of labour:

| Concern | Route |
|---|---|
| Channel list, landing-page payload (needs disk) | face `GET /data/channels.json`, `POST /data/channels/overview` |
| Roster edit | face `POST /data/channels/agents` |
| Channel creation (template copy + adopt + seed) | face `POST /data/channels` (renamed from `/data/strategies`) |
| Rename, reorder, new session | client calls `/api/workspace.rename`, `/api/workspace.insertBefore`, `/api/session.create` directly — no new face route |

All new `/data/*` routes go through the single existing fence `isTrustedDataRequest`
(`face/src/data.ts:120-131`); every POST additionally requires `content-type: application/json`.
Read §5 limit 3 before treating that fence as authentication — it is not.

**Deleting a channel** needs no new route and no new decision: remove the directory (Kairos's own
write map row 1, or the operator's shell), then `/api/workspace.delete`. Order matters —
`workspaceRegistry.create` rejects a nonexistent path, so once the directory is gone the reconcile
cannot resurrect the record. `delete` never touches the directory or the session logs; its
sessions simply become ungrouped.

---

## 4. Navigation and the landing page

### Navigation

Three tiers, achieved with a small delta rather than a restructure. The sidebar keeps its
grouped-session index (collapse state already persists in `localStorage["face.collapsed-groups"]`),
but the **group header becomes the channel entry**:

- click the **channel name** in the group header → the channel landing page opens in the right pane
- the header's **chevron keeps the fold gesture** — collapsing must not be lost, and the synthetic
  `archived` / `ungrouped` headers (which carry no `workspaceId`) stay fold-only, with no page
- click a **session row** → the conversation (today's behaviour, unchanged)
- **+ new** still opens the existing picker (`showStrategyPicker`, `face/client/chat.js:1291`);
  only its row source changes, from directory-scan-plus-cwd-guessing to the registry

Sessions stay on the sidebar deliberately: routing every conversation switch through a landing
page would cost three clicks for the commonest action.

The landing page is a detail page, so `.main.detail-mode` hides the composer. Under a three-tier
model this is **correct** — you do not type on the landing page; you click a session or "new
round". No CSS rule is overturned.

### Landing page — seven blocks, each skipped when its source is absent

1. **Header** — `title` (inline-editable → `/api/workspace.rename`) · status badge ·
   `missing-dir` warning · **member agent chips** (toggling writes `channels.json`) ·
   the directory path in small type.
2. **Headline** — the optional `status.yaml` keys: `one_line` (the current conclusion in one
   sentence) · `next` (the next step) · `numbers` (free key-value, rendered as a figure row).
3. **Thesis** — `THESIS.md` through the existing `renderMarkdown` (`face/client/markdown.js:61`).
   **An untouched template must be detected** — H1 `# <strategy name>` plus the placeholder
   question body are exact strings — and rendered as "no thesis yet". `strategies/storage-chain`
   is today a byte-identical copy of `_template`; without this check its page would present an
   empty shell as content.
4. **Latest evidence** — the newest JSON in `backtests/` by filename date, beside a list of every
   backtest file with date and size.

   **The existing renderers in `face/client/render.js` do not fit and must not be claimed.**
   `renderResult` (`:330`) is that file's only export; `genericTable` (`:110`) and `flatObject`
   (`:139`) are module-private. `genericTable` reads `payload.rows`, which no backtest JSON has;
   `flatObject` (`:140-141`) keeps only scalar entries, which on
   `strategies/市场情绪/backtests/2026-09-02-sentiment-regime-2yr.json` is **8 of its 21
   top-level keys** — silently dropping `rules`, `window`, `parameters`, `discarded`,
   `score_stats`, `conditioning`, `regime_filter` and both `buyhold_*` blocks. Dropping
   `discarded` unannounced is exactly what Rule 5 and P4 forbid, in a spec that cites Rule 5 as
   a conformance point.

   So the rule is: **the full JSON is always reachable** in a collapsed `<details><pre>`
   alongside any summary — for parseable payloads too, not only unparseable ones. This is a NEW
   pattern here, not an inherited one: the card's existing `raw` toggle keeps the full text in the
   DOM (`face/client/chat.js:343`) but *swaps* it for the summary rather than showing both
   (`face/client/chat.css:726-728`). Nothing is dropped because nothing is hidden.
   The summary view above it is a recursive walk flattening nested objects to dotted paths
   (`score_stats.max_drawdown`, `discarded.spy_days_missing`) and rendering arrays as a count
   plus a short preview, with a meta line naming anything elided. Generic is mandatory: the
   template's result JSON has 2 top-level keys, `市场情绪`'s has 21 with three levels of nesting,
   and `docs/backtest-rules.md` prescribes contents in prose only — there is no schema and no
   shared serializer.
5. **Journal** — `journal.md` parsed on the `- YYYY-MM-DD:` prefix into a timeline, most recent
   few with an expand-all.
6. **Files** — one level of the channel directory (name, size, mtime), `__pycache__` filtered.
7. **Sessions** — the channel's sessions = `workspace.sessionIds` joined against `session.list`
   summaries for title and time, plus **new round** → `session.create({workspaceId})`.

   **Two archive sets now coexist and must be reconciled here.** The face's own reversible set
   (`$DSH_HOME/face/archived.json`) and the host's one-way `workspaceRegistry.archivedSessionIds`
   already disagree on disk today: the host set holds `session-d1a8a9ff-…` (cwd
   `strategies/storage-chain`) while the face set is `[]`. The registry keeps an archived session
   in `sessionIds`, and `session.list` does not filter it either. Define it once: the **effective
   archive set** = `archived.json.archived` ∪ `workspaceRegistry.archivedSessionIds`. Archived
   members fold into a collapsed **"archived (n)"** sub-list — counted and reachable, never
   dropped (Rule 5). `/data/sessions/archive` continues to write only `archived.json` and never
   mirrors into the host set; un-archiving an id that sits in the host set is **refused with that
   reason shown**, because the host archive has no reverse method at this pin.

### `status.yaml` extension

Every key optional; a file with none of them behaves exactly as today.

```yaml
status: researching   # idea | researching | validated | paper | retired
one_line: 存储涨价周期仍在早期，但龙头已提前透支
next: 等 11 月合约价，验证 DRAM 现货/合约价差
numbers:
  样本天数: 526
  最大回撤: -18.98%
```

`numbers` is nested, so the scrape as it stood — `/(?:^|\n)status:\s*(\S+)/` at the pre-rename
`face/src/strategies.ts:69-72` — cannot read it. Promote **`js-yaml`** (already resolved at
`4.3.2` in `node_modules`, and `@types/js-yaml` is already an orphan devDependency that nothing
imports) to a direct dependency.

**A parse failure must degrade to the existing regex for `status` and list the channel
anyway.** Today an unreadable `status.yaml` is swallowed — "status is a badge, not a gate" — and
that property is load-bearing: a malformed YAML must never delete a channel from the index.

### Where the derivation lives

All of it server-side, in `channels.ts`: thesis-template detection, journal parsing, newest-
backtest selection, YAML parse and fallback. `POST /data/channels/overview` returns a
render-ready structure. The reason is testability — `tsx --test` reaches server-side pure
functions and cannot reach the DOM. The new client module `face/client/channels.js` is thin DOM
assembly only. This keeps every new judgement in this change under test instead of adding it to
`chat.js`, which is 2149 lines with zero exports and no unit coverage.

---

## 5. The channel roster

`$DSH_HOME/face/channels.json`, keyed by `workspaceId` so a directory rename does not lose it:

```json
{ "version": 1, "channels": { "<workspaceId>": { "agents": ["codex"] } } }
```

**Seeded at adoption** from the agents connected at that moment. There is no implicit
"absent means inherit everything" rule: at every moment a channel's roster is a definite set,
visible on its page.

Enforcement point: `agent_<bin>`'s `execute` already reads the calling session's cwd
(`face/src/agents.ts:458`). It resolves the workspace (`:469`, gated at `:470`), compares against the roster, and on a
miss **throws** — naming the current roster and where to change it. The tool pipeline
(`dsh-tools`) catches a thrown `execute` and converts it into an `isError` **tool result** carrying
that message, so what the model sees is a result, never a crash — but the mechanism at the
enforcement point itself is a thrown `Error`, not a returned value. That refusal message *is* the
roster contract; it is deliberately not written into the channel's `AGENTS.md`, because that file
is Kairos-writable and would drift from the operator-owned `channels.json`. One call teaches it,
and it cannot fall out of sync.

### The honest limits — to be stated in the spec, the README, and the code

1. **dsh tool registration is tree-wide.** There is no per-session scoping seam: `ctx.tools.register`
   (reached through the `registerTool` dep, `face/src/panels.ts:345`, and driven by `syncAgentTools`,
   `face/src/agents.ts:527`) publishes one flat name per bin (`agent_<bin>`, minted by `toolNameFor`,
   `face/src/agents.ts:84`) that every session sees. A non-member agent's *schema* is still
   visible in every channel; only the call is refused.
2. **Kairos has a shell.** One shell turn can invoke `claude` directly. Per Rule 2 — "enforce
   below the layer that runs arbitrary code — or admit the gate is prose" — **this roster is a
   menu, not a fence.** It reduces noise and states intent; it does not contain.
3. **The storage bypass, not just the effect bypass — and it predates this design.** The sandbox
   confines *file effects only*: the emitted Seatbelt profile is `(allow default) (deny
   file-write*)` plus write allow-lists (`dsh-sandbox-local/lib/index.js:66-74`), and
   `dsh-bash-sandbox`'s README states outright "Network stays unrestricted". Both loopback
   surfaces are **reachability fences, not authentication**: `face/src/data.ts:116` — "A request
   with no Origin (curl, the tests, …) passes on Host alone" — and `dsh-client-connection`'s
   README — "The fence is a reachability policy, not authentication." Verified against the
   running face: a `curl` POST to `/data/strategies` cleared the 403 and the 415 and reached the
   handler (refused only by name validation), while a forged `Host` 403'd; and a `curl` RPC
   `workspace.list` returned the real registry, HTTP 200.

   So **one un-escalated shell turn can rewrite `channels.json` via `POST /data/channels/agents`,
   or rename/delete a workspace via `/api/workspace.*`** — no approval card (nothing escalates),
   no git diff, no session event. This is not introduced here: `POST /data/agents/connect`
   (route at `face/src/panels.ts:672`, writing through `writeAgentsMeta`,
   `face/src/panels.ts:228-231`) already writes `$DSH_HOME/face/agents.json` and registers the
   tool live by the same path. It does mean the charter's "structurally unreachable, not merely
   forbidden" (`Kairos-Design.md:90`) is **narrower than it reads whenever the face runs**, and
   §11 must not claim otherwise.

   **Proportionate mitigation, not authentication** (Rule 5 — what is never surfaced is never
   governed): the roster-write route appends a dated line to a face log, so a roster change is
   *visible* even though it cannot be prevented. Building a token would be new security
   machinery against §7.4; recording the residual is what Rule 3 actually asks for.
4. Rule 3 requires recording residuals rather than shipping a guarantee that fails at code
   level, so (1)–(3) belong in `face/README.md` in the same voice as §4's Gate-2 honesty note —
   not only in a code comment.

Also note the pre-existing constraint the roster does not change: the agent-run mutex is a
module-level `Set<string>` keyed by bin alone (`face/src/agents.ts:311`), so two channels
calling the same agent concurrently still collide with a 409 (`face/src/agents.ts:333`). Re-keying it is out of scope.

---

## 6. Reconciliation, failure modes, migration

### Migration — one idempotent reconcile, run on every listing

The registry's bootstrap has already happened (`initialized: true` on disk) and **adopted
nothing**. Measured: 18 session directories exist under `~/.dsh/sessions/`; exactly two are
accounted to the repo-root workspace, both because dsh's own client created them with
`session.create({workspaceId})` (the record's `createdAt` precedes one header by 55 ms and its
`updatedAt` follows the other by 12 ms), and one more sits in `archivedSessionIds`. The other 15
— every session the face itself created, via `session.create({cwd})` — are Ungrouped, and the
README's "later cwd-only sessions remain Ungrouped" means they stay that way. Three of them are
under `strategies/`; seven are repo-root sessions the workbench channel adopts. Adoption is
three steps:

1. `workspaceRegistry.create(dir)` for each channel directory — those under `strategies/` after
   the `_template`/dot/`__` filter, **plus the repo root** (idempotent).
2. For each existing session whose `cwd` is that directory, `attachSession(sessionId)` — via the
   service, not RPC. It validates the session header's cwd against the workspace path and
   rejects a mismatch without writing, so the operation is safe to repeat.
3. Seed `channels.json` for the workspace if it has no entry.

Because the directory name does not change, every existing `cwd` stays valid and every session
is recoverable.

**The reconcile writes, so its writes must be safe.** The face's existing state files are plain
unserialized read-modify-write (`writeMeta` at `face/src/sessions.ts:81-84`, `writeAgentsMeta` at
`face/src/panels.ts:228-231`) — safe only because every writer today is a POST, serialized by the
human. Step 3 puts a read-modify-write on the **GET** path, where a sidebar poll mid-reconcile can
silently revert an operator's roster toggle. Three rules: (a) both `channels.json` writers go
through `withFileLock` + `writeFileAtomic` from `@deepseek-ai/dsh-atomic-write` (already resolved
in `node_modules`, used by the settings and credentials stores), doing the read **inside** the
lock; (b) the reconcile writes only when it actually seeds a missing entry, so a steady-state
listing is a pure read; (c) `attachSession` is cheap to repeat — it early-outs on membership
before any validation (`dsh-workspace/lib/index.js:88`).

`strategies/storage-chain` is a byte-identical copy of `_template` whose real output lives
outside the arena at `docs/storage-industry-chain-2026.md` and is referenced by nothing. After
adoption its page honestly reads "no thesis yet". That is the correct outcome, not a defect.

### Failure modes

| Situation | Behaviour |
|---|---|
| Directory gone, workspace remains | `status()` → `missing-dir`; shown greyed, **never auto-deleted** |
| Workspace deleted, directory remains | next listing `create`s a **new UUID**; the README states retained sessions are not re-adopted, so they fall into the ungrouped bucket |
| `status.yaml` fails to parse | degrade to the regex for `status`; the channel still lists |
| Foreign-project sessions (`trend-dragon`, `dsh-playground`) | collected into a collapsed **"ungrouped"** bucket **with a count** — never silently dropped (Rule 5: "What is never surfaced is never governed") |
| Backtest JSON of an unseen shape | generic summary + the full JSON always kept in a collapsed `<details><pre>` |
| `channels.json` fails to parse | **fail closed**: read as "no rosters", every agent call refused with the §5 message; the reconcile must never re-seed over an unparseable file |
| Session in the host archive set (one exists today: `session-d1a8a9ff…`) | attached by the reconcile as normal, then folded by the effective archive set on every surface |
| A session whose cwd resolves to no channel | falls into the counted ungrouped bucket; the roster check has no channel to consult, so it fails **open** — which equals today's behaviour, since tools are registered tree-wide with no per-session gate |

Before this change those foreign sessions were worse than ungrouped: `session.list` is globally
scoped, so `strategyLabel` (pre-registry `face/client/chat.js:1169`, removed in `a45d104`) bucketed
them as if they were strategies and the picker offered their directories as workspaces for a new
Kairos session. The registry-driven index fixes both — bucketing now runs through `bucketFor`
(`face/client/grouping.js:40`).

### One correctness fix in the code being touched (shipped in `42fea60`)

`deleteSession` (pre-fix at `face/src/sessions.ts:89-117`) matched on session id alone and scanned
**every** project slug before `rm -rf`, so the face's delete button could reach another project's
session directory. It now takes the repo root and refuses anything outside it — the function at
`face/src/sessions.ts:179-211`, the guard at `:198`. Since the sidebar becomes registry-driven in this change, constrain the delete to sessions whose
`cwd` is **inside this repo** — not "or in the registry", which would re-widen exactly what the
constraint closes. The cwd is available: `deleteSession` already resolves the session directory,
and the header's `cwd` is the first JSONL record.

---

## 7. Code changes

**Server**

- `face/src/strategies.ts` → **`face/src/channels.ts`**: directory discovery, workspace
  adoption, roster read/write, landing-page derivation, the four routes.
- Extract `readBody` and `StrategyError` (at the time of writing, imported by `sessions.ts` and `panels.ts`)
  into **`face/src/http.ts`** first, so the rename does not drag two unrelated modules.
- Split **`face/src/agents.ts`** out of `panels.ts` (1177 lines carrying roster + agent
  execution + memory + plugin): `EXEC_SPECS`, `runAgent`, `agentToolDefinition`,
  `syncAgentTools`. The roster check edits exactly these. **This one cut only** — memory and
  plugin panels are not refactored.
- `face/src/main.ts`: `registerChannelRoutes(booted.ctx.webServer, booted.ctx, process.cwd())`
  — the ctx is now needed for `workspaceRegistry`.
- `face/src/sessions.ts`: constrain `deleteSession` (pre-fix `:89-117`) to sessions whose header `cwd`
  is inside this repo (§6), and correct the docstring at `:4-17` (dsh **does** expose
  `workspace.archiveSession` at this pin) and record the real reason `archived.json` stays —
  the host's archive is add-only with no un-archive method, while `setArchived(home, id, false)`
  can reverse.

**Client**

- New `face/client/channels.js` — landing-page DOM assembly, consuming the server's
  render-ready payload.
- `face/client/chat.js` — group headers become channel entries; sidebar grouping and the picker
  read the registry-backed listing; `session.create` carries `workspaceId`.

**Package**

- `js-yaml` promoted from transitive to a direct dependency of `face/package.json`.
- `@deepseek-ai/dsh-atomic-write` likewise promoted to a direct dependency (`withFileLock`,
  `writeFileAtomic`), for the `channels.json` read-modify-write.

---

## 8. Testing and drills

`face/tests/strategies.test.ts` (5 cases) is rewritten as `channels.test.ts`. New server-side
pure functions each get cases: thesis-template detection · journal parsing · newest-backtest
selection · YAML parse and its regex fallback · roster seeding and toggling · directory↔workspace
reconciliation · `missing-dir` · **`_template` and `.`/`__`-prefixed names never adopted** (the
behaviour `face/tests/strategies.test.ts:28` pinned at the time of writing, which the rewrite must
not lose — it is pinned now by `face/tests/channels.test.ts:28`) · **the
repo root adopted as the workbench channel** · **concurrent seed-vs-toggle on `channels.json`** ·
**an unparseable `channels.json` failing closed without re-seeding** · **the effective archive set
(face ∪ host) and the refusal to un-archive a host-archived id**. `sessions.test.ts` gains a case
pinning that `deleteSession` refuses a session whose `cwd` is outside this repo. The two assertions in `panels.test.ts` that pin "runs in the
calling session's directory" move with the code into the agents tests.

`tests/strategies/test_market_sentiment.py` is **unaffected** — it loads
`strategies/市场情绪/sentiment.py` by absolute path at module scope, and the directory name is
unchanged. This is precisely what decision B bought.

**Drills.** `npm test` today reports **96 tests, 95 pass, 1 skipped**, and that single skip is
the entire boot smoke test, gated on `FACE_SMOKE !== "1"` (`face/tests/smoke.test.ts:38`) — so
both `/data` fence drills and the `ask_user_question` assertion do not run by default. Rule 4
("a guard that has never been drilled is presumed broken") and debt D6 ("a new guard ships with
its drill in the same change") therefore require: the roster refusal and the three new
`/data/channels*` routes get their drills **in the default suite**, following the forged-Host →
403 pattern at `face/tests/sessions.test.ts:125-159`, not only inside the gated smoke test.

---

## 9. Not building

- **Multi-party posting** — agents remain Kairos's tools (decision 1).
- **Channel kinds / per-kind templates** (decision 2).
- **Per-channel skills.** `dsh-skill-filesystem` resolves project scope to "the nearest `.git`
  ancestor" (its README, §Project scope), so every channel directory resolves to the same repo
  root. Making skills vary per channel would require dynamically patching the profile, against
  §7.3 "we configure it; we do not fork it or wrap it".
- **Per-channel PIT bed.** `ALPHA_PIT_ROOT: data/pit/2yr` is pinned on the single
  `dsh-mcp-client` row in the operator's `cordis.patch.yml`, and the client is "one plugin
  instance per MCP server" — one bed for the whole tree. Recorded as a limitation.
- **Per-channel model** — `session.selectModel` exists at this pin; no demand.
- **Session search** — `session-query-sqlite` is mounted `:memory:` with `openAt: never`
  (inherited from `dsh-base`), so `session.search` answers `SESSION_QUERY_SEARCH_DISABLED`.
  Recorded as a limitation.
- **A `pinned` artifact pointer**, a channel wall, and renaming `strategies/` — all excluded by
  the operator.

---

## 10. Recorded residuals (out of scope, per Rule 3)

Neither is caused by this change; both are recorded because the change touches their
neighbourhood and Rule 3 requires stating what actually holds.

1. **MCP tool writes bypass the sandbox.** The alpaca-kit server is a child of the *face
   process*, not of a session, so its writes never pass `ctx.sandboxPolicy`. Evidence on disk:
   `data/.screen_cache/` written at the repo root during 2026-09-02 strategy work with no
   approval card. The stakes are small today (gitignored cache), but "the write map becomes
   code" does not currently cover this path.
2. **The model is never told it is Kairos.** `system-prompt.persona` is `''` in `dsh-base` and
   is set by neither `face/src/overlay.ts` nor the operator's `cordis.patch.yml`; `Kairos`
   appears only as a UI literal and a directory name. The charter's "single agent Kairos" is
   currently a label on a page, not a composed property. `persona` is the already-present,
   config-authored seat for it.

---

## 11. Charter conformance

- **P1 (wide hands, no self-keys)** — identity and roster live outside the workspace and outside
  the git-reviewed arena, and the file-effect sandbox blocks any direct write to them; Kairos
  writes only channel *content*. **But enforcement is the loopback-trust posture of `/data` and
  `/api`, not structural unreachability** — one un-escalated shell turn can `curl` either surface.
  See §5 limit 3. This design does not widen that hole (`POST /data/agents/connect` is the same
  class and predates it), but it must not claim to close it.
- **P5 (human is the steady state)** — the roster is operator-curated through the face; no
  channel configures itself.
- **Rule 2 / Rule 3** — the roster is labelled a menu, not a fence, in spec, README, and code.
- **Rule 4 / D6** — the new guard ships with its drill, in the default suite.
- **Rule 5** — foreign and ungrouped sessions are counted and shown, never silently filtered.
- **Rule 6 (prefer prose until code earns its place)** — the landing page is derived-first; the
  only new schema is four optional keys, and a channel that uses none behaves as today.
- **Rule 8 (no substrate before content)** — one new file with one field, demanded by the
  operator's actual request; identity reuses the host registry rather than a new store.
- **§7.1 "No second agent"** — untouched: connected CLIs stay subordinate tools of one agent,
  never peers.
- **§7.3 "No bespoke harness"** — this change *removes* a re-implementation rather than adding
  one; it adopts `workspaceRegistry` and corrects the docstring that wrongly claimed dsh had no
  archive.
- **§7.5 "No memory substrate beyond what exists"** — git, the strategy directories, and dsh's
  own sessions remain the memory.

**Write-map impact: none for row 1** — it still reads `strategies/`, writer "Kairos, freely", and
the directory name does not change.

**One charter phrase is measurably narrower than it reads, and that is a finding, not a change
request.** Row 4 grades the harness home "outside the workspace — structurally unreachable, not
merely forbidden" (`Kairos-Design.md:90`). Verified against the running face: it is reachable over
loopback from inside the workspace, today, before this change. That is the operator's call to make
— either the phrase is softened, or the loopback surfaces get authentication (new security
machinery, against §7.4). This spec neither assumes nor forces either; it records the residual per
Rule 3 and states honestly in §5 and §11 what actually holds.
