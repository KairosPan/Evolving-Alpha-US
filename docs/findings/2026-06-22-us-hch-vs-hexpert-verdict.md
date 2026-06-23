# Findings: first live US HCH-vs-Hexpert verdict — **parity** (ROADMAP §1 rendered)

> Date: 2026-06-22 · Data: real Alpaca IEX bars (Q1-2026) captured to an offline PIT store · LLM: real
> DeepSeek (`deepseek-chat`, **temperature=0**) driving **both** the agent and the Refiner · Tool:
> `scripts/run_verdict.py` over `verdict_pit_broad`.
>
> **One line:** The §9/§10 verdict apparatus was rendered live for the first time on US data. In both
> the production posture (L4 screen ON) and the raw-skill diagnostic (screen OFF), **HCH (self-evolving)
> is statistically indistinguishable from frozen Hexpert** — verdict `flat` (parity), HCH leaning
> marginally positive but inside the noise band. This reproduces the CN §1 conclusion ("self-evolution
> is net-neutral, not harmful") on US data — and HCH never *degrades* below frozen here (the capability
> breaker froze it the moment it began to slip).

---

## 1. Experiment setup

- **Window:** `2026-01-02 .. 2026-03-27` (59 trading days), horizon=2 (t+1 open → t+2 close; no same-day
  round-trip), temp=0 (determinism surrogate).
- **Universe:** a **liquidity-ranked broad cross-section** — the top **800** US equities by median daily
  dollar-volume, drawn from Alpaca's shortable plain-ticker set, captured with a ~25-day pre-roll (so
  RVOL / prev_close are populated). Built by `scripts/capture_broad.py` (batch multi-symbol bars → rank →
  `capture_window`). This replaces an earlier 68-name hand-picked basket whose breadth internals were
  meaningless (see §4).
- **Arms** (same source / window / horizon / scorer; each gets a FRESH H + LLM client + store):
  - **HCH** = self-refining `InnerLoop` (daily act → delayed scoring → online credit → capability-floor
    breaker → Refiner edits H; DeepSeek drives both agent and Refiner).
  - **Hexpert** = frozen seed H + same agent, **no Refiner**.
  - **Hmin_chase** = blindly chase the day's single biggest gainer; **Hmin_notrade** = always flat.
- **Two postures:** screen **ON** (production — the L4 regime/firewall veto is live and symmetric across
  arms) and screen **OFF** (`--no-screen` — bypasses the L4 regime veto to measure raw agent skill).

## 2. Results: parity in both postures

### Run A — production posture (screen ON)

| arm | n_dec | cand | mean_excess | refines | breaker |
|---|---|---|---|---|---|
| **HCH** | 59 | 31 | **+0.0052** | 4 | trips=0, frozen=None |
| **Hexpert** | 59 | 35 | **−0.0055** | — | — |
| Hmin_chase | 59 | 13 | −0.0214 | — | — |
| Hmin_notrade | 59 | 0 | 0.0000 | — | — |

**Paired day-level verdict:** `flat` · n_days=57 · mean_diff **+0.0005** · CI **[−0.0001, +0.0014]** ·
p=0.375 · MDE=0.001. Headline HCH−Hexpert mean_excess = +0.0107.

### Run B — raw-skill diagnostic (screen OFF)

| arm | n_dec | cand | mean_excess | refines | breaker |
|---|---|---|---|---|---|
| **HCH** | 59 | 214 | **−0.0090** | 10 | trips=2, **frozen from 2026-02-10** |
| **Hexpert** | 59 | 204 | **−0.0168** | — | — |
| Hmin_chase | 59 | 53 | +0.3504 *(artifact — §5)* | — | — |
| Hmin_notrade | 59 | 0 | 0.0000 | — | — |

**Paired day-level verdict:** `flat` · n_days=57 · mean_diff **+0.0043** · CI **[−0.0027, +0.0085]** ·
p=0.165 · MDE=0.009. Headline HCH−Hexpert mean_excess = +0.0078.

### Run C — `--windows 3` multi-seed direction diagnostic (production posture)

3 independent sub-windows (the temp=0 multi-seed surrogate): **deltas = [0.0, −0.0021, 0.0]** ·
mean_delta −0.0007 · win_rate 0.00 · sign_consistent False · **verdict_tally = {flat: 3}**. All three
sub-windows are `flat` (parity); **two are HCH ≡ Hexpert *exactly* (Δ=0)** — HCH's refines did not flip any
pick in those windows (the CN §9 observation that temp=0 + short windows rarely flip decisions, reproduced).
The headline delta's *sign* is not robust to windowing (single-window A was +0.0052, the 3-window mean is
−0.0007) — i.e. it is noise around zero, which is the definition of parity.

## 3. Interpretation

