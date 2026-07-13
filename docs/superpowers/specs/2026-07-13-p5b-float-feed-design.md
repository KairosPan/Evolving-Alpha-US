# P5b — Float feed + float-based L3 sizing

> Owner: KairosPan · 2026-07-13 · the last P5b enrichment feed. Twin deliverable: a PIT-safe **float
> feed** (data layer) and **float-aware L3 sizing** (sizing layer) that consumes a float number to refine
> the tier into a liquidity-aware, share-count-sensitive position. Follows the exact P5a earnings / P5b
> short-interest / offerings feed template; extends L3 sizing additively (default-off, verdict-neutral).

## 1. Why

`DEVELOPMENT-PLAN.md` §1 P5b: "Float feed → float-based L3 sizing (`size_tier` is wired; share-count
sizing needs real float)." Today `size_tier` is a discrete label (`flat|probe|core|heavy`) from
`confidence × risk_gate` — it knows nothing about how much stock actually trades. A `heavy` tier on a
3M-share micro-float name and a `heavy` on a 500M-share large-cap are treated identically, yet the
micro-float name can't absorb the same dollar bet without the buyer moving the tape. Real free float is
the missing liquidity input. It is also the denominator the dormant `short_squeeze` skill needs
(`ShortInterest.percent_of_float = shares_short / float`, stubbed `None` until this feed lands).

Free float changes on **lockup expiries, buybacks, and secondary offerings** — each becomes knowable only
when it is reported/effective, so float is a *point-in-time* quantity, not a constant.

## 2. The PIT key (firewall)

`FloatFact.knowable_date` — the day the float figure became **knowable**: the SEC filing / disclosure /
effective date on which that share-structure figure was first reportable (a 10-Q/10-K cover-page shares
outstanding, a vendor's float revision tied to a lockup expiry that has actually elapsed, a completed
buyback or secondary). This is the exact analog of `corp_actions.announce_date := process_date`,
`EarningsFact.filing_date`, and `ShortInterest.publication_date`.

`FloatFact.as_of_period` — the balance-sheet / measurement date the count *describes* (e.g. a 10-Q cover
date). **INFORMATIONAL, never the PIT key.** Keying on it would leak the ~40-day filing lag between when a
share count is measured and when it is disclosed — the classic fundamentals backtest trap (identical to
earnings' `period_end` vs `filing_date`). A figure whose `knowable_date > as_of` is invisible; being late
(a stale float) is a safe under-claim, being early would leak.

Restatements / revisions are PIT-native: the same symbol can have several `FloatFact`s (a fresh count each
quarter, an intra-quarter revision after a secondary), each with its own `knowable_date`. `known_float`
returns every version knowable by `as_of`; **dedup-to-latest is a read-side concern** (`latest_known_float`),
never baked into the PIT primitive — same split as earnings' `latest_actual`.

## 3. The float model + capability (data layer)

`alpha/data/float_shares.py` (model + source-agnostic PIT primitives, mirrors `short_interest.py`):

```
FloatFact(frozen):
  symbol: str
  free_float: float              # free float in SHARES (shares outstanding − insider/restricted). RAW.
  knowable_date: Date            # PIT KEY — day this figure became knowable (filing/disclosure/effective)
  shares_outstanding: float|None # total shares outstanding (context)
  restricted_shares: float|None  # insider/lockup/restricted = outstanding − free_float (context)
  as_of_period: Date|None        # measurement date the count describes — INFORMATIONAL, not the PIT key
  source: str|None               # "vendor" | "edgar" | "snapshot"

known_float(records, as_of)               -> [f for f in records if f.knowable_date <= as_of]
latest_known_float(records, symbol, as_of) -> the most-recently-knowable FloatFact for symbol (or None)
float_to_frame / float_from_frame          -> persistence converters (dates: knowable_date, as_of_period)
```

**Unit note.** The feed stores **absolute shares** (RAW, like unadjusted prices — the honest source unit).
The pre-existing `StockSnapshot.free_float` (US-3d) is in **millions**; that is the legacy *state* channel,
reconciled to shares at exactly one seam (`SizingPolicy`, §5). The feed→state consume path that would make
the feed *populate* `StockSnapshot.free_float` is a future step (out of this footprint; noted in §7).

**Optional Protocol capability** (`alpha/data/source.py`), exactly like earnings/short-interest — a source
without it raises `NotImplementedError` (pure-swap), availability fail-closed default-`False`:

```
float_known(symbol, as_of) -> list[FloatFact]    # knowable_date <= as_of
float_available() -> bool                          # False = float artifact MISSING (fail-closed)
```

Wired through all five source shapes identically to the other P5 feeds:
- `FakeSource` — `float_facts=None` default → `float_available()` False → byte-identical to pre-P5b.
- `GuardedSource` — `float_known` guards `as_of`; `float_available` getattr-probe, default `False`.
- `SnapshotSource` — served from `PITStore`, PIT-filtered on `knowable_date`.
- `CompositeSource` — new `"float"` capability group routes `float_known`+`float_available` together.
- `PITStore` — `has_float`/`put_float`/`get_float` (tri-state MISSING seam like `has_short_interest`).

**Live backend** `alpha/data/float_feed.py::FloatSource` — the `float`-capability-only backend (mirrors
`FinraSource`): a stdlib-`urllib` `_get_json` mockable seam (fully offline-testable), maps a vendor JSON
record → `FloatFact` with `knowable_date` from the record's disclosure/filing date (falls back to
`as_of_period` **only if** no disclosure date — a conservative never-early key), and serves ONLY `float_*`;
every other `MarketDataSource` method raises `NotImplementedError`. The concrete vendor endpoint/auth is a
documented live-integration stub (free float has no single canonical free API — it is vendor-derived, or
reconstructed from EDGAR cover-page shares outstanding minus Forms 3/4/5 + Rule-144 restricted); the built
+ tested core is the record→FloatFact mapping, the disclosure→knowable PIT keying, and the symbol/PIT
filter. Registered as `"float_feed"` in `registry.py` (`ALPHA_DATA_COMPOSITE=float=float_feed`).

