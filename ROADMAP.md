# Evolving-Alpha-US — Roadmap

The single forward-looking backlog: **what's left**, prioritized. Sibling to `docs/PROJECT_STATE.md`,
which records **what's built** (the append-only status log).

**Discipline (avoid drift):** every item lives in exactly one place. Not-yet-done → here. Done → moved
out of here and recorded in `docs/PROJECT_STATE.md`. When an item ships, delete it from this file.

Status as of 2026-06-23: `main` @ `38f0879`, 520 tests green. Alpaca data source is live-verified and
vendor-swappable (`ALPHA_DATA_SOURCE`); the **interactive teaching cockpit** shipped (§6) — the console
is no longer read-only.

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

### Teaching cockpit (the meta-agent channel) — shipped 2026-06-23, follow-ups open

✅ **Interactive teaching cockpit shipped** (`main` @ `38f0879`, subagent-driven build + opus whole-branch
review) — Evolution is now the **home page**: paste text/URL → LLM (Claude, or DeepSeek as refiner)
proposes *directions* → a dry-run *edit queue* against `H=(doctrine,skills,memory)` → accept/reject/comment
per edit → **apply** commits through the same gated meta-tools the autonomous Refiner uses, into a
persistent **live brain** (seeds stay frozen as the `Hexpert` baseline); each round a rollback-able
*session*. Spec: `docs/superpowers/specs/2026-06-23-meta-agent-teaching-cockpit-design.md`. Open
follow-ups (also in spec §11):

- [ ] **Self-learning channel** — the agent's **second learning channel**: a reflection→directions stage
  on top of the Refiner's evidence path, surfaced into the *same* cockpit, so the agent proposes
  evolutions from its **own task runs** (realized-outcome trajectories), not just from human-fed content.
  Teaching (human→agent) ships today; self-learning (agent→itself) is the headline next step. Own
  brainstorm→spec→plan arc.
- [ ] **Image / chart ingestion** (Claude vision) — teach from a screenshot or `复盘` chart; extend the LLM
  client for image content blocks + upload handling.
- [ ] **`tweak` action** — manual inline arg-editing of a proposed edit (no LLM); the spec §8 route table
  lists it, but v1 shipped `accept` / `reject` / `comment→re-propose` + `apply` only.
- [ ] **Auto-resume an in-flight draft on `GET /`** — today a refresh starts a fresh cockpit (drafts persist
  + are browsable); render partials matching `Session.status` and re-validate dangling `target_id`s.
- [ ] **Post-apply red-line lint** — flag a taught skill/lesson whose `taboo`/`entry` contradicts an
  immutable doctrine red-line (only doctrine *text* is write-protected today).
- [ ] **General meta-agent core** — lift teach + self-learn off the trading-specific `doctrine/skills/memory`
  onto a domain-agnostic representation (trading = the first instance).
- [ ] **Branchable named brains** ("aggressive" vs "disciplined") + snapshot retention/pruning.
- [ ] **SSRF IP-range hardening** — **BLOCKING precondition before any non-localhost / multi-user serving.**
  The http(s) **scheme allowlist is DONE** (`38f0879`, closed the `file://` Local-File-Disclosure vector);
  still required: reject private/loopback/link-local ranges + the cloud-metadata IP `169.254.169.254`
  (DNS-rebinding-safe).

## 7. Known tradeoffs / review leftovers (accepted — no action planned)

- **M3** (review 2026-06-22): a `worthless_removal` delist whose `process_date == entry_day` is skipped by
  `ReturnOracle._delisted_between`'s strict `ex_date > entry_day`. Accepted — bar-disappearance is the
  primary not-yet-processed-delist signal. Listed so it isn't silently rediscovered.
- **M2 hint scope** (review 2026-06-22, addressed): a corp-actions fetch failure during `capture_window`
  still leaves a partial capture (bars persisted, no `corp_actions.parquet`); `_get_json` now raises an
  actionable error, and `capture_window` is idempotent (re-run completes it).