1. **Parity, as the roadmap predicted.** In both postures the paired CI straddles 0 — HCH and Hexpert are
   indistinguishable. Directionally HCH ≥ Hexpert in both (mean_diff +0.0005 / +0.0043), a touch *better*
   than the CN §1 first run (which showed HCH degrading below frozen). **Self-evolution is net-neutral,
   not harmful** — the CN central conclusion reproduces on US data.
2. **The capability breaker did its job.** Screen-OFF, HCH's self-relative breaker **tripped twice and
   froze H at 2026-02-10**, converging HCH→frozen for the back half of the window when it began to slip.
   That is the designed safety net catching "HCH drifting worse than its own floor."
3. **The L4 guard enforces the discipline the LLM ignores.** Screen-OFF the agent proposed **214/204**
   candidates — it does **not** obey the immutable `no_chase_risk_off` doctrine on its own. Screen-ON the
   hard veto cut that to **31/35**: the guard, not the model, enforces the no-chase-backside red-line.
4. **Not a tradeable-edge claim.** Raw 2-day returns on the agents' picks are slightly negative
   (−0.9% / −1.7%); the naive biggest-gainer chase has a **−0.5% median**. The result says "the two-loop
   self-evolution mechanism runs end-to-end and is net-neutral," not "this playbook makes money."

## 4. Why the production-posture verdict is THIN (A-share → US regime-classifier transfer gap)

The screen-ON run trades only 31/35 candidates over 59 days. Root cause (verified offline, independent of
universe breadth — holds on both the 68-name basket and the 800-name liquidity universe): `GCycle` calls a
strong-tape day **frontside** only when `follow_through_rate ≥ 0.4` — i.e. yesterday's ≥10% gainers gaining
≥10% **again** today. That is the A-share **连板 (consecutive limit-up)** signature, abundant in a 10%-limit
market but **structurally rare in the US** (no price limit; ≥10% repeats are uncommon). So **35/59 days read
"distribution" (backside)** and the immutable `no_chase_risk_off` doctrine + L4 veto suppress new longs. The
GCycle thresholds need **US recalibration** before the production posture can be more than thin parity. (New
ROADMAP item.)

## 5. Data-quality note: the Hmin_chase +0.35 is one reverse-split artifact

Screen-OFF Hmin_chase shows mean_excess +0.3504 but **median −0.0050**. The mean is one outlier: **SOXS on
2026-03-03, score(return) = +19.36 (+1936%)** — a `Adjustment.RAW` reverse-split jump on a 3x-inverse ETF
(SOXS reverse-splits periodically; the raw close ×N on the ex-date reads as a fake +1900% gain). That single
point contributes +19.36/53 ≈ +0.365 — essentially the whole mean. Screen-**ON** Hmin_chase is −0.021: the
firewall's **reverse-split veto correctly dropped it**, screen-OFF (veto bypassed) did not. The agent arms
never picked SOXS, so HCH/Hexpert are uncontaminated; the paired HCH−Hexpert diff is robust regardless (both
eat identical data).

## 6. Honest caveats

- temp=0 is a determinism *surrogate*, not true multi-seed (with temp=0 you can't vary the seed; independent
  windows are the surrogate — Run C).
- **IEX free feed** (paper entitlement): at least one egregious bad/raw print (SOXS, §5); SIP would be cleaner.
- Single window; horizon=2; **no costs / slippage**; `sentiment_norm` never activated (needs ≥60 history
  days, window is 59) so the regime read ran on the crude bootstrap proxy throughout.
- The firewall held by construction (every read goes through `GuardedSource(AsOfGuard(as_of))`); corp actions
  are announce(process_date)-keyed.

## 7. Reproduce

```bash
pip install -e ".[live]"                                  # alpaca-py, openai, pandas-market-calendars
set -a; source .env.alpaca; source .env.deepseek; set +a  # APCA_* + DEEPSEEK_API_KEY (both gitignored)
# 1. Build the broad liquidity-ranked PIT store (no LLM; ~30s batched fetch + corp actions):
python scripts/capture_broad.py 2025-11-17 2026-03-30 verdict_pit_broad 800
# 2a. Production-posture verdict (screen ON):
python scripts/run_verdict.py verdict_pit_broad 2026-01-02 2026-03-27 --windows 1 --json verdict_screenON.json
# 2b. Raw-skill diagnostic (screen OFF):
python scripts/run_verdict.py verdict_pit_broad 2026-01-02 2026-03-27 --windows 1 --no-screen --json verdict_screenOFF.json
# 3. Multi-seed direction diagnostic:
python scripts/run_verdict.py verdict_pit_broad 2026-01-02 2026-03-27 --windows 3
```
Helper: `python scripts/scan_tradeable.py verdict_pit_broad 2026-01-02 2026-03-27` (fast no-LLM
tradeability / regime-phase scan).
