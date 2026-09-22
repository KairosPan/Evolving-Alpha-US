"""The intent: what a strategy says the book should hold at a day's close.

One shape, validated once, whoever produced it: ``{"targets": [{"symbol", "weight"}, ...],
"note": optional}``. Weights are fractions of the book's value — each in [0, 1], summing to at
most 1, the remainder cash; an empty list means go flat. The book fills an intent at the NEXT
trading day's open (docs/backtest-rules.md rule 4), never at the close it was decided on.

The one producer today is a strategy's ``signal.py`` (``load_signal``): ``signal(source, day)``
with the GuardedSource for ``day`` — the engine hands it the guard, the strategy just reads — or
``signal(source, day, holdings)`` when the rule wants to know what the book holds (stops, holding
periods). ``strategies/`` is not a package, so the module is loaded by file path with the strategy
directory on ``sys.path`` for the duration of the import (a strategy may import a sibling module).
"""
from __future__ import annotations

import importlib.util
import inspect
import math
import re
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date as Date
from pathlib import Path
from typing import Any

MAX_TARGETS = 200
MAX_NOTE_CHARS = 500
WEIGHT_TOL = 1e-9
# Alpaca-style tickers: letters and digits, with '.', '-' and '/' for share classes and units.
SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9./-]{0,15}$")
SIGNAL_FILE = "signal.py"


class IntentError(ValueError):
    """A malformed intent, or a signal that could not be loaded or did not answer."""


@dataclass(frozen=True)
class Target:
    symbol: str
    weight: float


@dataclass(frozen=True)
class Intent:
    as_of: Date
    targets: tuple[Target, ...]
    note: str | None = None

    @property
    def gross(self) -> float:
        return float(sum(t.weight for t in self.targets))

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "as_of": self.as_of.isoformat(),
            "targets": [{"symbol": t.symbol, "weight": t.weight} for t in self.targets],
        }
        if self.note is not None:
            out["note"] = self.note
        return out


def _weight(raw: Any, symbol: str) -> float:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise IntentError(f"target {symbol}: weight must be a number, got {type(raw).__name__}")
    w = float(raw)
    if not math.isfinite(w):
        raise IntentError(f"target {symbol}: weight must be finite")
    if w < 0.0 or w > 1.0 + WEIGHT_TOL:
        raise IntentError(f"target {symbol}: weight {w} outside [0, 1]")
    return min(w, 1.0)


def validate_intent(raw: Any, as_of: Date) -> Intent:
    """Normalize and check one intent. Symbols are upper-cased; a duplicate, a bad weight, a
    gross above 1, or more than MAX_TARGETS names is refused. Unknown keys are ignored."""
    if not isinstance(raw, Mapping):
        raise IntentError(f"intent must be a mapping, got {type(raw).__name__}")
    targets_raw = raw.get("targets")
    if not isinstance(targets_raw, (list, tuple)):
        raise IntentError("intent needs a 'targets' list")
    if len(targets_raw) > MAX_TARGETS:
        raise IntentError(f"{len(targets_raw)} targets, more than MAX_TARGETS={MAX_TARGETS}")
    seen: set[str] = set()
    targets: list[Target] = []
    for i, item in enumerate(targets_raw):
        if not isinstance(item, Mapping):
            raise IntentError(f"target #{i} must be a mapping")
        sym = item.get("symbol")
        if not isinstance(sym, str) or not sym.strip():
            raise IntentError(f"target #{i}: symbol must be a non-empty string")
        sym = sym.strip().upper()
        if not SYMBOL_RE.match(sym):
            raise IntentError(f"target #{i}: {sym!r} is not a ticker")
        if sym in seen:
            raise IntentError(f"target {sym} listed twice")
        seen.add(sym)
        targets.append(Target(sym, _weight(item.get("weight"), sym)))
    gross = sum(t.weight for t in targets)
    if gross > 1.0 + WEIGHT_TOL:
        raise IntentError(f"weights sum to {gross:.6f}, more than 1")
    note = raw.get("note")
    if note is not None:
        if not isinstance(note, str):
            raise IntentError("note must be a string")
        note = note[:MAX_NOTE_CHARS]
    return Intent(as_of=as_of, targets=tuple(targets), note=note)


Signal = Callable[..., Any]


def load_signal(strategy_dir: Path) -> Signal:
    """Import ``<strategy_dir>/signal.py`` and return its ``signal`` callable.

    Loaded by path under a private module name, so two strategies' signals never shadow each
    other; the strategy directory is on ``sys.path`` only while the import runs."""
    strategy_dir = Path(strategy_dir)
    path = strategy_dir / SIGNAL_FILE
    if not path.is_file():
        raise IntentError(f"{strategy_dir.name} has no {SIGNAL_FILE}: no intent rule to run")
    name = f"_paper_signal_{abs(hash(str(path.resolve())))}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise IntentError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(strategy_dir))
    try:
        spec.loader.exec_module(module)
    except Exception as exc:                       # the strategy's own import error, named
        raise IntentError(f"{SIGNAL_FILE} failed to import: {exc}") from exc
    finally:
        try:
            sys.path.remove(str(strategy_dir))
        except ValueError:
            pass
    fn = getattr(module, "signal", None)
    if not callable(fn):
        raise IntentError(f"{SIGNAL_FILE} defines no signal(source, day)")
    return fn


def wants_holdings(fn: Signal) -> bool:
    """Whether ``signal`` declared a ``holdings`` parameter (positional or keyword)."""
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False
    if "holdings" in params:
        return True
    return any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())


def call_signal(fn: Signal, source: Any, day: Date, holdings: Mapping[str, Mapping[str, float]]) -> Any:
    """Call the rule with what it asked for. Whatever it raises propagates — the book records
    and re-raises, a day the rule could not answer is never silently flat."""
    if wants_holdings(fn):
        return fn(source, day, holdings=dict(holdings))
    return fn(source, day)
