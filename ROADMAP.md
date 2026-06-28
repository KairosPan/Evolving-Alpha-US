# Evolving-Alpha-US — Roadmap

The single forward-looking backlog: **what's left**, prioritized. Sibling to `docs/PROJECT_STATE.md`,
which records **what's built** (the append-only status log).

**Discipline (avoid drift):** every item lives in exactly one place. Not-yet-done → here. Done → moved
out of here and recorded in `docs/PROJECT_STATE.md`. When an item ships, delete it from this file.

Status as of 2026-06-25: `main` pushed to `origin/main` (in sync), 555 tests green. Alpaca data source is
live-verified and vendor-swappable (`ALPHA_DATA_SOURCE`); the teaching cockpit shipped (§6), was **rewritten
as "Sonia" — a standalone meta-agent service** (separate process, `deepseek-v4-pro` text-only, owns the
brain + gated apply; the console is a thin sync HTTP client), then got a **cockpit-hardening + Brain-drawer**
round (HTMX nesting fixes, hard-delete conversations, and a left-rail accordion grouping the six brain
components — see the teaching-cockpit §6 subsection).

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
- ✅ **§6 read-side FLIPPED ON** (2026-06-27) — recall + episode-taboo wired into the live decide path
  (`save_decisions`/`refine_live`) and the verdict harness (read-only `recall_store`, symmetric arms;
  HCH never self-writes mid-verdict). `for_asof(limit=None)` lifted the 50-cap at the two aggregation
  read sites. See `docs/superpowers/plans/2026-06-27-episode-readside-on.md` + `docs/PROJECT_STATE.md`.
- ✅ **Polish trio DONE** (2026-06-27) — (1) **`for_asof` cap audit**: confirmed only 3 production callers
  (recall, taboo, forge), all now pass `limit=None`; documented the no-cap convention in the `for_asof`
  docstring (default-50 = ad-hoc/display only; no production caller relies on it). (2) **`hit_max_iters`**:
  `run_conversation` now returns a fallback `final_text` on budget-exhaustion (the flag stays for
  programmatic detection) so a turn never silently shows empty prose. (3) **conftest**: DRY'd the
  brain/session isolation into one shared `brain_session_isolation` fixture (parent `tests/conftest.py`),
  consumed by symmetric autouse `_isolate_state` fixtures in `tests/web` + `tests/sonia`.
- [ ] **Activity space — inner-loop arena (P-A)** — build `alpha/arena/`: the `ActivitySpace` contract
  (O/A/E/F) + `ToolEnvironment` seam (`InProcessEnv`/`LocalEnv`) + a single dispatch **choke point** with
  capability tiers + the safety membrane. **Data rungs only (R1/R2)**; brain files live OUTSIDE the
  workspace + path-guarded so even a T2 shell can't write `snap.json`. Closes two live-face build gaps:
  wire `conflict_queue` + real provenance on the converse brain-edit path, and enforce `StagedEdit.status`
  (T4 human-confirm). Threads PIT-gated recall into the conversational prompt (+ PIT regression test).
  Specs: `docs/superpowers/specs/2026-06-27-activity-space-arena-design.md` (P-A) +
  `…-2026-06-27-modification-ladder-and-body-axis-design.md` (§8 NOW). Own writing-plans arc.

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
- [ ] **Body axis + code-level reshape (DEFERRED · commercial)** — the kernel `SandboxedEnv`
  (Seatbelt/bwrap/Docker) + writer-sidecar (H read-only to the runtime; brain writes only via the
  `try_apply_op` IPC) + outer supervisor (`BodyManager`) + `try_promote_body`/`BodyLog` +
  propose→fork-verify→rebuild-from-declared-diff + joint `(H-version, body-digest)` change-set rollback,
  unlocking the modification ladder **R3 skill-code → R4 tool-code → R5 runtime → R6 image/OS** in order.
  Gated by the **immutable-TCB** byte-hash pin + mandatory human approval; never autonomous, never on
  `LocalEnv`. A conscious scope-lift of parent spec §1.2. Spec:
  `docs/superpowers/specs/2026-06-27-modification-ladder-and-body-axis-design.md` (§5–§9).

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

### Teaching cockpit (the meta-agent channel) — v1 shipped 2026-06-23, rewritten as "Sonia" service, follow-ups open

✅ **Interactive teaching cockpit shipped** (`main` @ `38f0879`, subagent-driven build + opus whole-branch
review) — Evolution is now the **home page**: paste text/URL → LLM (Claude, or DeepSeek as refiner)
proposes *directions* → a dry-run *edit queue* against `H=(doctrine,skills,memory)` → accept/reject/comment
per edit → **apply** commits through the same gated meta-tools the autonomous Refiner uses, into a
persistent **live brain** (seeds stay frozen as the `Hexpert` baseline); each round a rollback-able
*session*. Spec: `docs/superpowers/specs/2026-06-23-meta-agent-teaching-cockpit-design.md`.

