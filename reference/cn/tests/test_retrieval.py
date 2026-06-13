# tests/test_retrieval.py — A1:预算化检索注入 + 试验位 + phase_prior 跨日传递(全离线)
from datetime import date, datetime

from youzi.agent.agent import LLMAgentPolicy
from youzi.agent.prompt import build_system_prompt
from youzi.agent.retrieval import MIN_MEMORY_WEIGHT, select_for_prompt
from youzi.harness.cycle import StateMachine
from youzi.harness.doctrine import Doctrine
from youzi.harness.harness import HarnessState
from youzi.harness.memory_item import Lesson
from youzi.harness.memory_store import MemoryStore
from youzi.harness.registry import SkillRegistry
from youzi.harness.skill import Skill
from youzi.llm.client import MockLLMClient
from youzi.schemas.market import MarketState
from youzi.universe.stock import StockSnapshot
from youzi.universe.universe import CandidateUniverse


def _skill(sid, regime=("主升",), status="active", n=0, name=None):
    s = Skill.from_seed({"skill_id": sid, "name_cn": name or f"技_{sid}", "type": "pattern",
                         "applicable_regime": list(regime), "trigger": "t", "entry": "e",
                         "exit_stop": "x", "status": status})
    s.stats.n = n
    return s


def _lesson(lid, weight=1.0, outcome="loss"):
    l = Lesson.from_seed({"lesson_id": lid, "regime": "主升", "outcome": outcome,
                          "lesson": f"教训_{lid}"})
    l.importance.time_decay = weight          # base=1 → weight()=weight
    return l


def _h(skills, lessons=()):
    return HarnessState(doctrine=Doctrine(entries=[]),
                        skills=SkillRegistry.from_skills(list(skills)),
                        memory=MemoryStore.from_lessons(list(lessons)),
                        cycle=StateMachine.from_seed_list([]))


# ── select_for_prompt:排序/预算/确定性 ──────────────────────────────────────

def test_select_phase_prior_hit_first_then_n_desc_then_id():
    h = _h([_skill("a1", ("主升",), n=0), _skill("b1", ("退潮",), n=9),
            _skill("c1", ("all",), n=5), _skill("d1", ("退潮",), n=9)])
    sel = select_for_prompt(h, phase_prior="主升", skill_budget=3)
    # 命中(主升∈phases 或 applies_all)优先:c1(n=5) > a1(n=0);非命中按 n 降序、id 升序:b1
    assert [s.skill_id for s in sel.skills] == ["c1", "a1", "b1"]


def test_select_phase_prior_none_orders_by_n_then_id():
    h = _h([_skill("a1", ("主升",), n=0), _skill("b1", ("退潮",), n=9),
            _skill("c1", ("all",), n=5), _skill("d1", ("退潮",), n=9)])
    sel = select_for_prompt(h, phase_prior=None, skill_budget=2)
    assert [s.skill_id for s in sel.skills] == ["b1", "d1"]      # n=9 并列 → id 升序


def test_select_phase_prior_freeform_normalized_and_gibberish_ignored():
    h = _h([_skill("hit", ("主升",), n=0), _skill("other", ("退潮",), n=9)])
    # 自由串"现在是主升浪"归一命中"主升" → hit 排前
    sel = select_for_prompt(h, phase_prior="现在是主升浪", skill_budget=2)
    assert [s.skill_id for s in sel.skills] == ["hit", "other"]
    # 认不出的胡话 → 等同无先验(n 降序)
    sel2 = select_for_prompt(h, phase_prior="火星相位", skill_budget=2)
    assert [s.skill_id for s in sel2.skills] == ["other", "hit"]


def test_select_trial_slots_newest_first_capped():
    h = _h([_skill("a1")])
    for sid in ("i1", "i2", "i3", "i4"):                 # 按创建序写入
        h.skills.write(_skill(sid, status="incubating"))
    sel = select_for_prompt(h, phase_prior=None, trial_slots=3)
    assert [s.skill_id for s in sel.trials] == ["i4", "i3", "i2"]   # 新→旧,截 3
    assert all(s.skill_id != "i1" for s in sel.skills)   # incubating 不混入 active 段


def test_select_memory_weight_cutoff_and_budget():
    h = _h([_skill("a1")],
           [_lesson("l_hi", 1.0), _lesson("l_mid", 0.5),
            _lesson("l_edge", MIN_MEMORY_WEIGHT), _lesson("l_lo", 0.14)])
    sel = select_for_prompt(h, phase_prior=None, memory_budget=10)
    ids = [l.lesson_id for l in sel.lessons]
    assert ids == ["l_hi", "l_mid", "l_edge"]            # weight 降序;<0.15 的 l_lo 被剔除
    sel2 = select_for_prompt(h, phase_prior=None, memory_budget=2)
    assert [l.lesson_id for l in sel2.lessons] == ["l_hi", "l_mid"]   # 预算截断


def test_select_is_deterministic_and_does_not_mutate_h():
    h = _h([_skill("a1", n=3), _skill("b1", n=3), _skill("c1", status="incubating")],
           [_lesson("l1", 0.9), _lesson("l2", 0.1)])
    before = h.to_dict()
    s1 = select_for_prompt(h, phase_prior="主升", skill_budget=1, memory_budget=1)
    s2 = select_for_prompt(h, phase_prior="主升", skill_budget=1, memory_budget=1)
    assert [x.skill_id for x in s1.skills] == [x.skill_id for x in s2.skills]
    assert [x.skill_id for x in s1.trials] == [x.skill_id for x in s2.trials]
    assert [x.lesson_id for x in s1.lessons] == [x.lesson_id for x in s2.lessons]
    assert h.to_dict() == before                          # 纯函数:不 mutate H


