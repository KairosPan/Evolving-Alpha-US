# Evolving-Alpha-US — Roadmap

The single forward-looking backlog: **what's left**, prioritized. Sibling to `docs/PROJECT_STATE.md`,
which records **what's built** (the append-only status log).

**Discipline (avoid drift):** every item lives in exactly one place. Not-yet-done → here. Done → moved
out of here and recorded in `docs/PROJECT_STATE.md`. When an item ships, delete it from this file.

Status as of 2026-06-22: `main` @ `7945672`, 413 tests green. Alpaca data source is live-verified and
vendor-swappable (`ALPHA_DATA_SOURCE`).

---

## 1. Next (highest leverage, doable now)

- ✅ **Render the empirical HCH-vs-Hexpert verdict** (2026-06-22) — DONE. Live temp=0 run (DeepSeek for
  both agent + Refiner) over a real Alpaca Q1-2026 PIT window. **Verdict = `flat` (parity)** in both the
  production posture (screen ON) and the raw-skill diagnostic (screen OFF) — HCH ≈ Hexpert, HCH leaning
  marginally positive but inside the noise band; the capability breaker froze HCH the moment it slipped.
  Full numbers + method + caveats: `docs/findings/2026-06-22-us-hch-vs-hexpert-verdict.md`.
- [ ] **Recalibrate `GCycle` for the US tape (frontside / follow-through).** The verdict run surfaced a
  real A-share→US transfer gap: GCycle's `follow_through_rate ≥ 0.4` frontside test is the **连板
  (consecutive limit-up)** signature — abundant in a 10%-limit market, structurally rare in the US, so
  ~35/59 days read "distribution" (backside) → the immutable `no_chase_risk_off` veto suppresses ~all new
  longs → the production-posture verdict is thin-by-construction. Recalibrate the phase thresholds / the
  frontside definition against US data (the Refiner is meant to calibrate these vs the oracle in US-2; a
  manual US prior is the faster first step) so the production posture can trade. See the findings doc §4.

## 2. Data-source layer (pluggable; mechanism shipped 2026-06-22)

Spec: `docs/superpowers/specs/2026-06-22-multi-source-switching-design.md` (Future work section).

- [ ] **A real second vendor** (Polygon / Tiingo) for **2016+ history** — Alpaca's free IEX bars only reach
  ~2021. Implement the `MarketDataSource` Protocol + register one line in `alpha/data/registry.py`. Own spec.
- [ ] **`CompositeSource`** (per-capability composition) — delegate each Protocol method to a different
  backend. The natural home for the real enrichment feeds in §3. Own spec.
- [ ] **Fallback/redundancy decorator** — primary + backup source, auto-failover.
- [ ] **A validated `DataConfig` object** — only if per-source constructor params proliferate.

## 3. Real data feeds (mechanisms wired; live ingestion deferred)

The schema + consume-path for each of these is already in place (offline placeholders); only real ingestion
is missing. Best delivered as `CompositeSource` backends (§2).

- [ ] **FINRA short-interest** ingestion (`short_interest` / `days_to_cover` consume-path wired).
- [ ] **Options-flow** + **social-sentiment** feeds (`gamma_squeeze` / `social_euphoria_top` consume-paths
  wired via the `depends_on` machinery).
- [ ] **EDGAR/SEC offerings feed** for dilution (offline dilution mechanism + schema in place) — plus the
  dilution-filing **withdrawal/expiry lifecycle** (today: any announced ATM/shelf/offering vetoes forever).
- [ ] **Float feed** → **float-based L3 sizing** (`size_tier` is wired; share-count sizing off float needs it).

## 4. Eval / methodology (gate-non-blocking, §10)

- [ ] **Purged & embargoed cross-validation.**
- [ ] **Regime-stratified eval.**
- [ ] **Hcredit (C4) ablation arm.**

## 5. Larger architecture

- ✅ **L3 correlation netting activated** (2026-06-22) — the agent now emits a per-candidate
  `narrative` (sympathy/theme key); `size_decision` nets same-narrative picks to one bet and surfaces
  `total_exposure` + `capped` (the "one correlated bet" doctrine is now executable + shown on the
  console). **Still open:** a true **per-narrative-line regime read** (a per-line `GCycle` vs today's
  global one) needs theme-level market breadth we don't have offline — deferred until a theme/sector
  feed lands (a §3-style data source).
- [ ] **Intraday path**: real LULD halts / halt-count (tick feed), **MWCB / `Breaker` portfolio wiring**
  (P&L state machine + index-crash monitor), and **intraday fill-feasibility** (size-at-offer; the
  `eval/fill` module + per-candidate `taboo_check` are deferred for the same reason).
- [ ] **Master-dispatch `G` sub-agents** (keeps the `G`-pass a reserved no-op today).
- [ ] **Keep-last-K checkpoint pruning.**

## 6. Web console (`alpha_web`) — follow-ups (the read-only console shipped 2026-06-22)

The "Regime Instrument" console (FastAPI + Jinja2 + HTMX) is built, reviewed, and its data-wiring
follow-ups are **all done** — every console page now reads real artifacts a run produced:

- ✅ **Decision store + browse** — `alpha/eval/decision_store.py::DecisionStore` (atomic by-date JSON) +
  `scripts/save_decisions.py` (act-only producer) + `/decisions` date-picker (`ALPHA_WEB_DECISIONS_DIR`).
- ✅ **`run_verdict.py --json` + verdict store + browse** — `comparison_to_view()` dumps the console
  view dict; `alpha/eval/verdict_store.py::VerdictStore` + `/verdict` run-picker (`ALPHA_WEB_VERDICTS_DIR`).
- ✅ **Evolution / edit-log view** — `scripts/save_evolution.py` dumps the Refiner's `EditRecord`
  trajectory; the `/evolution` page renders the timeline (`ALPHA_WEB_EVOLUTION`).

Optional future polish (not blocking): a live daily production loop that writes the stores
automatically (instead of the on-demand producer scripts); HTMX-swap the date/run pickers; auth +
non-localhost serving if it ever leaves the desk.

## 7. Known tradeoffs / review leftovers (accepted — no action planned)

- **M3** (review 2026-06-22): a `worthless_removal` delist whose `process_date == entry_day` is skipped by
  `ReturnOracle._delisted_between`'s strict `ex_date > entry_day`. Accepted — bar-disappearance is the
  primary not-yet-processed-delist signal. Listed so it isn't silently rediscovered.
- **M2 hint scope** (review 2026-06-22, addressed): a corp-actions fetch failure during `capture_window`
  still leaves a partial capture (bars persisted, no `corp_actions.parquet`); `_get_json` now raises an
  actionable error, and `capture_window` is idempotent (re-run completes it).
