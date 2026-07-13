"""Panic-state detection — the momentum-crash L4 guard (manuscript §1.1 `panic_state`, §4.3
`panic_state_ban.rule`; Appendix B routes it to `alpha/guard` as an L4 veto).

The momo GCycle reads a single day's breadth, so a sharp panic rebound (gainers dominate) reads
`trend`/`ignition`/`recovery` with frontside=True — the existing veto never fires. That is the
momentum-crash blind spot: buying leaders into a bear-market rally systematically underperforms
(研究已验证). The distinction between a genuine trend and a bear-market rally lives in the PRECEDING
context (a bear-market decline), not in the rebound day itself — so the detector needs history the
single-day classifier does not have.

`detect_panic_state` is a pure, deterministic function over `MarketState` counts already on the guard
path. It fires when three proxies co-occur (bear backdrop AND (high dispersion OR a deep bear) AND a
sharp rebound), and it LATCHES: once a trigger day is seen, the panic persists across the ensuing
choppy rally days — the manuscript's §4.3 ban spans the whole crash window, not just the days that
themselves happen to look like a ≥`REBOUND_SHARE_MIN` bounce. The latch is a pure function of history
(a trigger day still visible in the trailing window keeps the state latched); there is no hidden
mutable state.

**Scope (fail-toward-strict, deliberate).** Manuscript §4.3 scopes `panic_state_ban` to strong-list
(leader) names. No strong-list / leader-membership signal exists pre-P2 (the leader list is P2's job),
so this veto blocks ALL new entries on a latched panic day rather than a subset. That broadening is
fail-toward-strict and intentional: on a genuine momentum crash the reflex to chase is exactly the
error the ban targets, and there is no worse-than-hold new entry it wrongly blocks that a held name
would have wanted. P2 MAY narrow the scope to the leader list once it exists; it must NOT be narrowed
before then. The true doctrine release condition (a new base + a follow-through day + a fresh leader
list) is likewise not computable pre-P2 — the `PANIC_LATCH_MIN_DAYS` latch is its conservative proxy.

All thresholds are 「文献值待P2校准」 named constants; P2's three-clock regime successor owns their
calibration and the live-history wiring. This module holds only the detection; the veto reason lives in
`veto.py`.
"""
from __future__ import annotations

import statistics
from collections.abc import Sequence

from alpha.state.market import MarketState

# ── thresholds (文献值待P2校准) ─────────────────────────────────────────────────────────────────
PANIC_LOOKBACK = 15          # trailing prior days considered for the bear/vol backdrop
PANIC_MIN_HISTORY = 5        # min NON-EMPTY prior days before a backdrop can be assessed (below -> no veto)
PANIC_LATCH_MIN_DAYS = 10    # latch floor: panic persists at least this many days past the last trigger
BEAR_SHARE_MAX = 0.35        # 熊市标志: mean gainer-share over the window at/below this = sustained weakness
DEEP_BEAR_SHARE_MAX = 0.25   # 深熊: mean share at/below this is a severe bear even at zero dispersion (waterfall)
BEAR_DOWN_DAY_FRAC = 0.60    # 熊市标志 (alt): fraction of prior days with negative breadth at/above this
VOL_SHARE_STD_MIN = 0.15     # 高波动: population stdev of daily gainer-share at/above this = high dispersion
REBOUND_SHARE_MIN = 0.60     # 指数急反弹: today's gainer-share must be at/above this (gainers dominate)
REBOUND_JUMP_MIN = 0.20      # 指数急反弹: today's share must exceed the trailing mean by at least this


def gainer_share(state: MarketState) -> float:
    """gainer / (gainer + loser) — the day's up-fraction. Empty tape -> 0.0 (never divides by zero)."""
    denom = state.gainer_count + state.loser_count
    return state.gainer_count / denom if denom else 0.0


def _is_empty(state: MarketState) -> bool:
    """A 0/0 tape (feed outage): no gainers AND no losers — insufficient evidence, not bearish evidence."""
    return (state.gainer_count + state.loser_count) == 0


