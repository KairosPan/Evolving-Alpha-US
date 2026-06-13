# tests/test_credit.py
from datetime import date, datetime, time

from youzi.eval.decision import Candidate, DecisionPackage
from youzi.eval.metrics import ScoredCandidate
from youzi.eval.trajectory import EntrySnap, Trajectory, TrajectoryStep
from youzi.harness.cycle import StateMachine
from youzi.harness.doctrine import Doctrine
from youzi.harness.harness import HarnessState
from youzi.harness.memory_store import MemoryStore
from youzi.harness.registry import SkillRegistry
from youzi.harness.skill import Skill
from youzi.refine.credit import apply_credit, resolve_skill
from youzi.schemas.market import MarketState

_SCORE = {"continued": 1.0, "faded": 0.0, "nuked": -1.0}


def _state(d, max_board=0):
    return MarketState(date=d, max_board_height=max_board, limit_up_count=0,
                       blowup_count=0, blowup_rate=0.0, limit_down_count=0,
                       echelon=[], money_effect_raw=0.0, sentiment_raw=0.0,
                       as_of=datetime.combine(d, time(15, 0)))


def _skill(sid, name="技能"):
    return Skill(skill_id=sid, name_cn=name, type="pattern",
                 trigger="t", entry="e", exit_stop="s", status="active")


def _harness(skills):
    return HarnessState(doctrine=Doctrine(), skills=SkillRegistry.from_skills(skills),
                        memory=MemoryStore.from_lessons([]), cycle=StateMachine())


def _step(d, code, pattern, oc, boards, max_board):
    sc = ScoredCandidate(decision_date=d, code=code, pattern=pattern, outcome=oc,
                         score=_SCORE[oc])
    return TrajectoryStep(
        date=d, market=_state(d, max_board),
        decision=DecisionPackage(date=d, candidates=[Candidate(code=code, pattern=pattern)]),
        entries={code: EntrySnap(code=code, status="limit_up", boards=boards)},
        scored=True, outcomes={code: sc})


def test_resolve_skill_by_id_then_name_then_none():
    h = _harness([_skill("pat_a", "龙头接力")])
    assert resolve_skill("pat_a", h).skill_id == "pat_a"       # by skill_id
    assert resolve_skill("龙头接力", h).skill_id == "pat_a"     # by name_cn
    assert resolve_skill("不存在", h) is None
    assert resolve_skill("", h) is None


def test_resolve_skill_normalizes_whitespace_and_case():
    # A1:strip+casefold 归一——变体不再漏进 unattributed(孵化期样本稀缺经不起再漏)
    h = _harness([_skill("pat_a", "龙头接力"), _skill("Mixed_Case", "混合案例")])
    assert resolve_skill(" pat_a ", h).skill_id == "pat_a"      # 首尾空白
    assert resolve_skill("PAT_A", h).skill_id == "pat_a"        # 大小写
    assert resolve_skill(" 龙头接力 ", h).skill_id == "pat_a"    # name_cn 空白
    assert resolve_skill("mixed_case", h).skill_id == "Mixed_Case"
    assert resolve_skill("   ", h) is None                       # 纯空白不命中


def test_apply_credit_updates_stats_and_distinguishes_faded_nuked():
    d0, d1, d2 = date(2024, 6, 26), date(2024, 6, 27), date(2024, 6, 28)
    h = _harness([_skill("pat_a")])
    traj = Trajectory(steps=[
        _step(d0, "X", "pat_a", "continued", 3, 3),
        _step(d1, "Y", "pat_a", "faded", 2, 3),
        _step(d2, "Z", "pat_a", "nuked", 3, 3),
    ], horizon=1)
    rep = apply_credit(traj, h)
    st = h.skills.get("pat_a").stats
    assert st.n == 3 and st.wins == 1 and st.losses == 2 and st.nukes == 1
    assert abs(st.expectancy - 0.0) < 1e-9               # mean(1,0,-1)=0
    # ewma:1.0 → 0.1*0+0.9*1=0.9 → 0.1*0+0.9*0.9=0.81
    assert abs(st.ewma_winrate - 0.81) < 1e-9
    cr = rep.per_skill["pat_a"]
    assert cr.n == 3 and cr.wins == 1 and cr.nukes == 1
    assert abs(cr.hit_rate - 1 / 3) < 1e-9 and abs(cr.expectancy) < 1e-9
    assert rep.n_scored == 3 and rep.unattributed is None


def test_apply_credit_unattributed_bucket():
    d0 = date(2024, 6, 26)
    h = _harness([_skill("pat_a")])
    traj = Trajectory(steps=[_step(d0, "X", "无此技能", "nuked", 1, 2)], horizon=1)
    rep = apply_credit(traj, h)
    assert h.skills.get("pat_a").stats.n == 0           # 未匹配 → 不动任何技能
    assert rep.per_skill == {}
    assert rep.unattributed is not None
    assert rep.unattributed.n == 1 and rep.unattributed.nukes == 1


