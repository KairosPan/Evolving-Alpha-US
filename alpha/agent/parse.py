from __future__ import annotations

import json
from datetime import date as Date, datetime as DateTime

from alpha.eval.decision import Candidate, DecisionPackage
from alpha.llm.extract import extract_json_object
from alpha.universe.universe import CandidateUniverse


def _clamp01(v: object, default: float = 0.5) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return min(1.0, max(0.0, f))


def parse_decision(raw: str, day: Date, universe: CandidateUniverse,
                   as_of: DateTime | None = None) -> DecisionPackage:
    """Robustly parse LLM text into a DecisionPackage: drop hallucinated/duplicate symbols
    (re-anchor to the universe), clamp confidence; malformed output -> no-trade fallback.
    `as_of` (the inference-path snapshot timestamp, §4.1) is stamped on EVERY package, incl. no-trade."""
    extracted = extract_json_object(raw)
    if extracted is None:                              # no JSON object at all -> no-trade
        return DecisionPackage(date=day, as_of=as_of, no_trade_reason="LLM output parse failed")
    try:
        data = json.loads(extracted)
        if not isinstance(data, dict):
            raise ValueError("top level not an object")
    except (json.JSONDecodeError, ValueError):
        return DecisionPackage(date=day, as_of=as_of, no_trade_reason="LLM output parse failed")

    cands: list[Candidate] = []
    seen: set[str] = set()
    for c in (data.get("candidates") or []):
        if not isinstance(c, dict):
            continue
        sym = (str(c.get("symbol")) if c.get("symbol") is not None else "").strip()
        snap = universe.get(sym)
        if snap is None or snap.symbol in seen:        # hallucinated / not tradeable / duplicate -> drop
            continue
        seen.add(snap.symbol)
        cands.append(Candidate(symbol=snap.symbol, name=snap.name,
                               pattern=str(c.get("pattern") or ""), reason=str(c.get("reason") or ""),
                               confidence=_clamp01(c.get("confidence", 0.5))))
    return DecisionPackage(date=day, as_of=as_of, candidates=cands,
                           no_trade_reason=str(data.get("no_trade_reason") or ""),
                           regime_read=str(data.get("regime_read") or "").strip())
