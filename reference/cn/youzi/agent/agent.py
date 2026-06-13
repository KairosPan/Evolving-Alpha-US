from __future__ import annotations

from typing import Literal

from youzi.agent.parse import parse_decision
from youzi.agent.prompt import build_system_prompt, build_user_prompt
from youzi.agent.retrieval import (
    DEFAULT_MEMORY_BUDGET,
    DEFAULT_SKILL_BUDGET,
    DEFAULT_TRIAL_SLOTS,
)
from youzi.eval.decision import DecisionPackage
from youzi.harness.harness import HarnessState
from youzi.llm.client import LLMClient
from youzi.schemas.market import MarketState
from youzi.universe.universe import CandidateUniverse


class LLMAgentPolicy:
    """LLM 驱动的 DecisionPolicy:harness 包住模型,读盘面+候选→决策包。

    持有 harness 而非预渲染提示:每次 decide 按当前 H 重建系统提示,
    使 Phase-1b 的 Refiner 改 H 后立即对 agent 可见。

    injection(A1):"full"(默认,零回归)全量渲染;"retrieval" 预算化检索注入
    (active 按 phase_prior 命中优先截 skill_budget,记忆按 weight 截 memory_budget)。
    phase_prior = 上一次 decide 输出的 regime_read(≤t 自身判读,无未来函数);
    InnerLoop._rebind(rollback 后)重建本对象会丢失该状态 → 回到 None,可接受:
    回滚语义下旧判读已作废,首日无先验同。
    """

    def __init__(self, harness: HarnessState, llm: LLMClient,
                 injection: Literal["full", "retrieval"] = "full",
                 skill_budget: int = DEFAULT_SKILL_BUDGET,
                 memory_budget: int = DEFAULT_MEMORY_BUDGET,
                 trial_slots: int = DEFAULT_TRIAL_SLOTS) -> None:
        self._harness = harness
        self._llm = llm
        self._injection: Literal["full", "retrieval"] = injection
        self._skill_budget = skill_budget
        self._memory_budget = memory_budget
        self._trial_slots = trial_slots
        self._phase_prior: str | None = None   # 上一决策日自己的 regime_read(≤t)

    def decide(self, state: MarketState, universe: CandidateUniverse) -> DecisionPackage:
        system = build_system_prompt(self._harness, injection=self._injection,
                                     phase_prior=self._phase_prior,
                                     skill_budget=self._skill_budget,
                                     memory_budget=self._memory_budget,
                                     trial_slots=self._trial_slots)
        user = build_user_prompt(state, universe)
        raw = self._llm.complete(system, user)
        pkg = parse_decision(raw, state.date, universe)
        # 严格"上一次输出":解析失败/空判读 → 先验清空,不留陈旧相位
        self._phase_prior = pkg.regime_read or None
        return pkg
