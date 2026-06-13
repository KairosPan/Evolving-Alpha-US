# tests/test_inner_loop.py
from datetime import date, timedelta

import pandas as pd
import pytest

from youzi.eval.trajectory import Trajectory
from youzi.loop.inner_loop import (InnerLoop, LoopConfig, LoopReport, RefineEvent, BreakerEvent,
                                   _fallback_trip, _shadow_trip, _shadow_eps_abs, _mad)
from youzi.harness.skill import Skill
from youzi.harness.registry import SkillRegistry
from youzi.harness.memory_store import MemoryStore
from youzi.harness.doctrine import Doctrine, DoctrineEntry
from youzi.harness.cycle import StateMachine
from youzi.harness.harness import HarnessState
from youzi.harness.snapshot import SnapshotStore
from youzi.harness.manager import HarnessManager
from youzi.llm.client import MockLLMClient
from tests.conftest import FakeSource


def _seed_h():
    skills = SkillRegistry.from_skills([
        Skill.from_seed({"skill_id": "longtou", "name_cn": "龙头接力", "type": "pattern",
                         "applicable_regime": ["主升"], "trigger": "t", "entry": "e",
                         "exit_stop": "x", "status": "active"})])
    doc = Doctrine(entries=[DoctrineEntry.from_seed(
        {"section": "主升作战", "regime": "主升", "immutable": False, "guidance": "持有龙头"})])
    return HarnessState(doctrine=doc, skills=skills,
                        memory=MemoryStore.from_lessons([]), cycle=StateMachine())


def _mgr(tmp_path):
    return HarnessManager(_seed_h(), SnapshotStore(tmp_path))


def _decision(code):
    return ('{"candidates": [{"code": "%s", "pattern": "龙头接力", "confidence": 0.7}],'
            ' "no_trade_reason": ""}') % code


def _loop(tmp_path, src, agent_scripts, refiner_scripts, config=None, shadow_daily=None):
    mgr = _mgr(tmp_path)
    return InnerLoop(mgr, src, src.trading_calendar()[0], src.trading_calendar()[-1],
                     MockLLMClient(agent_scripts), MockLLMClient(refiner_scripts),
                     config=config, shadow_daily=shadow_daily), mgr


def test_models_frozen_and_truthy():
    rep = LoopReport(trajectory=Trajectory())
    assert bool(rep) is True
    with pytest.raises(Exception):
        rep.frozen_from = date(2024, 1, 1)        # frozen


def test_loop_constructs_and_rebinds(tmp_path):
    src = FakeSource({("zt", date(2024, 6, 26)): pd.DataFrame({"code": ["A"], "name": ["A"], "boards": [1]})},
                     [date(2024, 6, 26)])
    loop, mgr = _loop(tmp_path, src, [_decision("A")], ['{"ops": []}'])
    # 构造后 agent/refiner 已绑定到 mgr.harness
    assert loop._agent._harness is mgr.harness
    assert loop._refiner._h is mgr.harness
    # rollback 后 _rebind 指向还原态新对象
    v = mgr.checkpoint("c0")
    mgr.tools.retire_skill("longtou")
    mgr.rollback_to(v)
    loop._rebind()
    assert loop._agent._harness is mgr.harness
    assert loop._refiner._h is mgr.harness
    assert mgr.harness.skills.get("longtou").status == "active"   # 还原


def _continued_src():
    """A 每日涨停(continued);3 日。"""
    days = [date(2024, 6, 26), date(2024, 6, 27), date(2024, 6, 28)]
    frames = {}
    for d in days:
        frames[("zt", d)] = pd.DataFrame({"code": ["A"], "name": ["甲"], "boards": [2]})
    return FakeSource(frames, days)


