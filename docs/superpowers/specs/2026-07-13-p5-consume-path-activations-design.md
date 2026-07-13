# P5 — Feed consume-path activations (short-squeeze / offerings veto swap / capture persistence)

- **Date:** 2026-07-13
- **Status:** design + build (activates the P5b feeds the ingestion arcs shipped DORMANT)
- **Scope:** medium — three additive activations, each byte-identical when its feed is absent.
- **Predecessors (INGESTION shipped, consume-path deferred):**
  `2026-07-13-p5b-shortinterest-offerings-design.md` (FINRA short-interest + EDGAR offerings lifecycle),
  `2026-07-13-p5b-float-feed-design.md` (float feed), `2026-07-13-p5a-earnings-feed-design.md` +
  `2026-07-13-p5b-earnings-consume-design.md` (the earnings feed + its already-shipped consume path —
  the additive pattern this spec copies). The feeds carry their own PIT primitives + source Protocol
  capabilities; this step WIRES them into the decide path, the guard, and capture.

## What the ingestion arcs left dormant

- **`short_squeeze` skill** (`seeds/skills.json` `depends_on: ["short_interest", "days_to_cover"]`) is
  surfaced to the agent only when BOTH signals are live on the universe
  (`alpha/agent/prompt.py::available_data_signals` reads `StockSnapshot` optional fields that are
  non-None for at least one candidate). The FINRA + float feeds shipped, but nothing populated
  `StockSnapshot.short_interest` (% of float) / `.days_to_cover` from them, so the skill stayed dormant.
- **Offerings lifecycle** (`is_dilution_overhang`) shipped as the lifecycle-aware successor to the
  veto-forever `has_dilution_filing`, but `alpha/guard/screen.py` still called only `has_dilution_filing`,
  so a withdrawn/expired shelf could never stop vetoing.
- **Capture** (`scripts/capture_window.py` → `alpha/data/capture.py`) persisted only bars / snapshot /
  calendar / corp actions. The new feeds' PITStore artifacts existed but capture never wrote them, so a
  captured PIT window replayed offline was blind to earnings / short-interest / offerings / float.

## The three activations (each additive / default-off / verdict-neutral)

### 1. `short_squeeze` activation — populate `StockSnapshot.short_interest` (% of float) + `.days_to_cover`

`alpha/features/short_squeeze.py` (new leaf helper, sibling of `alpha/features/earnings.py`):

```python
short_squeeze_signals(short_records, float_records, symbol, as_of) -> (pct_of_float | None, days_to_cover | None)
```

- Inputs are the lists a source's `short_interest_known(symbol, as_of)` / `float_known(symbol, as_of)`
  ALREADY PIT-filtered (`publication_date <= as_of` / `knowable_date <= as_of`) — the helper never
  re-opens a lookahead window, it only picks among what was knowable (the earnings-helper philosophy).
- `days_to_cover` rides straight from the LATEST-published `ShortInterest` (max `publication_date`).
  It needs the short-interest feed ALONE.
- `pct_of_float` = `latest.shares_short / latest_float.free_float × 100` (both in RAW shares → a %),
  computed only when the FLOAT feed also supplies a float (`latest_known_float`, `free_float > 0`).
  So `short_squeeze` (which `depends_on` BOTH signals) fully activates only when short-interest AND
  float are both present; short-interest alone lights `days_to_cover` but leaves `short_interest` None
  → the skill stays dormant (depends_on unmet).

Wiring in `alpha/universe/universe.py` (`build_universe` + `build_trend_template_universe`):
- Read `short_interest_available()` / `float_available()` ONCE before the screen loop.
- Per kept symbol, when short-interest is available, fetch the PIT-filtered feed lists and call
  `short_squeeze_signals`; **prefer the feed value, fall back to the pre-existing snapshot column**
  (`_opt_float(rec.get("short_interest"))` / `days_to_cover`). Feed absent → both flags False → no feed
  read → the fields come from the snapshot columns exactly as today → **byte-identical**.
- The feed reads ride the SAME (Guarded) source the builder already holds; availability-gating means a
  source that raises `NotImplementedError` on the data methods (e.g. `AlpacaSource`) is never called
  (its `*_available()` is False), preserving the pure-swap contract.

### 2. Offerings veto swap — lifecycle-aware `is_dilution_overhang` when the feed is present

`alpha/guard/screen.py::screen_decision`: read `offerings_available()` once (on the fresh
`GuardedSource(AsOfGuard(as_of))`, so the per-symbol `offering_events_known` is PIT-guarded exactly like
`corporate_actions_known`). Per enter-candidate, the `dilution` veto flag becomes:

```python
dilution = (is_dilution_overhang(guarded.offering_events_known(sym, as_of), sym, as_of)
            if offerings_available else has_dilution_filing(corp, sym, as_of))
```

- **Feed absent → `has_dilution_filing` (veto-forever fail-closed default), unchanged / byte-identical.**
- **Feed present → the lifecycle reducer:** an `announce` with no known close still reduces to `active`
  → still vetoes; a `withdrawn`/`expired` event reduces the offering to `closed` → the veto LIFTS **as of
  that event's own `process_date`, and no earlier** (True the day before, False on/after).

