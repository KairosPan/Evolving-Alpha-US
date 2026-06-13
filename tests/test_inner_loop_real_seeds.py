# tests/test_inner_loop_real_seeds.py
"""真实种子(seeds/)端到端内环:act→延迟打分→在线信用→每日 refine(+熔断)。

与 test_inner_loop.py 的玩具 _seed_h() 不同,这里用 load_seeds("seeds/") 的全量
真实 HarnessState(57 技能 / 22 doctrine 段),证明 InnerLoop 在真实 H 上可跑通:
- agent 决策引用真实技能 name_cn(一进二/relay_1to2),在线信用能归因到该技能;
- refiner 各 pass 的 ops 含 1 条对真实 mutable doctrine 段(主升相位作战指导)的 rewrite
  + 1 条对真实技能(弱转强/w2s_weak_to_strong)的 retire,均带非空 rationale,入 EditLog;
- 单独构造坏结局验证熔断 rollback + 冻结。
全离线(FakeSource + MockLLMClient)。
"""
from datetime import date, timedelta

import pandas as pd

from youzi.harness.loader import load_seeds
from youzi.harness.manager import HarnessManager
from youzi.harness.snapshot import SnapshotStore
from youzi.llm.client import MockLLMClient
from youzi.loop.inner_loop import InnerLoop, LoopConfig
from tests.conftest import FakeSource

# ── 真实种子里确实存在的引用目标(见 seeds/skills.json、seeds/doctrine.json) ──
SEED_SKILL_NAME = "一进二"               # relay_1to2.name_cn,agent 决策 pattern 用它(走 name_cn 解析)
SEED_SKILL_ID = "relay_1to2"
RETIRE_SKILL_ID = "w2s_weak_to_strong"   # 弱转强;agent 不引用它,refiner K-pass 退役它
MUTABLE_SECTION = "主升相位作战指导"      # immutable=False 的真实 doctrine 段,refiner p-pass 改写它


def _seeds_mgr(tmp_path):
    h = load_seeds("seeds/")
    return HarnessManager(h, SnapshotStore(tmp_path))


def _decision(code: str) -> str:
    """决策包 JSON:选 code,pattern 用真实种子技能 name_cn,使在线信用能归因。"""
    return ('{"candidates": [{"code": "%s", "pattern": "%s", "confidence": 0.7}],'
            ' "no_trade_reason": ""}') % (code, SEED_SKILL_NAME)


def _continued_src(n_days: int) -> FakeSource:
    """code A 每日涨停(被选后 horizon=1 必 continued)。"""
    days = [date(2024, 6, 26) + timedelta(days=k) for k in range(n_days)]
    frames = {("zt", d): pd.DataFrame({"code": ["A"], "name": ["甲"], "boards": [2]})
              for d in days}
    return FakeSource(frames, days)


def _refiner_scripts() -> list[str]:
    """refiner 各 pass 脚本。_PASS_ORDER=(p,G,K,M),G 为空(no-op 不发 LLM 调用),
    故每次 refine 对 LLM 调用 3 次:p→K→M。首次 refine:
      call#0 (p): 改写真实 mutable doctrine 段;
      call#1 (K): 退役真实技能 w2s_weak_to_strong;
      call#2 (M): 空。
    其后 MockLLM 重复末元素(空 ops)→ 后续 refine 不再产生编辑。"""
    p = ('{"ops": [{"tool": "rewrite_doctrine",'
         ' "args": {"section": "%s", "new_guidance": "内环集成测试改写:主升只打核心龙头不接力"},'
         ' "rationale": "证据窗口显示接力胜率走弱,收紧主升打法"}]}') % MUTABLE_SECTION
    k = ('{"ops": [{"tool": "retire_skill", "args": {"skill_id": "%s"},'
         ' "rationale": "弱转强本窗口连续被砸,退役观察"}]}') % RETIRE_SKILL_ID
    m = '{"ops": []}'
    return [p, k, m]