def test_apply_credit_idempotency_doubles():
    d0 = date(2024, 6, 26)
    h = _harness([_skill("pat_a")])
    traj = Trajectory(steps=[_step(d0, "X", "pat_a", "continued", 3, 3)], horizon=1)
    apply_credit(traj, h)
    apply_credit(traj, h)                               # 契约:每条 trajectory 调一次;调两次=累计翻倍
    assert h.skills.get("pat_a").stats.n == 2


def test_apply_credit_uses_sc_score_for_expectancy():
    # 直接用 sc.score(收益)算 expectancy,而非 SCORE[outcome]
    from datetime import date
    from youzi.eval.trajectory import Trajectory, TrajectoryStep
    from youzi.eval.decision import DecisionPackage, Candidate
    from youzi.eval.metrics import ScoredCandidate
    from youzi.schemas.market import MarketState
    from datetime import datetime
    from youzi.refine.credit import apply_credit
    from tests.test_metatools import _harness

    h = _harness()                       # 技能 "a"(active),pattern 用 name_cn 解析
    mkt = MarketState(date=date(2026, 6, 1), max_board_height=3, limit_up_count=5,
                      blowup_count=1, blowup_rate=0.2, limit_down_count=0, echelon=[],
                      money_effect_raw=1.0, sentiment_raw=0.0, as_of=datetime(2026, 6, 1, 15))
    # outcome=continued(win)但 score=收益 +0.08(非 SCORE=1.0)
    sc = ScoredCandidate(decision_date=date(2026, 6, 1), code="X", pattern="甲",
                         outcome="continued", score=0.08)
    step = TrajectoryStep(date=date(2026, 6, 1), market=mkt,
                          decision=DecisionPackage(date=date(2026, 6, 1),
                                                   candidates=[Candidate(code="X", pattern="甲")]),
                          scored=True, outcomes={"X": sc})
    rep = apply_credit(Trajectory(steps=[step], horizon=1), h)
    # 无 day_baseline → advantage 回退=score(0.08):双口径此处同值
    assert h.skills.get("a").stats.expectancy == 0.08     # advantage 口径(回退=score)
    assert h.skills.get("a").stats.expectancy_raw == 0.08  # 原始口径
    assert h.skills.get("a").stats.wins == 1              # win 仍由 outcome=continued
    assert rep.per_skill["a"].expectancy == 0.08
    assert rep.per_skill["a"].expectancy_raw == 0.08


def test_apply_credit_dual_welford_advantage_vs_raw():
    """C2:expectancy 记 advantage(score−day_baseline),expectancy_raw 记原始 score,双套 Welford 同步。"""
    d0, d1 = date(2024, 6, 26), date(2024, 6, 27)
    h = _harness([_skill("pat_a")])

    def _step_with_base(d, code, oc, base):
        sc = ScoredCandidate(decision_date=d, code=code, pattern="pat_a", outcome=oc,
                             score=_SCORE[oc], day_baseline=base)   # advantage 由模型回填
        return TrajectoryStep(
            date=d, market=_state(d, 3),
            decision=DecisionPackage(date=d, candidates=[Candidate(code=code, pattern="pat_a")]),
            entries={code: EntrySnap(code=code, status="limit_up", boards=2)},
            scored=True, outcomes={code: sc})

    traj = Trajectory(steps=[
        _step_with_base(d0, "X", "continued", 0.5),   # score=1.0, adv=+0.5
        _step_with_base(d1, "Y", "faded", -0.5),      # score=0.0, adv=+0.5
    ], horizon=1)
    rep = apply_credit(traj, h)
    st = h.skills.get("pat_a").stats
    assert abs(st.expectancy - 0.5) < 1e-9            # mean(+0.5, +0.5):去市场β后的技能信号
    assert abs(st.expectancy_raw - 0.5) < 1e-9        # mean(1.0, 0.0):原始口径(此处碰巧同值)
    cr = rep.per_skill["pat_a"]
    assert abs(cr.expectancy - 0.5) < 1e-9 and abs(cr.expectancy_raw - 0.5) < 1e-9
    # 第二条轨迹拉开两口径:score=1.0 但基线高(0.9)→ adv=+0.1
    traj2 = Trajectory(steps=[_step_with_base(date(2024, 6, 28), "Z", "continued", 0.9)],
                       horizon=1)
    apply_credit(traj2, h)
    assert abs(st.expectancy - (0.5 + 0.5 + 0.1) / 3) < 1e-9       # advantage 均值 ≈ 0.3667
    assert abs(st.expectancy_raw - (1.0 + 0.0 + 1.0) / 3) < 1e-9   # 原始均值 = 2/3,两口径分离