## 4. Float-based sizing (sizing layer)

Two refinements, both **additive / default-off / verdict-neutral**, in `alpha/sizing/float_size.py` (a
pure module — tier + float number + config in, refined tier / share-count out; no source or universe
imports). Thresholds live on `SizingConfig` (frozen, all new fields defaulted → backward-compatible):

```
float_large_shares: float = 50_000_000    # free float >= this -> UNCONSTRAINED (huge-float name)
float_mid_shares:   float = 10_000_000    # [mid, large) -> cap 'core'; below mid -> cap 'probe'
max_float_participation: float = 0.01     # a single bet takes at most this fraction of free float
name_dollar_unit: float = 100_000         # $ per single-name unit (heavy = 1.0x) -> share-count target
```

**(a) Liquidity-aware tier cap** — `float_capped_tier(tier, free_float_shares, config) -> SizeTier`:
- `free_float_shares is None` (no float feed) → tier **unchanged** (the byte-identical default-off case).
- `>= float_large_shares` → tier **unchanged** (a huge-float name is not float-constrained).
- `[mid, large)` → cap at `core`; `< mid` → cap at `probe`.
- **Only ever tightens** — never raises a smaller tier (safety-only, exactly like `derisk_tier`). It
  never zeroes a kept candidate to `flat`: dropping a name is the L4 guard's job, not sizing's.

**(b) Float participation share-count** — `float_participation_shares(tier, price, free_float_shares,
config) -> (shares|None, capped)`: the actual share count for the tier's dollar budget
(`SIZE_TIER_WEIGHT[tier] × name_dollar_unit × max_name_weight ÷ price`), **capped** so it never exceeds
`max_float_participation × free_float`. A small-float name → the participation cap binds → fewer shares
for the same dollar risk. A huge-float name → the cap never binds → full dollar-budget shares. `None`
price/float → `(None, False)` (not computable / off). `refine_sizing(...)` bundles both into a frozen
`FloatSizing(tier, target_shares, participation_capped)`.

**Where it lands.** `float_capped_tier` refines the Candidate's existing `size_tier` field in-place
(`size_decision`) and the portfolio's netted exposure (`plan_portfolio`) — no new eval-model field (the
`Candidate`/`Portfolio` models are out of this footprint and unchanged). The share-count helper is a pure
function a downstream consumer (console / DAgger record, with price + capital) calls on demand.

