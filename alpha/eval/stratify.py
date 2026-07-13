"""Regime-stratified eval (P6 spec §2). Report metrics per the regime read ON THE DECISION DAY, so
"does HCH beat Hexpert" is answerable per-regime — the tool that lets the growth market-clock thresholds
+ the §5 dead-band be calibrated against realized per-state outcomes.

The regime label per date comes from the SHARED decision-day market (identical across arms — same
source/window/history; MarketState and the regime read are s_t-side, independent of H, unchanged even
across a breaker rollback), so stratifying the paired daily-diff series by decision-day regime is
symmetric by construction (verdict symmetry preserved). Key functions mirror `guard/screen.py`'s
vocabulary dispatch exactly."""
from __future__ import annotations

from collections.abc import Sequence
from datetime import date as Date
from typing import Callable

from alpha.eval.metrics import EvalReport
from alpha.eval.stats import StatVerdict, daily_series, verdict
from alpha.eval.trajectory import Trajectory, report_from_trajectory
from alpha.regime.classifier import GCycle
from alpha.regime.growth_clock import GrowthMarketClock
from alpha.state.market import MarketState

RegimeKey = Callable[[MarketState, Sequence[MarketState]], str]


def momo_phase(market: MarketState, history: Sequence[MarketState]) -> str:
    """Momo six-phase read (single-day GCycle; `history` ignored — GCycle is memoryless)."""
    return GCycle().read(market).phase


def growth_clock_phase(market: MarketState, history: Sequence[MarketState]) -> str:
    """Growth three-state market-clock read (`market:{confirmed_uptrend|under_pressure|correction}`)."""
    return GrowthMarketClock().read(history, market).phase


def regime_key_for(vocabulary: str) -> RegimeKey:
    """Pick the regime reader the way guard/screen.py does: growth -> the three-state clock, else momo."""
    return growth_clock_phase if vocabulary == "growth" else momo_phase


def label_steps(traj: Trajectory, key_fn: RegimeKey) -> dict[Date, str]:
    """Map each step's decision date -> its decision-day regime label, replaying history forward
    (history = the markets of strictly-prior steps). Faithful to the live read: both accumulate the same
    window-local strictly-prior MarketStates, starting empty at the window's first day."""
    labels: dict[Date, str] = {}
    hist: list[MarketState] = []
    for step in traj.steps:
        labels[step.date] = key_fn(step.market, hist)
        hist.append(step.market)
    return labels


def stratified_reports(traj: Trajectory, key_fn: RegimeKey, horizon: int = 2) -> dict[str, EvalReport]:
    """Bucket scored steps by decision-day regime label; one EvalReport per label."""
    labels = label_steps(traj, key_fn)
    buckets: dict[str, list] = {}
    for step in traj.scored_steps():
        buckets.setdefault(labels[step.date], []).append(step)
    return {lab: report_from_trajectory(Trajectory(steps=steps), horizon=horizon)
            for lab, steps in buckets.items()}


def stratified_verdicts(hch_traj: Trajectory, hexpert_traj: Trajectory, key_fn: RegimeKey,
                        **verdict_kwargs) -> dict[str, StatVerdict]:
    """Per-regime paired day-level HCH-Hexpert verdict. Stratifies the paired daily-diff series by the
    decision-day regime (labels from the shared markets -> symmetric), then runs `verdict()` per bucket.
    This answers 'does HCH beat Hexpert per-regime' and calibrates the growth-clock states."""
    labels = label_steps(hch_traj, key_fn)
    da, db = dict(daily_series(hch_traj)), dict(daily_series(hexpert_traj))
    by_label: dict[str, list[float]] = {}
    for d in sorted(set(da) & set(db)):
        by_label.setdefault(labels[d], []).append(da[d] - db[d])
    return {lab: verdict(diffs, **verdict_kwargs) for lab, diffs in by_label.items()}
