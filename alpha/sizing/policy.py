from __future__ import annotations

from collections.abc import Mapping
from typing import Callable

from alpha.eval.decision import DecisionPackage, Portfolio
from alpha.regime.classifier import GCycle
from alpha.sizing.action import candidate_action, derisk_tier
from alpha.sizing.correlation import Pick
from alpha.sizing.float_size import float_capped_tier
from alpha.sizing.portfolio import plan_portfolio
from alpha.sizing.position import SizingConfig, size_tier
from alpha.state.market import MarketState

_DEFAULT_CONFIG = SizingConfig()

# StockSnapshot.free_float (US-3d) is in MILLIONS of shares; the float feed + float-aware sizing math work
# in RAW shares. This is the one seam that reconciles the legacy millions convention to shares.
_SHARES_PER_MILLION = 1_000_000.0


def _float_map_from_universe(universe) -> dict[str, float]:
    """Per-symbol free float in RAW SHARES from a CandidateUniverse (StockSnapshot.free_float millions ->
    x1e6). Names with no float are skipped (absent -> no cap, byte-identical for that name)."""
    out: dict[str, float] = {}
    for s in universe.all():
        ff = getattr(s, "free_float", None)
        if ff is not None:
            out[s.symbol] = ff * _SHARES_PER_MILLION
    return out


def size_decision(decision: DecisionPackage, *, state: MarketState,
                  config: SizingConfig = _DEFAULT_CONFIG,
                  floats: Mapping[str, float] | None = None) -> DecisionPackage:
    """Apply L3 sizing to a (already L4-guarded) DecisionPackage: assign each KEPT candidate a size_tier
    from confidence x regime risk_gate, and attach the portfolio plan (exposure budget + correlated
    groups). VERDICT-NEUTRAL: scoring is equal-weighted and never reads size_tier/portfolio, so this only
    enriches the human-confirmation surface (+ the DAgger record). FIREWALL-CLEAN: reads only the decision
    + state (no source fetch). Frozen models -> rebuilt via model_copy.

    The correlation key is candidate.narrative (the sympathy/theme tag the agent emits, US-5): same
    narrative -> one netted bet, so the portfolio reflects the "one correlated bet" doctrine. Untagged
    ("") names stand alone. DEFERRED: fill_feasibility (needs the intraday inference path — no eval/fill
    module), per-candidate taboo_check (the L4 guard drops vetoed candidates rather than soft-annotating),
    and a per-narrative-line regime read (needs theme-level market breadth we don't have offline).

    P0.6 (spec 2026-07-13-p06): each candidate's tier is mapped through `derisk_tier(action, tier)` so a
    trim/exit recommendation reduces to core / flat ('持仓降至核心仓位'). Holdings aren't modelled yet,
    so `candidate_action` defaults to `enter` (byte-identical). The Portfolio exposure plan counts only
    `enter` names — a derisk on a held name adds no NEW exposure.

    P5b float-aware sizing (spec 2026-07-13-p5b-float-feed): `floats` maps symbol -> free float in RAW
    shares. When provided, each tier is further capped for a small-float name (liquidity-aware; the
    portfolio exposure reflects the same caps). ADDITIVE / DEFAULT-OFF: floats=None -> the cap branch is
    never entered -> byte-identical. VERDICT-NEUTRAL: the cap only touches size_tier/portfolio, which
    scoring never reads.
    """
    regime = decision.regime or GCycle().read(state)
    rg = regime.risk_gate

    def _tier(c) -> str:
        t = derisk_tier(candidate_action(c), size_tier(c.confidence, rg))
        if floats is not None:
            t = float_capped_tier(t, floats.get(c.symbol), config)
        return t

    sized = [c.model_copy(update={"size_tier": _tier(c)}) for c in decision.candidates]
    plan = plan_portfolio([Pick(symbol=c.symbol, narrative=c.narrative, confidence=c.confidence)
                           for c in sized if candidate_action(c) == "enter"], rg, config, floats=floats)
    portfolio = Portfolio(total_exposure_budget=plan.total_exposure_budget,
                          correlated_groups=plan.correlated_groups,
                          total_exposure=plan.total_exposure, capped=plan.capped)
    return decision.model_copy(update={"candidates": sized, "portfolio": portfolio})


class SizingPolicy:
    """Composable L3 sizing decorator: wraps any DecisionPolicy, runs it, then sizes the result. Compose
    OUTSIDE GuardedPolicy so it sizes the post-veto survivors: SizingPolicy(GuardedPolicy(agent, source)).

    `float_aware` (P5b; default False -> byte-identical) opts in to float-aware sizing: when True the float
    map is derived from the CandidateUniverse this policy already receives (StockSnapshot.free_float) and
    threaded into size_decision, so a small-float survivor sizes smaller. The decorator ORDER (size the
    post-veto survivors) is unchanged; float_aware is an orthogonal flag."""

    def __init__(self, inner, *, float_aware: bool = False,
                 config: SizingConfig = _DEFAULT_CONFIG) -> None:
        self._inner = inner
        self._float_aware = float_aware
        self._config = config

    def decide(self, state: MarketState, universe, *,
              collect: Callable[[dict], None] | None = None) -> DecisionPackage:
        # `collect`: D3 prompt-audit pass-through (default None = byte-identical); see GuardedPolicy.decide.
        kw = {} if collect is None else {"collect": collect}
        decision = self._inner.decide(state, universe, **kw)
        floats = _float_map_from_universe(universe) if self._float_aware else None
        return size_decision(decision, state=state, config=self._config, floats=floats)