def _window_stats(states: Sequence[MarketState]) -> tuple[float, float, float] | None:
    """`(trailing_mean, down_day_frac, share_pstdev)` over the NON-EMPTY days in the trailing
    `PANIC_LOOKBACK` window, or None when fewer than `PANIC_MIN_HISTORY` non-empty days exist.

    Empty-tape (0/0) days are EXCLUDED from every proxy (Fix: a feed outage is 'no evidence', not
    maximally-bearish evidence) — consistent with the warm-up posture: too little real evidence -> the
    detector abstains (the caller reads None as no-veto)."""
    window = [s for s in list(states)[-PANIC_LOOKBACK:] if not _is_empty(s)]
    if len(window) < PANIC_MIN_HISTORY:
        return None
    shares = [gainer_share(s) for s in window]
    down_day_frac = sum(1 for s in window if (s.gainer_count - s.loser_count) < 0) / len(window)
    return statistics.mean(shares), down_day_frac, statistics.pstdev(shares)


def _is_bear(stats: tuple[float, float, float]) -> bool:
    """熊市标志: sustained weakness — a low trailing mean OR a majority of down-breadth days."""
    trailing_mean, down_day_frac, _ = stats
    return trailing_mean <= BEAR_SHARE_MAX or down_day_frac >= BEAR_DOWN_DAY_FRAC


def _triggers(history: Sequence[MarketState], today: MarketState) -> bool:
    """True iff the three proxies co-fire ON `today` given its strictly-prior `history`: a bear backdrop
    AND volatility evidence (high dispersion OR a deep bear — a waterfall crash minimises dispersion
    exactly when the bear is most severe, so `DEEP_BEAR_SHARE_MAX` is the OR-leg that catches it) AND a
    sharp broad rebound. Fail-toward-strict: all comparisons are inclusive."""
    stats = _window_stats(history)
    if stats is None:
        return False
    trailing_mean, _down, share_pstdev = stats
    vol_evidence = share_pstdev >= VOL_SHARE_STD_MIN or trailing_mean <= DEEP_BEAR_SHARE_MAX   # 高波动 或 深熊
    today_share = gainer_share(today)
    sharp_rebound = today_share >= REBOUND_SHARE_MIN and (today_share - trailing_mean) >= REBOUND_JUMP_MIN
    return _is_bear(stats) and vol_evidence and sharp_rebound


def detect_panic_state(history: Sequence[MarketState], today: MarketState) -> bool:
    """True iff `today` is inside a momentum-crash window where buying leaders is systematically wrong.

    `history` = the strictly-prior daily `MarketState`s in chronological order; `today` = the day being
    screened. Two ways to fire:

    1. `today` itself is a sharp rebound out of a bear + high-vol/deep-bear backdrop (`_triggers`).
    2. LATCH — a prior trigger day is still visible in the trailing window and the panic has not yet
       released. Release requires BOTH the bear backdrop to have cleared AND the trigger to be older
       than `PANIC_LATCH_MIN_DAYS` (i.e. the latch persists while the bear holds OR for at least
       `PANIC_LATCH_MIN_DAYS`, whichever is longer). This keeps the veto on across the choppy
       continuation days of a bear rally (a 0.545-share follow-through the day after a trigger is still
       vetoed) instead of releasing every day the tape fails to re-clear `REBOUND_SHARE_MIN`.

    Honest limit: the true doctrine release (a new base + a follow-through day + a fresh leader list) is
    not computable pre-P2; the latch is its conservative proxy (see the module docstring). With fewer
    than `PANIC_MIN_HISTORY` non-empty prior days the backdrop cannot be assessed and this returns False
    — a positive detection needs evidence, it is not a fail-open bypass (P2 wires enough live history).

    Pure function: the latch state is derived from `history` alone (a trigger day recomputed from its own
    prefix), so there is no hidden mutable state — the same `(history, today)` always yields the same
    answer."""
    hist = list(history)
    if _triggers(hist, today):
        return True
    stats_now = _window_stats(hist)
    bear_now = stats_now is not None and _is_bear(stats_now)
    n = len(hist)
    for age in range(1, min(n, PANIC_LOOKBACK) + 1):   # scan the trailing window for a still-latching trigger
        j = n - age                                    # hist[j] is the day `age` sessions before today
        if _triggers(hist[:j], hist[j]) and (age <= PANIC_LATCH_MIN_DAYS or bear_now):
            return True
    return False
