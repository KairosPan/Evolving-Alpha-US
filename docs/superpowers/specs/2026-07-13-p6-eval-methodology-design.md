# P6 — Eval methodology (purged CV · regime-stratified · Hcredit ablation)

Status: spec 2026-07-13. Source: DEVELOPMENT-PLAN.md §1 P6; kairos-mining §2.8; P2 spec (growth
market-clock thresholds + §5 dead-band 待verdict校准). Gate-non-blocking — these are eval-QUALITY
tools; they change no live decision and touch no red-line / TCB surface.

## 0. Framing

Three additive, default-off eval tools land, all preserving **verdict symmetry** (both arms see
identical inputs; HCH gets nothing Hexpert doesn't; the verdict threads a READ-ONLY `recall_store`,
never `episode_store`) and **honest eval** (returns gross; delisting −1.0 kept; guard DROPS vetoed
candidates; sizing verdict-neutral; `SizingPolicy(GuardedPolicy(…))` order load-bearing):

1. **Purged & embargoed cross-validation** — native in `walk_forward.py` + `compare.py`.
2. **Regime-stratified eval** — metrics per decision-day regime read (momo phases / growth clock states).
3. **Hcredit (C4) ablation arm** — an HCH with the credit-assignment (SkillStats/`apply_credit`) seam
   removed, alongside HCH/Hexpert/Hmin.

Everything default-off is **byte-identical** to today (existing `tests/eval` + `tests/loop` unchanged).

## 1. Purged & embargoed CV

### 1.1 The leakage surface here

A decision at trading-day `t` enters at `t+1` open and exits at `t+horizon` close — its forward-return
LABEL spans `[t+1, t+horizon]`. `WalkForwardEval` and the `InnerLoop` already leave the **last
`horizon` decisions of a window unscored** (no `t+horizon` day inside the window). That trailing-tail
unscored set IS the built-in López de Prado purge: a window's scored labels only read data ≤ its own
last day, so contiguous windows never leak labels backward across a split.

P6 makes this explicit and generalizes it:

- **`embargo` (int ≥ 0)** — drop `embargo` MORE trailing scored decisions beyond the structural
  `horizon`, an autocorrelation / edge-measurement buffer at the window's right edge. `embargo=0` →
  byte-identical.
- **Fold gaps** — when windows are used as CV folds, separate adjacent folds by a gap of
  `horizon − 1 + embargo` trading days so no scored label (nor its embargo buffer) crosses a boundary.
- **Reserved holdout** — reserve the last `reserved` windows as a held-out set never looked at while
  iterating on refiner prompts/config. The residual Goodhart surface is *human* meta-iteration;
  reserving folds mitigates but cannot eliminate it (documented, not enforced).

### 1.2 Mechanism (`alpha/eval/purged_cv.py`, pure, no deps)

- `scored_cutoff(n_days, horizon, embargo=0) -> int` — highest scored decision index
  (`n_days − 1 − horizon − embargo`; `−1` if nothing scored). Formalizes the `scored` flag.
- `embargo_trajectory(traj, embargo=0) -> Trajectory` — return a copy with the last `embargo` **scored**
  steps re-marked `scored=False, outcomes={}` (their labels sit at the right edge / would cross a
  contiguous-fold boundary). `embargo ≤ 0` → returns `traj` unchanged (byte-identical). Applied
  **symmetrically** to every arm — the single embargo implementation both `WalkForwardEval.walk()` and
  `compare_harnesses` call, so HCH and Hexpert share one date grid and one purge rule.
- `partition_folds(days, n_folds, horizon, embargo=0, reserved=0) -> (iterate, reserved_folds)` — split a
  trading-day slice into `n_folds` contiguous NON-overlapping windows separated by the
  `horizon − 1 + embargo` gap; the last `reserved` folds are the held-out set. Raises if `days` is too
  short. A caller utility (a future daily loop / a human building `multi_window` inputs); `multi_window`
  itself does not require it.

### 1.3 Wiring

- `WalkForwardEval(..., embargo=0)` — `walk()` returns `embargo_trajectory(traj, self._embargo)`. Covers
  Hexpert (`wf.walk`) and both Hmin arms (`wf.run`) uniformly. `embargo=0` → returns the same object.
