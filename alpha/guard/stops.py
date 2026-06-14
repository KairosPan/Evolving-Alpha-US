from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from alpha.regime.classifier import RegimeRead

StopKind = Literal["form", "regime", "time"]


@dataclass(frozen=True)
class Position:
    symbol: str
    entry_price: float
    current_price: float
    stop_price: float
    days_held: int
    narrative: str = ""


@dataclass(frozen=True)
class StopSignal:
    symbol: str
    kind: StopKind
    reason: str


def stop_signals(position: Position, regime: RegimeRead, max_hold_days: int) -> list[StopSignal]:
    """Stop discipline: form (price <= stop), regime (tape turned backside), time (held past plan)."""
    out: list[StopSignal] = []
    if position.current_price <= position.stop_price:
        out.append(StopSignal(position.symbol, "form",
                              f"price {position.current_price} <= stop {position.stop_price}"))
    if not regime.frontside:
        out.append(StopSignal(position.symbol, "regime",
                              f"regime backside ({regime.phase}); exit / no add"))
    if position.days_held > max_hold_days:
        out.append(StopSignal(position.symbol, "time",
                              f"held {position.days_held} > max {max_hold_days} days"))
    return out
