"""§1.4 three-clock authority CASCADE — composing the theme (§1.2) + stock (§1.3) clock reads onto the
live growth market-clock (§1.1) veto/appetite surface as a **downward veto cascade**.

The doctrine's §1.4 authority rule (threshold-independent, user-specified):

> 高尺度**否决**低尺度的动作（权威向下），低尺度**不给高尺度打分**。

expressed here as a pure composition:

  market (top, already live) — `GrowthMarketClock` → `RegimeRead(frontside/risk_gate)`, applied by the
      immutable `alpha/guard/veto.py::veto`. This module NEVER touches it; it only ADDS on top.
  theme (middle)            — a candidate's sector/theme phase modulates APPETITE, tighten-only:
      `exhaustion` → VETO (no new entries in the theme); `public_laggard` → cap (laggard_timer, no
      chasing); `emerging` → probe-only; `institutional` → full appetite (主战场, no cap).
  stock (finest)            — a per-candidate LONG-ELIGIBILITY gate (§1.3 只在 advance 做多): only
      `stock:advance` is long-eligible; `base`/`top`/`decline` → VETO; `climax_run` on an advance is a
      REDUCE flag (caps the tier, never an add) but stays eligible.

**Downward-only / safety-only-tightens is STRUCTURAL** (the offerings-swap posture): the cascade returns
only ADDITIONAL veto reasons (OR-ed onto the market veto → a superset) and a tier CAP (a `min` over the
tier weights → the tier can only fall). A lower clock can therefore never LOOSEN a higher gate — it cannot
remove a market veto nor raise a size tier. Abstention (an undetermined theme / an unreadable stock stage)
contributes NOTHING (禁止补格 — no fabricated gate), so a missing read never manufactures a veto.

This is a pure `s_t`-side composition (no source, no I/O); the guard (`alpha/guard/screen.py`) computes the
per-candidate theme phase + stock stage and calls `compose_downward_cascade`, the sizing seam
(`alpha/sizing/policy.py`) reads the attached per-candidate reads and applies `clock_tier_cap`. Everything
is gated behind the `clock_authority` flag (default OFF → this module is never entered → byte-identical).

Threshold posture: the phase→appetite mapping constants are 文献值待verdict校准 (no Refiner-calibration
path — the same posture as the three clocks themselves).
"""
from __future__ import annotations

from dataclasses import dataclass

from alpha.regime.stock_clock import StockStageReading
from alpha.sizing.position import SIZE_TIER_WEIGHT, SizeTier

# ── theme-lifecycle (§1.2) → appetite tier CAP (tighten-only; absent phase = full appetite / no cap) ──
#   institutional = 机构接力，本稿主战场 → full appetite (no cap); public_laggard = laggard_timer 拨响 →
#   half (no chasing laggards); emerging = 内行与先手建仓 → probe-only (early, small); exhaustion = VETO
#   (see _THEME_VETO — a dropped candidate needs no cap). 文献值待verdict校准.
_THEME_TIER_CAP: dict[str, SizeTier] = {
    "theme:emerging": "probe",
    "theme:public_laggard": "core",
}
_THEME_VETO: dict[str, str] = {
    "theme:exhaustion": "theme exhaustion (轮动加速, 兑现不再推动股价): no new entries in this theme",
}

# ── stock-stage (§1.3) → new-entry VETO (只在 advance 做多). advance is the only long-eligible stage;
#   base = 建仓形态未确认 (watch, no entry); top = 放量滞涨 distribution; decline = 破位 below the line. ──
_STOCK_VETO: dict[str, str] = {
    "stock:base": "stock base: not in a confirmed advance (只在 advance 做多)",
    "stock:top": "stock top: distribution (放量滞涨) — no new entry",
    "stock:decline": "stock decline: below the trend line, RS deteriorating — no new entry",
}
# a climax_run on an advance is REDUCE language (§1.3: 减仓不是加仓) — stays long-eligible, caps the tier.
_CLIMAX_TIER_CAP: SizeTier = "core"

_ADVANCE = "stock:advance"


