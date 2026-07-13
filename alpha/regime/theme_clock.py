"""Growth theme-lifecycle clock — the second of the growth doctrine's three clocks (§1.2 `theme_lifecycle`).

The market clock (`alpha/regime/growth_clock.py::GrowthMarketClock`, P2) bands the market's breadth into
three states. The doctrine fractals the cycle into three scales (§0 序章): this is the THEME scale — it
reads P5b's per-group breadth signals (`alpha/features/theme_breadth.py::ThemeBreadthReading`) and places
each sector/theme group on the §1.2 lifecycle:

  emerging       -- breadth rising off a low base + leaders leading (rs_dispersion WIDE): 内行与先手建仓,龙头浮现.
  institutional  -- broad participation, breadth + RS trending up together: 机构接力,本稿主战场.
  public_laggard -- laggards catching up = rs_dispersion COMPRESSING while breadth still high: the laggard_timer.
  exhaustion     -- breadth rolling over + RS trend down: 轮动加速,兑现不再推动股价.

§1.2 reads COMPOSITION not sentiment — 持仓构成,现在是谁在买 — expressed through the breadth signals P5b
exposes, never a price band. The tokens are Option-B scale-typed (`theme:emerging` …), the sibling of P2's
`market:confirmed_uptrend` and the stock clock's future `stock:advance`.

Cross-reading, not memoryless. P1/P2's HIGH bug was a per-day classifier that FLICKERS (the ABAB day-parity
oscillation `GrowthMarketClock` fixed with an FTD anchor). This clock does not repeat it: the state is a
deterministic machine replayed FORWARD over each group's determined-reading history + today — a PURE
function of `(history, today)` with no hidden mutable state (recomputable; same inputs -> same read). The
lifecycle is a forward progression, which gives hysteresis structurally (each state persists until the next
transition fires); two extra guards mirror the market clock: a cycle-PEAK dispersion anchor (public_laggard
rings only on real compression from a wide peak — the FTD-anchor analog) and a sustained-RUN guard on the
terminal `-> exhaustion` flip (an isolated weak reading cannot un-confirm institutional — the DEEP_MIN_DAYS
analog). Abstain is explicit — an undetermined, warm-up, or dormant group is ABSENT from the read, never a
fabricated phase (the doctrine's §0.2 禁止补格 discipline).

This is a READ (an s_t-side label), never written back into H (SSOT), exactly like GCycle / GrowthMarketClock.
The §1.4 clock_cadence action wiring (theme phase -> appetite/guard) and the per-candidate narrative-cluster
half are separate deferred steps — see docs/superpowers/specs/2026-07-13-theme-clock-consumer-design.md §6.

Two scales live here (do not mix): `pct_above_200dma` / `breadth_trend` are FRACTIONS in [0,1]; the RS
fields (`rs_dispersion`, `rs_trend`, `laggard_rs_mean`) are cross-sectional PERCENTILES in [0,100].
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from alpha.features.theme_breadth_types import GroupBreadthReading, ThemeBreadthReading
from alpha.state.market import MarketState

# ── thresholds (文献值待verdict校准; no Refiner-calibration path, same posture as GrowthMarketClock) ────
# breadth-fraction scale [0,1]:
BREADTH_HIGH = 0.55           # broad participation: institutional/public_laggard hold breadth at/above this
BREADTH_LOW_BASE = 0.35       # a low base: emerging rises off below-this; exhaustion resets to dormant below it
BREADTH_RISING = 0.05         # breadth_trend >= this => participation broadening (rising)
BREADTH_ROLLING_OVER = -0.05  # breadth_trend <= this => participation rolling over
# RS-percentile scale [0,100]:
RS_RISING = 2.0               # rs_trend >= this => the group gaining relative strength vs the whole tape
RS_FALLING = -2.0             # rs_trend <= this => the group losing relative strength (exhaustion leg)
DISPERSION_WIDE = 20.0        # rs_dispersion >= this => leaders dominate (emerging signature / a real peak)
DISPERSION_COMPRESS = 15.0    # disp <= peak - this => compressed from the cycle peak (the laggard_timer tell)
# machine guards:
EXHAUSTION_CONFIRM = 2        # consecutive readings of (roll-over AND RS down) before -> exhaustion (no-flicker)
MIN_HISTORY = 3               # min determined readings (incl. today) before a group is classified (else abstain)

_CLASSIFIED_CONF = 0.6        # confidence for a placed group (warm-up already abstains, so every read is full)

# internal machine states — DORMANT is pre-cycle / no-active-theme (abstain); the four §1.2 phases map to tokens.
_DORMANT, _EMERGING, _INSTITUTIONAL, _PUBLIC_LAGGARD, _EXHAUSTION = (
    "dormant", "emerging", "institutional", "public_laggard", "exhaustion")
_TOKENS = {                                        # machine state -> exposed Option-B token (DORMANT: absent)
    _EMERGING: "theme:emerging",
    _INSTITUTIONAL: "theme:institutional",
    _PUBLIC_LAGGARD: "theme:public_laggard",
    _EXHAUSTION: "theme:exhaustion",
}


@dataclass(frozen=True)
class ThemeLifecycleRead:
    """One group's lifecycle placement (an s_t-side label; parallels `RegimeRead`, not written into H)."""
    group: str
    phase: str            # one of the four `theme:` tokens
    confidence: float     # [0,1]