def test_real_seeds_end_to_end_act_score_credit_refine(tmp_path):
    n = 4
    src = _continued_src(n)
    mgr = _seeds_mgr(tmp_path)
    # 退役前 sanity:真实种子里这两个技能/段确实存在且为预期初态
    assert mgr.harness.skills.get(SEED_SKILL_ID).name_cn == SEED_SKILL_NAME
    assert mgr.harness.skills.get(SEED_SKILL_ID).stats.n == 0
    assert mgr.harness.skills.get(RETIRE_SKILL_ID).status == "active"
    # 退役证据门(Phase-1b-3d):该技能 agent 不引用、stats.n 永为 0,会被门拦下;
    # 本端到端测试意在验证 retire 流(refine→H→EditLog→reset-free),故预置足够样本让其过门。
    mgr.harness.skills.get(RETIRE_SKILL_ID).stats.n = 5
    assert mgr.harness.doctrine.get(MUTABLE_SECTION).immutable is False
    doc_before = mgr.harness.doctrine.get(MUTABLE_SECTION).guidance

    loop = InnerLoop(
        mgr, src, src.trading_calendar()[0], src.trading_calendar()[-1],
        MockLLMClient([_decision("A")]), MockLLMClient(_refiner_scripts()),
        # A3:evidence_min=1 保持原意(每日 1 候选即 refine;默认 6 在 4 日窗内永不触发)
        config=LoopConfig(breaker_min_days=10_000, evidence_min=1),   # 不熔断
    )
    rep = loop.run()

    # ① 轨迹:n 步;horizon=1 → 前 n-1 步已打分,尾步未打分
    assert rep.trajectory.n_decisions() == n
    scored = rep.trajectory.scored_steps()
    assert len(scored) == n - 1
    assert rep.trajectory.steps[-1].scored is False
    # 延迟 outcomes 正确:被选 A 每日仍涨停 → continued
    assert all(s.outcomes["A"].outcome == "continued" for s in scored)

    # ② 在线信用:真实技能 relay_1to2(pattern 一进二)被引用且 continued → H 内 stats 已更新
    st = mgr.harness.skills.get(SEED_SKILL_ID).stats
    assert st.n == n - 1 and st.wins == n - 1
    # C2 语义变更:expectancy=advantage(score−当日池基线)。单码池 {A} 基线=1.0 →
    # 选 A=闭眼买全池,超额=0;原始口径移至 expectancy_raw(仍=全 continued 的 +1 均值)。
    assert st.expectancy == 0.0
    assert st.expectancy_raw == 1.0

    # ③ refine 每日触发(有新证据起):day1/day2/day3 各一次
    assert [e.date for e in rep.refine_events] == \
        [date(2024, 6, 27), date(2024, 6, 28), date(2024, 6, 29)]
    assert rep.refine_events[0].checkpoint_version is not None
    # 首次 refine 应用了 2 条编辑(doctrine rewrite + skill retire),均带 rationale
    applied = rep.refine_events[0].report.applied
    tools = {a.tool for a in applied}
    assert {"rewrite_doctrine", "retire_skill"} <= tools
    assert all(a.rationale.strip() for a in applied)

    # ④ 编辑落到真实 H + 入 EditLog(带 rationale);n_edits 计数一致
    assert mgr.harness.skills.get(RETIRE_SKILL_ID).status == "dormant"   # 真实技能被退役
    assert mgr.harness.doctrine.get(MUTABLE_SECTION).guidance != doc_before
    log = mgr.log.records()
    assert any(r.tool == "retire_skill" and r.target_id == RETIRE_SKILL_ID
               and r.rationale.strip() for r in log)
    assert any(r.tool == "rewrite_doctrine" and r.target_id == MUTABLE_SECTION
               and r.rationale.strip() for r in log)
    assert rep.n_edits == len(log)

    # ⑤ reset-free:退役于 day1 refine 后 → day1 决策提示仍列该技能行,day2 已不列。
    # 提示模式库行渲染为 "name_cn(skill_id)",用 (skill_id) token 精确定位该技能行
    # (子串 "弱转强" 会在红线/其他技能名里误命中,故不可用名做判据)。
    sys_day1 = loop._agent_llm.calls[1][0]
    sys_day2 = loop._agent_llm.calls[2][0]
    retire_token = f"({RETIRE_SKILL_ID})"
    assert retire_token in sys_day1
    assert retire_token not in sys_day2
    # 而 agent 引用的 relay_1to2 始终在(未被退役)
    assert f"({SEED_SKILL_ID})" in sys_day2


def _bad_pick_src(n_days: int) -> FakeSource:
    """每日池 {G, C_i}:G 持续涨停(+1), C_i 次日跌停(-1),用于制造负超额。"""
    days = [date(2024, 6, 1) + timedelta(days=k) for k in range(n_days)]
    frames: dict = {}
    for i, d in enumerate(days):
        frames[("zt", d)] = pd.DataFrame({"code": ["G", f"C{i}"], "name": ["稳", f"C{i}"],
                                          "boards": [3, 1]})
        if i >= 1:
            frames[("dt", d)] = pd.DataFrame({"code": [f"C{i-1}"], "name": [f"C{i-1}"]})
    return FakeSource(frames, days)


def test_real_seeds_breaker_rolls_back_then_freezes(tmp_path):
    """坏结局:持续跑输同日池均值 → 首次整段回滚再武装,二次触发冻结。"""
    n = 10
    src = _bad_pick_src(n)
    days = src.trading_calendar()
    mgr = _seeds_mgr(tmp_path)
    agent_scripts = [_decision("G")] * 3 + [_decision(f"C{i}") for i in range(3, n)]
    # A3:evidence_min=1 保持原意(熔断前需先发生过 refine 才有 checkpoint 可回滚)
    cfg = LoopConfig(breaker_k_max=3, refine_every=1, evidence_min=1)
    loop = InnerLoop(mgr, src, src.trading_calendar()[0], src.trading_calendar()[-1],
                     MockLLMClient(agent_scripts), MockLLMClient(['{"ops": []}']),
                     config=cfg)
    rep = loop.run()

    assert [be.mode for be in rep.breaker_events] == ["rollback", "frozen"]
    first, second = rep.breaker_events
    assert "floor_abs" in first.reason
    assert first.rolled_back_to is not None
    pre_window = [e for e in rep.refine_events if e.date < days[2]]
    assert first.rolled_back_to == pre_window[-1].checkpoint_version
    assert second.rolled_back_to == first.rolled_back_to
    assert rep.frozen_from == second.date
    # 冻结后不再 refine
    assert all(e.date < rep.frozen_from for e in rep.refine_events)
    # rollback 后 agent/refiner 已 _rebind 指向还原态同一 live H
    assert loop._agent._harness is mgr.harness
    assert loop._refiner._h is mgr.harness
