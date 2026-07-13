# Design: P5b — FINRA short interest + EDGAR offerings lifecycle (P5's 2nd & 3rd real feeds)

- **Date:** 2026-07-13
- **Status:** Draft (P5b — two of P5's remaining real feeds, following the P5a earnings template)
- **Scope:** medium — two new data-model modules + two new source capability groups
  (`short_interest`, `offerings`) on the `MarketDataSource` Protocol, two live backends behind a
  stdlib-`urllib` `_get_json` seam (offline-testable by mocking that one method), offline PITStore
  backends, and — for offerings — a source-agnostic **dilution-overhang lifecycle reducer** that lets a
  withdrawn/expired shelf STOP vetoing as of its own lifecycle date. No firewall change (TCB untouched);
  no consume-path wiring (guard veto / `depends_on` skill activation / capture is a SEPARATE later step —
  §"Not built here").
- **Builds on:** `2026-07-13-p4-composite-source-design.md` (the CompositeSource per-capability seam) and
  `2026-07-13-p5a-earnings-feed-design.md` (the template these two feeds copy method-for-method).
- **Design input:** kairos-mining §3 "Dilution lifecycle as typed update events" — `updates_since`-shaped
  typed events, each keyed on its own announce/process date (PIT); keep today's veto-forever as the
  explicit fail-closed no-connector default.

## Context

Two P5 feeds land here, each as a CompositeSource backend composed for one capability group:

1. **FINRA short interest** (`short_interest` / `days_to_cover`) — the data prerequisite that activates the
   dormant `short_squeeze` skill via `Skill.depends_on` (seeds/skills.json:
   `depends_on: ["short_interest", "days_to_cover"]`).
2. **EDGAR/SEC offerings + withdrawal/expiry lifecycle** — today ANY announced ATM/shelf/offering vetoes
   **forever** (`alpha/data/corp_actions.py::has_dilution_filing`). This feed adds typed offering
   lifecycle events so a **withdrawn or expired** shelf stops vetoing as of its lifecycle date — while
   veto-forever stays the explicit fail-closed default when there is no lifecycle data.

## PIT key choices — the load-bearing decisions

The firewall (CLAUDE.md PIT firewall; `alpha/data/firewall.py`, TCB-pinned) requires every dated artifact
to key on a **lookahead-safe availability date** — the day the fact became knowable to us, never the day
the underlying event is *dated*. `announce_date := process_date` (corp actions) and `filing_date` /
`known_asof` (earnings, P5a) are the precedents. P5b adds two more:

### Short interest → `publication_date` (the FINRA dissemination date), NOT the settlement date

FINRA collects each security's short position as of a bi-monthly **settlement date** (mid-month and
end-of-month), then **disseminates** it roughly 8 business days later on a fixed public schedule. The
settlement-date snapshot describes a position in the past, but you could not have *acted* on it until it
was published. So:

