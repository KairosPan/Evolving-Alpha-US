from __future__ import annotations

from datetime import date as Date
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from youzi.schemas.market import MarketState
from youzi.universe.universe import CandidateUniverse


class Candidate(BaseModel):
    """策略选出的一个候选标的(v1 评测只看选了哪些 code + 声明的模式)。"""
    model_config = ConfigDict(frozen=True)
    code: str
    name: str = ""
    pattern: str = ""              # 命中的模式/skill_id(策略声明,用于 by_pattern 归因)
    reason: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class DecisionPackage(BaseModel):
    """某交易日的决策包(co-pilot 输出的 v1 子集:候选池 + 不参与理由)。

    约定:`candidates` 内 `code` 应唯一——策略若返回重复 code,会在指标里
    被重复计数(double-count)。去重/校验归 policy 或 WalkForwardEval 契约负责
    (Bundle B 实现),本 schema 不强制。
    """
    model_config = ConfigDict(frozen=True)
    date: Date
    candidates: list[Candidate] = Field(default_factory=list)
    no_trade_reason: str = ""
    # A1:agent 对当日情绪相位的判读原文(≤t 自身输出)。下一交易日作 phase_prior
    # 喂回检索注入(预算化技能选择),并为 G_cycle 留监督信号。可选默认空 → 旧 JSON 兼容。
    regime_read: str = ""


class DecisionPolicy(Protocol):
    """策略接口:读当日聚合状态 + 候选 universe,产决策包。

    LLM Agent(Phase-1)在构造期持有 HarnessState/LLM,decide 仍只吃 (state, universe)。
    """
    def decide(self, state: MarketState, universe: CandidateUniverse) -> DecisionPackage: ...
