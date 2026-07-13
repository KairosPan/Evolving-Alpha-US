from __future__ import annotations

from dataclasses import dataclass

from alpha.state.market import MarketState


@dataclass(frozen=True)
class RegimeRead:
    """G_cycle output (an s_t-side label, NOT written back into H — SSOT)."""
    phase: str            # one of the canonical 6 US phases
    confidence: float     # [0,1]
    frontside: bool       # global frontside (risk-on) vs backside (every pop sold)
    risk_gate: float      # [0,1] speculative risk appetite / size multiplier


_FRONTSIDE = {"recovery", "ignition", "trend"}


class GCycle:
    """Read-only regime classifier (the G_cycle sub-agent). Deterministic, oracle-auditable rules.

    SSOT: read() returns a RegimeRead; this class has NO method that writes a phase into a harness.

    The phase thresholds below are FIXED literals: no edit path (metatool / try_apply_op) touches them,
    so the Refiner cannot calibrate them in place. Threading them through a declared H-params object was
    the US-2 intent and is the P2 conditional sub-item — DEFERRED (kairos-mining §4.5, verified drift:
    the earlier docstring claimed a Refiner-editable surface that does not exist). Growth-pack runs read
    the three-state successor `alpha/regime/growth_clock.py::GrowthMarketClock` instead (P2); its
    thresholds are likewise fixed named constants 待verdict校准. Per-narrative-line phases need theme
    tagging (P5). Here GCycle reads the GLOBAL mother-state for the momo pack.
    """

    def read(self, state: MarketState) -> RegimeRead:
        sn = state.sentiment_norm
        ft = state.follow_through_rate if state.follow_through_rate is not None else 0.0
        fb_rate = state.failed_breakout_count / state.gainer_count if state.gainer_count else (
            1.0 if state.failed_breakout_count else 0.0)
        if sn is not None:
            proxy = sn
            confidence = 0.7
        else:
            denom = state.gainer_count + state.loser_count
            proxy = (state.gainer_count / denom) if denom else 0.0
            confidence = 0.4                       # no regime-relative normalization yet

        # phase rules (objective; ordered by tape strength). fb_rate / follow-through split
        # frontside trend from backside distribution at similar strength.
        if proxy < 0.2:
            phase = "washout"
        elif proxy < 0.4:
            phase = "recovery"
        elif proxy < 0.6:
            phase = "ignition" if fb_rate < 0.4 else "distribution"
        else:  # strong tape
            if fb_rate >= 0.4 or ft < 0.4:
                phase = "flush" if (state.loser_count > state.gainer_count) else "distribution"
            else:
                phase = "trend"

        # Without regime context (sentiment_norm None) we can't be confidently risk-on, so cap the
        # size-multiplier output at neutral (phase banding still uses the raw proxy above).
        risk_gate = proxy if sn is not None else min(proxy, 0.5)
        return RegimeRead(phase=phase, confidence=confidence,
                          frontside=phase in _FRONTSIDE, risk_gate=risk_gate)