- **PIT key = `publication_date`** (FINRA's dissemination date). `settlement_date` is carried as
  **informational only** — it is explicitly NOT the PIT key, exactly as `announce_date` documents
  `process_date` and `period_end` documents nothing.
- **Conservative-never-leaks argument** (same shape as `process_date`/`filed`): the dissemination date can
  only **lag** the settlement it describes, never precede it, and is the earliest day the datapoint is
  retrievable. Keying on it never leaks the future. (A settlement-date key would leak ~8 trading days of
  hindsight — the classic short-interest backtest trap.)
- `FinraSource` prefers a dissemination-date field on the raw record when present; else it derives the
  publication date from the settlement date by a **calendar-day cushion chosen to provably exceed FINRA's
  ~8-business-day dissemination in any holiday window** (8 business days spans at most ~14 calendar days
  even across the Christmas/New-Year double-holiday span; the default cushion is 16 days, constructor-
  overridable). The derived key is therefore ALWAYS `>=` the true dissemination — never early (a leak),
  only conservatively late (a safe under-claim). A plain `settlement + N` business-day count that skips
  only weekends would land *earlier* than the true dissemination in a holiday-dense window, so the cushion
  is calendar-day and deliberately generous.

### Offering lifecycle events → each event's OWN `process_date`

Each lifecycle transition (announce / effective / withdrawn / expired) is a separate typed event keyed on
the day THAT transition became knowable — its EDGAR filing/index date (or, for a Rule-415 shelf expiry,
the scheduled expiry date itself). A `withdrawn` event keyed on the RW-filing date lifts the veto exactly
then and no earlier; an `announce` keyed on the S-3 filing date starts it. This is the `updates_since`
append-only-log shape from kairos-mining §3: the feed is a log of typed updates; the *current* overhang
state is a fold over the events known by `as_of`.

## Data models

Both new modules are frozen Pydantic (`ConfigDict(frozen=True)`, matching `MarketState`/`EarningsFact`),
PIT-keyed, siblings of `corp_actions.py` / `earnings.py`, so `source.py` stays focused on the Protocol.

### `alpha/data/short_interest.py`

```python
class ShortInterest(BaseModel):        # one bi-monthly FINRA short-interest observation, PIT-keyed on publication
    model_config = ConfigDict(frozen=True)
    symbol: str
    settlement_date: Date              # position measured as-of — INFORMATIONAL, *not* the PIT key
    publication_date: Date             # PIT KEY — FINRA dissemination date; knowable-as-of
    shares_short: float                # current short position (shares)
    avg_daily_volume: float | None = None
    days_to_cover: float | None = None # shares_short / avg_daily_volume (FINRA supplies "daysToCover")
    shares_short_prior: float | None = None  # previous settlement's position (change% context)
    percent_of_float: float | None = None    # shares_short / float — needs the (deferred) float feed; else None
    source: str | None = None          # "finra" | "snapshot"
```

- `known_short_interest(records, as_of) -> list[ShortInterest]` — `publication_date <= as_of`.
- Frame ⇄ model converters `si_to_frame` / `si_from_frame` with a `SI_COLUMNS` constant (dates
  iso-serialized on write, parsed on read — the `PITStore.put/get_corp_actions` idiom).
- **`percent_of_float` is the cross-feed seam.** `MarketStock.short_interest` is documented as "% of float
  (0-100)"; FINRA gives shares-short + days-to-cover but NOT percent-of-float (that needs float / shares
  outstanding). So `days_to_cover` maps straight through, but the `short_interest` leg is populated only
  when the **deferred float feed** supplies a float — i.e. `short_squeeze` (which `depends_on` BOTH signals)
  fully activates when short interest AND float are both present. Reported, not built here.

### `alpha/data/offerings.py`

```python
OFFERING_EVENTS = ("announce", "effective", "withdrawn", "expired")   # the lifecycle transitions
_CLOSED_EVENTS  = frozenset({"withdrawn", "expired"})                 # terminal -> veto lifts

class OfferingEvent(BaseModel):        # one typed lifecycle transition of one offering, PIT-keyed on its own date
    model_config = ConfigDict(frozen=True)
    symbol: str
    offering_id: str                   # groups one offering's events across its lifecycle (EDGAR accession/file no.)
    event: str                         # one of OFFERING_EVENTS
    kind: str                          # dilution kind: "atm" | "shelf" | "offering" (corp_actions.DILUTION_KINDS)
    process_date: Date                 # PIT KEY — when THIS event became knowable (EDGAR filing / expiry date)
    form: str | None = None            # provenance: "S-3" | "424B5" | "RW" | "EFFECT" | ...
    source: str | None = None          # "edgar" | "snapshot"
```

- `known_offering_events(events, as_of) -> list[OfferingEvent]` — `process_date <= as_of`.
- `offering_states(events, symbol, as_of) -> dict[str, str]` — the **reducer**: per `offering_id`, fold
  the events known by `as_of`; state is `"closed"` iff any known event is `withdrawn`/`expired` (terminal),
  else `"active"`. A close event with no known announce is defensively `"closed"` (no veto).
- `is_dilution_overhang(events, symbol, as_of) -> bool` — True iff any offering reduces to `"active"`. This
  is the lifecycle-aware successor to `has_dilution_filing`: a withdrawn/expired shelf drops out as of its
  own lifecycle date; an announce with no close event still vetoes (veto-forever until a close arrives).
