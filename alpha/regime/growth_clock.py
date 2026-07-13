"""Growth market-clock — GCycle's successor for the growth pack (manuscript §1.1 `market_three_states`,
§4.3 `market_state_actions.rule`).

The momo `GCycle` bands a single day's breadth into six phases whose `follow_through_rate >= 0.4`
frontside test is the A-share 连板 signature (structurally rare in the US -> thin-by-construction). The
growth doctrine reads a weeks-to-months MARKET clock with three states instead:

  confirmed_uptrend  -- a follow-through day has confirmed the uptrend; new buys allowed (frontside).
  under_pressure     -- a distribution-day cluster; 禁新建仓, graded appetite (NOT frontside).
  correction         -- deep breadth weakness; 现金是仓位 (NOT frontside, risk_gate below the risk-off floor).

Built NATIVELY from tape/breadth facts, never by translating momo phases (the deleted bridge, ratified
`alpha/harness/growth_regime.py` tail). The read is expressed THROUGH the existing `RegimeRead` surface
(phase/frontside/risk_gate) so the immutable veto (`alpha/guard/veto.py`) needs zero changes — see the
`_MAP` table below. Panic (`panic_state`) is an ORTHOGONAL cross-cut flag handled by the guard's veto
path (`detect_panic_state`), not by this three-state read (§1.1 framing).

Honest proxy (limits stated, not assumed). `MarketState` has NO index price and NO index volume, and
the P0.4 breadth family (`pct_above_200dma`/`advances`/`declines`) is None on the live decide path. So
the index-direction signal is the gainer/loser breadth `gainer_share` — the same primitive the panic
detector reads. A follow-through day ("index up on higher volume") is proxied by a strong-breadth up
day (`share >= FTD_SHARE`); a distribution day ("index down on higher volume") by a down-breadth day
(`share <= DD_SHARE`). Volume is unobservable, so a broad low-volume up day counts as a follow-through
day — an accepted proxy limit. (A future caller that threads the breadth family can refine the DD test
with `advances`/`declines`; deferred, see the P2 spec §5.)

Cross-day, not memoryless. P1's lesson is that a per-day detector flickers, so the state is computed by
replaying a deterministic state machine forward over `history + today` — a PURE function of
`(history, today)` with no hidden mutable state (recomputable; same inputs -> same read), exactly like
`detect_panic_state`'s latch. All thresholds are 「文献值待verdict校准」 named constants; the Refiner-
calibration metatool path is deferred (P2 conditional sub-item not taken).
"""
from __future__ import annotations

import statistics
from collections.abc import Sequence

from alpha.regime.classifier import RegimeRead
from alpha.state.market import MarketState

# ── thresholds (文献值待verdict校准) ─────────────────────────────────────────────────────────────────
FTD_SHARE = 0.60         # follow-through day proxy: a strong-breadth up day at/above this confirms
DD_SHARE = 0.40          # distribution day proxy: a down-breadth day at/below this share
UP_DAY_SHARE = 0.50      # a plain up day (heals correction -> under_pressure without a full FTD)
DEEP_SHARE = 0.30        # deep-breadth-weakness: mean share (since the last confirmation) at/below this
DEEP_MIN_DAYS = 3        # min days since confirmation before the deep-mean can downgrade (no single-day twitch)
DD_WINDOW = 25           # distribution-day counting window cap (O'Neil literature: ~25 sessions)
DD_UNDER_PRESSURE = 5    # >= this many DDs SINCE the last FTD downgrades a confirmed uptrend to under_pressure
DD_CORRECTION = 8        # >= this many DDs (or a deep-breadth read) is the deeper correction state
MIN_HISTORY = 5          # min NON-EMPTY prior days before the backdrop can be assessed (else warm-up)

# per-state RegimeRead mapping — expresses §4.3 action semantics through the existing veto surface:
#   confirmed_uptrend -> frontside, clear risk_gate (可新建仓、可加仓)
#   under_pressure    -> NOT frontside, risk_gate above the risk-off floor (禁新建仓, 加仓减半)
#   correction        -> NOT frontside, risk_gate below the risk-off floor 0.2 (禁新建仓、禁加仓, 现金是仓位)
UPTREND_GATE = 0.60
PRESSURE_GATE = 0.35
CORRECTION_GATE = 0.15
_HISTORY_CONF = 0.6      # confidence with enough history to assess the backdrop
_WARMUP_CONF = 0.4       # warm-up: too little history, conservative abstention

_UPTREND, _PRESSURE, _CORRECTION = "confirmed_uptrend", "under_pressure", "correction"
_MAP = {                                           # state -> (frontside, risk_gate)
    _UPTREND: (True, UPTREND_GATE),
    _PRESSURE: (False, PRESSURE_GATE),
    _CORRECTION: (False, CORRECTION_GATE),
}


def gainer_share(state: MarketState) -> float:
    """gainer / (gainer + loser) — the day's up-fraction (index-direction proxy). 0.0 on a 0/0 empty
    tape (feed outage), never a divide-by-zero. Mirrors the panic detector's primitive."""
    denom = state.gainer_count + state.loser_count
    return state.gainer_count / denom if denom else 0.0


