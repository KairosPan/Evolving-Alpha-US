# tests/test_rule_policy_loop.py
"""E2 确定性规则策略中层:GateSpec + HarnessRulePolicy + InnerLoop agent_factory。

让"编辑 H → 决策改变 → 分数改变"因果链首次进 CI:
- 单元:gate 匹配语义 / skill_id 序 / 确定性 / 空仓 / gate=None 不参与 / 真读 live H;
- 回归:GateSpec 经 patch_skill(metatools 路径)可编辑,dict→GateSpec 强转,extra 键被拒;
- 中层集成(全离线 FakeSource + 脚本化 MockLLM 只驱动 Refiner):
  retire / patch gate / promote 三条断言,均按 horizon 滞后对齐(编辑于 day t →
  day t+1 起决策改变;in-flight 的 day≤t 决策仍归因原技能是 apply_credit 既有正确语义)。
"""
from datetime import date, datetime, timedelta

import pandas as pd
import pytest
from pydantic import ValidationError

from youzi.agent.agent import LLMAgentPolicy
from youzi.eval.rule_policy import HarnessRulePolicy, gate_matches
from youzi.harness.cycle import StateMachine
from youzi.harness.doctrine import Doctrine, DoctrineEntry
from youzi.harness.harness import HarnessState
from youzi.harness.manager import HarnessManager
from youzi.harness.memory_store import MemoryStore
from youzi.harness.metatools import MetaTools
from youzi.harness.registry import SkillRegistry
from youzi.harness.skill import GateSpec, Skill
from youzi.harness.snapshot import SnapshotStore
from youzi.llm.client import MockLLMClient
from youzi.loop.inner_loop import InnerLoop, LoopConfig
from youzi.refine.refiner import RefinerConfig
from youzi.schemas.market import MarketState
from youzi.universe.stock import StockSnapshot
from youzi.universe.universe import CandidateUniverse
from tests.conftest import FakeSource

NO_OP = '{"ops": []}'


# ── 构造辅助 ─────────────────────────────────────────────────────────────────

def _snap(code, status="limit_up", boards=None):
    return StockSnapshot(code=code, name=code, status=status, boards=boards)


def _state(d=date(2024, 6, 26)):
    return MarketState(date=d, max_board_height=4, limit_up_count=2, blowup_count=1,
                       blowup_rate=0.3, limit_down_count=0, echelon=[],
                       money_effect_raw=0.0, sentiment_raw=0.0, sentiment_norm=None,
                       as_of=datetime(2024, 6, 26, 15, 0))


def _skill(sid, status="active", gate=None):
    """测试技能;gate 传裸 dict → pydantic 在构造期强转 GateSpec(顺带覆盖 seed 路径)。"""
    return Skill.from_seed({"skill_id": sid, "name_cn": sid, "type": "pattern",
                            "applicable_regime": ["主升"], "trigger": "t", "entry": "e",
                            "exit_stop": "x", "status": status, "gate": gate})


def _h(skills):
    doc = Doctrine(entries=[DoctrineEntry.from_seed(
        {"section": "主升作战", "regime": "主升", "immutable": False, "guidance": "g"})])
    return HarnessState(doctrine=doc, skills=SkillRegistry.from_skills(skills),
                        memory=MemoryStore.from_lessons([]), cycle=StateMachine())


def _rule_loop(tmp_path, src, harness, refiner_scripts, refiner_config=None):
    """规则决策层内环:agent 经 factory 注入 HarnessRulePolicy,agent_llm 永不该被调。"""
    mgr = HarnessManager(harness, SnapshotStore(tmp_path))
    cal = src.trading_calendar()
    loop = InnerLoop(mgr, src, cal[0], cal[-1],
                     MockLLMClient("agent 不应被调用"), MockLLMClient(refiner_scripts),
                     config=LoopConfig(breaker_min_days=10_000, evidence_min=1),
                     refiner_config=refiner_config,
                     agent_factory=HarnessRulePolicy)
    return loop, mgr