- Frame ⇄ model converters `events_to_frame` / `events_from_frame` + `OFFERING_COLUMNS`.

### The veto-forever fail-closed default (unchanged, re-documented)

`corp_actions.py::has_dilution_filing` STAYS the default when the offerings lifecycle feed is **absent**:
any announced dilution kind vetoes forever (no withdrawal/expiry data ⇒ conservatively assume still
active). Its docstring is updated to name the relationship (the lifecycle-aware refinement is
`offerings.is_dilution_overhang`, used only when the feed is present). The consume path chooses: feed
present ⇒ `is_dilution_overhang`; feed absent ⇒ `has_dilution_filing`. No-connector = conservative =
veto-forever. This is the "safety-only-tightens / conservative-when-blind" posture: lifecycle data can
only *lift* a veto that it can prove is closed; it never introduces a new veto the old path missed.

## Source capabilities — the `short_interest` and `offerings` groups

Four methods added to `MarketDataSource` (`alpha/data/source.py`), two **OPTIONAL** capability groups (a
source without them raises `NotImplementedError` on the data methods — the pure-swap contract, exactly
like `daily_snapshot` on `AlpacaSource`):

```python
def short_interest_known(self, symbol: str, as_of: Date) -> list[ShortInterest]: ...  # publication_date <= as_of
def short_interest_available(self) -> bool: ...          # False = artifact MISSING (fail-closed)
def offering_events_known(self, symbol: str, as_of: Date) -> list[OfferingEvent]: ... # process_date <= as_of
def offerings_available(self) -> bool: ...               # False = artifact MISSING (fail-closed)
```

Both `_available()` methods mirror `corp_actions_available()`/`earnings_available()`'s tri-state MISSING
seam: they distinguish "checked, nothing found" from "no backend at all", so a future guard can fail-closed
on absence rather than reading empty as "no short interest / no overhang".

### Wiring across the existing sources (all in `alpha/data/*`; none in TCB except firewall.py)

| Source | `*_known` | `short_interest_available` / `offerings_available` |
|---|---|---|
| `FakeSource` | in-memory (new `short_interest=` / `offering_events=` ctor params) | flag (default False; True iff passed) |
| `GuardedSource` | `guard.check(as_of)` then delegate (mirrors `corporate_actions_known`) | date-independent passthrough (getattr default **False** — absent ⇒ MISSING, fail-*closed*, like earnings) |
| `CompositeSource` | route to the `short_interest` / `offerings`-group backend | route to that backend |
| `AlpacaSource` | `NotImplementedError` (no such feed) | `False` |
| `SnapshotSource` | read `PITStore` fixtures, filter symbol + PIT | `store.has_short_interest()` / `has_offering_events()` |
| `FinraSource` (new) | live FINRA short interest | `short_interest_available` True; everything else raises |
| `EdgarOfferingsSource` (new) | live EDGAR offering lifecycle | `offerings_available` True; everything else raises |

`CompositeSource`: add `"short_interest"` and `"offerings"` to `_CAPABILITIES`; the four methods route via
`_route(...)`. An un-overridden group falls to base → base raises `NotImplementedError` → the pure-swap
contract holds through the composite by delegation (identical to the corp/earnings paths).

### Live backends behind the `_get_json` seam (offline-testable)

Both copy `EdgarSource`'s stdlib-`urllib` `_get_json(url)` seam (fixed host, typed HTTP/URL errors →
actionable `RuntimeError`), so they are **fully offline-testable by mocking `_get_json`** — zero live
calls, zero keys in tests. Each implements ONLY its own capability group; every other Protocol method is a
`NotImplementedError` stub with a callable `corp_actions_available` (so the P3 `sorted(_SOURCES)`
conformance parametrization stays green — the method is never routed to them under composition).