# ── per-reading predicates (None-guarded: a missing signal never satisfies its leg) ──────────────────

def _broad(breadth: float | None) -> bool:
    return breadth is not None and breadth >= BREADTH_HIGH


def _low_base(breadth: float | None) -> bool:
    return breadth is not None and breadth < BREADTH_LOW_BASE


def _rising(bt: float | None) -> bool:
    return bt is not None and bt >= BREADTH_RISING


def _rolling_over(bt: float | None) -> bool:
    return bt is not None and bt <= BREADTH_ROLLING_OVER


def _rs_up(rt: float | None) -> bool:
    return rt is not None and rt >= RS_RISING


def _rs_down(rt: float | None) -> bool:
    return rt is not None and rt <= RS_FALLING


def _wide(disp: float | None) -> bool:
    return disp is not None and disp >= DISPERSION_WIDE


def _run_theme_machine(readings: Sequence[GroupBreadthReading]) -> str:
    """Replay the lifecycle machine forward over the chronological `readings` (a single group's DETERMINED
    readings, history + today) and return the state after the last one. Pure: depends only on `readings`.

    Start at `dormant` (no active theme). A cycle begins when breadth rises off a low base with leaders
    leading (-> emerging) or the group is already broadly bought (-> institutional, the arrive-late path).
    `peak` tracks the max dispersion SINCE the cycle began (updated only while emerging/institutional,
    frozen thereafter) — the leaders-dominate anchor from which the laggard_timer measures compression
    (the FTD-anchor analog: a real peak, not nothing). `exh_run` counts CONSECUTIVE readings meeting the
    exhaustion signal (roll-over AND RS down); the `-> exhaustion` flip needs a full EXHAUSTION_CONFIRM
    run, so a single weak reading cannot un-confirm institutional (the DEEP_MIN_DAYS analog / no-flicker).
    """
    state = _DORMANT
    peak = 0.0                                     # cycle-peak rs_dispersion (leaders-dominate anchor)
    exh_run = 0                                    # consecutive readings meeting the exhaustion signal
    for r in readings:
        breadth, bt, rt, disp = r.pct_above_200dma, r.breadth_trend, r.rs_trend, r.rs_dispersion
        if state in (_EMERGING, _INSTITUTIONAL) and disp is not None:
            peak = max(peak, disp)                  # accumulate the peak while leaders can still dominate
        exh_run = exh_run + 1 if (_rolling_over(bt) and _rs_down(rt)) else 0

        if state == _DORMANT:
            if _rising(bt) and _wide(disp) and not _broad(breadth):
                state, peak = _EMERGING, disp       # rising off a low base, leaders leading
            elif _broad(breadth) and _rs_up(rt):
                state, peak = _INSTITUTIONAL, (disp if disp is not None else 0.0)  # arrive-late: already broad
        elif state == _EMERGING:
            if _broad(breadth) and not _rolling_over(bt) and _rs_up(rt):
                state = _INSTITUTIONAL              # participation broadened
            elif _low_base(breadth) and not _rising(bt):
                state, peak = _DORMANT, 0.0         # emergence fizzled (not "exhaustion")
        elif state == _INSTITUTIONAL:
            if exh_run >= EXHAUSTION_CONFIRM:
                state = _EXHAUSTION                 # sustained roll-over + RS down
            elif (_broad(breadth) and disp is not None
                  and peak >= DISPERSION_WIDE and disp <= peak - DISPERSION_COMPRESS):
                state = _PUBLIC_LAGGARD             # laggard_timer: compression from a wide peak, breadth high
        elif state == _PUBLIC_LAGGARD:
            if exh_run >= EXHAUSTION_CONFIRM:
                state = _EXHAUSTION                 # the late warning holds until the roll-over confirms
        elif state == _EXHAUSTION:
            if _low_base(breadth):
                state, peak = _DORMANT, 0.0         # theme over; ready for a fresh cycle
    return state