def _patterns(step):
    return [c.pattern for c in step.decision.candidates]


def _codes(step):
    return [c.code for c in step.decision.candidates]


# ── GateSpec / gate 匹配语义(单元)──────────────────────────────────────────

def test_gate_matches_boards_semantics():
    g = GateSpec(min_boards=2)
    assert gate_matches(g, _snap("A", boards=2))
    assert not gate_matches(g, _snap("A", boards=1))
    assert not gate_matches(g, _snap("A", boards=None))      # boards=None 不臆造 0 → 不匹配
    g2 = GateSpec(max_boards=2)
    assert gate_matches(g2, _snap("A", boards=2))
    assert not gate_matches(g2, _snap("A", boards=3))
    assert not gate_matches(g2, _snap("A", boards=None))


def test_gate_matches_status_and_conjunction():
    g = GateSpec(status_in=["blowup"])
    assert gate_matches(g, _snap("A", status="blowup"))
    assert not gate_matches(g, _snap("A", status="limit_up", boards=5))
    # 非 None 条件取与(AND)
    g2 = GateSpec(min_boards=1, max_boards=3, status_in=["limit_up"])
    assert gate_matches(g2, _snap("A", boards=2))
    assert not gate_matches(g2, _snap("A", status="blowup", boards=2))
    # 全 None(空与)匹配任意快照
    assert gate_matches(GateSpec(), _snap("A", status="limit_down"))


def test_gatespec_forbids_extra_and_bad_types():
    with pytest.raises(ValidationError):
        GateSpec(min_bords=2)               # typo 键被 extra="forbid" 拒
    with pytest.raises(ValidationError):
        GateSpec(min_boards="abc")          # 类型垃圾被拒


def test_skill_gate_default_none_and_snapshot_roundtrip():
    # 默认 None:57 真种子(seed dict 无 gate 键)零改动
    assert _skill("k0").gate is None
    # checkpoint/rollback 路径:to_dict/from_dict 保 gate
    h = _h([_skill("k1", gate={"min_boards": 2, "status_in": ["limit_up"]})])
    h2 = HarnessState.from_dict(h.to_dict())
    g = h2.skills.get("k1").gate
    assert isinstance(g, GateSpec) and g.min_boards == 2 and g.status_in == ["limit_up"]


# ── HarnessRulePolicy(单元)─────────────────────────────────────────────────

def test_rule_policy_first_match_by_skill_id_order():
    # 两技能 gate 都匹配 → skill_id 字典序第一个认领
    h = _h([_skill("b_late", gate={"min_boards": 1}),
            _skill("a_first", gate={"min_boards": 1})])
    uni = CandidateUniverse.from_stocks([_snap("X", boards=2)])
    pkg = HarnessRulePolicy(h).decide(_state(), uni)
    assert _patterns_pkg(pkg) == ["a_first"]
    assert pkg.candidates[0].reason == "rule:gate 命中 a_first"


def _patterns_pkg(pkg):
    return [c.pattern for c in pkg.candidates]


def test_rule_policy_deterministic_and_code_sorted():
    h = _h([_skill("k1", gate={"min_boards": 1})])
    uni = CandidateUniverse.from_stocks([_snap("B", boards=2), _snap("A", boards=1)])
    pol = HarnessRulePolicy(h)
    p1, p2 = pol.decide(_state(), uni), pol.decide(_state(), uni)
    assert p1 == p2                                          # 零 LLM,完全确定
    assert [c.code for c in p1.candidates] == ["A", "B"]     # code 排序定序


def test_rule_policy_no_match_goes_no_trade():
    h = _h([_skill("k1", gate={"min_boards": 5})])
    uni = CandidateUniverse.from_stocks([_snap("A", boards=1)])
    pkg = HarnessRulePolicy(h).decide(_state(), uni)
    assert pkg.candidates == [] and pkg.no_trade_reason


