from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from alpha.harness.regime import CANONICAL_PHASES


class Transition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    to: str
    signal: str


class EmotionPhase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phase: str
    you_see: list[str] = Field(default_factory=list)
    transitions: list[Transition] = Field(default_factory=list)


class StateMachine(BaseModel):
    """US momentum cycle state machine (G_cycle seed; read-only structure — no inference here)."""
    phases: list[EmotionPhase] = Field(default_factory=list)

    def get(self, phase: str) -> EmotionPhase | None:
        return next((p for p in self.phases if p.phase == phase), None)

    def next_signals(self, phase: str) -> list[tuple[str, str]]:
        p = self.get(phase)
        return [(t.to, t.signal) for t in p.transitions] if p else []

    def phase_names(self) -> list[str]:
        return [p.phase for p in self.phases]

    @classmethod
    def from_seed_list(cls, items: list[dict]) -> "StateMachine":
        phases = [EmotionPhase(**d) for d in items]
        seen: set[str] = set()
        for p in phases:
            if p.phase in seen:
                raise ValueError(f"duplicate phase: {p.phase}")
            seen.add(p.phase)
        return cls(phases=phases)


def default_us_cycle() -> StateMachine:
    """The canonical 6-state US momentum cycle (blueprint §6). Transition signals are seed prose;
    US-1g/US-2 refine them. Frontside = recovery/ignition/trend; backside = distribution/flush."""
    return StateMachine.from_seed_list([
        {"phase": "washout", "you_see": ["few big gainers", "runners failing", "IWM downtrend",
                                         "new-lows high", "no follow-through"],
         "transitions": [{"to": "recovery", "signal": "first clean gap-and-go survivors + a day-2 continuation"},
                         {"to": "washout", "signal": "every pop sold; breadth stays dead"}]},
        {"phase": "recovery", "you_see": ["first first-green-day survivors", "breadth ticking up"],
         "transitions": [{"to": "ignition", "signal": "a narrative gets multiple movers same day"},
                         {"to": "washout", "signal": "the early leaders fail; follow-through collapses"}]},
        {"phase": "ignition", "you_see": ["a narrative ignites (many tickers up big)",
                                          "index follow-through day", "RVOL spikes"],
         "transitions": [{"to": "trend", "signal": "clear lead runner + sympathy basket extends"},
                         {"to": "distribution", "signal": "ignition fails to extend; leaders churn"}]},
        {"phase": "trend", "you_see": ["lead runner makes new highs daily", "sympathy runs",
                                       "low failed-breakout rate"],
         "transitions": [{"to": "distribution",
                          "signal": "first big distribution day on the leader + no next-day recovery"}]},
        {"phase": "distribution", "you_see": ["choppy", "laggards run while leaders churn",
                                              "failed-breakout rate climbing"],
         "transitions": [{"to": "flush", "signal": "leader breaks down on volume / parabolic blowoff"},
                         {"to": "trend", "signal": "leaders reclaim; risk-on resumes"}]},
        {"phase": "flush", "you_see": ["leaders + sympathy co-flush", "the hot ticker dumped", "SSR broad"],
         "transitions": [{"to": "washout",
                          "signal": "breadth collapses; old leaders stop falling, new narrative stirs"}]},
    ])
