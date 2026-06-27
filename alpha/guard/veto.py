from __future__ import annotations

from dataclasses import dataclass

from alpha.regime.classifier import RegimeRead

RISK_OFF_THRESHOLD = 0.2     # below this risk_gate, do not chase new longs (immutable-core)


@dataclass(frozen=True)
class CandidateContext:
    """Inputs the guard needs to clear a NEW entry. Data flags default False; US-3 sets them from
    intraday/fundamental sources (the mechanism is here; the data is later)."""
    symbol: str
    regime: RegimeRead
    reverse_split_pending: bool = False     # from US-0 corp_actions (PIT by announcement)
    dilution: bool = False                  # ATM/shelf/offering (US-3)
    halt_then_dump: bool = False            # (US-3 intraday)
    going_concern: bool = False             # (US-3 fundamental)
    regulatory: bool = False                # SEC/exchange action (US-3)
    ssr: bool = False                       # short-sale restriction active (US-3)
    episode_taboo: bool = False             # from §6: strong PIT-masked nuke history for this symbol


@dataclass(frozen=True)
class VetoVerdict:
    vetoed: bool
    reasons: list[str]


def veto(ctx: CandidateContext) -> VetoVerdict:
    """Hard veto on a new entry (overrides the agent). Accumulates all firing reasons."""
    reasons: list[str] = []
    # no chasing in risk-off OR on the backside (new entries only on the frontside) — mirrors the
    # regime stop in stops.py (stops exit on backside; veto blocks new entries on backside).
    if ctx.regime.risk_gate < RISK_OFF_THRESHOLD:
        reasons.append(f"risk-off regime (risk_gate {ctx.regime.risk_gate:.2f} < {RISK_OFF_THRESHOLD}): no chasing")
    elif not ctx.regime.frontside:
        reasons.append(f"backside regime ({ctx.regime.phase}): no new entries")
    if ctx.reverse_split_pending:
        reasons.append("reverse split pending")
    if ctx.dilution:
        reasons.append("dilution / offering / ATM-shelf")
    if ctx.halt_then_dump:
        reasons.append("halt-then-dump")
    if ctx.going_concern:
        reasons.append("going-concern risk")
    if ctx.regulatory:
        reasons.append("regulatory / SEC action")
    if ctx.ssr:
        reasons.append("short-sale restriction active (SSR): don't fight it")
    if ctx.episode_taboo:
        reasons.append("episode taboo: strong nuke history (don't chase)")
    return VetoVerdict(vetoed=bool(reasons), reasons=reasons)