def test_rule_policy_gate_none_and_non_active_not_participating():
    # gate=None 的 active 技能(如真种子)不参与;incubating/dormant 带 gate 也不参与
    h = _h([_skill("k_nogate", gate=None),
            _skill("k_incub", status="incubating", gate={"min_boards": 1}),
            _skill("k_dorm", status="dormant", gate={"min_boards": 1})])
    uni = CandidateUniverse.from_stocks([_snap("A", boards=3)])
    pkg = HarnessRulePolicy(h).decide(_state(), uni)
    assert pkg.candidates == [] and pkg.no_trade_reason


def test_rule_policy_reads_live_h():
    # 真读 live H:retire(→dormant)后不再匹配;promote(→active)后开始匹配
    h = _h([_skill("k1", gate={"min_boards": 1}),
            _skill("k2", status="incubating", gate={"status_in": ["blowup"]})])
    uni = CandidateUniverse.from_stocks([_snap("A", boards=2), _snap("Z", status="blowup")])
    pol = HarnessRulePolicy(h)
    assert _patterns_pkg(pol.decide(_state(), uni)) == ["k1"]
    h.skills.retire("k1")                                    # → dormant
    h.skills.promote("k2")                                   # → active
    pkg = pol.decide(_state(), uni)                          # 同一 policy 实例,无需重建
    assert _patterns_pkg(pkg) == ["k2"]
    assert [c.code for c in pkg.candidates] == ["Z"]


# ── GateSpec 经 patch_skill 可编辑(metatools 路径回归)──────────────────────

def test_gate_not_in_patch_forbidden():
    assert "gate" not in SkillRegistry._PATCH_FORBIDDEN      # 保持可 patch(E2 设计)


def test_patch_skill_gate_dict_coerced_to_gatespec():
    h = _h([_skill("k1", gate={"min_boards": 1})])
    tools = MetaTools(h)
    tools.patch_skill("k1", rationale="收紧高位板", gate={"min_boards": 1, "max_boards": 2})
    g = h.skills.get("k1").gate
    assert isinstance(g, GateSpec) and g.max_boards == 2     # 裸 dict 经 validate_assignment 强转
    assert any(r.tool == "patch_skill" for r in tools.log.records())   # 编辑入 EditLog


def test_patch_skill_gate_extra_key_rejected_and_rolled_back():
    h = _h([_skill("k1", gate={"min_boards": 1})])
    tools = MetaTools(h)
    with pytest.raises(ValidationError):
        tools.patch_skill("k1", rationale="typo", gate={"min_boards": 1, "min_bords": 9})
    g = h.skills.get("k1").gate
    assert isinstance(g, GateSpec) and g.min_boards == 1 and g.max_boards is None  # 原 gate 未动
    assert all(r.tool != "patch_skill" for r in tools.log.records())   # 失败不入 EditLog


# ── InnerLoop agent_factory(单元)───────────────────────────────────────────

def test_inner_loop_agent_factory_rebind_after_rollback(tmp_path):
    d = date(2024, 6, 26)
    src = FakeSource({("zt", d): pd.DataFrame({"code": ["A"], "name": ["A"], "boards": [1]})}, [d])
    mgr = HarnessManager(_h([_skill("k1", gate={"min_boards": 1})]), SnapshotStore(tmp_path))
    built = []

    def factory(harness):
        pol = HarnessRulePolicy(harness)
        built.append(pol)
        return pol

    loop = InnerLoop(mgr, src, d, d, MockLLMClient("agent 不应被调用"), MockLLMClient(NO_OP),
                     agent_factory=factory)
    assert loop._agent is built[-1] and loop._agent._harness is mgr.harness
    # rollback 替换 harness 对象 → _rebind 必须经 factory 重建(固定实例会静默读废弃 H)
    v = mgr.checkpoint("c0")
    mgr.tools.retire_skill("k1")
    mgr.rollback_to(v)
    old = loop._agent
    loop._rebind()
    assert loop._agent is not old
    assert loop._agent._harness is mgr.harness               # 绑到还原态新对象
    assert mgr.harness.skills.get("k1").status == "active"