def test_run_interleaves_scoring_and_online_credit(tmp_path):
    src = _continued_src()
    loop, mgr = _loop(tmp_path, src, [_decision("A")], ['{"ops": []}'],
                      config=LoopConfig(breaker_min_days=10_000))  # 不熔断
    rep = loop.run()
    # 轨迹:3 步,前 2 步已打分(horizon=1),尾步未打分
    assert rep.trajectory.n_decisions() == 3
    assert [s.date for s in rep.trajectory.scored_steps()] == [date(2024, 6, 26), date(2024, 6, 27)]
    assert rep.trajectory.steps[2].scored is False
    assert rep.trajectory.steps[0].outcomes["A"].outcome == "continued"
    # 在线信用:技能 longtou(pattern "龙头接力")被引用且 continued → stats 在 H 内已更新
    st = mgr.harness.skills.get("longtou").stats
    assert st.n == 2 and st.wins == 2          # 2 个已打分决策都归因到 longtou 且 continued


def test_refine_edits_visible_next_day_resetfree(tmp_path):
    src = _continued_src()
    # refiner:refine1 在 K-pass 退役 longtou;p/M 空;之后全空(MockLLM 重复末元素)
    refiner_scripts = ['{"ops": []}',
                       '{"ops": [{"tool": "retire_skill", "args": {"skill_id": "longtou"},'
                       ' "rationale": "示例退役"}]}',
                       '{"ops": []}']
    # A3:evidence_min=1 保持原意(每日 1 候选即 refine;默认 6 在 3 日窗内永不触发)
    loop, mgr = _loop(tmp_path, src, [_decision("A")], refiner_scripts,
                      config=LoopConfig(breaker_min_days=10_000, evidence_min=1))  # 不熔断
    # 退役证据门(Phase-1b-3d):day1 refine 时 longtou 仅累计 n=1<默认门槛,会被拦下;
    # 本测试意在验证退役的 reset-free 可见性,故预置足够样本让其过门。
    mgr.harness.skills.get("longtou").stats.n = 5
    rep = loop.run()
    # refine 每日触发(有新证据起):day1、day2 各一次
    assert [e.date for e in rep.refine_events] == [date(2024, 6, 27), date(2024, 6, 28)]
    assert rep.refine_events[0].checkpoint_version is not None
    # reset-free:day1 决策(call#1)系统提示仍含 longtou;day2(call#2)已不含(退役于 day1 refine 后)
    sys_day1 = loop._agent_llm.calls[1][0]
    sys_day2 = loop._agent_llm.calls[2][0]
    assert "龙头接力" in sys_day1
    assert "龙头接力" not in sys_day2
    # 编辑入 EditLog(带 rationale)
    assert any(r.tool == "retire_skill" and r.rationale for r in mgr.log.records())


def _nuke_src(n_days):
    """每日 C_i 涨停;次日 C_i 跌停(被选后必 nuked)。"""
    days = [date(2024, 6, 1) + timedelta(days=k) for k in range(n_days)]
    frames = {}
    for i, d in enumerate(days):
        frames[("zt", d)] = pd.DataFrame({"code": [f"C{i}"], "name": [f"C{i}"], "boards": [1]})
        if i >= 1:
            frames[("dt", d)] = pd.DataFrame({"code": [f"C{i-1}"], "name": [f"C{i-1}"]})
    return FakeSource(frames, days)


# ── B2 熔断重设计:日级武装 + MAD 自标定 fallback + 影子配对双门 + 真冻结 + 整段回滚再武装 ──
#(旧 test_breaker_trips_rolls_back_and_freezes / test_breaker_freezes_without_checkpoint_when_no_refine
#  按新语义重写:武装单位从"40 已评分候选"改为"breaker_min_days 已评分决策日";判定从
#  原始分 rolling vs floor_abs/相对地板,改为日级 advantage 序列的 MAD 自标定/影子配对。)