**Activation.** `size_decision` and `plan_portfolio` gain an optional `floats: Mapping[str, float] | None
= None` (symbol → free float in **shares**); `None` → the cap branch is never entered → **byte-identical**.
`SizingPolicy` gains a keyword-only `float_aware: bool = False`; when `True` it derives the float map from
the `CandidateUniverse` it already receives (`StockSnapshot.free_float` millions × 1e6 → shares) and
threads it in. Default `False` → `SizingPolicy` is byte-identical, so every existing caller,
`compare_harnesses`, and the whole offline suite are unchanged (dormant exactly like the P5 feeds — merge
activates nothing). The `SizingPolicy(GuardedPolicy(...))` decorator order (size the post-veto survivors)
is untouched; `float_aware` is an orthogonal flag.

## 5. Verdict-neutral + default-off contract (the proofs)

**Verdict-neutral (structural).** The eval scorers (`ReturnScorer`/`PoolScorer`), `walk_forward`,
`metrics`, and `stats` read only `symbol`/`pattern` + forward returns — grep confirms **nothing in
`alpha/eval` or `alpha/loop` reads `size_tier` or `portfolio`** (`compare.py` already documents "Sizing is
verdict-neutral"). Float refinement changes only `size_tier`/`portfolio`, so it provably cannot move the
verdict. Pinned **non-vacuously**: a test sizes the SAME decision two ways (float-present vs tier-only),
asserts the tiers actually **differ** (refinement is real), then feeds both through the real
`PoolScorer.score_step` and asserts identical scores (mirrors the existing
`test_sizing_annotations_are_verdict_neutral`). A `compare_harnesses` run over a float-bearing source is
pinned equal to the float-absent baseline (the scoring path is float-blind end-to-end).

**Default-off / byte-identical.** `floats=None` (no float map threaded) and `float_aware=False` (the
`SizingPolicy` default) each leave every tier and the portfolio exactly as today. Pinned: `size_decision`
with and without a `floats=None` arg produce identical packages; a large-float name (`>= float_large_shares`)
is unchanged even when floats ARE threaded.

## 6. Tests (TDD)

Data (`tests/data/test_float_shares.py`, `test_float_feed.py`, extend `test_composite.py`,
`test_pit_store.py`, `test_registry.py`, `test_source.py` shapes):
- PIT guard — a `FloatFact` with `knowable_date > as_of` is invisible; keying on `as_of_period` would leak.
- `latest_known_float` picks the most-recently-knowable revision (restatement/secondary).
- pure-swap — `FloatSource` raises `NotImplementedError` on every non-float method.
- CompositeSource routes the `float` group; fail-closed availability (`float_available` default `False`).
- PITStore round-trip + `has_float` tri-state (present-empty vs MISSING).
- `_get_json` seam mockable offline; conservative fallback key (`as_of_period` only when no disclosure date).

Sizing (`tests/sizing/test_float_size.py`, extend `test_policy.py`):
- small float → capped tier (`heavy`→`core`/`probe`); huge float → unchanged; `None` → unchanged.
- share-count: small float → participation-capped (fewer shares); huge float → full dollar-budget shares.
- `size_decision(floats=...)` shrinks a small-float name's tier; `floats=None` byte-identical.
- verdict-neutral (non-vacuous, via `PoolScorer`) + `compare_harnesses` float-present == baseline.
- `SizingPolicy(float_aware=True)` caps from the universe's float; `float_aware=False` byte-identical;
  decorator order preserved.

## 7. Deliberately not done (report to plan)

- **`short_squeeze` full activation** needs BOTH `percent_of_float` (this feed) AND short-interest — wiring
  `ShortInterest.percent_of_float = shares_short / latest_known_float` is a consume-path step in
  `alpha/state`/`alpha/features` (out of this footprint).
- **Feed → state consume path** (float feed populating `StockSnapshot.free_float`, and the shares/millions
  reconciliation living there instead of at the `SizingPolicy` seam) — `alpha/state`/`alpha/universe`/
  `capture`, out of footprint. Until then sizing reads the legacy snapshot `free_float` channel.
- **Live vendor endpoint/auth** — documented stub (§3), like FinraSource.
- No eval-model field for the share-count (`Candidate`/`Portfolio` are out of footprint); the share-count
  is a pure helper computed on demand.
```