def test_inner_loop_default_path_unchanged(tmp_path):
    # 不传 agent_factory → 现行 LLMAgentPolicy(向后兼容)
    d = date(2024, 6, 26)
    src = FakeSource({("zt", d): pd.DataFrame({"code": ["A"], "name": ["A"], "boards": [1]})}, [d])
    mgr = HarnessManager(_h([_skill("k1")]), SnapshotStore(tmp_path))
    loop = InnerLoop(mgr, src, d, d, MockLLMClient(NO_OP), MockLLMClient(NO_OP))
    assert isinstance(loop._agent, LLMAgentPolicy)


# ── 中层集成:编辑 H → 决策改变 → 分数改变(horizon 滞后对齐)────────────────

def _zt_src(days, codes_boards):
    """每日同一 zt 池;codes_boards = [(code, boards), ...]。"""
    codes = [c for c, _ in codes_boards]
    boards = [b for _, b in codes_boards]
    frames = {("zt", d): pd.DataFrame({"code": codes, "name": codes, "boards": boards})
              for d in days}
    return frames


def test_retire_changes_decisions_next_day_and_stats_stop_growing(tmp_path):
    """断言 a:Refiner retire X 于 day t → day t+1 起决策不再含 pattern=X;
    X.stats.n 终值=2(day0 + day t=day1 的 in-flight 决策),t+1 起做出的决策打分后不再归因 X。"""
    days = [date(2024, 6, 3) + timedelta(days=k) for k in range(6)]
    src = FakeSource(_zt_src(days, [("HIGH", 4), ("LOW", 2)]), days)
    h = _h([_skill("k_high", gate={"min_boards": 3}),
            _skill("k_low", gate={"min_boards": 1, "max_boards": 2})])
    # refine#1(idx=1,day t=days[1])的 K-pass 退役 k_high;此后 MockLLM 重复末元素(全 no-op)
    retire = ('{"ops": [{"tool": "retire_skill", "args": {"skill_id": "k_high"},'
              ' "rationale": "规则层因果链验证:day t 退役"}]}')
    # min_retire_samples=1:refine#1 时 k_high 仅累计 n=1(step0 刚打分),默认门槛 5 会拦下
    loop, mgr = _rule_loop(tmp_path, src, h, [NO_OP, retire, NO_OP],
                           refiner_config=RefinerConfig(min_retire_samples=1))
    rep = loop.run()
    # 退役确实发生在 day t=days[1](防 vacuous:编辑被拒则下面全废)
    assert rep.refine_events[0].date == days[1]
    assert any(e.tool == "retire_skill" for e in rep.refine_events[0].report.applied)
    assert mgr.harness.skills.get("k_high").status == "dormant"
    steps = rep.trajectory.steps
    # 决策改变:day≤t(idx 0..1)含 pattern=k_high;day t+1 起(idx 2..)不再含,HIGH 整票消失
    assert all("k_high" in _patterns(s) for s in steps[:2])
    assert all("k_high" not in _patterns(s) for s in steps[2:])
    assert all("HIGH" not in _codes(s) for s in steps[2:])
    assert all("k_low" in _patterns(s) for s in steps)        # k_low 不受影响,全程入选
    # 分数改变(horizon=1 滞后对齐):in-flight 的 day≤t 决策(step0/step1)打分后仍归因 X
    # (apply_credit 不过滤 status,是既有正确语义)→ n=2;day t+1 起的决策不再产生 X 归因,
    # 故跑完全窗(steps 0..4 均已打分)n 恒为 2、不再增长。
    assert mgr.harness.skills.get("k_high").stats.n == 2
    assert mgr.harness.skills.get("k_low").stats.n == 5       # 对照:5 个已打分步全归因 k_low
    assert loop._agent_llm.calls == []                        # 决策层零 LLM