def theme_lifecycle(history: Sequence[ThemeBreadthReading],
                    today: ThemeBreadthReading) -> dict[str, ThemeLifecycleRead]:
    """Classify each group present-and-determined in `today`, given its strictly-prior chronological
    `history` of `ThemeBreadthReading`s. For each such group, replay the machine over that group's
    determined readings (across history, undetermined days dropped like P2 drops 0/0 feed-outage days) +
    today's reading.

    A group ABSTAINS — is ABSENT from the returned mapping, never a fabricated phase — when it is
    undetermined today, has fewer than MIN_HISTORY determined readings (warm-up: no trajectory), or the
    machine ends in `dormant` (determined but no active theme). Returned reads are keyed by group; only
    placed groups (one of the four §1.2 phases) appear. Pure function of `(history, today)`."""
    result: dict[str, ThemeLifecycleRead] = {}
    for group, reading in today.groups.items():
        if not reading.determined:
            continue                                # abstain: cannot read a group we cannot see today
        series = [h.groups[group] for h in history
                  if group in h.groups and h.groups[group].determined]
        series.append(reading)
        if len(series) < MIN_HISTORY:
            continue                                # abstain: warm-up, no trajectory to anchor a lifecycle
        token = _TOKENS.get(_run_theme_machine(series))
        if token is None:
            continue                                # abstain: dormant / no active theme (never fabricate)
        result[group] = ThemeLifecycleRead(group=group, phase=token, confidence=_CLASSIFIED_CONF)
    return result


class GrowthThemeClock:
    """Read-only per-group theme-lifecycle classifier (the market clock's theme-scale sibling).
    Deterministic, oracle-auditable. `read()` returns per-group `ThemeLifecycleRead`s; it writes nothing
    into H (SSOT)."""

    def read(self, history: Sequence[MarketState],
             today: MarketState) -> dict[str, ThemeLifecycleRead]:
        """Classify each theme group as of `today`, reading the additive `MarketState.theme_breadth`
        bundle (P5b feed) threaded onto each state — mirrors `GrowthMarketClock.read(history, today)`.

        `today.theme_breadth is None` (the default-off state: no feed threaded, or an off-cadence day per
        §1.4 `clock_cadence`) ⇒ **abstain on every group** (empty mapping) — byte-identical to a run with
        no theme clock. History states whose `theme_breadth` is None are simply skipped (an off-cadence
        day is not a reading), the natural analog of P2 dropping a feed-outage day. Delegates the per-group
        replay to `theme_lifecycle`."""
        if today.theme_breadth is None:
            return {}
        prior = [s.theme_breadth for s in history if s.theme_breadth is not None]
        return theme_lifecycle(prior, today.theme_breadth)
