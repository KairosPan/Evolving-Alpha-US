# tests/test_refiner_prompt.py
from datetime import date, datetime
from youzi.refine.refiner_prompt import build_refiner_system_prompt, build_refiner_user_prompt
from youzi.refine.credit import CreditReport, SkillCredit
from youzi.refine.signatures import FailureSignature
from youzi.eval.trajectory import Trajectory, TrajectoryStep
from youzi.eval.decision import DecisionPackage, Candidate
from youzi.eval.metrics import ScoredCandidate
from youzi.schemas.market import MarketState
from tests.test_metatools import _harness


def test_system_prompt_k_pass_lists_skill_tools_and_rules():
    p = build_refiner_system_prompt(_harness(), "K")
    assert "write_skill" in p and "promote_skill" in p
    assert "rationale" in p
    assert "immutable" in p or "红线" in p
    assert "ops" in p                                   # 输出契约
    assert "rewrite_doctrine" not in p                  # K-pass 不暴露 doctrine 工具


def test_system_prompt_p_pass_lists_mutable_doctrine():
    p = build_refiner_system_prompt(_harness(), "p")
    assert "rewrite_doctrine" in p
    assert "主升作战" in p                              # mutable 段渲染出来


def test_system_prompt_m_pass_lists_memory_tools():
    p = build_refiner_system_prompt(_harness(), "M")
    assert "process_memory" in p and "demote_memory" in p


def test_user_prompt_renders_evidence():
    mkt = MarketState(date=date(2024, 6, 27), max_board_height=5, limit_up_count=10,
                      blowup_count=3, blowup_rate=0.3, limit_down_count=1, echelon=[],
                      money_effect_raw=1.0, sentiment_raw=0.0, sentiment_norm=0.5,
                      as_of=datetime(2024, 6, 27, 15, 0))
    step = TrajectoryStep(
        date=date(2024, 6, 27), market=mkt,
        decision=DecisionPackage(date=date(2024, 6, 27),
                                 candidates=[Candidate(code="000001", name="平安",
                                                       pattern="接力", reason="r", confidence=0.6)]),
        scored=True,
        outcomes={"000001": ScoredCandidate(decision_date=date(2024, 6, 27), code="000001",
                                            pattern="接力", outcome="nuked", score=-1.0)})
    traj = Trajectory(steps=[step], horizon=1)
    credit = CreditReport(per_skill={"a": SkillCredit(skill_id="a", n=3, wins=0, losses=3,
                                                      nukes=2, hit_rate=0.0, nuke_rate=0.67,
                                                      expectancy=-0.67)}, n_scored=3)
    sigs = [FailureSignature(date=date(2024, 6, 27), code="000001", pattern="接力",
                             skill_id="a", kind="chased_into_nuke", score=-1.0,
                             evidence="boards=5/max=5 → 追最高板被闷")]
    u = build_refiner_user_prompt(traj, credit, sigs, window=10)
    assert "000001" in u and "nuked" in u
    assert "a" in u and "nuke" in u.lower()
    assert "chased_into_nuke" in u and "追最高板被闷" in u


def test_k_pass_prompt_has_retire_discipline():
    from youzi.refine.refiner_prompt import build_refiner_system_prompt
    from tests.test_metatools import _harness
    p = build_refiner_system_prompt(_harness(), "K", min_retire_samples=7)
    assert "n≥7" in p                      # 注入的真实门槛值
    assert "收缩纪律" in p
    assert "faded" in p and "nuked" in p and "空耗" in p
    # p-pass 不含收缩纪律段(纪律是 K 专属)
    assert "收缩纪律" not in build_refiner_system_prompt(_harness(), "p", min_retire_samples=7)


def test_build_prompt_backward_compatible_two_args():
    from youzi.refine.refiner_prompt import build_refiner_system_prompt
    from tests.test_metatools import _harness
    # 2-参调用仍可用(默认 K=5)
    p = build_refiner_system_prompt(_harness(), "K")
    assert "n≥5" in p


# ── A3:编辑史段 + 涉案技能全文渲染 ──

