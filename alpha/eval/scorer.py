from __future__ import annotations

from datetime import date as Date
from typing import Protocol

from alpha.eval.decision import DecisionPackage
from alpha.eval.metrics import ScoredCandidate
from alpha.eval.oracle import SCORE, DayMembership, outcome
from alpha.eval.return_oracle import ReturnOracle


class Scorer(Protocol):
    """Score one matured decision into {symbol: ScoredCandidate} (de-duped; may drop missing-data).

    decision_mem = decision-day (<=t) exogenous membership, used only to define the day_baseline set.
    exit_mem = exit-day membership, used for the realized outcome category. Always consumes t+ labels
    post-hoc; never feeds the decision path (firewall).
    """
    def score_step(self, decision: DecisionPackage, decision_mem: DayMembership,
                   exit_mem: DayMembership, entry_day: Date, exit_day: Date,
                   oracle: ReturnOracle | None) -> dict[str, ScoredCandidate]: ...


class PoolScorer:
    """Diagnostic: outcome category + SCORE[outcome]. baseline = mean SCORE over decision gainers."""

    def score_step(self, decision: DecisionPackage, decision_mem: DayMembership,
                   exit_mem: DayMembership, entry_day: Date, exit_day: Date,
                   oracle: ReturnOracle | None) -> dict[str, ScoredCandidate]:
        base = self._baseline(decision_mem, exit_mem)
        out: dict[str, ScoredCandidate] = {}
        for c in decision.candidates:
            if c.symbol in out:
                continue
            oc = outcome(c.symbol, exit_mem)
            score = SCORE[oc]
            out[c.symbol] = ScoredCandidate(
                decision_date=decision.date, symbol=c.symbol, pattern=c.pattern, outcome=oc,
                score=score, day_baseline=base,
                advantage=score - base if base is not None else score)
        return out

    @staticmethod
    def _baseline(decision_mem: DayMembership, exit_mem: DayMembership) -> float | None:
        pool = decision_mem.gainers
        if not pool:
            return None
        return sum(SCORE[outcome(s, exit_mem)] for s in pool) / len(pool)


class ReturnScorer:
    """Primary: score = forward return (delist=-1.0 KEPT; genuine missing -> discard).
    outcome = exit-day category (for reporting). baseline = mean forward return over decision gainers."""

    def score_step(self, decision: DecisionPackage, decision_mem: DayMembership,
                   exit_mem: DayMembership, entry_day: Date, exit_day: Date,
                   oracle: ReturnOracle | None) -> dict[str, ScoredCandidate]:
        if oracle is None:
            raise ValueError("ReturnScorer requires a ReturnOracle")
        base = self._baseline(decision_mem, entry_day, exit_day, oracle)
        out: dict[str, ScoredCandidate] = {}
        # SCORING FENCE (P0.6 spec §6 / P0.5 spec §8): every candidate here is scored as a forward-return
        # LONG from entry_day to exit_day. Today `Candidate.action` is always "enter", so scoring every
        # candidate is correct. The producer that FIRST emits a trim/exit candidate (a derisk on a HELD
        # name, not a new long) must fence those out of scoring — mirror the verdict `for_asof(kind="trade")`
        # fence: score action=="enter" only. Inert today (no producer emits trim/exit); pin, do not skip.
        for c in decision.candidates:
            if c.symbol in out:
                continue
            ret = oracle.score(c.symbol, entry_day, exit_day)
            if ret is None:
                continue                              # genuine missing data -> discard
            oc = outcome(c.symbol, exit_mem)
            out[c.symbol] = ScoredCandidate(
                decision_date=decision.date, symbol=c.symbol, pattern=c.pattern, outcome=oc,
                score=ret, day_baseline=base,
                advantage=ret - base if base is not None else ret)
        return out

    @staticmethod
    def _baseline(decision_mem: DayMembership, entry_day: Date, exit_day: Date,
                  oracle: ReturnOracle) -> float | None:
        rets = [r for s in sorted(decision_mem.gainers)
                if (r := oracle.score(s, entry_day, exit_day)) is not None]
        return sum(rets) / len(rets) if rets else None
