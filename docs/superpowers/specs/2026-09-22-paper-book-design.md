# The Paper Book — Design

**Status:** built 2026-09-22 on branch `feat/paper-book` (stacked on `feat/bought-data`); the
as-built truth is consolidated in `DEVELOPMENT.md` (§2.9, §3.4, §3.5, §4.2, §4.4–4.6, §7.4, §9
R-P1–R-P6, §10 item 6, Appendix A). Proposed 2026-09-22 as the framework half of the team's split
— the strategy module is Kairos's team's, the book that measures it is the framework's — and it
is the first piece of ROADMAP item (3), *paper forward-testing behind the order gate*, the slot
the skeleton spec (2026-08-29, §10) reserved as "workbench first, evolve later".
**Pins:** dsh `0.1.1-rc.2`, cordis `4.0.2` unchanged; no new dependency (pandas + stdlib on the
Python side, nothing on the face's).
**Language of citations:** bare paths are this repository; `home:` cites the paper home
(`$DSH_HOME/face/paper`). Every claim below was read from source on 2026-09-22 and the bed drill
in §7 was run the same day.

---

## 1. Context and decision history

What existed on 2026-09-22. ACCOUNT was an Alpaca paper account read through three tools and
the `/account` page; `place_order` / `cancel_order` sat in `alpaca_kit/account.py` pinned to the
paper host behind Gate 1 (never armed in the real home) and Gate 2 (its human half undrilled, D3).
Nothing in the tree held a position, a fill or a ledger: every backtest computed its own per-trade
statistics, and the strategy contract ended at `screen.py` (candidate symbols for a day) and
`backtests/*.json`. `status: paper` was a reserved badge. `DEVELOPMENT.md` §10 item 6 put paper
forward-testing after the order drill *and* after an independent evaluator exists (D1, D7), and
the charter's §1 says nothing runs unattended.

So "connect the strategies to a simulated account" was missing three things, none of them a
broker: a machine-readable output from a strategy, a book that attributes positions and value to
one strategy, and an engine that fills, marks and records under the five rules. This arc builds
those three, and only those.

Decisions, in the order taken:

1. **A book, not a broker.** The source of truth is a local, per-strategy book. One Alpaca paper
   account is one ledger for every strategy; Alpaca allows three paper accounts per user, each
   with its own key, which stops at three; Gate 2 cards one order at a time, so a 25-name
   rebalance would be 25 cards; and a paper account cannot replay history. The local book can
   be walked over a captured bed (so its accounting is testable offline and re-verifiable) and
   stepped forward one day at a time on the same code path. Mirroring the book's target
   positions into the Alpaca paper account through the two existing gates is a later step
   (§8), after D3.
2. **The intent is the contract.** A strategy that wants a book carries `signal.py`:
   `signal(source, day)` → `{"targets": [{"symbol", "weight"}, …], "note"?}`. Weights are
   fractions of the book's value, each in [0, 1], summing to at most 1; the remainder is cash;
   an empty list is flat. Weights rather than quantities, because a rule thinks in exposure and
   sizing is the book's job. Long only. The engine hands the rule the GuardedSource for the day
   (the same wrapper `replay_days` yields), so the rule reads exactly what a backtest may read;
   optionally `signal(source, day, holdings)` receives what the book holds (quantity and entry).
   The file left of the engine is the strategy's; everything right of it is the framework's.
3. **The book lives outside the workspace** — `$DSH_HOME/face/paper/<strategy>/`, the wallet
   home's pattern. Placement is what makes it a measurement: the sandbox denies writes outside
   the workspace, so Kairos can read its own book and cannot edit it. This is the charter's P1
   ("where this is enforced by placement, placement holds") applied to D1, and it is why the
   books are not under `strategies/<name>/`, where git would carry them but the measured party
   could write them.
4. **The engine is the only writer, and the operator's hand runs it.** `scripts/paper_book.py`
   (`open` / `walk` / `step` / `verify` / `show`) is invoked by the operator; nothing schedules
   it. The charter's "nothing runs unattended" holds unchanged; ROADMAP item (2), the daily
   cadence, stays deferred and would reopen D5 exactly as §10 already says.
5. **The five rules, applied to a book.** Rule 1: every read goes through the guard the engine
   builds per day. Rule 2: a `delist` row, or a held name with no bar for
   `presume_delisted_after` consecutive days (default 5), is written to zero as a realized loss and
   counted. Rule 3: `fees_bps` defaults to 0, gross; when set it is a declared parameter of the
   book. Rule 4: an intent decided at day t's close fills at the next trading day's open, never
   at t. Rule 5: a leg with no bar on its fill day is skipped and counted; a held name with no bar
   keeps its last mark and counts a stale day; nothing is interpolated. One band beyond the rules:
   `min_trade_weight` (default 0) leaves a drift smaller than that fraction of the book alone and
   counts the skip — a daily-rebalance rule otherwise trades a few shares every day as prices
   move (the drill measured 109 fills in 64 days at 0; 64 fills and 47 skips at 0.5%, two
   volatile names in Q1 2016 crossing the band most days).
6. **Fail loudly.** A rule that raises, or answers with an intent the validator refuses, is
   recorded on the ledger (`signal_error` / `intent_rejected`) and re-raised after the day's mark
   is saved. The day is never read as "flat"; the walk stops where it stands and resumes from the
   next day. A lookahead inside the rule surfaces the same way (`LookaheadError` on the ledger).
7. **Corporate actions are applied by tape date.** The book asks `corporate_actions(day, day)`
   (ex-date keyed) for held names each morning and applies splits (quantity × ratio, cost ÷
   ratio), `delist` (terminal loss) and `cash_dividend` (cash += quantity × rate, on the ex-date);
   every other kind is recorded as not modelled and counted. A source that cannot check
   (`corp_actions_available()` false — the bought bed) is recorded on every mark row as
   `corp_checked: false` and counted per day, never read as clean. Accounting follows the tape;
   the decision-side PIT rule is the rule's business through the guard.
8. **The face reads, never computes.** The landing page shows a "paper book" card from the
   engine's own `summary.json`, narrowed to the headline; no number is derived in the face.
   The card is marked off from `status.yaml`'s self-reported headline by an accent rule.

## 2. What the operator sees

**The command.** From the repo root, with the book home defaulting to `$DSH_HOME/face/paper`
(`ALPHA_PAPER_HOME` overrides):

```
python scripts/paper_book.py open   <strategy> [--cash 100000] [--fees-bps 0] [--presume-delisted-after 5] [--min-trade-weight 0]
python scripts/paper_book.py walk   <strategy> --start YYYY-MM-DD --end YYYY-MM-DD [--source snapshot --pit-root data/pit/2yr]
python scripts/paper_book.py step   <strategy> [--day YYYY-MM-DD]
python scripts/paper_book.py verify <strategy>
python scripts/paper_book.py show   <strategy>
```

Every command prints one JSON object and exits 0 iff it says `ok` — the `face_data.py`
contract. `walk` bounds the replay (rule 1's trap) and skips days the book has already stepped,
so it extends a book; `step` is a one-day walk, defaulting to the source's last trading day up to
today. The source is `make_source()` — `ALPHA_DATA_SOURCE` / `ALPHA_PIT_ROOT` or the flags — so a
book walks a bed offline or steps on the live adapter with keys, exactly as a backtest would.

**The home.** `home:<strategy>/ledger.jsonl` (append-only; every row carries `seq`, `prev` = the
sha256 of the previous row as written, `at`, `day`, `kind`), `book.json` (the state, rewritten
atomically after every step, carrying the chain head), `nav.jsonl` (one row per stepped day),
`intents/<day>.json` (each intent as validated, with `received_at` and the value it was sized
on), `summary.json` (the headline). `verify` recomputes the chain, the cash and the positions
from the ledger alone and names every disagreement; `load` refuses a book whose ledger and
state disagree (an interrupted step) rather than stepping on it.

**The landing page.** A channel with a book shows, under the status headline, a card reading
`paper book · 64 days stepped · last 2016-03-31`, four figures — NAV, return, max drawdown,
positions — a line for the pending intent (`intent of 2016-03-31 pending: 2 names, fills at the
next open`) and a `counted:` line naming every non-zero counter the engine kept instead of
filling (discarded, small skipped, cash short, signal errors, rejected intents, delisted,
presumed delisted, days corp unchecked). No book, no card. The face's boot line says where it
reads from: `kairos-face: paper books read from <home>`.

## 3. What Kairos sees

`strategies/_template/signal.py` — a rule that raises `NotImplementedError` until written, with
the contract in its docstring and a `__main__` that runs it by hand on a bed. `AGENTS.md` carries
the same paragraph: what the intent is, that the operator runs the book, where it lives (readable,
not writable), that a raising rule stops the day, and that `status: paper` is still a badge that
schedules nothing. A channel session can `cat $DSH_HOME/face/paper/<name>/summary.json` and read
its own `ledger.jsonl`; the sandbox refuses a write there.

## 4. Substrate and mechanism

### 4.1 `alpaca_kit/paper/`

| Module | What |
|---|---|
| `intent.py` | `validate_intent(raw, as_of)` → `Intent(as_of, targets, note)`: symbols upper-cased and checked against the ticker grammar, duplicates / bad weights / a gross above 1 / more than 200 names / a non-string note refused with the reason; `load_signal(dir)` imports `signal.py` by path under a private module name with the strategy directory on `sys.path` during the import; `wants_holdings` / `call_signal` pass `holdings` only to a rule that declares it |
| `home.py` | `paper_home(env)`: `ALPHA_PAPER_HOME` > `$DSH_HOME/face/paper` > `~/.dsh/face/paper`; `is_strategy_name` (the face's channel grammar: opens on a letter or digit, then letters, digits, marks, `_`, `-`, ≤ 41 code points, never `_template` / `__…` / a leading dot); `book_dir` |
| `book.py` | `PaperBook.open / load`, `step`, `walk`, `verify`, `summary`; the files above |

**One step**, in order: (1) corporate actions with ex-date = day on held names; (2) the pending
intent filled at the day's open — target quantity = ⌊weight × NAV_ref / open⌋ where NAV_ref is
the book's value at the intent's mark; a held name the intent leaves out targets 0; sells run
before buys (they fund them); a buy the cash cannot cover is cut to what it can (`cash_short`
recorded and counted); (3) every held name marked at the close (or a stale day counted);
(4) the `mark` row, the `nav.jsonl` row, `book.json` saved; (5) the rule asked, its intent
validated, written to `intents/`, recorded as `intent`, and held as pending. Row kinds:
`open`, `intent`, `intent_rejected`, `signal_error`, `fill`, `discard`, `cash_short`,
`intent_filled`, `corp_action` (applied or not, with the reason), `delist`, `dividend`,
`presumed_delisted`, `mark`. Quantities are floats (a reverse split leaves a fraction); fills
are integer targets.

### 4.2 `scripts/paper_book.py`

argparse with the five sub-commands; `--home` / `--root` on all, `--source` / `--pit-root` on
`walk` and `step`. It loads the rule before it builds a source (a strategy without `signal.py`
fails before any market read), refuses a name outside the grammar before any path is formed, and
catches `BookError` / `IntentError` / `ValueError` / `OSError` / `RuntimeError` into the
`{ok:false, error}` line. Neither the script nor the package imports `alpaca_kit.account` or
names an order function; `tests/paper/test_cli.py` greps both.

### 4.3 Face — `feat/paper-book`

`src/channels.ts`: `PaperTile`, `paperHomeOf(dshHome, env)` (`FACE_PAPER_HOME || <dshHome>/face/paper`),
`readPaperSummary(paperHome, name)` — a name outside `NAME_RE` (the repo root among them) never
reaches the filesystem; absent, unreadable, malformed, a non-object, or a summary missing any
headline number is `null`; `counts` keeps numbers only; `pending` is narrowed to `{as_of,
n_targets}`. `ChannelRouteDeps.paperHome?` and the overview's `paper` key, present only when a
book exists for that channel. `src/main.ts` resolves the home once and logs it.
`client/channels.js`: the card (§2), formatting only. `client/chat.css`: `.ch-card.ch-paper`.

### 4.4 The fixture — `strategies/paper-drill/`

The paper book's `room-drill`: `signal.py` holds the N (5) most-traded names on the day's
snapshot (close × volume) equal-weighted with 2% cash, ties broken on the symbol; `status: idea`,
`one_line: the paper book's drill fixture, not a strategy`; the rest is the template. It needs
daily snapshots, so it runs on a captured bed and not on live keys.

## 5. Charter conformance and amendments

Conforms as built: nothing runs unattended (§1); Kairos writes `signal.py` under `strategies/`
(§4, its row); the engine's writes land outside the workspace (§4's `$DSH_HOME` row: the
operator's, through a script the operator runs); no order path is touched, so both order gates
and D3 / D8 are unchanged; the face adds a read (§3's FACE row). Proposed amendments, for the
operator to accept or edit — this document does not change the charter:

- **§1, ACCOUNT bullet**, append: *"— and, per strategy, a paper book: the operator's engine
  fills the strategy's declared intent at the next open, marks it daily and keeps a chained
  ledger outside the workspace; Kairos reads it and cannot write it."*
- **§4 write map**, new row: *`$DSH_HOME/face/paper/<strategy>/` (paper books) | the engine,
  run by the operator (`scripts/paper_book.py`); the face reads | the ledger's hash chain
  (`verify`); the landing page card; git carries `signal.py`, not the book.*
- **D1**, narrow: the paper measurements are no longer self-reported (the book is written
  outside Kairos's reach); what remains of D1 is `backtests/` and `journal.md`, due as before.
- **§8**, new trigger: *"A paper book stepped by anything but the operator's hand (a schedule,
  a face button, a tool) → §1 'nothing runs unattended' · D5 · the daily-capture residual R-P5."*

## 6. Residuals

- **R-P1 — The rule reads what it likes.** `signal.py` runs in the engine's process; it is
  handed the guarded source, but nothing stops it from calling `make_source()` raw or opening
  the bed's parquet. This is P3's class, the same as for `backtest.py`: the guard holds the
  sanctioned channel, review holds the rest. A lookahead through the guard is on the ledger.
- **R-P2 — The home is readable, and the chain is tamper-evidence, not authorship.** Every shell
  turn can read the key-less book (that is the point); the placement holds only while the
  sandbox denies writes outside the workspace (D10's class for the loopback routes does not
  apply — the face has no write route to the home). `verify` proves internal consistency;
  it does not prove who wrote a row.
- **R-P3 — Fills are a model.** Next open, no slippage, no partial fills, no market impact,
  integer targets, longs only, one fee parameter. A book is a forward test of a rule, not of
  execution; the Alpaca mirror (§8) is where execution facts enter.
- **R-P4 — Corporate actions are partial.** Splits, `delist` and cash dividends (credited on the
  ex-date; the frame has no payable date) are modelled; mergers, spin-offs, stock dividends and
  the rest are counted as ignored. An action Alpaca processes after its ex-date is missed on
  the day (the live accessor is announce-bounded) and never re-applied. A bed with no corp file
  is unchecked and says so on every row.
- **R-P5 — Forward days need a bed.** A snapshot-driven rule cannot run on live keys
  (`AlpacaSource.daily_snapshot` raises); the daily capture that would extend a bed is ROADMAP
  item (2)'s territory and is not built. A bars-only rule steps on the live adapter today.
- **R-P6 — `at` and `received_at` are the engine's wall clock.** In a replay they say when the
  engine ran, not when the market day was; `day` is the market fact. Reproducibility of a walk
  is the rule's and the bed's; the chain is per run.

## 7. Drills

**Automated.** `tests/paper/` (66 tests, offline on `FakeSource`): the intent grammar and every
refusal; the loader (by path, sibling imports, no shadowing, the three refusals); the home
grammar; and the book — fills at the next open and never the deciding close, sizing, sells
before buys, an unchanged target untraded, the band (never on an exit), a leg with no bar
discarded and filled later, zero/NaN bars as no bar, stale marks then a presumed delisting, a
`delist` row, a split's continuity, a dividend and an ignored kind, an unchecked bed reported per
day, fees and `cash_short`, a raising rule and a malformed intent recorded and raised, the guard
inside the rule, `holdings`, monotonic days, resume, the chain and `verify` catching an edited
row, the intent files and summary, the CLI end to end, the order-path fence, the template's
refusal and the fixture's answer. The face: `channels.test.ts` covers `readPaperSummary` (the
narrowing, every null case, the name grammar), `paperHomeOf`, and the overview carrying `paper`
only for a channel with a book and never for the root.

**The bed drill** (this machine, 2026-09-22, the bought bed `data/pit/massive-2016-2017`, AAPL
and MSFT, 521 days, no corp file): `open paper-drill` → `walk --start 2016-01-04 --end 2016-03-31`
→ 64 days stepped in 0.8 s, NAV 100,000 → 111,465.54 (+11.47%), max drawdown −5.15%, 2
positions, 109 fills, 64 intents, `days_corp_unchecked 64`; `verify` ok over 301 chained rows;
`step --day 2016-04-01` extended the book by one day (NAV 109,649.36). With
`--min-trade-weight 0.005` over the same window: 64 fills, 47 small skips, NAV 111,498.46
(+11.50%), max drawdown −5.16%, `verify` ok over 256 rows.

**Manual, not yet run:** the landing page card in a browser — boot the face with
`ALPHA_PAPER_HOME` and `FACE_PAPER_HOME` pointing at the same scratch home, open the
`paper-drill` channel, see the card and the boot line. Steps in `face/README.md`, "The paper-book
drill".

## 8. Not built

- **The Alpaca paper mirror** — diff the book's target positions into orders through Gate 1 and
  Gate 2, after D3's manual drill (charter §8's first trigger); one card per rebalance would be a
  new gate shape.
- **The daily cadence** (ROADMAP item 2) and **the daily capture** that would extend a bed
  for snapshot-driven rules (R-P5).
- **Discretionary intents from a session** — a `paper_intent` tool attributed like the wallet
  tools, for a forward test where the agent, not a rule, decides each day.
- **Per-strategy cost accounting** — folding the wallet ledger's spend by channel into the
  book's return.
- Shorts, partial fills, a `/paper` page, `holdings` beyond quantity and entry.
