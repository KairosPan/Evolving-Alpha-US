from __future__ import annotations

from typing import Literal

from alpha.agent.parse import parse_decision
from alpha.agent.prompt import available_data_signals, build_system_prompt, build_user_prompt
from alpha.agent.retrieval import DEFAULT_MEMORY_BUDGET, DEFAULT_SKILL_BUDGET, DEFAULT_TRIAL_SLOTS
from alpha.eval.decision import DecisionPackage
from alpha.harness.regime import normalize_phase
from alpha.harness.state import HarnessState
from alpha.llm.client import LLMClient
from alpha.state.market import MarketState
from alpha.universe.universe import CandidateUniverse


def _phase_from_read(regime_read: str) -> str | None:
    """Extract the first CANONICAL phase token from a free-text regime_read.

    The output contract makes regime_read a multi-token string (e.g. 'trend frontside' or
    'AI frontside; trend'), so normalize_phase() on the whole string returns None. Scan tokens
    (comma/semicolon/space-separated) and return the first that maps to a canonical phase, else None.
    """
    for tok in (regime_read or "").replace(",", " ").replace(";", " ").split():
        p = normalize_phase(tok)
        if p is not None:
            return p
    return None


class LLMAgentPolicy:
    """LLM-driven DecisionPolicy: the harness wraps the model. Reads state + universe -> DecisionPackage.

    Holds H (not a pre-rendered prompt): each decide() rebuilds the system prompt from the CURRENT H,
    so the US-2b Refiner's edits become visible immediately. Default injection='retrieval' renders a
    budgeted, phase-prior-ordered slice of H (the spec's intent as H grows); 'full' is an opt-in debug
    path that dumps all active skills + all lessons. phase_prior = the CANONICAL phase extracted from
    the agent's own prior-day regime_read (<=t, no lookahead); a rollback that rebuilds this object
    resets it to None (acceptable — under rollback the prior read is void, same as day 1).
    """

    def __init__(self, harness: HarnessState, llm: LLMClient,
                 injection: Literal["full", "retrieval"] = "retrieval",
                 skill_budget: int = DEFAULT_SKILL_BUDGET,
                 memory_budget: int = DEFAULT_MEMORY_BUDGET,
                 trial_slots: int = DEFAULT_TRIAL_SLOTS) -> None:
        self._harness = harness
        self._llm = llm
        self._injection: Literal["full", "retrieval"] = injection
        self._skill_budget = skill_budget
        self._memory_budget = memory_budget
        self._trial_slots = trial_slots
        self._phase_prior: str | None = None

    def decide(self, state: MarketState, universe: CandidateUniverse) -> DecisionPackage:
        system = build_system_prompt(self._harness, injection=self._injection,
                                     phase_prior=self._phase_prior, skill_budget=self._skill_budget,
                                     memory_budget=self._memory_budget, trial_slots=self._trial_slots,
                                     available_signals=available_data_signals(universe),
                                     asof=state.as_of)
        user = build_user_prompt(state, universe)
        raw = self._llm.complete(system, user)
        pkg = parse_decision(raw, state.date, universe, as_of=state.as_of)
        self._phase_prior = _phase_from_read(pkg.regime_read)   # canonical phase only; None if no phase token
        return pkg