- **`FinraSource` (`alpha/data/finra.py`).** FINRA publishes a public bi-monthly consolidated short
  interest product. The concrete dissemination endpoint/auth is a **documented live-integration stub**
  (FINRA's API shape is public; the exact URL/OAuth is wired at live time); the built+tested core is the
  record→`ShortInterest` mapping, the `settlement_date`→`publication_date` PIT keying (prefer a record
  dissemination field; else the conservative calendar cushion above), the `days_to_cover` passthrough, and
  the symbol/PIT filter. Zero-valued numeric fields (a fully-covered short, zero days-to-cover) are
  preserved as `0.0`, not dropped as missing. Reads a descriptive `User-Agent` from `ALPHA_FINRA_USER_AGENT`
  like `EdgarSource`.
- **`EdgarOfferingsSource` (`alpha/data/edgar.py`, sibling of `EdgarSource`).** `updates_since`-shaped over
  EDGAR's submissions feed (`data.sec.gov/submissions/CIK{cik10}.json` — recent filings: form + filing
  date + accession). Maps form types → lifecycle events, each keyed on its filing date (`process_date`):
  registration/prospectus (S-1/S-3/F-1/F-3/424B\*) → `announce` (kind shelf/offering); `EFFECT` →
  `effective`; `RW`/`AW` → `withdrawn`; a Rule-415 shelf expiry → `expired` with `process_date` anchored
  to the offering's **initial EFFECT date + 3y** (Rule 415(a)(5) runs the window from effectiveness;
  fallback = the filing date for an automatic/WKSI shelf effective on filing — anchoring on the filing for
  a non-automatic S-3 would lift the veto weeks-to-months early). A deterministic scheduled event —
  knowable in advance but only *lifting* the veto once the date passes, exactly like a corp action's future
  `ex_date` staying "pending". The exact
  form taxonomy is a documented design surface; the mapping + PIT keying + the withdrawal/expiry paths are
  built and tested against mocked submissions payloads. Injected `cik_map` (tests) / lazy
  `company_tickers.json` (live), like `EdgarSource`.

### Registry — `alpha/data/registry.py`

- `_build_finra` → `FinraSource()`, `_build_edgar_offerings` → `EdgarOfferingsSource()`, registered as
  `"finra"` / `"edgar_offerings"` in `_SOURCES` so `ALPHA_DATA_COMPOSITE=short_interest=finra,
  offerings=edgar_offerings` works end-to-end and the P3 conformance parametrization auto-covers them.
- `make_composite_source` already accepts instances + names → no change for code-level wiring.
- `make_source`'s default (`alpaca`) + RAW-return unchanged; default path byte-identical (pinned).

### Offline persistence — `alpha/data/pit_store.py` + `SnapshotSource`

`PITStore`: `put_short_interest` / `get_short_interest` / `has_short_interest`
(`short_interest.parquet`) and `put_offering_events` / `get_offering_events` / `has_offering_events`
(`offering_events.parquet`), via the frame converters (iso-dates on write, parse on read — mirrors
`put/get_corp_actions`). `has_*()` is the tri-state MISSING seam (True even for an empty frame, False only
when absent). `SnapshotSource` serves both from these fixtures. **Capture wiring** (`capture_window`
persisting live FINRA/EDGAR-offerings data + `CHECKSUMS`) is deferred to the consume-path step (see below)
— this task makes the store *able* to hold fixtures (tests build them directly, like every PITStore test).

## PIT-guard tests (the acceptance core) — `tests/data/`, all offline/keyless

Mirroring `tests/data/test_corp_actions.py` + `test_earnings.py` + `test_edgar.py` + `test_composite.py`:

1. **`test_short_interest.py`** — `known_short_interest` filters on `publication_date` not
   `settlement_date`: an observation whose `settlement_date <= as_of` but `publication_date > as_of` is
   **INVISIBLE** (the core no-lookahead assertion); frame round-trips (NaN optionals → None); frozen model.
2. **`test_finra.py`** — `_get_json` monkeypatched to canned FINRA payloads: record→`ShortInterest`
   mapping; `settlement→publication` PIT keying; `days_to_cover` passthrough; an observation published
   after as_of is invisible through `short_interest_known`; symbol filter; unknown symbol → empty; every
   non-short-interest method raises `NotImplementedError`; an HTTP error surfaces an actionable `RuntimeError`.
3. **`test_offerings.py`** — `known_offering_events` PIT on `process_date`; the reducer:
   announce ⇒ overhang True; announce **+ later withdrawn** ⇒ overhang False **as of the withdrawal
   process_date** and still True the day before (the lifecycle core); announce + expired ⇒ same via expiry;
   a withdrawn event alone ⇒ not an overhang; multi-offering (one active, one closed) ⇒ still an overhang;
   frame round-trips.