# ── build_system_prompt:试验位段(两模式都渲染)+ retrieval 预算 + full 零回归 ──

def test_full_mode_renders_trial_slots_with_pattern_instruction():
    h = _h([_skill("a1")])
    for sid in ("i1", "i2", "i3", "i4"):
        h.skills.write(_skill(sid, status="incubating"))
    prompt = build_system_prompt(h)                       # 默认 full 也渲染试验位(死锁修复不依赖切模式)
    assert "试验位" in prompt and "[试验]" in prompt
    assert "技_i4" in prompt and "技_i2" in prompt
    assert "技_i1" not in prompt                          # 超出 trial_slots=3(最旧)不渲染
    assert "pattern 必须填其 skill_id" in prompt          # 归因指示:孵化技能攒战绩的唯一通道


def test_full_mode_without_incubating_has_no_trial_section():
    h = _h([_skill("a1")], [_lesson("l1", 1.0)])
    prompt = build_system_prompt(h)
    assert "试验" not in prompt                           # 无孵化技能 → 试验位段整段不出现(零回归)


def test_full_mode_zero_regression_active_and_memory_are_full():
    # full:active 全量 + 记忆全量(weight<0.15 也渲染,demote 在 full 仍按旧行为)
    h = _h([_skill(f"s{i}", n=i) for i in range(6)], [_lesson("l_lo", 0.01)])
    p_default = build_system_prompt(h)
    p_explicit = build_system_prompt(h, injection="full", phase_prior="主升",
                                     skill_budget=2, memory_budget=1)
    assert p_default == p_explicit                        # full 下预算/先验不改变渲染
    for i in range(6):
        assert f"技_s{i}" in p_default
    assert "教训_l_lo" in p_default


def test_retrieval_mode_budgets_and_demote_effective():
    h = _h([_skill(f"s{i}", n=i) for i in range(4)],
           [_lesson("l_hi", 1.0), _lesson("l_lo", 0.1)])
    p = build_system_prompt(h, injection="retrieval", skill_budget=2, memory_budget=10)
    assert "技_s3" in p and "技_s2" in p                  # n 降序 top-2
    assert "技_s1" not in p and "技_s0" not in p          # 预算外不渲染
    assert "教训_l_hi" in p
    assert "教训_l_lo" not in p                           # weight=0.1<0.15 → demote 即时生效


def test_retrieval_mode_phase_prior_prioritizes_hit_skill():
    h = _h([_skill("hit", ("主升",), n=0), _skill("other", ("退潮",), n=9)])
    p = build_system_prompt(h, injection="retrieval", phase_prior="主升", skill_budget=1)
    assert "技_hit" in p and "技_other" not in p          # 命中压过战绩 n


# ── LLMAgentPolicy:phase_prior 跨日传递 + injection 默认 full 零回归 ──────────

def _state(d):
    return MarketState(date=d, max_board_height=3, limit_up_count=1,
                       blowup_count=0, blowup_rate=0.0, limit_down_count=0, echelon=[],
                       money_effect_raw=1.0, sentiment_raw=5.0, sentiment_norm=None,
                       as_of=datetime(d.year, d.month, d.day, 15, 0))


def _uni():
    return CandidateUniverse.from_stocks(
        [StockSnapshot(code="000001", name="甲", status="limit_up", boards=3)])


def test_agent_phase_prior_carries_to_next_day_and_resets_on_parse_failure():
    h = _h([_skill("hit", ("主升",), n=0), _skill("other", ("退潮",), n=9)])
    ok = ('{"regime_read":"主升","candidates":'
          '[{"code":"000001","pattern":"hit","reason":"r","confidence":0.6}],'
          '"no_trade_reason":""}')
    llm = MockLLMClient([ok, "这不是 JSON", ok])
    agent = LLMAgentPolicy(h, llm, injection="retrieval", skill_budget=1)
    # 第 1 日:无先验 → 按 n 降序,other 入选
    agent.decide(_state(date(2024, 6, 27)), _uni())
    assert "技_other" in llm.calls[0][0] and "技_hit" not in llm.calls[0][0]
    # 第 2 日:先验=昨日 regime_read("主升",≤t 自身输出)→ hit 压过 other
    agent.decide(_state(date(2024, 6, 28)), _uni())
    assert "技_hit" in llm.calls[1][0] and "技_other" not in llm.calls[1][0]
    # 第 2 日解析失败 → 先验清空;第 3 日回到无先验排序
    agent.decide(_state(date(2024, 6, 29)), _uni())
    assert "技_other" in llm.calls[2][0] and "技_hit" not in llm.calls[2][0]


def test_agent_default_full_mode_prompt_is_prior_independent():
    # 默认 injection='full' 零回归:全量渲染,系统提示不随 regime_read 先验变化
    h = _h([_skill("hit", ("主升",), n=0), _skill("other", ("退潮",), n=9)])
    ok = '{"regime_read":"主升","candidates":[],"no_trade_reason":"观望"}'
    llm = MockLLMClient([ok, ok])
    agent = LLMAgentPolicy(h, llm)
    agent.decide(_state(date(2024, 6, 27)), _uni())
    agent.decide(_state(date(2024, 6, 28)), _uni())
    assert llm.calls[0][0] == llm.calls[1][0]             # H 未变 → 提示逐字不变
    assert "技_hit" in llm.calls[0][0] and "技_other" in llm.calls[0][0]   # active 全量
