from __future__ import annotations

from datetime import date as Date

import pandas as pd

from alpha.data.calendar import prev_trading_day
from alpha.data.corp_actions import has_reverse_split_pending
from alpha.data.firewall import AsOfGuard
from alpha.data.source import GuardedSource
from alpha.eval.decision import DecisionPackage
from alpha.guard.veto import CandidateContext, veto
from alpha.regime.classifier import GCycle
from alpha.state.market import MarketState

SSR_DROP_PCT = -10.0   # Reg SHO Rule 201: a >=10% prior-day decline restricts short sales the next session


def _prior_day_pct(source, symbol: str, prev: Date) -> float | None:
    """Close-to-close % change for `symbol` ENDING at `prev` (the trading day before the decision day).
    Missing/short data -> None (never fabricate). Reads only bars dated <= prev (firewall-safe)."""
    cal = source.trading_calendar()
    le = [d for d in cal if d <= prev]
    if len(le) < 2:
        return None
    bars = source.daily_bars(symbol, le[-2], prev)
    if bars is None or bars.empty or "date" not in bars.columns:
        return None
    df = bars.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    closes = list(pd.to_numeric(df[df["date"] <= prev].sort_values("date")["close"], errors="coerce").dropna())
    if len(closes) < 2 or closes[-2] == 0:
        return None
    return (closes[-1] - closes[-2]) / closes[-2] * 100.0


def ssr_active(source, symbol: str, as_of: Date) -> bool:
    """Reg SHO Rule 201: True iff `symbol` fell >= 10% (close-to-close) on the PRIOR trading day, so a
    short-sale restriction is in effect on `as_of` (don't chase a one-sided tape). Missing data -> False."""
    prev = prev_trading_day(source.trading_calendar(), as_of)
    if prev is None:
        return False
    pct = _prior_day_pct(source, symbol, prev)
    return pct is not None and pct <= SSR_DROP_PCT


def screen_decision(decision: DecisionPackage, *, source, state: MarketState) -> DecisionPackage:
    """Apply the L4 hard veto to a freshly-produced DecisionPackage: DROP candidates the immutable-core
    guard blocks (SSR / reverse-split-pending / risk-off / backside regime), record dropped reasons in
    key_risks, and populate the structured regime. Frozen models -> rebuilt via model_copy.

    PIT-safe: all data reads go through a fresh GuardedSource(AsOfGuard(state.date)); SSR reads only
    prior-day bars (< as_of) and corp actions are announce-keyed (<= as_of). Vetoed candidates are
    dropped (never entered/scored) rather than annotated — a kept-but-failed candidate would still be
    scored as an entry by the drivers, defeating the hard veto."""
    as_of = state.date
    guarded = GuardedSource(source, AsOfGuard(as_of))
    regime = GCycle().read(state)
    corp = guarded.corporate_actions_known(as_of)
    kept, notes = [], []
    for c in decision.candidates:
        ctx = CandidateContext(symbol=c.symbol, regime=regime,
                               ssr=ssr_active(guarded, c.symbol, as_of),
                               reverse_split_pending=has_reverse_split_pending(corp, c.symbol, as_of))
        v = veto(ctx)
        if v.vetoed:
            notes.append(f"vetoed {c.symbol}: {'; '.join(v.reasons)}")
        else:
            kept.append(c)
    update = {"candidates": kept, "regime": regime, "key_risks": list(decision.key_risks) + notes}
    if not kept and decision.candidates:
        update["no_trade_reason"] = decision.no_trade_reason or "all candidates vetoed by L4 guard"
    return decision.model_copy(update=update)


class GuardedPolicy:
    """Composable L4 guard: wraps any DecisionPolicy; runs it, then applies screen_decision so the
    immutable-core hard veto overrides the agent. Works in any driver that calls policy.decide()."""

    def __init__(self, inner, source) -> None:
        self._inner = inner
        self._source = source

    def decide(self, state: MarketState, universe) -> DecisionPackage:
        decision = self._inner.decide(state, universe)
        return screen_decision(decision, source=self._source, state=state)
