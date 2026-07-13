# P5b — Earnings consume-path activation (the T-3 checklist gate)

> Status: design + build (2026-07-13). Activates the P5a earnings feed into the decide path.
> Predecessor: `2026-07-13-p5a-earnings-feed-design.md` (INGESTION: the feed + PIT primitives +
> feature helpers). This step WIRES that feed into `screen_decision` so the doctrine's
> `earnings_gap_discipline.rule` (§4.5) becomes executable.
> Manuscript: `docs/doctrine/2026-07-12-us-growth-doctrine-draft.md` §4.5, §2.4, §4.8.

## What P5a left dormant

P5a shipped the earnings *feed* — `EarningsFact`/`EarningsCalendarEntry` (filing_date / known_asof
PIT keys), the `earnings_known` / `earnings_calendar` / `earnings_available` source Protocol
capability (EdgarSource + offline backend, routed through CompositeSource), and the derived signal
helpers in `alpha/features/earnings.py` (`days_to_earnings`, `has_upcoming_earnings(within_days=3)`,
`next_earnings`, `latest_actual`). It explicitly deferred the consume path: "wire
`earnings_gap_discipline.rule` (§4.5 T-3 gate) into the guard/doctrine decide path." That is this
step.

## The doctrine (manuscript §4.5 `earnings_gap_discipline.rule`)

> 财报日前 T-3 起强制完成论点检查清单：①验证节点预期已登记？②对手盘论点有无新证据？③本季哪个数字证伪论点？
> 清单未完成 = 不得扛（guard veto 候选）。

Scope: earnings-event gaps only (non-event drift / technical breakdown route to `stop_discipline`
and `derisk_on_breakdown`). From T-3 before the report the thesis checklist is mandatory; an
incomplete checklist means 不得扛 — do not hold-through. `earnings_checklist_gate` is a listed
immutable red-line **candidate** for seeds_v2 (§4.8).

## The warn-vs-veto decision — surfaced checklist risk, NOT a hard veto

The activated behaviour is a **warn-the-human surfaced risk** in `DecisionPackage.key_risks`, not a
guard drop. A new-entry candidate whose next known report is within T-3 gets a per-symbol checklist
note; the candidate is **kept**, and the human running the co-pilot decides at confirm time. Five
reasons, each principled against the manuscript:

1. **The rule's own subject is 扛 (hold-through), not new entry.** §4.5 is titled 财报缺口纪律（原
   "论点在就扛"）. "清单未完成 = 不得扛" gates whether you may HOLD a position through the report.
   A new entry T-3 is a distinct decision; the doctrine mandates the checklist be *completed*, it
   does not say "no new entry inside T-3." The warn surfaces the mandate at exactly the human
   confirm point §4.5 already names ("用户批准时显式确认").

2. **The gate's CONDITION is not code-decidable.** The trigger ("earnings within T-3") is a PIT date
   fact — code's domain (骨). But "清单未完成" is a prose judgment over thesis-card text (是否登记了验证
   节点 / 对手盘有无新证据 / 哪个数字证伪) — the LLM/human's domain (魂). The 魂骨宪法 (§序章) is
   explicit: 量化只有否决权与限额权……没有选择权与论证权. The guard can KNOW "within T-3"; it cannot
   KNOW "the checklist is done." A hard veto on T-3 *alone* would drop every candidate whose checklist
   IS complete — the guard usurping a judgment (selection) it constitutionally may not make, using a
   date as a false proxy for a homework check.

3. **The system is human-confirm decision support with no order path.** There is nothing to
   auto-block; the decision surface is the human's. `key_risks` is where the co-pilot warns before a
   human confirm — the natural, spec-named home for "earnings within T-3, complete the checklist."

4. **Contrast with the existing hard vetoes.** Every current veto (SSR, reverse-split, dilution,
   halt-then-dump, panic-state, episode-taboo) is an *unconditional* code-decidable block — no "but
   if the human did the homework it's fine" branch exists. earnings-within-T-3 is conditional on a
   judgment the code can't see, so it belongs in `key_risks`, alongside the P3 `CORP_BLIND_NOTE`
   (also warn-the-human, also not a veto), not in `veto.py`.

5. **The red-line-candidate contrast is deliberate (§4.8 vs §4.3).** `earnings_checklist_gate` is a
   red-line *candidate* for seeds_v2, not an active immutable veto. Crucially the manuscript gives
   `panic_state_ban` an explicit acceptance condition — "验收条件 = 蒸馏为 L4 guard 硬否决（散文拦不住
   十年肌肉记忆）" — because that ban is *fully* fact-decidable (bear + high-vol + sharp rebound → don't
   buy leaders). It withholds that "must be a hard veto" acceptance from `earnings_checklist_gate`,
   whose trigger is fact-decidable but whose condition (checklist done) is not. Surfacing the
   requirement is the faithful executable form.

### What this defers (deliberately not done)

- **The 扛 (hold-through) veto.** "清单未完成 = 不得扛" gates HELD positions through a report. No
  holdings / hold-through producer exists yet (`candidate_action` is always `enter`; holdings aren't
  modeled — see P0.6 in screen.py). When a hold-through producer lands, the checklist-incomplete →
  do-not-hold branch can be wired *there* (it needs the checklist-completeness signal, an
  LLM/human/thesis-card input, not a date). Queued behind that producer.