4. **`test_edgar.py` additions** — `EdgarOfferingsSource` over a mocked submissions payload: S-3 →
   `announce`, RW → `withdrawn`, the reducer flips off as of the RW filing date; a Rule-415 expiry event is
   emitted at effective+3y and lifts the veto only once as_of passes it; a filing dated after as_of is
   invisible through `offering_events_known`; non-offerings methods raise `NotImplementedError`.
5. **`test_source.py` / `test_composite.py` additions** — `FakeSource` short-interest + offerings
   round-trip + `*_available` flags; `GuardedSource` blocks a future `as_of` on both `*_known` and passes
   `*_available` through (default-False when absent); `CompositeSource` routes each group to its backend
   while bars/snapshot stay on base; an un-overridden group falls to base and raises `NotImplementedError`
   (pure-swap); `"short_interest"`/`"offerings"` ∈ `_CAPABILITIES`.
6. **`test_snapshot_source.py` / `test_pit_store.py` additions** — put→get round-trips; `has_*()`
   tri-state (absent=False, present-even-empty=True); `SnapshotSource` PIT + symbol filter; `*_available`
   reflects artifact presence.
7. **`test_registry.py` additions** — `make_source("finra")`/`("edgar_offerings")` construct keyless;
   `ALPHA_DATA_COMPOSITE=short_interest=finra,offerings=edgar_offerings` composes; default path still
   `AlpacaSource` (byte-identical pin); the P3 parametrization includes the two new names and stays green.

## Not built here (consume-path activation — the SEPARATE next step)

Deliberately out of this task's footprint (`alpha/data/*` + `tests/data/*` only; a parallel A6 batch owns
`scripts/` + `alpha/llm`). Reported for the next builder:

- **`short_squeeze` activation wiring.** `Skill.depends_on` is enforced in `alpha/agent/prompt.py`
  (`_available_signals` reads optional-enrichment fields present on `MarketStock`). To activate
  `short_squeeze`, the consume path must populate `MarketStock.short_interest` (% of float) and
  `.days_to_cover` from the FINRA feed keyed on `publication_date` — done in `alpha/universe`/`alpha/state`
  (out of footprint). `days_to_cover` maps straight from `ShortInterest.days_to_cover`; the
  `short_interest` (% of float) leg needs the **deferred float feed** for `percent_of_float` (both feeds
  present ⇒ full activation).
- **Offerings veto swap.** `alpha/guard/screen.py:152` calls `has_dilution_filing(corp, symbol, as_of)`.
  The lifecycle swap — feed present ⇒ `offerings.is_dilution_overhang(events, symbol, as_of)`; feed absent
  ⇒ unchanged `has_dilution_filing` (veto-forever) — is `alpha/guard`, out of footprint. The data-layer
  primitives + fail-closed default are provided; the branch is consume-path.
- **`capture_window` persistence** (+ `CHECKSUMS` lines) — the live daily producer persisting FINRA short
  interest + EDGAR offering events into the PITStore is `scripts/`, out of footprint (and A6-adjacent). The
  store methods exist, unused by capture for now — identical posture to P5a earnings.
- **Live endpoint/auth finalization.** FINRA's concrete dissemination URL/OAuth and the full EDGAR
  offerings form taxonomy are documented design stubs; the seams are built and mocked. Wiring the real
  endpoints is a live-integration step on the same `_get_json` seam.

## Consequences

- Short interest and the offerings lifecycle each land as one composite backend + one capability group +
  PIT primitives, without touching the base vendor or the firewall — the P4 promise.
- `has_dilution_filing`'s veto-forever becomes a fail-closed **default** rather than the only behavior: with
  the offerings feed present, a withdrawn/expired shelf correctly stops vetoing as of its lifecycle date.
- `publication_date` (short interest) and each offering event's `process_date` join `announce_date`,
  `filing_date`, and `known_asof` as the codebase's documented lookahead-safe availability keys — same
  conservative "can only lag, never lead" argument.
</content>
</invoke>
