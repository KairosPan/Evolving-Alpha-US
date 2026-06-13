# youzi/eval/rule_policy.py
from __future__ import annotations

from youzi.eval.decision import Candidate, DecisionPackage
from youzi.harness.harness import HarnessState
from youzi.harness.skill import GateSpec
from youzi.schemas.market import MarketState
from youzi.universe.stock import StockSnapshot
from youzi.universe.universe import CandidateUniverse


def gate_matches(gate: GateSpec, snap: StockSnapshot) -> bool:
    """gate 匹配语义(确定性,零 LLM):所有非 None 条件取与(AND)。

    - min_boards / max_boards:对 snap.boards 的闭区间下/上限;
      boards 为 None(源未提供)时视为**不匹配**该条件——不臆造 0,与
      StockSnapshot 注释"不臆造为0"一致;
    - status_in:snap.status 必须在列表内;
    - 全 None 的 GateSpec(空与)匹配任意快照。
    """
    if gate.min_boards is not None and (snap.boards is None or snap.boards < gate.min_boards):
        return False
    if gate.max_boards is not None and (snap.boards is None or snap.boards > gate.max_boards):
        return False
    if gate.status_in is not None and snap.status not in gate.status_in:
        return False
    return True


class HarnessRulePolicy:
    """确定性规则策略中层(E2,实现 DecisionPolicy 协议):零 LLM、真读 live H。

    构造期持 HarnessState 引用,decide 每次按**当前** H 的 active 技能集合匹配——
    Refiner retire(→dormant)后技能自然不再匹配,promote(→active)后开始匹配,
    与 agent/prompt.py 仅渲染 active 的语义对齐。由此"编辑 H→决策改变→分数改变"
    因果链可在秒级离线测试中确定性复现(与 LLM 黄金 run 层互补:规则层测机制)。

    匹配规则:对 universe 每只候选(按 code 排序定序),在
    sorted(active 且 gate 非 None 的技能, key=skill_id) 中找**第一个** gate 匹配者,
    产出 Candidate(pattern=skill_id)(resolve_skill 先按 skill_id 精确匹配,归因无歧义);
    gate=None 视为不参与(57 个无 gate 真种子不会被规则层误触发);
    无任何匹配 → 空仓(带 no_trade_reason)。

    防火墙:只读 universe(GuardedSource 产物)与 H,不取数、不引入 t+ 信息。
    """

    def __init__(self, harness: HarnessState) -> None:
        self._harness = harness          # live 引用:Refiner 就地编辑后,次日 decide 立即可见

    def decide(self, state: MarketState, universe: CandidateUniverse) -> DecisionPackage:
        # 每次 decide 现读 H:技能集 / gate / status 的编辑 reset-free 生效
        gated = sorted((s for s in self._harness.skills.by_status("active")
                        if s.gate is not None), key=lambda s: s.skill_id)
        cands: list[Candidate] = []
        for snap in sorted(universe.all(), key=lambda s: s.code):    # code 排序,输出可复现
            for sk in gated:
                if gate_matches(sk.gate, snap):
                    cands.append(Candidate(code=snap.code, name=snap.name,
                                           pattern=sk.skill_id,
                                           reason=f"rule:gate 命中 {sk.skill_id}"))
                    break                                            # 首个匹配技能认领(skill_id 序)
        if not cands:
            return DecisionPackage(date=state.date, no_trade_reason="rule:无 active 技能 gate 匹配,空仓")
        return DecisionPackage(date=state.date, candidates=cands)