def test_patch_gate_tightening_filters_high_boards_next_day(tmp_path):
    """断言 b:patch gate(max_boards 收紧)于 day t → 次日起高位板被过滤。"""
    days = [date(2024, 6, 3) + timedelta(days=k) for k in range(5)]
    src = FakeSource(_zt_src(days, [("HI", 4), ("LO", 1)]), days)
    h = _h([_skill("k_all", gate={"min_boards": 1})])
    patch = ('{"ops": [{"tool": "patch_skill", "args": {"skill_id": "k_all",'
             ' "gate": {"min_boards": 1, "max_boards": 2}},'
             ' "rationale": "收紧:不追 3 板以上高位"}]}')
    loop, mgr = _rule_loop(tmp_path, src, h, [NO_OP, patch, NO_OP])
    rep = loop.run()
    assert rep.refine_events[0].date == days[1]
    assert any(e.tool == "patch_skill" for e in rep.refine_events[0].report.applied)
    g = mgr.harness.skills.get("k_all").gate
    assert isinstance(g, GateSpec) and g.max_boards == 2      # Refiner 裸 dict → GateSpec 强转
    steps = rep.trajectory.steps
    # day≤t 决策含 HI+LO;day t+1 起 HI(4板)被过滤,只剩 LO —— 决策改变
    assert all(_codes(s) == ["HI", "LO"] for s in steps[:2])
    assert all(_codes(s) == ["LO"] for s in steps[2:])
    # 分数改变:已打分步 0..3 → 归因数 = 2+2+1+1 = 6(不收紧则为 8)
    assert mgr.harness.skills.get("k_all").stats.n == 6
    assert loop._agent_llm.calls == []


def test_promote_incubating_starts_selecting_and_accruing_stats(tmp_path):
    """断言 c:promote incubating→active 于 day t → 次日起该技能开始入选并积累 stats。

    promote 经脚本化 Refiner 走 metatools(入 EditLog)。并行工作(A1)已在
    Refiner._apply_op 落地晋升证据门:n≥min_promote_samples 且 expectancy(超额)>0
    才放行——按 spec 兜底取"预填达标 stats"这条路:给 k_blow 预填强证据
    (n=20, wins=16, expectancy=+0.5),让晋升门放行;若门变严仍拒,
    本测试会在 applied 断言处显式报错(非静默)。
    """
    days = [date(2024, 6, 3) + timedelta(days=k) for k in range(6)]
    frames = _zt_src(days, [("LOW", 2)])
    for d in days:
        frames[("blowup", d)] = pd.DataFrame({"code": ["BLOW"], "name": ["BLOW"]})
    src = FakeSource(frames, days)
    h = _h([_skill("k_low", gate={"min_boards": 1, "max_boards": 2}),
            _skill("k_blow", status="incubating", gate={"status_in": ["blowup"]})])
    st = h.skills.get("k_blow").stats
    # 预填达标证据(见 docstring):n 过样本门,expectancy>0 过超额门
    st.n, st.wins, st.losses, st.ewma_winrate = 20, 16, 4, 0.8
    st.expectancy, st.expectancy_raw = 0.5, 0.5
    n_before = st.n
    promote = ('{"ops": [{"tool": "promote_skill", "args": {"skill_id": "k_blow"},'
               ' "rationale": "孵化期证据达标,晋升参战"}]}')
    loop, mgr = _rule_loop(tmp_path, src, h, [NO_OP, promote, NO_OP])
    rep = loop.run()
    assert rep.refine_events[0].date == days[1]
    assert any(e.tool == "promote_skill" for e in rep.refine_events[0].report.applied)
    assert mgr.harness.skills.get("k_blow").status == "active"
    steps = rep.trajectory.steps
    # day≤t:incubating 不参与规则层 → BLOW 未入选;day t+1 起以 pattern=k_blow 入选
    assert all("k_blow" not in _patterns(s) for s in steps[:2])
    assert all("BLOW" not in _codes(s) for s in steps[:2])
    assert all("k_blow" in _patterns(s) and "BLOW" in _codes(s) for s in steps[2:])
    # 分数改变(horizon 滞后):day t+1 起的 BLOW 决策中 steps 2..4 已打分 → n 净增 3
    assert mgr.harness.skills.get("k_blow").stats.n == n_before + 3
    assert loop._agent_llm.calls == []