- `compare_harnesses(..., embargo=0)` — builds `wf` with `embargo=embargo` (Hexpert/Hmin) and applies
  `embargo_trajectory(lr.trajectory, embargo)` to the HCH (and ablation) trajectory **before** report /
  `daily_series` / `contribution_split`. Symmetric: both arms use the same `embargo_trajectory`.
  **The embargo is a measurement fence only** — the `InnerLoop` still refines internally over its full
  matured set (that is HCH's live behavior); the embargo trims what the COMPARISON scores, identically
  for both arms. It does not change how HCH evolves.
- `multi_window(..., embargo=0, reserved=0)` — threads `embargo` into every `compare_harnesses` call
  (both arms, every window — identical holdout windows preserved). `reserved` splits the window list:
  existing fields (`deltas`/`mean_delta`/`win_rate`/`sign_consistent`/`verdicts`/`verdict_tally`) stay
  **byte-identical** over ALL windows; additive `iterate_*` / `reserved_*` fields give the held-out view.

## 2. Regime-stratified eval (`alpha/eval/stratify.py`, pure)

Report metrics stratified by the regime read **on the decision day** — so "does HCH beat Hexpert" is
answerable per-regime, the tool that lets the growth-clock thresholds + §5 dead-band be calibrated
against realized per-state outcomes.

- Key functions mirror `guard/screen.py`'s dispatch exactly:
  - `momo_phase(market, history) -> str` = `GCycle().read(market).phase` (history ignored; GCycle is
    single-day).
  - `growth_clock_phase(market, history) -> str` = `GrowthMarketClock().read(history, market).phase`
    (e.g. `"market:confirmed_uptrend"`).
  - `regime_key_for(vocabulary) -> key_fn` — `growth_clock_phase` iff `vocabulary == "growth"`, else
    `momo_phase`.
- `label_steps(traj, key_fn) -> {date: label}` — replay history forward (history = strictly-prior steps'
  markets). Faithful to the live read: both accumulate the same window-local strictly-prior MarketStates,
  starting empty at the window's first day.
- `stratified_reports(traj, key_fn, horizon=2) -> {label: EvalReport}` — bucket scored steps by
  decision-day label; one `EvalReport` per label.
- `stratified_verdicts(hch_traj, hexpert_traj, key_fn, **verdict_kwargs) -> {label: StatVerdict}` — the
  paired day-level HCH−Hexpert verdict per regime. **Symmetric:** the label per date comes from the
  SHARED decision-day market (identical across arms — same source/window/history; MarketState and the
  regime read are s_t-side, independent of H, unchanged even across a breaker rollback), so stratifying
  the paired daily-diff series by decision-day regime gives each arm the same buckets.

Surfaced in `compare_harnesses(..., stratify=False)` as the additive-Optional
`ComparisonReport.stratified: dict[str, StatVerdict] | None` (per-regime HCH−Hexpert verdicts under the
run's vocabulary). Default `False` → `None` → byte-identical.

## 3. Hcredit (C4) ablation arm

**What the credit seam contributes to HCH:** `apply_credit` updates each matched skill's `SkillStats`
in place AND returns the `CreditReport` fed to the Refiner; the Refiner reads that report + the mutated
stats, and the gate's `min_retire/promote_samples` floors read `skill.stats.n`. Removing it removes
the credit-informed half of refinement, isolating how much of HCH's edge is the credit seam vs the raw
Refiner.

**Ablation function (`alpha/eval/ablation.py`):** `ablate_credit(traj, h, decay=0.1, *,
episode_store=None) -> CreditReport` — a drop-in with `apply_credit`'s exact signature that mutates NO
SkillStats and returns an empty `CreditReport()`. (In the verdict/compare context `episode_store` is
always `None`, so this arm writes nothing anywhere — SSOT preserved.)

**Injection seam (`alpha/loop/inner_loop.py`, additive/default-off):** `InnerLoop(..., credit_fn=None)`;
`self._credit_fn = credit_fn or apply_credit`; the single `apply_credit(...)` call site becomes
`self._credit_fn(...)`. Default `None` → `apply_credit` → byte-identical (all `tests/loop` unchanged).

**Arm (`compare_harnesses(..., credit_ablation=False)`):** when `True`, run a second `InnerLoop` —
identical source/window/`recall_store`/configs/shadow reference, fresh LLM clients (MockLLM is
stateful), `credit_fn=ablate_credit` — embargo its trajectory the same way, and add
`arms["HCH_nocredit"]` + `ComparisonReport.hch_minus_nocredit_mean_excess`. Default `False` → no extra
arm, no extra factory calls (factory-isolation test unchanged). This delta is a **diagnostic, not the
North-Star verdict** (which stays HCH−Hexpert).

## 4. Footprint & TCB

In-footprint (P6 owns): `alpha/eval/{purged_cv,stratify,ablation,walk_forward}.py`, `tests/eval/*`,
`tests/loop/*`. Out-of-footprint but required by the goal ("native in … `compare.py`", "arm alongside
HCH/Hexpert/Hmin"), REPORTED: `alpha/loop/compare.py` (wiring) and a 3-line additive seam in
`alpha/loop/inner_loop.py`. None of these are in `tcb.lock` (verified: only `alpha/loop/floor_breaker.py`
is, under `alpha/loop`). No `alpha/data|guard|refine|harness`, no `seeds` touched (read-only imports of
`alpha.refine.credit.CreditReport` and `alpha.regime.*` only). Offline, keyless, no new deps.

## 5. StatVerdict reporting-shape borrow

Per kairos-mining §2.8: borrow only the per-metric tolerance-with-reasons REPORTING shape. `StatVerdict`
already carries `verdict` + `ci_low/ci_high/p_value/mde` (the "reasons"); the stratified + ablation
tools reuse it verbatim (no new stat machinery). Both arms always see identical holdout windows.

## 6. Out of scope (deferred)

- Pooled cross-window / cross-fold significance test (stays the `win_rate` / sign-consistency direction
  diagnostic — MDE ~0.26 @ ~30 days). `partition_folds` provides the honest folds; pooling them into one
  test is future work.
- Auto-selecting the embargo length / fold count from measured return autocorrelation.
- Calibrating the growth-clock thresholds themselves — P6 ships the MEASUREMENT tool
  (`stratified_verdicts` per growth-clock state); turning its readings into new thresholds is a P2
  carry-forward run against captured PIT windows.
