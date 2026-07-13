# Design: P5a — earnings calendar + EPS/revenue feed (P5's first real feed)

- **Date:** 2026-07-13
- **Status:** Draft (P5a — the FIRST of P5's real feeds; promoted to first by the 2026-07-12 growth pivot)
- **Scope:** medium — new data models + one new source capability group (`earnings`) on the
  `MarketDataSource` Protocol, a live EDGAR-facts backend behind the `_get_json` REST/urllib seam, an
  offline snapshot backend, and PIT-safe derived feature helpers. No firewall change; no consume-path
  wiring (guard veto / doctrine activation is a SEPARATE later step — §"Not built here").
- **Builds on:** `docs/superpowers/specs/2026-07-13-p4-composite-source-design.md` (the CompositeSource
  per-capability seam this lands on).
- **Doctrine driver:** `docs/doctrine/2026-07-12-us-growth-doctrine-draft.md` §2.4 `verification_nodes`
  (calendar-anchored verification with pre-registered surprise) + §4.5 `earnings_gap_discipline.rule`
  (the T-3-before-earnings checklist gate). Earnings is named the manuscript's ONLY hard data gap
  (§0.7 (6); §4.5 automation "待财报数据源 (P5 首项)").

## Context & why earnings is first

The growth doctrine has exactly one node that is manual-until-a-feed-lands: earnings. Two doctrine
elements need earnings data:

1. **`earnings_gap_discipline.rule` (§4.5)** — from **T-3 trading days before a name's earnings**, a
   thesis checklist is forced; an incomplete checklist is a guard-veto candidate. This needs a
   **calendar**: *when does symbol X next report?* → `days_to_earnings`.
2. **`verification_nodes` / `pead_humility` (§2.4)** — each thesis card's verification node is
   calendar-anchored to an external event (earnings), with a **pre-registered surprise** (轮回 anchor
   A-15). Reviewing that node needs the **actual result** (EPS/revenue) and, where available, the
   **consensus estimate** to compute a realized surprise. (The card's OWN pre-registered expectation is
   an agent/harness-side artifact — see "Not built here".)

## PIT key choice — the load-bearing decision

The firewall (CLAUDE.md PIT firewall; `alpha/data/firewall.py`, TCB-pinned) requires every dated/learned
artifact to key on a **lookahead-safe availability date** — the day the fact became knowable to us, never
the day the underlying event is *dated*. Corp actions do this with `announce_date := process_date`
(`alpha/data/corp_actions.py`). Earnings has two record kinds with two different availability keys:

### Earnings FACTS → `filing_date` (the SEC filing acceptance date)

A company's quarterly numbers (actual EPS, revenue) are knowable only **as of when the company files**
its 10-Q/10-K with the SEC — **NOT** as of the fiscal period end. A period ending 2026-03-31 is not
public until the 10-Q is filed, typically 4–6 weeks later. So:

- **PIT key = `filing_date`** (EDGAR's `filed` field, `YYYY-MM-DD`). `period_end` (EDGAR's `end`) is
  carried as *informational only* — it is explicitly **not** the PIT key, and a comment says so, exactly
  as `announce_date` documents `process_date`.
- **Conservative-never-leaks argument** (same shape as `process_date`): the raw earnings *release* is
  often an 8-K press release a few days before the formal 10-Q. EDGAR's `filed` date of the structured
  XBRL fact can therefore only **lag** the real-world release, never precede it — so keying on `filed`
  never leaks the future. It is the earliest date the *structured* fact is retrievable from EDGAR. (A
  vendor "earnings announcement datetime" feed could tighten this to the press-release instant; that is
  a vendor-seam refinement, not a correctness fix — `filed` is already lookahead-safe.)
- **Restatements are PIT-native.** The same `(fiscal_year, fiscal_period)` can be reported more than once
  on EDGAR (original 10-Q, then a later 10-K/A with a corrected value), each with its own `filed`. We
  emit **one `EarningsFact` per XBRL datapoint**, each keyed by its own `filing_date`. `known_earnings`
  then returns, at any `as_of`, exactly the versions filed by then — the original before the restatement's
  filing_date, both after. Dedup-to-latest-per-period is a read-side/consumer concern, not baked into the
  PIT primitive (mirrors `known_corporate_actions` returning the raw announced set).

### Earnings CALENDAR entries → `known_asof` (when the expected date became knowable)

An *upcoming* report date is an expectation known before the event. Its availability key is the day that
particular expected date became knowable — a company confirms its next earnings date ~2–4 weeks ahead via
IR. So a calendar entry carries its **own `known_asof`** distinct from `expected_date`:

- `earnings_calendar(as_of)` returns entries with `known_asof <= as_of`. A future `expected_date` is fine
  (it's pending, like a corp action with a future `ex_date`); a future `known_asof` is invisible (no
  lookahead — you can't have known a date announced tomorrow).
- **EDGAR has no forward calendar.** From EDGAR we can derive, PIT-safely and for free: (a) **past** report
  dates — each historical filing is a report that was known as of its own `filing_date`
  (`expected_date = known_asof = filing_date`, `is_confirmed=True`); and (b) **one naive forward estimate**
  per symbol (`expected_date ≈ last_filing + 91d`, `known_asof = last_filing_date`, `is_confirmed=False`,
  `source="edgar_estimate"`) — a heuristic, clearly flagged, never leaking (its `known_asof` is a past
  filing date). A **confirmed** forward calendar (official date, bmo/amc session) is a vendor product and
  rides the vendor seam (offline-stubbed; see "Live vs offline-stubbed").

## Data models — `alpha/data/earnings.py`

Frozen Pydantic (`ConfigDict(frozen=True)`, matching `MarketState`), PIT-keyed. New module, sibling of
`corp_actions.py`, so `source.py` stays focused on the Protocol.

```python
class EarningsFact(BaseModel):          # one reported (or restated) quarterly result, PIT-keyed on filing
    model_config = ConfigDict(frozen=True)
    symbol: str
    fiscal_period: str                  # "2026Q1" / "2026FY" (fy+fp), for grouping/display
    period_end: Date                    # fiscal period end — INFORMATIONAL, *not* the PIT key
    filing_date: Date                   # PIT KEY — SEC acceptance/filed date; knowable-as-of
    form: str | None = None             # "10-Q" / "10-K" / "10-K/A" — provenance
    actual_eps: float | None = None     # us-gaap EarningsPerShareDiluted (fallback Basic)
    actual_revenue: float | None = None # us-gaap Revenue* (see mapping)
    estimate_eps: float | None = None   # analyst consensus — VENDOR only (EDGAR has none → None)
    estimate_revenue: float | None = None
    eps_surprise: float | None = None   # actual − estimate (or vendor-supplied); None if either leg absent
    revenue_surprise: float | None = None
    source: str | None = None           # provenance: "edgar" | "vendor" | "snapshot"

class EarningsCalendarEntry(BaseModel): # a scheduled/expected report date, PIT-keyed on knowability
    model_config = ConfigDict(frozen=True)
    symbol: str
    expected_date: Date                 # scheduled/expected (may be past or future vs as_of)
    known_asof: Date                    # PIT KEY — when this expected_date became knowable
    is_confirmed: bool = False          # company-confirmed vs estimated
    session: str | None = None          # "bmo" / "amc" — before/after market (vendor)
    source: str | None = None
```

### Source-layer PIT primitives (same module — mirror `corp_actions.py`)

- `known_earnings(facts, as_of) -> list[EarningsFact]` — `filing_date <= as_of`.
- `known_calendar(entries, as_of) -> list[EarningsCalendarEntry]` — `known_asof <= as_of`.
- Frame ⇄ model converters for persistence + as the EDGAR/vendor normalization target:
  `facts_to_frame` / `facts_from_frame` / `calendar_to_frame` / `calendar_from_frame`, with
  `FACT_COLUMNS` / `CALENDAR_COLUMNS` constants (dates iso-serialized on write, parsed on read — same
  idiom as `PITStore.put/get_corp_actions`).

### Derived FEATURE helpers — `alpha/features/earnings.py` (the consume-path-facing signals)

Kept out of the data layer (which answers *what is knowable*) — these are *derived* trailing-only signals
a future guard/doctrine step reads. Default-safe: no calendar → `None`/`False` (byte-identical when off).

- `next_earnings(entries, symbol, as_of) -> EarningsCalendarEntry | None` — soonest `expected_date >= as_of`
  among `known_calendar(entries, as_of)`.
- `days_to_earnings(entries, symbol, as_of) -> int | None` — `(next.expected_date - as_of).days`, else None.
- `has_upcoming_earnings(entries, symbol, as_of, within_days=3) -> bool` — `days_to_earnings ∈ [0, within]`.
  Default `within_days=3` is exactly the §4.5 **T-3** checklist trigger.
- `latest_actual(facts, symbol, as_of) -> EarningsFact | None` — most recently *filed* fact ≤ as_of
  (restatement-aware: max `filing_date`), the verification-node "what did they actually report" leg.

## Source capability — the `earnings` group

Three methods added to `MarketDataSource` (`alpha/data/source.py`), an **OPTIONAL** capability (a source
that doesn't provide earnings raises `NotImplementedError` on the data methods — the pure-swap contract,
exactly like `AlpacaSource.daily_snapshot` today). Grouped as one composite capability `earnings`:

```python
def earnings_known(self, symbol: str, as_of: Date) -> list[EarningsFact]: ...      # filing_date <= as_of
def earnings_calendar(self, as_of: Date) -> list[EarningsCalendarEntry]: ...       # known_asof  <= as_of
def earnings_available(self) -> bool: ...   # False = earnings artifact MISSING (tri-state, like corp)
```

`earnings_available()` mirrors `corp_actions_available()`'s tri-state MISSING seam: it distinguishes
"checked, nothing reported" from "no earnings backend at all", so a future guard can fail-closed on
absence rather than silently reading empty as "no upcoming earnings".

### Wiring across the existing sources (all in `alpha/data/*`; none in TCB except firewall.py)

| Source | `earnings_known` / `earnings_calendar` | `earnings_available` |
|---|---|---|
| `FakeSource` | in-memory (new `earnings=`/`earnings_calendar=` ctor params) | flag (default False; True iff earnings passed) |
| `GuardedSource` | `guard.check(as_of)` then delegate (mirrors `corporate_actions_known`) | date-independent passthrough (getattr default **False** — absent ⇒ MISSING, the fail-*closed* default; note this differs from corp's default-True legacy-inner posture and why) |
| `CompositeSource` | route to the `earnings`-group backend | route to the `earnings`-group backend |
| `AlpacaSource` | `NotImplementedError` (no Alpaca earnings feed) | `False` (no earnings feed present) |
| `SnapshotSource` | read `PITStore` earnings fixtures, filter symbol + PIT | `store.has_earnings()` |
| `EdgarSource` (new) | live EDGAR facts / derived calendar | `True` (live feed always checkable) |

`CompositeSource`: add `"earnings"` to `_CAPABILITIES`; the three methods route via
`_route("earnings")`. A composite with no earnings override falls to base → base (alpaca) raises
`NotImplementedError` → the pure-swap contract holds through the composite by delegation (identical to
the corp path). P5 consume-path later wires `make_composite_source(base, {"earnings": EdgarSource(...)})`.

### EDGAR-facts backend — `alpha/data/edgar.py`

`EdgarSource` implements **only** the `earnings` group; every other Protocol method is a
`NotImplementedError` stub (earnings-only backend, composed for that group — matches "full Protocol or
NotImplementedError"). Live access via a stdlib-`urllib` `_get_json(url)` seam copied from
`AlpacaSource._get_json` (fixed SEC host, typed HTTP/URL errors → actionable `RuntimeError`), so it is
**fully offline-testable by mocking `_get_json`** — zero live calls, zero keys in tests. SEC fair-access
requires a descriptive `User-Agent`: read `ALPHA_EDGAR_USER_AGENT` (sensible default; never fails at
construction, so `make_source("edgar")` works keyless in the P3 conformance test — the UA only matters on
an actual fetch).

**EDGAR endpoints & mapping (`data.sec.gov`, no key):**
- **Facts:** `/api/xbrl/companyconcept/CIK{cik10}/us-gaap/{concept}.json` → `units → {UNIT: [{start, end,
  val, fy, fp, form, filed, frame}, …]}`.
  - EPS concept: `EarningsPerShareDiluted` (fallback `EarningsPerShareBasic`).
  - Revenue concept, tried in order: `RevenueFromContractWithCustomerExcludingAssessedTax` →
    `Revenues` → `SalesRevenueNet` (schema drifted across years).
  - Map each datapoint: `filed → filing_date` (PIT key), `end → period_end`, `fy`+`fp` → `fiscal_period`
    (`"{fy}{fp}"`, `fp="FY"` for annual), `val → actual_{eps|revenue}`, `form → form`. Merge EPS+revenue
    by `(fy, fp, filed)` into one `EarningsFact`. `estimate_*`/`*_surprise` = `None` (EDGAR has no
    consensus). `source="edgar"`.
- **Calendar (derived):** past entries from the distinct filing dates (each `is_confirmed=True`,
  `expected_date=known_asof=filing_date`, `source="edgar"`) + one naive forward estimate
  (`is_confirmed=False`, `source="edgar_estimate"`).
- **CIK resolution:** EDGAR keys by zero-padded CIK, not ticker. `EdgarSource(cik_map=…)` accepts an
  injected `{TICKER: cik}` map (tests inject it — no network); a live path lazily fetches
  `https://www.sec.gov/files/company_tickers.json` via the same seam and caches it. An unknown ticker →
  empty result (no crash).

### Registry — `alpha/data/registry.py`

- `_build_edgar(*, pit_root=None) -> EdgarSource()` and register `"edgar"` in `_SOURCES` so
  `ALPHA_DATA_COMPOSITE=earnings=edgar` works end-to-end and the P3 `sorted(_SOURCES)` conformance
  parametrization auto-covers it (EdgarSource exposes a callable `corp_actions_available` stub → the
  callability assertion passes; the method itself is never routed to EDGAR under composition).
- `make_composite_source` already accepts instances + names → no change needed for code-level wiring.
- `make_source`'s default (`alpaca`) + RAW-return unchanged; default path byte-identical (pinned).

### Offline persistence — `alpha/data/pit_store.py` + `SnapshotSource`

`PITStore`: `put_earnings(facts)` / `get_earnings()` / `has_earnings()` (file `earnings_facts.parquet`)
and `put_earnings_calendar(entries)` / `get_earnings_calendar()` (file `earnings_calendar.parquet`),
using the frame converters (iso-dates on write, parse on read — mirrors `put/get_corp_actions`).
`has_earnings()` reflects the facts artifact (the primary; calendar optional). `SnapshotSource` serves
earnings from these fixtures. **Capture wiring** (`capture_window` persisting live EDGAR earnings +
`CHECKSUMS`) is intentionally deferred to the consume-path step (see below) — this task makes the store
*able* to hold fixtures (tests build them directly, like every offline PITStore test).

## PIT-guard tests (the acceptance core) — `tests/data/`, `tests/features/`

Mirroring `tests/data/test_corp_actions.py` + `test_composite.py` style, all offline/keyless:

1. **`test_earnings.py`** — `known_earnings` filters on `filing_date` not `period_end`: a fact whose
   `period_end` ≤ as_of but `filing_date` > as_of is **INVISIBLE** (the core no-lookahead assertion);
   `known_calendar` filters on `known_asof`; a restatement (same period, later `filing_date`) is invisible
   until its own filing_date; frame⇄model round-trips.
2. **`test_edgar.py`** — with `_get_json` monkeypatched to canned EDGAR payloads: EPS+revenue merge by
   period; `filed → filing_date` PIT key; revenue concept fallback order; unknown ticker → empty;
   derived calendar (past `is_confirmed=True` + one `edgar_estimate`); a fact filed after as_of is
   invisible through `earnings_known`; every non-earnings method raises `NotImplementedError`; an HTTP
   error surfaces an actionable `RuntimeError`.
3. **`test_source.py` / `test_composite.py` additions** — `FakeSource` earnings round-trip +
   `earnings_available` flag; `GuardedSource` blocks a future `as_of` on `earnings_known`/`_calendar` and
   passes `earnings_available` through (default-False when absent); `CompositeSource` routes `earnings`
   to the earnings backend while bars/snapshot stay on base; an un-overridden earnings capability falls to
   base and raises `NotImplementedError` (pure-swap); unknown-capability `ValueError` unchanged.
4. **`test_snapshot_source.py` / `test_pit_store.py` additions** — put→get earnings round-trip;
   `has_earnings()` tri-state (absent=False, present-even-empty=True); `SnapshotSource.earnings_known`
   PIT + symbol filter; `earnings_available` reflects artifact presence.
5. **`test_registry.py` addition** — `make_source("edgar")` is an `EdgarSource`; `ALPHA_DATA_COMPOSITE=
   earnings=edgar` composes; default path still `AlpacaSource` (byte-identical pin); the P3 conformance
   parametrization now includes `edgar` and stays green.
6. **`tests/features/test_earnings.py`** — `days_to_earnings` / `has_upcoming_earnings` (T-3 boundary:
   exactly 3 days ⇒ True at default) / `next_earnings` skips past dates / `latest_actual` picks the
   restatement after its filing_date; all return `None`/`False` cleanly with an empty calendar
   (default-off byte-identical).

## Not built here (consume-path activation — the SEPARATE next step)

Deliberately out of this task's footprint (a parallel agent owns `alpha/eval`; guard/doctrine wiring is a
later step). Reported for the next builder:

- **No guard veto / doctrine activation.** `earnings_gap_discipline.rule` staying a veto (incomplete-
  checklist within T-3 ⇒ drop) is NOT wired — no `alpha/guard`, `alpha/refine`, `alpha/agent`, `seeds`
  touched. This feed only makes `days_to_earnings` / `latest_actual` *computable*.
- **No per-candidate state field.** Threading `days_to_earnings` onto the per-symbol screen/candidate
  state (so a package can show "reports in N days") lives in `alpha/universe`/`alpha/agent`, out of
  footprint. The feature helpers are provided; the field-threading is consume-path.
- **No `capture_window` earnings wiring** (+ its `CHECKSUMS` line) — the live daily producer persisting
  EDGAR earnings into the PITStore is consume-path; the store method exists, unused by capture for now.
- **No thesis-card pre-registered expectation.** §2.4's *pre-registered surprise* is the card's own
  expectation, an agent/harness artifact; this feed supplies the *actual* + (vendor) *consensus* legs only.
- **Vendor calendar/estimate backend** (confirmed forward dates, bmo/amc, analyst consensus → real
  `estimate_*`/surprise) is offline-stubbed by the model shape + `source="vendor"`; a concrete vendor
  adapter is a later P5 sub-item on the same `earnings` seam.

## Consequences

- Earnings lands as one composite backend (`{"earnings": EdgarSource(...)}`) + one capability group + PIT
  primitives + feature helpers, without touching the base vendor or the firewall — the P4 promise.
- The growth doctrine's only hard data gap becomes *computable*; flipping it into a live guard/doctrine
  gate is the next, separately-scoped step.
- `filing_date` (facts) and `known_asof` (calendar) join `announce_date` as the codebase's third and
  fourth documented lookahead-safe availability keys — same conservative "can only lag, never lead" argument.
</content>
</invoke>