def _bad_pick_src(n_days):
    """每日池 {G, C_i}:G 持续涨停(continued,+1);C_i 次日跌停(nuked,−1)。

    日基线 =(+1−1)/2 = 0 → 选 C_i 的 advantage=−1(真·负超额),选 G 的 advantage=+1。
    与旧 _nuke_src 的关键差异:单码池里"选谁都=闭眼买全池",advantage 恒 0,B2 的
    advantage 口径熔断永不触发——必须有池内赢家垫出非零基线差。
    """
    days = [date(2024, 6, 1) + timedelta(days=k) for k in range(n_days)]
    frames = {}
    for i, d in enumerate(days):
        frames[("zt", d)] = pd.DataFrame({"code": ["G", f"C{i}"], "name": ["稳", f"C{i}"],
                                          "boards": [3, 1]})
        if i >= 1:
            frames[("dt", d)] = pd.DataFrame({"code": [f"C{i-1}"], "name": [f"C{i-1}"]})
    return FakeSource(frames, days)


# ── B2 判定纯函数(手算例)──

def test_fallback_trip_mad_hand_calc():
    # 触发例:全历史 [0, .1, −.05, .05, −.6, −.7, −.65] → median=−0.05,
    # MAD=median(|x+0.05|)=0.15 → 阈=−0.05−2×0.15=−0.35;
    # rolling(k=3)=mean(−.6,−.7,−.65)=−0.65 < −0.35 → 触发
    hist = [0.0, 0.1, -0.05, 0.05, -0.6, -0.7, -0.65]
    trip, rolling, thr, reason = _fallback_trip(hist, k=3, c=2.0, floor_abs=-0.2)
    assert trip
    assert rolling == pytest.approx(-0.65)
    assert thr == pytest.approx(-0.35)
    assert "MAD" in reason and "floor_abs" not in reason     # 走自标定分支,非兜底
    # 不触发例:[0, .1, −.05, .05, −.1] → median=0,MAD=0.05 → 阈=−0.1;
    # rolling(k=3)=mean(−.05,.05,−.1)=−0.0333 > −0.1 → 不触发
    hist2 = [0.0, 0.1, -0.05, 0.05, -0.1]
    trip2, rolling2, thr2, _ = _fallback_trip(hist2, k=3, c=2.0, floor_abs=-0.2)
    assert not trip2
    assert rolling2 == pytest.approx(-0.1 / 3)
    assert thr2 == pytest.approx(-0.1)


def test_fallback_trip_degenerate_mad_uses_floor_abs():
    # MAD≈0(序列恒常数 → 自标定失效)→ 退回绝对地板 floor_abs 兜底
    trip, rolling, thr, reason = _fallback_trip([-0.1] * 5, k=3, c=2.0, floor_abs=-0.2)
    assert not trip and thr == -0.2 and "floor_abs" in reason     # −0.1 > −0.2:不触发
    trip2, rolling2, thr2, reason2 = _fallback_trip([-0.5] * 5, k=3, c=2.0, floor_abs=-0.2)
    assert trip2 and "floor_abs" in reason2                       # −0.5 < −0.2:触发
    assert _mad([-0.5] * 5) == 0.0                                # 兜底前提确实成立


def test_shadow_trip_eps_blocks_tiny_negative_with_zero_std():
    # temp=0 实证 HCH≡Hexpert 配对差恒 0 是常态(findings §9):微小负差 + std≈0,
    # 无 ε_abs 时 mean<−λ·0 会误触发——ε_abs 兜底挡下
    trip, mean_d, thr, _ = _shadow_trip([-0.001] * 3, k=3, lam=1.0, eps_abs=0.05)
    assert not trip
    assert mean_d == pytest.approx(-0.001)
    assert thr == -0.05                                  # 阈=−max(λ·0, 0.05)=−0.05


def test_shadow_trip_persistent_large_negative_trips():
    # 持续大负差:mean=−0.55 < −max(σ=0.05, ε=0.05)=−0.05;方向门 3/3 全负 → 触发
    trip, mean_d, thr, _ = _shadow_trip([-0.5, -0.6, -0.55], k=3, lam=1.0, eps_abs=0.05)
    assert trip
    assert mean_d == pytest.approx(-0.55)