@dataclass(frozen=True)
class ClockCascade:
    """The composed downward-cascade verdict for ONE candidate: the ADDITIONAL tighten-only veto reasons
    (theme + stock gates, applied ON TOP of the immutable market veto), the tightest appetite/stage tier
    cap, and the climax reduce flag. `veto_reasons` only ADD; `tier_cap` only LOWERS — the cascade never
    loosens a higher gate (低尺度不给高尺度打分)."""
    veto_reasons: tuple[str, ...] = ()
    tier_cap: SizeTier | None = None
    reduce_flag: bool = False

    @property
    def vetoed(self) -> bool:
        return bool(self.veto_reasons)


def _tighter(a: SizeTier | None, b: SizeTier | None) -> SizeTier | None:
    """The tighter (smaller-weight) of two tier caps; `None` = no cap (the loosest). A `min` over
    `SIZE_TIER_WEIGHT` → the composed cap can only ever equal or lower each input (tighten-only)."""
    if a is None:
        return b
    if b is None:
        return a
    return a if SIZE_TIER_WEIGHT[a] <= SIZE_TIER_WEIGHT[b] else b


def theme_appetite_cap(theme_phase: str | None) -> SizeTier | None:
    """The §1.2 theme-lifecycle appetite tier cap for a candidate in a theme at `theme_phase`. `None`
    (abstain / institutional / exhaustion) → no cap here. exhaustion is a VETO not a cap (see
    `compose_downward_cascade`); institutional is 主战场 (full appetite)."""
    return _THEME_TIER_CAP.get(theme_phase or "")


def stock_stage_cap(stock_stage: str | None, *, climax_run: bool = False) -> SizeTier | None:
    """The §1.3 stock-stage appetite tier cap. Only `advance` is long-eligible (the other stages VETO →
    dropped, no cap); a `climax_run` on an advance caps at `core` (reduce into strength, never an add)."""
    return _CLIMAX_TIER_CAP if (stock_stage == _ADVANCE and climax_run) else None


def clock_tier_cap(stock_stage: str | None, theme_phase: str | None, *,
                   climax_run: bool = False) -> SizeTier | None:
    """The tightest (tighten-only) appetite/stage tier cap from the per-candidate clock reads the guard
    attached to the Candidate — the SIZING-side consumer. Empty reads (`""`/`None`, the flag-off /
    abstain case) → `None` → NO cap → byte-identical sizing. VERDICT-NEUTRAL (touches only size_tier)."""
    return _tighter(theme_appetite_cap(theme_phase), stock_stage_cap(stock_stage, climax_run=climax_run))


def compose_downward_cascade(*, theme_phase: str | None,
                             stock: StockStageReading | None) -> ClockCascade:
    """Compose the theme (middle) + stock (finest) reads into the §1.4 downward veto cascade, applied ON
    TOP of the immutable market veto (the top gate, handled by `veto()`). Additive/tighten-only: it can
    only ADD veto reasons or LOWER the tier cap, never loosen a higher gate (低尺度不给高尺度打分).

    - theme `exhaustion` → VETO; `emerging`/`public_laggard` → a tier cap; `institutional`/absent → full.
    - stock `base`/`top`/`decline` → VETO (只在 advance 做多); `advance` → eligible; advance+`climax_run`
      → the reduce cap + `reduce_flag` (never an add).
    Abstention (`theme_phase is None` / `stock is None`) contributes nothing — 禁止补格."""
    reasons: list[str] = []
    if theme_phase in _THEME_VETO:
        reasons.append(_THEME_VETO[theme_phase])
    stage = stock.stage if stock is not None else None
    climax = bool(stock is not None and stock.climax_run)
    if stage in _STOCK_VETO:
        reasons.append(_STOCK_VETO[stage])
    return ClockCascade(
        veto_reasons=tuple(reasons),
        tier_cap=_tighter(theme_appetite_cap(theme_phase), stock_stage_cap(stage, climax_run=climax)),
        reduce_flag=bool(stage == _ADVANCE and climax),
    )