- **The disproof-direction branch** ("缺口方向与论点预期相反且触发证伪条件 → 次日按 thesis_price_matrix").
  Needs post-earnings actuals wired against a registered thesis expectation (the `latest_actual` leg
  + thesis-card verification nodes) and a next-day exit producer — none of which exist yet.
- **A structured per-candidate `days_to_earnings` field** on `Candidate` / `MarketState`. That would
  touch `alpha/eval/decision.py` / `alpha/state` (out of this step's footprint) and isn't needed for
  the warn surface. The guard computes it inline for the note.

## The threading (mirrors the P3 corp-blind additive pattern)

All changes live in `alpha/guard/screen.py::screen_decision` — the same function P3 threaded
`corp_actions_available` through, reading the SAME `source` already injected into `GuardedPolicy`
(no signature change anywhere; the earnings capability rides on the existing source object).

1. Read availability + the PIT-filtered calendar once, before the candidate loop:
   ```python
   earnings_available = guarded.earnings_available()
   earnings_cal = guarded.earnings_calendar(as_of) if earnings_available else []
   ```
   `guarded` is the fresh `GuardedSource(AsOfGuard(as_of))`, so `earnings_calendar` is PIT-guarded
   (known_asof <= as_of) exactly like `corporate_actions_known`.

2. Per KEPT enter-candidate (after it passes `veto`), surface the checklist note when within T-3:
   ```python
   if earnings_available and has_upcoming_earnings(earnings_cal, c.symbol, as_of):
       notes.append(earnings_checklist_note(c.symbol, days_to_earnings(earnings_cal, c.symbol, as_of)))
   ```
   `has_upcoming_earnings` uses `within_days=3` (§4.5 T-3), boundary `0 <= d <= 3` (day 3 in, day 4
   out). The note carries the actual day count so the human sees T-0 (reports today) vs T-3.

Placement gates the note precisely:
- **enter-only** — a `trim`/`exit` hits the P0.6 `continue` and never reaches the note (reducing
  exposure into earnings is prudent, not a risk to warn about; the checklist is about a NEW
  hold-through exposure).
- **kept-only** — a candidate vetoed for another reason (reverse-split, SSR, …) is dropped in the
  vetoed branch; no earnings note for a candidate that isn't there.

## The additive / default-off contract (byte-identical when the feed is absent)

- No earnings backend → `earnings_available()` is False (GuardedSource defaults absence to False,
  fail-closed) → `earnings_cal = []` → `has_upcoming_earnings` is always False → **no note**. Every
  pre-P5b caller and every FakeSource without `earnings=`/`earnings_calendar=` is byte-identical.
- Feed present but no entry within T-3 for a symbol → no note (distinct from feed-absent, same
  present-vs-missing distinction P3 draws for corp).
- The note appears ONLY when the feed is present AND a kept enter-candidate reports within T-3.

## Verdict-neutrality & arm-symmetry (both pinned)

- **Neutral.** The note lands in `key_risks`; the candidate is kept unchanged. `ReturnScorer` /
  `PatternScorer` iterate `decision.candidates` only — they never read `key_risks` (grep-pinned).
  A run WITH the feed (note fires) yields a byte-identical `EvalReport` to the same run without it.
- **Symmetric.** Both verdict arms wrap the SAME source object (the screen-flag / recall_store
  symmetry pattern), so both see the same calendar and emit the same note day-for-day; the note,
  being unscored, cannot tilt `hch_minus_hexpert_*`.

## Footprint & TCB

- Modified: `alpha/guard/screen.py` (additive) — NOT in `tcb.lock`.
- New tests: `tests/guard/test_screen_earnings_checklist.py`,
  `tests/loop/test_p5b_earnings_symmetry.py`.
- New import edge guard → `alpha.features.earnings` (leaf feature layer already consumed by
  `alpha/state/builder.py` and `alpha/universe/universe.py`; no AST rule forbids it).
- Untouched: `alpha/data`, `alpha/features`, `alpha/eval`, `alpha/loop`, `alpha/agent` (incl. the
  TCB `retrieval.py`), `alpha/state`, `seeds_v2` (the `earnings_gap_discipline` /
  `earnings_checklist_gate` doctrine prose already ships dormant — this step supplies its executable
  half, no seed edit needed).

## Tests (acceptance)

- (a) kept enter-candidate within T-3 + feed present → the checklist note in `key_risks`.
- (b) no feed → byte-identical, no note (and the existing screen suite stays green).
- (c) verdict-neutral: candidates/regime identical with vs without the note; EvalReport identical.
- (d) arm-symmetric: the note appears in both arms day-for-day; the verdict delta stays < 1e-9.
- (e) exact boundary: report in 3 days → note; in 4 days → no note.
- edge: feed-present-but-not-within-T-3 → no note; a within-T-3 candidate vetoed for another reason
  → dropped, no note; a within-T-3 trim/exit → no note.