def test_shadow_trip_direction_gate_blocks_spikes():
    # 单日大负+余日为零(spec 原例):主门已挡(mean=−0.5 > −σ≈−0.866)
    trip, *_ = _shadow_trip([0.0, 0.0, -1.5], k=3, lam=1.0, eps_abs=0.05)
    assert not trip
    # 两日大负+一日零:主门过(mean=−0.8 < −σ≈−0.693)但严格负日 2/3 < ⌈3/2⌉+1=3 →
    # 方向一致性副门单独挡下(证明副门非冗余)
    diffs = [-1.2, 0.0, -1.2]
    trip2, mean_d, thr, _ = _shadow_trip(diffs, k=3, lam=1.0, eps_abs=0.05)
    assert not trip2
    assert mean_d < thr                                  # 主门确实已过 → 必是方向门挡的


def test_shadow_eps_abs_calibration():
    assert _shadow_eps_abs([0.0, 0.0, 0.0], c=0.25, floor=0.05) == 0.05   # 全零影子 → 绝对兜底
    assert _shadow_eps_abs([0.5, 0.5, 0.5], c=0.25, floor=0.05) == 0.05   # 非零但常数 → MAD=0 → 兜底
    # 非零项 [1,2,4]:median=2,MAD=median(1,0,2)=1 → ε=0.25×1(零项不参与标定)
    assert _shadow_eps_abs([1.0, 2.0, 4.0, 0.0], c=0.25, floor=0.05) == pytest.approx(0.25)


# ── B2 ① 日级武装:3 个有候选的已评分日即可评估(旧 40 候选门不再挡)──

def test_breaker_arms_on_scored_days_not_candidates(tmp_path):
    n = 5
    src = _bad_pick_src(n)
    agent_scripts = [_decision(f"C{i}") for i in range(n)]    # 每日选必被砸的 C_i(advantage=−1)
    # 默认 breaker_min_days=3;refine_every 极大 → 无 checkpoint → 首次触发直接 frozen
    loop, mgr = _loop(tmp_path, src, agent_scripts, ['{"ops": []}'],
                      config=LoopConfig(refine_every=10_000))
    rep = loop.run()
    assert len(rep.breaker_events) == 1
    be = rep.breaker_events[0]
    # 第 3 个已评分日(d2 于 idx=3 回填)即评估并触发——总候选仅 3 个,旧 40 候选门下永不上膛
    assert be.date == date(2024, 6, 4)
    assert "floor_abs" in be.reason          # 全 −1 → 全历史 MAD≈0 → 退化分布走绝对兜底
    assert be.rolling == pytest.approx(-1.0)
    assert be.mode == "frozen" and be.rolled_back_to is None
    assert rep.frozen_from == be.date


def test_breaker_freezes_without_checkpoint_when_no_refine(tmp_path):
    # 无 refine → 无 checkpoint → B2 ⑤ 首次触发即"直接 frozen"(照旧路径)
    n = 6
    src = _bad_pick_src(n)
    agent_scripts = [_decision(f"C{i}") for i in range(n)]
    loop, mgr = _loop(tmp_path, src, agent_scripts, ['{"ops": []}'],
                      config=LoopConfig(refine_every=10_000))
    rep = loop.run()
    assert len(rep.breaker_events) == 1
    assert rep.breaker_events[0].rolled_back_to is None       # 无 checkpoint → 只冻结
    assert rep.breaker_events[0].mode == "frozen"
    assert rep.refine_events == []


# ── B2 ④ frozen 真冻结:apply_credit 停写,打分/轨迹照常 ──

def test_frozen_stops_credit_but_keeps_scoring(tmp_path):
    # 旧语义假定 credit 总是写(冻结后 stats 仍随打分增长);B2 新语义=冻结即停回注,
    # 冻结的 H(含提示里的技能战绩)不再漂移,与"冻结基线"一致。
    n = 7
    src = _bad_pick_src(n)
    agent_scripts = [_decision(f"C{i}") for i in range(n)]
    loop, mgr = _loop(tmp_path, src, agent_scripts, ['{"ops": []}'],
                      config=LoopConfig(refine_every=10_000))
    rep = loop.run()
    assert rep.frozen_from == date(2024, 6, 4)                # 第 3 个已评分日触发(同上)
    # 打分/轨迹照常:6 个已评分步(d0..d5)全部回填 outcomes
    assert len(rep.trajectory.scored_steps()) == n - 1
    # stats 只计冻结前已回注的 3 步(d0..d2;d2 与触发同迭代、先回注后熔断);
    # 未门控时会是 6 —— 差值即"冻结后提示漂移"被堵住的量
    st = mgr.harness.skills.get("longtou").stats
    assert st.n == 3 and st.nukes == 3