def _history_reports():
    from youzi.refine.refiner import RefineReport, AppliedEdit, RejectedEdit
    r1 = RefineReport(applied=[AppliedEdit(pass_kind="K", tool="patch_skill", target_id="a",
                                           seq=1, rationale="收紧触发条件")],
                      rejected=[])
    r2 = RefineReport(applied=[],
                      rejected=[RejectedEdit(pass_kind="M", tool="process_memory",
                                             target_id="ls1", reason="重复 lesson_id")])
    return r1, r2


def test_user_prompt_renders_edit_history_applied_and_rejected():
    # A3:applied(tool/target/rationale)与 rejected(tool/target/拒因)各自渲染,提示纪律在
    r1, r2 = _history_reports()
    u = build_refiner_user_prompt(Trajectory(steps=[], horizon=1), CreditReport(n_scored=0),
                                  [], window=10, recent_reports=[r1, r2])
    assert "## 近期编辑史" in u
    assert "[第1次/applied] K/patch_skill → a: 收紧触发条件" in u
    assert "[第2次/rejected] M/process_memory → ls1: 拒因=重复 lesson_id" in u
    # 提示纪律:applied 别重复提;rejected 别原样重发
    assert "不要重复提" in u and "不要原样重发" in u


def test_user_prompt_edit_history_empty_renders_none():
    # 无历史 → 编辑史段写 "(无)"(段落仍在,LLM 知道这是首轮)
    u = build_refiner_user_prompt(Trajectory(steps=[], horizon=1), CreditReport(n_scored=0),
                                  [], window=10)
    assert "## 近期编辑史" in u
    assert "(无)" in u.split("近期编辑史")[1]


def _two_skill_harness():
    from youzi.harness.skill import Skill
    from youzi.harness.registry import SkillRegistry
    from youzi.harness.memory_store import MemoryStore
    from youzi.harness.doctrine import Doctrine
    from youzi.harness.cycle import StateMachine
    from youzi.harness.harness import HarnessState
    skills = SkillRegistry.from_skills([
        Skill.from_seed({"skill_id": "a", "name_cn": "甲", "type": "pattern",
                         "applicable_regime": ["主升"], "trigger": "甲的触发器",
                         "entry": "甲的入场", "exit_stop": "甲的止损",
                         "taboo": ["禁追最高板", "禁尾盘买"], "status": "active"}),
        Skill.from_seed({"skill_id": "b", "name_cn": "乙", "type": "pattern",
                         "applicable_regime": ["退潮"], "trigger": "乙的触发器",
                         "entry": "乙的入场", "exit_stop": "乙的止损", "status": "active"})])
    return HarnessState(doctrine=Doctrine(entries=[]), skills=skills,
                        memory=MemoryStore.from_lessons([]), cycle=StateMachine())


def test_k_pass_involved_skill_full_text_others_single_line():
    # A3:涉案技能(a)渲染全文(trigger/taboo/applicable_regime/stats),非涉案(b)仍单行
    h = _two_skill_harness()
    h.skills.get("a").stats.n = 3      # 让 stats 段有内容(双口径走 None 防御也另测)
    p = build_refiner_system_prompt(h, "K", involved_skill_ids={"a"})
    assert "⟨本窗涉案,全文⟩" in p
    assert "甲的触发器" in p and "甲的入场" in p and "甲的止损" in p
    assert "禁追最高板; 禁尾盘买" in p                  # taboo 现值可见(防盲改覆盖)
    assert "applicable_regime: 主升" in p
    assert "stats: n=3" in p
    # 非涉案技能 b 保持单行:全文字段不渲染
    assert "b(乙)" in p
    assert "乙的触发器" not in p and "乙的入场" not in p


def test_k_pass_patch_discipline_line_present():
    # A3(verdict 发现的坑):patch_skill 整字段替换纪律,先用提示挡
    p = build_refiner_system_prompt(_two_skill_harness(), "K", involved_skill_ids=set())
    assert "整字段替换" in p
    assert "全部既有项+新增项" in p


def test_k_pass_no_involved_all_single_line_backward_compatible():
    # 不传 involved_skill_ids(旧调用形态)→ 全部单行,无全文标记
    p = build_refiner_system_prompt(_two_skill_harness(), "K")
    assert "⟨本窗涉案,全文⟩" not in p
    assert "甲的触发器" not in p