**Safety-only-tightens preservation (the property the swap must not break).** The lifecycle view is the
authoritative successor to the corp dilution flag; presence of the feed can only LIFT a veto for which it
holds POSITIVE PROOF of closure (a terminal `withdrawn`/`expired` event). With no proof — no close event,
or the feed absent — it keeps vetoing (conservative-when-blind). It never clears an `active` overhang, and
a symbol with no offering at all is un-vetoed either way (`is_dilution_overhang([]) == has_dilution_filing(∅)
== False`), so the swap introduces no new veto on a clean name. Lifting always requires a dated proof of
closure.

### 3. `capture_window` persistence — the new feeds + CHECKSUMS

`alpha/data/capture.py::capture_window`: after the corp-actions block, for each OPTIONAL feed, gate on the
source's availability (probed defensively via `getattr`, so a source predating a capability — e.g.
`AlpacaSource` lacks `float_available` entirely — is treated as absent, never an `AttributeError`), gather
everything KNOWABLE BY THE WINDOW END across the captured symbols, and persist through the existing PITStore
converters:
- earnings facts (`earnings_known(sym, end)` per symbol) + calendar (`earnings_calendar(end)`, scoped to the
  captured symbols) → `put_earnings` / `put_earnings_calendar`.
- short interest (`short_interest_known(sym, end)`) → `put_short_interest`.
- offering events (`offering_events_known(sym, end)`) → `put_offering_events`.
- float (`float_known(sym, end)`) → `put_float`.

Capturing "as of end" + the SnapshotSource re-filtering each read on the PIT key (`known_*` <= query as_of)
= per-day PIT-correct offline replay, exactly the corp-actions posture. `write_checksums(store.root)` is
already the final call and walks the whole tree, so it AUTOMATICALLY covers every new parquet — no CHECKSUMS
code change needed. Default source (`AlpacaSource`) reports every feed absent → nothing new persisted →
capture output byte-identical.

**theme-breadth is N/A for capture.** `alpha/data/sector_map.py` is a STATIC in-process bootstrap map and
`theme_breadth` is DERIVED at state-build time from the already-captured daily snapshot cross-section + that
map (spec `2026-07-13-p5b-theme-breadth-design.md` §"NOT a new data source"). There is no ingestion feed and
no PITStore artifact to persist; a captured window already reconstructs the theme breadth offline. Recorded
here rather than silently skipped.

## PIT keys (firewall — unchanged; no TCB touched)

Every read keys on the lookahead-safe availability date the feed already documents:
`ShortInterest.publication_date`, `FloatFact.knowable_date`, `OfferingEvent.process_date` (each `<= as_of`).
`firewall.py` is untouched (TCB); the consume path only calls the feeds' existing PIT primitives.

## Additive / default-off + verdict-neutral contract (the proofs)

- **Byte-identical when absent.** Every activation is gated on a feed `*_available()` that is False for a
  bare source: no short-interest feed → `StockSnapshot` fields from the snapshot columns (unchanged); no
  offerings feed → `has_dilution_filing` (unchanged); no feed on capture → nothing new written (unchanged
  capture output, unchanged CHECKSUMS).
- **Arm-symmetric (not neutral-when-present — these are ACTIVATIONS).** Both are byte-identical when the
  feed is absent; when present they legitimately change behaviour, but SYMMETRICALLY across the two verdict
  arms, which wrap the SAME source object (the screen-flag / recall_store symmetry). (a) The short-squeeze
  fields feed ONLY the agent's skill-eligibility menu (`available_data_signals` → prompt), never the L4
  veto and never the eval scorer (scoring reads `symbol`/`pattern` + forward returns) — so they cannot
  change a score directly, and both arms see the same signals. (b) The offerings swap changes only the
  `dilution` veto flag — the guard DROPS a vetoed candidate (never scores it), and both arms read the same
  offering events and drop the same names day-for-day, so `hch_minus_hexpert` stays < 1e-9 (pinned). A
  withdrawn-before-window shelf reduces the eval EXACTLY to the no-feed clean baseline (pinned, non-vacuous).
  (c) Capture is a producer, off the verdict path entirely.
- **Honest eval preserved.** The guard still DROPS vetoed candidates (never annotates); the swap only
  narrows/lifts the drop set with dated proof.

## Footprint & TCB

- New: `alpha/features/short_squeeze.py`.
- Modified (all NON-TCB): `alpha/universe/universe.py`, `alpha/guard/screen.py`, `alpha/data/capture.py`.
- New tests: `tests/features/test_short_squeeze.py`, `tests/universe/test_short_squeeze_activation.py`,
  `tests/guard/test_screen_offerings_swap.py`, `tests/loop/test_p5_offerings_symmetry.py`,
  `tests/data/test_capture_feeds.py`.
- TCB: `tcb.lock` unchanged — none of the four production files is a TCB member; `firewall.py` untouched.

## Deliberately not done (reported to plan)

- **Live endpoints.** FINRA/EDGAR-offerings/float/earnings live backends stay documented `_get_json` stubs
  (their specs); this step wires the CONSUME paths, provably offline against `FakeSource`/`SnapshotSource`.
- **theme-breadth capture** — N/A (derived; see above).
- **The 扛 hold-through earnings veto / disproof-direction branch** — still queued behind a holdings /
  hold-through producer (earnings-consume spec §"defers").
- **float-aware L3 sizing consume wiring** (feed → `StockSnapshot.free_float` in shares) — the float feed
  already refines sizing via the legacy snapshot channel; feeding the RAW-shares float into state is a
  separate state/universe step (float-feed spec §7). This activation populates only the short-squeeze
  denominator, not the sizing float channel.
</content>
</invoke>