# ── B2 ⑤ 整段回滚(退化窗起点前最近 checkpoint,非 last_ckpt)+ 可再武装 ──

def test_breaker_rolls_back_to_pre_window_checkpoint_and_rearms(tmp_path):
    # 8 日:前 3 日选 G(advantage=+1),d3 起选 C_i(−1)。日级史 [1,1,1,−1,−1] 在第 5 个
    # 已评分日(idx=5):median=1、MAD=0 → floor_abs 兜底,rolling(k=3)=−1/3 < −0.2 → 触发。
    # 退化窗=最近 3 已评分日 [d2,d3,d4] → 起点 d2 → 回滚目标=日期<d2 的最近 ckpt(d1 的 v0),
    # 而非 last_ckpt(d4 的 v3)——撤销整段退化期编辑而非最后一刀。
    n = 8
    src = _bad_pick_src(n)
    days = src.trading_calendar()
    agent_scripts = [_decision("G")] * 3 + [_decision(f"C{i}") for i in range(3, n)]
    cfg = LoopConfig(breaker_k_max=3, refine_every=1, evidence_min=1)
    loop, mgr = _loop(tmp_path, src, agent_scripts, ['{"ops": []}'], config=cfg)
    rep = loop.run()
    assert len(rep.breaker_events) == 1
    be = rep.breaker_events[0]
    assert be.mode == "rollback"
    assert rep.frozen_from is None                            # 再武装:未冻结,继续跑
    # 回滚目标 = 退化窗起点 d2 之前的最近 checkpoint(d1 那次 refine 的版本)
    pre_window = [e for e in rep.refine_events if e.date < days[2]]
    assert be.rolled_back_to == pre_window[-1].checkpoint_version
    # 而非触发前最后一个 checkpoint(旧语义)——两者必须不同,否则测试空泛
    last_ckpt_before_trip = [e for e in rep.refine_events if e.date < be.date][-1].checkpoint_version
    assert be.rolled_back_to != last_ckpt_before_trip
    # 回滚后 _rebind:agent/refiner 指向还原态 live H;且回滚后仍在 refine(再武装继续跑)
    assert loop._agent._harness is mgr.harness
    assert any(e.date > be.date for e in rep.refine_events)


def test_breaker_second_trip_freezes_after_rearm(tmp_path):
    # 可再武装状态机:首次触发 → rollback+清证据继续跑;再积满 breaker_min_days 个新
    # 已评分日后第二次触发 → 永久 frozen(计数器;第二次仍回滚撤销本段退化)。
    n = 10
    src = _bad_pick_src(n)
    days = src.trading_calendar()
    agent_scripts = [_decision("G")] * 3 + [_decision(f"C{i}") for i in range(3, n)]
    cfg = LoopConfig(breaker_k_max=3, refine_every=1, evidence_min=1)
    loop, mgr = _loop(tmp_path, src, agent_scripts, ['{"ops": []}'], config=cfg)
    rep = loop.run()
    assert [be.mode for be in rep.breaker_events] == ["rollback", "frozen"]
    first, second = rep.breaker_events
    # 第一次:窗 [d2,d3,d4] → 回滚到 d1 的 ckpt;第二次:窗 [d5,d6,d7](清证据后重积),
    # 弃时间线 ckpt 已剪枝 → 目标仍是 d1 的 v0(d5 当日 ckpt 不早于窗起点,不取)
    assert second.date > first.date
    assert second.rolled_back_to == first.rolled_back_to
    assert rep.frozen_from == second.date
    # 冻结后不再 refine
    assert all(e.date < rep.frozen_from for e in rep.refine_events)