def market_share(state: MarketState) -> float:
    """The index-direction proxy the clock reads. Prefers the FULL-cross-section advance/decline breadth
    (`advances`/`declines`) when a caller has threaded it (a far better market-trend signal than the
    gainer-tail); falls back to `gainer_share` otherwise. On the live decide path the breadth family is
    None, so this is exactly `gainer_share` (byte-identical) — the a/d read only kicks in when populated
    (the calibration --breadth path, or a future P5 theme-breadth feed)."""
    adv, dec = state.advances, state.declines
    if adv is not None and dec is not None and (adv + dec) > 0:
        return adv / (adv + dec)
    return gainer_share(state)


def _has_signal(state: MarketState) -> bool:
    """True iff the day carries a usable breadth signal: an a/d count, or a non-empty gainer/loser tape.
    A day with neither (0/0 and no a/d) is a feed outage — insufficient evidence, excluded from the
    window (mirrors the panic detector's empty-day handling)."""
    adv, dec = state.advances, state.declines
    if adv is not None and dec is not None and (adv + dec) > 0:
        return True
    return (state.gainer_count + state.loser_count) > 0


def _run_machine(shares: Sequence[float]) -> str:
    """Replay the three-state machine forward over the chronological `shares` (history + today) and
    return the state after the last day. Pure: depends only on `shares`.

    Start conservative at under_pressure; a follow-through day (`s >= FTD_SHARE` out of a downgraded
    state) confirms the uptrend AND anchors a fresh distribution count (O'Neil: an FTD starts a new
    rally, so its DD tally resets). Distribution days and the deep-breadth mean are counted ONLY SINCE
    that anchor (capped at DD_WINDOW) — NOT over a fixed trailing window that would carry stale pre-FTD
    DDs into the freshly-confirmed state and un-confirm it the next day (the ABAB-oscillation bug). A
    confirmed uptrend downgrades to under_pressure at >= DD_UNDER_PRESSURE post-anchor DDs, to correction
    at >= DD_CORRECTION or a sustained deep-breadth read (>= DEEP_MIN_DAYS days averaging <= DEEP_SHARE,
    guarded so a single weak day cannot flip it). Hysteresis: isolated weakness never un-confirms."""
    state = _PRESSURE
    anchor = -1                                     # index of the most recent confirmation (FTD)
    for i, s in enumerate(shares):
        dd_lo = max(anchor + 1, i - DD_WINDOW + 1)  # DDs SINCE the last confirmation (O'Neil), window-capped
        dd_count = sum(1 for x in shares[dd_lo:i + 1] if x <= DD_SHARE)
        # deep = a SUSTAINED recent breadth collapse (a waterfall the slow DD count would miss): the mean
        # over the last DEEP_MIN_DAYS days, clamped so it never reaches across the anchor (no stale pre-FTD
        # bleed) and needs a full DEEP_MIN_DAYS post-anchor days (no single-day twitch).
        deep_win = shares[max(anchor + 1, i - DEEP_MIN_DAYS + 1):i + 1]
        deep = len(deep_win) >= DEEP_MIN_DAYS and statistics.mean(deep_win) <= DEEP_SHARE
        if state == _UPTREND:
            if dd_count >= DD_CORRECTION or deep:
                state = _CORRECTION
            elif dd_count >= DD_UNDER_PRESSURE:
                state = _PRESSURE
            # else: stay confirmed (hysteresis — isolated weakness does not un-confirm)
        else:                                       # under_pressure / correction
            if s >= FTD_SHARE:
                state = _UPTREND                    # follow-through day confirms AND anchors a fresh DD count
                anchor = i
            elif dd_count >= DD_CORRECTION or deep:
                state = _CORRECTION
            elif state == _CORRECTION and s >= UP_DAY_SHARE and dd_count < DD_UNDER_PRESSURE:
                state = _PRESSURE                   # heal correction -> under_pressure on improvement
    return state


class GrowthMarketClock:
    """Read-only three-state market-clock classifier (GCycle's growth successor). Deterministic,
    oracle-auditable. `read()` returns a `RegimeRead`; it writes nothing into H (SSOT)."""

    def read(self, history: Sequence[MarketState], today: MarketState) -> RegimeRead:
        """Classify `today` given its strictly-prior `history` (chronological). Warm-up (fewer than
        MIN_HISTORY non-empty prior days) abstains to a conservative under_pressure — the backdrop
        can't be assessed, so no confirmed-uptrend is granted. An empty (0/0, no-signal) `today` also
        ABSTAINS — a feed-outage day is no evidence, so the state is carried forward from the prior read
        (today is NOT baked in as a synthetic 0.0 max-bearish distribution day, which would diverge from
        the panic detector and let a datum a later day treats as never-existing move the read)."""
        prior = [s for s in history if _has_signal(s)]
        if len(prior) < MIN_HISTORY:
            frontside, risk_gate = _MAP[_PRESSURE]
            return RegimeRead(phase=f"market:{_PRESSURE}", confidence=_WARMUP_CONF,
                              frontside=frontside, risk_gate=risk_gate)
        shares = [market_share(s) for s in prior]
        if _has_signal(today):                      # an empty today abstains -> carry the prior state forward
            shares.append(market_share(today))
        state = _run_machine(shares)
        frontside, risk_gate = _MAP[state]
        return RegimeRead(phase=f"market:{state}", confidence=_HISTORY_CONF,
                          frontside=frontside, risk_gate=risk_gate)
