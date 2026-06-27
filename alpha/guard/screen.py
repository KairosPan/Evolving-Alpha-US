from __future__ import annotations

from datetime import date as Date

import pandas as pd

from alpha.data.calendar import prev_trading_day
from alpha.data.corp_actions import has_dilution_filing, has_reverse_split_pending
from alpha.data.firewall import AsOfGuard
from alpha.data.source import GuardedSource
from alpha.eval.decision import DecisionPackage
from alpha.guard.veto import CandidateContext, veto
from alpha.memory.aggregate import is_episode_taboo, summarize
from alpha.regime.classifier import GCycle
from alpha.state.market import MarketState

SSR_DROP_PCT = -10.0   # Reg SHO Rule 201: a >=10% prior-day decline restricts short sales the next session
HALT_SPIKE_PCT = 0.15   # an intraday high >=15% above prior close ~ a LULD halt-up (Tier-1 band) event


def _num(value) -> float | None:
    """None-and-NaN-safe scalar float (snapshot rows can carry NaN)."""
    return None if value is None or pd.isna(value) else float(value)


def halt_then_dump_proxy(row) -> bool:
    """Daily-OHLC proxy for a halt-then-dump: the name spiked intraday >= HALT_SPIKE_PCT above its prior
    close (a likely LULD halt-up) but round-tripped to close at/below the prior close — a failed spike, do
    not chase it long. `row` is a daily-snapshot record (dict) or None. Real intraday LULD halts/halt-count
    need a tick feed (deferred); this is the daily-cadence proxy. Missing/NaN data -> False (never fabricated).

    Distinct from failed_breakout (gap-up at the OPEN that closes red): this keys on the intraday HIGH
    spike (the halt-up signature), so it also catches names that opened flat, spiked, and dumped."""
    if row is None:
        return False
    prev, high, close = _num(row.get("prev_close")), _num(row.get("high")), _num(row.get("close"))
    if prev is None or high is None or close is None or prev <= 0:
        return False
    spiked = (high - prev) / prev >= HALT_SPIKE_PCT
    dumped = close <= prev
    return spiked and dumped


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


def screen_decision(decision: DecisionPackage, *, source, state: MarketState, episode_store=None) -> DecisionPackage:
    """Apply the L4 hard veto to a freshly-produced DecisionPackage: DROP candidates the immutable-core
    guard blocks (SSR / reverse-split-pending / risk-off / backside regime) — plus, when an `episode_store`
    is wired, an §6 episode-taboo (a symbol with a strong PIT-masked nuke history). Record dropped reasons
    in key_risks, and populate the structured regime. Frozen models -> rebuilt via model_copy.

    PIT-safe: all data reads go through a fresh GuardedSource(AsOfGuard(state.date)); SSR reads only
    prior-day bars (< as_of) and corp actions are announce-keyed (<= as_of); episode recall is masked at
    `for_asof(state.date)`. Vetoed candidates are dropped (never entered/scored) rather than annotated — a
    kept-but-failed candidate would still be scored as an entry by the drivers, defeating the hard veto."""
    as_of = state.date
    guarded = GuardedSource(source, AsOfGuard(as_of))
    regime = GCycle().read(state)
    corp = guarded.corporate_actions_known(as_of)
    snap = guarded.daily_snapshot(as_of)               # day's OHLC for the halt-then-dump proxy (guard-safe)
    rows = ({str(r["symbol"]): r for r in snap.to_dict("records")}
            if snap is not None and not snap.empty else {})
    taboo_stats = (summarize(episode_store.for_asof(as_of, limit=None), key=lambda e: e.symbol)
                   if episode_store is not None else {})   # limit=None: full PIT history (past the 50-cap)
    kept, notes = [], []
    for c in decision.candidates:
        ctx = CandidateContext(symbol=c.symbol, regime=regime,
                               ssr=ssr_active(guarded, c.symbol, as_of),
                               reverse_split_pending=has_reverse_split_pending(corp, c.symbol, as_of),
                               dilution=has_dilution_filing(corp, c.symbol, as_of),
                               halt_then_dump=halt_then_dump_proxy(rows.get(c.symbol)),
                               episode_taboo=is_episode_taboo(taboo_stats.get(c.symbol)))
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

    def __init__(self, inner, source, *, episode_store=None) -> None:
        self._inner = inner
        self._source = source
        self._episode_store = episode_store

    def decide(self, state: MarketState, universe) -> DecisionPackage:
        decision = self._inner.decide(state, universe)
        return screen_decision(decision, source=self._source, state=state,
                               episode_store=self._episode_store)