# ── B2 ② 影子配对地板(shadow_daily 注入)──

def test_shadow_paired_floor_trips_in_loop(tmp_path):
    # 本臂日级 −1 vs 影子恒 0 → 配对差恒 −1:std=0 由 ε_abs 兜底(影子全零 → ε=0.05),
    # 方向门 3/3 全负 → 双门齐过,第 3 个配对日触发(直抓"比 frozen 差")
    n = 5
    src = _bad_pick_src(n)
    days = src.trading_calendar()
    shadow = {d: 0.0 for d in days}
    agent_scripts = [_decision(f"C{i}") for i in range(n)]
    loop, mgr = _loop(tmp_path, src, agent_scripts, ['{"ops": []}'],
                      config=LoopConfig(refine_every=10_000), shadow_daily=shadow)
    rep = loop.run()
    assert len(rep.breaker_events) == 1
    be = rep.breaker_events[0]
    assert be.reason.startswith("shadow")
    assert be.rolling == pytest.approx(-1.0)             # 最近 k 日配对差均值
    assert be.baseline == pytest.approx(-0.05)           # 阈=−max(λ·0, ε_floor=0.05)
    assert be.mode == "frozen"                           # 无 refine → 无 ckpt → 直接 frozen


def test_shadow_daily_ignores_future_keys_no_lookahead(tmp_path):
    # 防前视:shadow_daily 含未来日期键(非零、有离散度——若泄漏进 ε_abs 标定,
    # ε 会从兜底 0.05 变成 0.25×MAD([1,2,4])=0.25,触发阈随之改变)。
    # InnerLoop 严格只消费 ≤ 当前已评分日的条目 → 阈值必须仍是 −0.05。
    n = 5
    src = _bad_pick_src(n)
    days = src.trading_calendar()
    shadow = {d: 0.0 for d in days}
    shadow[date(2024, 7, 1)] = 1.0       # 未来键(窗外)
    shadow[date(2024, 7, 2)] = 2.0
    shadow[date(2024, 7, 3)] = 4.0
    agent_scripts = [_decision(f"C{i}") for i in range(n)]
    loop, mgr = _loop(tmp_path, src, agent_scripts, ['{"ops": []}'],
                      config=LoopConfig(refine_every=10_000), shadow_daily=shadow)
    rep = loop.run()
    assert len(rep.breaker_events) == 1
    be = rep.breaker_events[0]
    assert be.date == date(2024, 6, 4)                   # 触发时点不变(第 3 个配对日)
    assert be.baseline == pytest.approx(-0.05)           # ε 仍为兜底 0.05 → 未来键未被消费


def test_loop_config_rejects_degenerate():
    from pydantic import ValidationError
    for bad in ({"horizon": 0}, {"breaker_window": 0}, {"baseline_window": 0},
                {"breaker_min_samples": 0}, {"refine_every": 0}, {"credit_window": 0},
                {"evidence_min": 0}):
        with pytest.raises(ValidationError):
            LoopConfig(**bad)


def test_inner_loop_accepts_return_scorer(tmp_path):
    from youzi.eval.scorer import ReturnScorer
    days = [date(2024, 6, 26), date(2024, 6, 27), date(2024, 6, 28)]
    frames = {("zt", d): pd.DataFrame({"code": ["W"], "name": ["赢家"], "boards": [2]}) for d in days}
    ohlcv = {"W": pd.DataFrame([(date(2024, 6, 27), 10.0, 11, 9, 10.5, 100),
                                (date(2024, 6, 28), 10.6, 12, 10, 11.0, 200)],
                               columns=["date", "open", "high", "low", "close", "volume"])}
    src = FakeSource(frames, days, ohlcv=ohlcv)
    mgr = _mgr(tmp_path)
    loop = InnerLoop(mgr, src, days[0], days[-1], MockLLMClient(_decision("W")),
                     MockLLMClient('{"ops": []}'),
                     config=LoopConfig(horizon=1, breaker_min_days=10_000),
                     scorer=ReturnScorer())
    rep = loop.run()
    # 决策 6/26 → entry=exit=6/27:(10.5−10)/10=+0.05;score 为收益
    sc = rep.trajectory.scored_steps()[0].outcomes["W"]
    assert sc.outcome == "continued" and abs(sc.score - 0.05) < 1e-9


