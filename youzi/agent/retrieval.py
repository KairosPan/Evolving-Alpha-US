# youzi/agent/retrieval.py
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from youzi.harness.harness import HarnessState
from youzi.harness.memory_item import Lesson
from youzi.harness.regime import classify_regime
from youzi.harness.skill import Skill

# A1 预算默认值:挑过的注入量级(全量 ~55 技能+21 教训 ≈24K 字符 → 预算化后约减半)。
DEFAULT_SKILL_BUDGET = 20    # active 技能预算 B1
DEFAULT_MEMORY_BUDGET = 12   # 记忆预算 B2
DEFAULT_TRIAL_SLOTS = 3      # 孵化试验位上限(孵化技能积累归因样本的唯一通道)
MIN_MEMORY_WEIGHT = 0.15     # weight() 低于此值的教训不渲染 → demote 即时生效


class Selection(BaseModel):
    """预算化提示注入选集(frozen 容器;成员是 H 内对象的只读引用,不拷贝不修改)。

    skills:active 技能,phase_prior 命中优先 + 战绩排序后截预算;
    trials:孵化试验位(≤trial_slots 条 incubating,创建新→旧);
    lessons:记忆按 importance.weight() 降序截预算,weight<MIN_MEMORY_WEIGHT 的已剔除。
    """
    model_config = ConfigDict(frozen=True)
    skills: list[Skill] = Field(default_factory=list)
    trials: list[Skill] = Field(default_factory=list)
    lessons: list[Lesson] = Field(default_factory=list)


def _normalize_phase(phase_prior: str | None) -> str | None:
    """把自由串 phase_prior(上一日 regime_read 原文)归一为 canonical 相位。

    认不出相位(生态词/胡话/空)→ None,等同无先验:决不臆造命中。
    """
    if phase_prior is None or not str(phase_prior).strip():
        return None
    kind, value = classify_regime(str(phase_prior))
    return value if kind == "phase" else None


def select_for_prompt(h: HarnessState, *, phase_prior: str | None,
                      skill_budget: int = DEFAULT_SKILL_BUDGET,
                      memory_budget: int = DEFAULT_MEMORY_BUDGET,
                      trial_slots: int = DEFAULT_TRIAL_SLOTS) -> Selection:
    """从 H 选出预算内注入提示的技能/试验位/记忆(纯函数:确定性、只读、不 mutate H)。

    排序规则:
    - 技能:active 中按 (phase_prior 命中优先, stats.n 降序, skill_id 升序) 截 top-skill_budget;
      命中 = canonical(phase_prior) ∈ skill.phases 或 applies_all;phase_prior=None →
      无命中维度,全 active 按 (n 降序, skill_id) 同序截断。
    - 试验位:incubating 按创建新→旧(registry 插入序反转,稳定确定)截 top-trial_slots。
    - 记忆:importance.weight() ≥ MIN_MEMORY_WEIGHT 者按 (weight 降序, lesson_id 升序)
      截 top-memory_budget——demote 压低 weight 后下一次渲染立即生效(治 demote no-op)。

    防火墙:phase_prior 应来自上一交易日(≤t)自己的 regime_read 输出,本函数不校验来源。
    """
    canon = _normalize_phase(phase_prior)

    def _hit(s: Skill) -> bool:
        return canon is not None and (s.applies_all or canon in s.phases)

    actives = sorted(h.skills.by_status("active"),
                     key=lambda s: (not _hit(s), -s.stats.n, s.skill_id))
    # registry 保插入序(dict),write_skill 追加在尾 → 反转即"创建新→旧"且稳定
    trials = list(reversed(h.skills.by_status("incubating")))[:trial_slots]
    lessons = sorted((l for l in h.memory.all()
                      if l.importance.weight() >= MIN_MEMORY_WEIGHT),
                     key=lambda l: (-l.importance.weight(), l.lesson_id))
    return Selection(skills=actives[:skill_budget], trials=trials,
                     lessons=lessons[:memory_budget])
