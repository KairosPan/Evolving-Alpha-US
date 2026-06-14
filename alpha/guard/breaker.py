from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BreakerConfig:
    """Loss circuit-breaker thresholds (fractions). Seed initial values — evolvable later."""
    max_single_day_loss: float = 0.06       # day P&L worse than -6% -> halt
    max_consecutive_losses: int = 4         # N losing days in a row -> halt
    max_single_name_loss: float = 0.15      # cumulative single-name loss worse than -15% -> halt adds to it


class Breaker:
    """Portfolio loss circuit-breaker. record_day_pnl per closed day; check() before new entries."""

    def __init__(self, config: BreakerConfig | None = None) -> None:
        self._config = config or BreakerConfig()
        self._last_day_pnl: float = 0.0
        self._consecutive_losses: int = 0
        self._mwcb: bool = False
        self._name_pnl: dict[str, float] = {}

    def record_day_pnl(self, pnl: float) -> None:
        self._last_day_pnl = pnl
        if pnl < 0:
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0

    def record_name_pnl(self, symbol: str, pnl: float) -> None:
        """Accumulate per-name P&L (fraction) so a single name's drawdown can halt adds to it."""
        self._name_pnl[symbol] = self._name_pnl.get(symbol, 0.0) + pnl

    def set_mwcb(self, active: bool) -> None:
        """Market-wide circuit breaker event (US-3 index data sets this)."""
        self._mwcb = active

    def check(self) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        if self._last_day_pnl <= -self._config.max_single_day_loss:
            reasons.append(f"single-day loss {self._last_day_pnl:.2%} <= -{self._config.max_single_day_loss:.0%}")
        if self._consecutive_losses >= self._config.max_consecutive_losses:
            reasons.append(f"{self._consecutive_losses} consecutive losing days")
        if self._mwcb:
            reasons.append("MWCB market-wide halt active")
        return (bool(reasons), reasons)

    def check_name(self, symbol: str) -> tuple[bool, list[str]]:
        """Single-name circuit breaker: True if cumulative loss for `symbol` breaches the limit."""
        loss = self._name_pnl.get(symbol, 0.0)
        if loss <= -self._config.max_single_name_loss:
            return (True, [f"single-name {symbol} loss {loss:.2%} <= -{self._config.max_single_name_loss:.0%}"])
        return (False, [])