# ── A3:水位线非重叠证据窗 + evidence_min 触发门 + 编辑史随 _rebind 作废 ──

def test_watermark_evidence_window_does_not_overlap(tmp_path):
    # 同一证据(决策/签名里的 code)不跨 refine 重现:refine1 见 C0,refine2 只见 C1、不再见 C0
    n = 4
    src = _nuke_src(n)
    agent_scripts = [_decision(f"C{i}") for i in range(n)]
    loop, mgr = _loop(tmp_path, src, agent_scripts, ['{"ops": []}'],
                      config=LoopConfig(breaker_min_days=10_000, evidence_min=1))  # 不熔断
    rep = loop.run()
    assert len(rep.refine_events) >= 2
    # 每次 refine 发 3 次 live 调用(p/K/M),同一 user prompt;取每次 refine 的第 1 条
    u_refine1 = loop._refiner_llm.calls[0][1]
    u_refine2 = loop._refiner_llm.calls[3][1]
    assert "C0" in u_refine1                      # refine1 证据=步0(C0 被砸)
    assert "C0" not in u_refine2                  # 水位线推进 → refine2 不再重现 C0
    assert "C1" in u_refine2                      # refine2 证据=步1(C1)


def test_evidence_min_gates_refine_per_candidate(tmp_path):
    # 未达不触发:1 候选/日、evidence_min=2 → day1(1 候选)不触发;day2 累积 2 候选触发;
    # 触发后水位线推进 → day3 仅 1 新候选,不再触发
    days = [date(2024, 6, 26) + timedelta(days=k) for k in range(4)]
    frames = {("zt", d): pd.DataFrame({"code": ["A"], "name": ["甲"], "boards": [2]}) for d in days}
    src = FakeSource(frames, days)
    loop, mgr = _loop(tmp_path, src, [_decision("A")], ['{"ops": []}'],
                      config=LoopConfig(breaker_min_days=10_000, evidence_min=2))
    rep = loop.run()
    assert [e.date for e in rep.refine_events] == [days[2]]    # 仅 day3(idx=2,累积 2 候选)
    # 完全未达(evidence_min=4 > 窗内最大可累积 3 候选)→ 永不触发,refiner LLM 不被调
    loop2, _ = _loop(tmp_path / "b", src, [_decision("A")], ['{"ops": []}'],
                     config=LoopConfig(breaker_min_days=10_000, evidence_min=4))
    rep2 = loop2.run()
    assert rep2.refine_events == []
    assert loop2._refiner_llm.calls == []


def test_evidence_min_counts_candidates_not_steps(tmp_path):
    # 按候选计(非按步):单步 2 候选即满足 evidence_min=2,首个可 refine 日就触发
    days = [date(2024, 6, 26), date(2024, 6, 27)]
    frames = {("zt", d): pd.DataFrame({"code": ["A", "B"], "name": ["甲", "乙"],
                                       "boards": [2, 1]}) for d in days}
    src = FakeSource(frames, days)
    two_picks = ('{"candidates": [{"code": "A", "pattern": "龙头接力", "confidence": 0.7},'
                 ' {"code": "B", "pattern": "龙头接力", "confidence": 0.6}],'
                 ' "no_trade_reason": ""}')
    loop, mgr = _loop(tmp_path, src, [two_picks], ['{"ops": []}'],
                      config=LoopConfig(breaker_min_days=10_000, evidence_min=2))
    rep = loop.run()
    assert [e.date for e in rep.refine_events] == [days[1]]    # 1 步×2 候选 ≥ 2 → 触发