✅ **v2 — "Sonia" standalone meta-agent service shipped** (2026-06-23, `main` @ `fc133e7`, 539 tests;
subagent-driven build + opus whole-branch review + live two-process smoke). The v1 teaching *front* was
replaced by a ChatGPT-style **chat cockpit** talking to **Sonia** — a separate FastAPI process
(`python -m sonia`, :8810, `deepseek-v4-pro` **text-only**) that owns the live brain + gated apply/rollback
+ the conversation thread; `alpha_web` (:8100) is a thin **sync** httpx client (brain read-only). Spec:
`docs/superpowers/specs/2026-06-23-sonia-standalone-meta-agent-service-design.md`. **Sonia-service
follow-ups (non-blocking, from the final review — all bounded by the single-user/localhost threat model):**

- [ ] **Widen Sonia `/chat`'s `try` to include the brain load** — `_brain_store().load()` sits outside the
  `try` that wraps `make_client` + `respond`, so a corrupt `brain.json` would 500 (atomic writes make this
  unlikely; one-line fix).
- [ ] **`edit_action` under `_MUTATION_LOCK`** — the accept/reject route writes session state without the
  lock, while the design says all mutating routes serialize on it (touches only the session JSON, not the
  brain → the race is theoretical on a single-user tool; one-line fix).
- [ ] **File-count / aggregate-size cap in `ingest_attachments`** — each file's extracted text is capped at
  ~50k chars, but the *number* of files is unbounded (abuse-hardening; pairs with the SSRF item below,
  needed before any multi-user serving).
- [ ] **Distinguish "Sonia 404" from "Sonia unavailable" in the console banner** — both surface as one
  `httpx.HTTPError` today, so a stale session/edit id (Sonia returns 404) reads as a service outage; split
  `ConnectError` (down) from `HTTPStatusError` 404 (stale id → "refresh / new chat").

✅ **v3 — cockpit hardening + Brain drawer shipped** (2026-06-24/25, `main` @ `741f290` local, 555 tests;
subagent-driven build + opus whole-branch review = Ready-to-merge/0 Critical/0 Important; **pushed, in sync**).
Fixed an HTMX nesting-bug class (New-chat → `204 + HX-Redirect`, session links → plain `<a href>`; a
3-agent Workflow audited all 32 HTMX interactions, 0 others); added **hard-delete conversations** (per-row
`×` → Sonia owns it, empty-200 `<li>` removal, `SessionStore._path` path-traversal guard); and the
**Brain left-rail accordion drawer** grouping the six brain components — doctrine·memory·workflow·skill·
connector·subagent — with server auto-expand + a vanilla-JS toggle (no HTMX in the rail). Spec:
`docs/superpowers/specs/2026-06-24-brain-drawer-design.md`. **Brain-drawer follow-ups (deferred — UI-first
round shipped only the views; the three NEW components are read-only stubs):**

- [ ] **Real models / stores / seed data for `workflow`, `connector`, `subagent`** — today they are read-only
  stub pages (`brain_stub.html`). Each needs its own meaning + model before anything can populate it. Likely
  one brainstorm→spec→plan round per component type.
- [ ] **Make Sonia EDIT the three new components** — extend `H` + the meta-tools + gated-apply path + the
  Sonia prompt + `edit_log` `target_kind` so teaching can touch workflow/connector/subagent (today Sonia
  edits only doctrine/skills/memory). Blocked on the models above.
- [ ] **Delete-`×` while Sonia is DOWN** swaps the `unavailable` banner into the `<li>` (cosmetic stray
  banner; never-500-safe). Minor polish from the v3 final review.

**Broader meta-agent follow-ups (also in spec §11):**

- [ ] **Self-learning channel** — the agent's **second learning channel**: a reflection→directions stage
  on top of the Refiner's evidence path, surfaced into the *same* cockpit, so the agent proposes
  evolutions from its **own task runs** (realized-outcome trajectories), not just from human-fed content.
  Teaching (human→agent) ships today; self-learning (agent→itself) is the headline next step. Own
  brainstorm→spec→plan arc.
- [ ] **Image / chart ingestion (vision)** — teach from a screenshot or `复盘` chart. Deferred in v2:
  `deepseek-v4-pro` has **no vision via the API** (verified vs DeepSeek's API ref + NVIDIA NIM card), and
  Sonia rejects images with a friendly note today; needs a vision-capable copilot (Claude, or a future
  multimodal endpoint) + image content blocks + re-enabling the composer's image upload.
- [ ] **`tweak` action** — manual inline arg-editing of a proposed edit (no LLM); the spec §8 route table
  lists it, but v1 shipped `accept` / `reject` / `comment→re-propose` + `apply` only.
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