def test_watermark_advances_after_refine(tmp_path):
    # refine 成功后水位线推进到已评分步末尾(下窗不重叠)
    src = _continued_src()    # 3 日 → 2 个已评分步
    loop, mgr = _loop(tmp_path, src, [_decision("A")], ['{"ops": []}'],
                      config=LoopConfig(breaker_min_days=10_000, evidence_min=1))
    rep = loop.run()
    assert len(rep.refine_events) == 2
    assert loop._last_refined_idx == 2       # 2 个已评分步全被消费


def test_rebind_clears_refiner_edit_history(tmp_path):
    # _rebind(rollback 后)重建 Refiner → 编辑史清空(回滚后旧编辑史作废,见 inner_loop 注释)
    from youzi.refine.refiner import RefineReport
    src = _continued_src()
    loop, mgr = _loop(tmp_path, src, [_decision("A")], ['{"ops": []}'])
    loop._refiner._recent_reports.append(RefineReport())
    assert len(loop._refiner._recent_reports) == 1
    loop._rebind()
    assert len(loop._refiner._recent_reports) == 0


# ── C4:enable_refine 消融门(Hcredit 臂 = 只回注战绩、无结构编辑)──

def test_enable_refine_false_blocks_refine_keeps_credit(tmp_path):
    # 门控只挡 refine 块:refiner LLM 永不被调、零编辑;apply_credit 在线信用照常写 stats
    src = _continued_src()
    loop, mgr = _loop(tmp_path, src, [_decision("A")], ['{"ops": []}'],
                      config=LoopConfig(breaker_min_days=10_000, evidence_min=1,
                                        enable_refine=False))
    rep = loop.run()
    assert rep.refine_events == []                # 同条件 enable_refine=True 时每日触发(对照上方测试)
    assert loop._refiner_llm.calls == []          # refiner LLM 从未被调
    assert rep.n_edits == 0                       # 无结构编辑(EditLog 为空)
    st = mgr.harness.skills.get("longtou").stats
    assert st.n == 2 and st.wins == 2             # 战绩回注照常:2 个已打分决策都归因 longtou


def test_enable_refine_false_breaker_freezes_without_rollback(tmp_path):
    # enable_refine=False → 无 checkpoint(checkpoint 在 refine 块内)→ 熔断走
    # last_ckpt=None 分支:只冻结不回滚,路径不崩(C4 revision 注意事项)
    n = 6
    src = _bad_pick_src(n)
    agent_scripts = [_decision(f"C{i}") for i in range(n)]
    cfg = LoopConfig(floor_abs=-0.5, evidence_min=1, enable_refine=False)
    loop, mgr = _loop(tmp_path, src, agent_scripts, ['{"ops": []}'], config=cfg)
    rep = loop.run()
    assert len(rep.breaker_events) == 1
    assert rep.breaker_events[0].rolled_back_to is None     # 无 checkpoint → 只冻结
    assert rep.frozen_from == rep.breaker_events[0].date
    assert rep.refine_events == []                          # 冻结前后均无 refine


def test_refine_skips_zero_evidence_no_trade_days(tmp_path):
    # 冰点:zt 池空、agent 空仓 → 所有已评分步 outcomes={} → 不应触发 refine(省 LLM/磁盘)
    days = [date(2024, 6, 26), date(2024, 6, 27), date(2024, 6, 28)]
    frames = {("zt", d): pd.DataFrame() for d in days}
    src = FakeSource(frames, days)
    no_trade = '{"candidates": [], "no_trade_reason": "冰点空仓"}'
    # A3:evidence_min=1 使测试非空泛——专测"零候选不算证据"路径而非 evidence_min 门本身
    loop, mgr = _loop(tmp_path, src, [no_trade], ['{"ops": []}'],
                      config=LoopConfig(breaker_min_days=10_000, evidence_min=1))
    rep = loop.run()
    assert rep.trajectory.n_no_trade() == 3
    assert rep.refine_events == []                # 零证据 → 不 refine
    assert loop._refiner_llm.calls == []          # refiner LLM 从未被调
