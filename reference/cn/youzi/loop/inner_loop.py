# youzi/loop/inner_loop.py
from __future__ import annotations

import math
import statistics
from datetime import date as Date
from typing import Callable, Literal

from pydantic import BaseModel, ConfigDict, Field

from youzi.agent.agent import LLMAgentPolicy
from youzi.eval.decision import DecisionPolicy
from youzi.eval.oracle import PoolRecord
from youzi.eval.scorer import PoolScorer
from youzi.eval.trajectory import EntrySnap, Trajectory, TrajectoryStep
from youzi.harness.harness import HarnessState
from youzi.harness.manager import HarnessManager
from youzi.llm.client import LLMClient
from youzi.refine.credit import apply_credit, merge_credit_reports
from youzi.refine.refiner import RefineReport, Refiner, RefinerConfig
from youzi.refine.signatures import extract_signatures
from youzi.replay.engine import ReplayEngine
from youzi.universe.universe import build_universe

# ── B2 熔断常量 ──
_MAD_EPS = 1e-9     # MAD≈0(退化分布)判定阈
_ZERO_EPS = 1e-12   # 影子序列"非零项"判定阈


class LoopConfig(BaseModel):
    """内环配置。

    B2 熔断重设计:武装单位=**已评分决策日**(非候选数;旧 40 候选门=熔断从未上膛
    的算术必然,findings §2),判定走日级 advantage 序列(每个已评分决策日一个值,
    空仓日记 0.0;advantage=score−同日池基线,自带零点 → 天然 scorer 无关,
    "熔断 scorer-aware 重标定"债务作废):
      · 有影子(InnerLoop shadow_daily)→ 配对差双门 + 方向一致性副门(主判定);
      · 无影子 → 全历史 median−c·MAD 自标定地板(MAD≈0 退化分布时 floor_abs 兜底)。
    触发后整段回滚(退化窗起点前最近 checkpoint)+ 可再武装,第二次触发才永久
    frozen,见 InnerLoop.run。
    """
    # 整数窗口/节奏一律 >=1(防退化配置:除零/空窗口;仿 WalkForwardEval horizon>=1 先例)
    horizon: int = Field(default=1, ge=1)            # 延迟打分窗口(同 WalkForwardEval)
    refine_every: int = Field(default=1, ge=1)       # refine 节奏上限门(与 evidence_min 取与;A3 起非唯一触发条件)
    # 【A3:已被水位线取代,仅保留兼容】旧语义=滑动证据窗(最近 N 已评分步),会重叠重现同一签名;
    # A3 起 refine 证据 = scored_steps[水位线:](非重叠),本字段在代码中已无消费点,
    # 保留仅为旧 LoopConfig JSON 反序列化不破。
    credit_window: int = Field(default=10, ge=1)
    evidence_min: int = Field(default=6, ge=1)       # 水位线后新增**已打分候选**数(按候选计,非按步)≥ 此值才 refine
    # ── B2 熔断:日级武装 ──
    breaker_min_days: int = Field(default=3, ge=1)   # 已评分决策日数 ≥ 此值才评估熔断(武装门;真实窗每窗 3~20 候选也能上膛)
    breaker_k_max: int = Field(default=5, ge=1)      # 退化窗长 k = min(已评分日数, k_max);akshare 30 日限制下每窗 ~5 交易日,
                                                     # 小 k 脆弱性由 ε_abs + 方向门 + 可再武装三重对冲(spec B2 revision (c))
    # ── B2 ③ fallback 自标定地板(无影子时的主判定)──
    breaker_mad_c: float = Field(default=2.0, ge=0.0)    # 触发:最近 k 日 rolling < 全历史 median − c·MAD
    # floor_abs 语义变更(B2):不再是主地板,仅 fallback 路 MAD≈0(退化分布,如日级序列恒常数)
    # 时的绝对兜底(池 SCORE 量纲;与日级 advantage 均值比较)。
    floor_abs: float = Field(default=-0.2, ge=-1.0, le=1.0)
    # ── B2 ② 影子配对地板(InnerLoop 注入 shadow_daily 时的主判定)──
    breaker_shadow_lambda: float = Field(default=1.0, ge=0.0)      # 主门:mean(配对差) < −max(λ·std(配对差), ε_abs) 的 λ
    breaker_shadow_eps_c: float = Field(default=0.25, ge=0.0)      # ε_abs = c·MAD(影子日序列非零项)——堵 std≈0 微小负差误触发(findings §9)
    breaker_shadow_eps_floor: float = Field(default=0.05, ge=0.0)  # 影子序列全零/近零 → ε_abs 退此绝对兜底(池 SCORE 量纲)
    # ── 【B2 deprecated:以下四项已不再被消费,仅保留旧 LoopConfig JSON 反序列化不破】──
    breaker_window: int = Field(default=20, ge=1)         # deprecated:候选计数滚动窗 → 改日级 k 窗(breaker_k_max)
    baseline_window: int = Field(default=20, ge=1)        # deprecated:前 N 候选均值基线 → 改全历史 median/MAD 自标定
    floor_rel_margin: float = Field(default=0.15, ge=0.0)  # deprecated:自相对地板结构上抓不到"比 frozen 差"(findings §4)
    breaker_min_samples: int = Field(default=40, ge=1)    # deprecated:40 候选武装门 → 改已评分决策日门(breaker_min_days)
    # C4 消融开关:False = Hcredit 臂("只有战绩回注、无结构编辑")。只挡 refine 块
    # (含其中的 checkpoint);apply_credit 在线信用与熔断照常。注意:无 refine →
    # 无 checkpoint → 熔断无回滚目标 → 首次触发即走"直接 frozen"分支(run() 已有该路径)。
    enable_refine: bool = True


class RefineEvent(BaseModel):
    model_config = ConfigDict(frozen=True)
    date: Date
    checkpoint_version: int | None
    report: RefineReport


class BreakerEvent(BaseModel):
    model_config = ConfigDict(frozen=True)
    date: Date
    rolling: float                # 最近 k 日均值(fallback 路=日级 advantage;影子路=配对差 本臂−影子)
    baseline: float | None        # 触发阈值(fallback: median−c·MAD;MAD≈0 兜底: floor_abs;影子: −max(λ·std, ε_abs))
    reason: str
    rolled_back_to: int | None
    # B2 ⑤ 可再武装:首次触发且有"退化窗起点前 checkpoint"= rollback(整段回滚+清证据继续跑);
    # 第二次触发或无 ckpt 可回滚 = frozen(永久冻结)。旧 JSON 缺省 → frozen(旧语义=一次性冻结)。
    mode: Literal["rollback", "frozen"] = "frozen"


class LoopReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    trajectory: Trajectory
    refine_events: list[RefineEvent] = Field(default_factory=list)
    breaker_events: list[BreakerEvent] = Field(default_factory=list)
    frozen_from: Date | None = None
    n_edits: int = 0

    def __bool__(self) -> bool:
        return True


# ── B2 熔断判定纯函数(模块级,离线可手算可测)──────────────────────────────

def _mad(xs: list[float]) -> float:
    """中位数绝对偏差 MAD = median(|x − median(x)|)。鲁棒尺度,重尾/离群免疫。"""
    m = statistics.median(xs)
    return statistics.median([abs(x - m) for x in xs])


def _fallback_trip(history: list[float], k: int, c: float,
                   floor_abs: float) -> tuple[bool, float, float, str]:
    """B2 ③ fallback 自标定地板(无影子时的主判定)。

    history=日级 advantage 全历史(到当前为止,按日升序);触发条件:
        rolling(最近 k 日均值) < median(全历史) − c·MAD(全历史)
    MAD < 1e-9(退化分布:序列恒常数等)时自标定失效 → 退回绝对地板 floor_abs。
    返回 (是否触发, rolling, 触发阈值, reason)。调用方保证 1 ≤ k ≤ len(history)。
    """
    window = history[-k:]
    rolling = sum(window) / len(window)
    mad = _mad(history)
    if mad < _MAD_EPS:
        return rolling < floor_abs, rolling, floor_abs, "rolling<floor_abs(MAD~0兜底)"
    thr = statistics.median(history) - c * mad
    return rolling < thr, rolling, thr, "rolling<median-c*MAD"


def _shadow_eps_abs(shadow_vals: list[float], c: float, floor: float) -> float:
    """B2 ② 影子双门的 ε_abs 标定:ε_abs = c·MAD(影子日序列非零项)。

    影子序列全零(空仓影子)或非零项 MAD≈0(常数影子)时自标定同样失效 →
    退回 floor(池 SCORE 量纲绝对兜底,默认 0.05)。
    """
    nz = [v for v in shadow_vals if abs(v) > _ZERO_EPS]
    if not nz:
        return floor
    m = _mad(nz)
    if m < _MAD_EPS:
        return floor
    return c * m


def _shadow_trip(diffs: list[float], k: int, lam: float,
                 eps_abs: float) -> tuple[bool, float, float, str]:
    """B2 ② 影子配对地板:双门 + 方向一致性副门(spec B2 revision (a)(b))。

    diffs=按日升序的配对差(本臂−影子)全历史;取最近 k 日:
      主门:mean(最近 k 日) < −max(λ·std(最近 k 日), ε_abs)
            (std 用样本标准差;ε_abs 堵 std≈0 时微小负差误触发——temp=0 实证
             HCH≡Hexpert 配对差恒 0 是常态,findings §9);
      方向副门:最近 k 日中**严格为负**的天数 ≥ ⌈k/2⌉+1(防"单日大负+余日为零"单点触发)。
    返回 (是否触发, mean, 触发阈值(−max(λσ,ε)), reason)。调用方保证 1 ≤ k ≤ len(diffs)。
    """
    win = diffs[-k:]
    mean_d = sum(win) / len(win)
    sd = statistics.stdev(win) if len(win) >= 2 else 0.0
    thr = max(lam * sd, eps_abs)
    n_neg = sum(1 for d in win if d < 0.0)
    need = math.ceil(k / 2) + 1
    trip = (mean_d < -thr) and (n_neg >= need)
    return trip, mean_d, -thr, "shadow:mean(diff)<-max(λσ,ε)&方向门"


class InnerLoop:
    """内环编排:交错 act→延迟打分→在线信用→(每日)refine,reset-free + 能力地板熔断。

    持有 HarnessManager(live H + EditLog + MetaTools + SnapshotStore);
    agent/refiner 由 manager.harness/manager.tools 构造,rollback 后 _rebind 重建。

    B2 熔断:日级武装(breaker_min_days 个已评分决策日)→ 有 shadow_daily 走影子
    配对双门、无则走 median−c·MAD 自标定地板;触发后回滚到"退化窗起点前最近
    checkpoint"并再武装(清证据继续跑),第二次触发(或无 ckpt 可回滚)才永久 frozen;
    frozen 后 apply_credit 停写(真冻结),打分/轨迹照常记录。
    """

    def __init__(self, manager: HarnessManager, source, start: Date, end: Date,
                 agent_llm: LLMClient, refiner_llm: LLMClient,
                 config: LoopConfig | None = None,
                 refiner_config: RefinerConfig | None = None,
                 scorer=None,
                 agent_factory: Callable[[HarnessState], DecisionPolicy] | None = None,
                 shadow_daily: dict[Date, float] | None = None) -> None:
        self._mgr = manager
        self._source = source
        self._start = start
        self._end = end
        self._agent_llm = agent_llm
        self._refiner_llm = refiner_llm
        self._cfg = config or LoopConfig()
        self._refiner_cfg = refiner_config or RefinerConfig()
        self._scorer = scorer or PoolScorer()
        # E2 决策层注入:None=现行 LLMAgentPolicy;给 factory(如 HarnessRulePolicy)
        # 则零 LLM 规则决策。必须是 factory 而非实例:rollback_to 替换 harness 对象,
        # 固定实例会静默读废弃 H(manager.rollback_to docstring 明确警告)→ _rebind 重建。
        self._agent_factory = agent_factory
        # B2 ② 影子日级序列(影子臂[如 Hexpert]每日 advantage 均值;None=走 fallback ③)。
        # 调用方约定只含 ≤ 当前已评分日的条目;InnerLoop 消费时仍严格按"≤ 当前已评分
        # 决策日"过滤(防前视,run() 内有防御断言)——故整窗序列(如 compare 先跑完
        # Hexpert)也可安全注入。
        self._shadow_daily = dict(shadow_daily) if shadow_daily is not None else None
        # A3 水位线:scored_steps 的索引,refine 证据 = scored_steps[水位线:](非重叠窗);
        # refine 成功后推进到 len(scored_steps)。B2 起熔断回滚后可再武装继续 refine,
        # 但水位线指向 run 局部、单调追加的 scored_steps 索引,与 H 版本无关 → 无需重置
        # (回滚后下窗证据=回滚后新增已评分步,非重叠性质保持)。
        self._last_refined_idx = 0
        self._rebind()

    def _rebind(self) -> None:
        """(重)绑定 agent/refiner 到 manager 当前的 harness/tools——启动与 rollback 后调用。

        注意(A3):重建 Refiner 会清空其近期编辑史(_recent_reports)——可接受:
        rollback 已把 H 还原,旧编辑史描述的编辑均已撤销,作废是正确语义。
        E2:agent 经 factory 重建(传 manager **当前** harness),保证 rollback 后
        决策层读的是还原态 H 而非废弃对象;默认 None 走现行 LLMAgentPolicy。
        """
        if self._agent_factory is not None:
            self._agent = self._agent_factory(self._mgr.harness)
        else:
            self._agent = LLMAgentPolicy(self._mgr.harness, self._agent_llm)
        self._refiner = Refiner(self._mgr.harness, self._refiner_llm,
                                self._mgr.tools, self._refiner_cfg)

    def run(self) -> LoopReport:
        cfg = self._cfg
        self._last_refined_idx = 0          # 防御:run() 重入时水位线归零(scored_steps 是 run 局部状态)
        engine = ReplayEngine(self._source, self._start, self._end)
        record = PoolRecord()
        days_seen: list[Date] = []
        drafts: list[dict] = []
        pending: list[int] = []
        scored_steps: list[TrajectoryStep] = []
        per_step_credits: list = []
        refine_events: list[RefineEvent] = []
        breaker_events: list[BreakerEvent] = []
        # ── B2 熔断状态 ──
        breaker_days: list[tuple[Date, float]] = []  # 证据:已评分决策日→日级 advantage 均值(空仓日 0.0);再武装时清空
        ckpts: list[tuple[int, Date]] = []           # checkpoint(版本, 创建日):⑤ 回滚找"退化窗起点前最近 ckpt"用
        breaker_trips = 0                            # ⑤ 再武装计数:第 2 次触发(或首发即无 ckpt)→ 永久 frozen
        frozen = False
        frozen_from: Date | None = None
        idx = 0
        while True:
            cursor = engine.cursor
            days_seen.append(cursor)
            state = engine.observe()
            universe = build_universe(engine.guarded_source, cursor)
            record.record(cursor, universe)
            decision = self._agent.decide(state, universe)
            entries: dict[str, EntrySnap] = {}
            for c in decision.candidates:
                if c.code in entries:
                    continue
                snap = universe.get(c.code)
                if snap is not None:
                    entries[c.code] = EntrySnap(code=c.code, status=snap.status, boards=snap.boards)
            drafts.append({"date": cursor, "market": state, "decision": decision,
                           "entries": entries, "scored": False, "outcomes": {}})
            pending.append(idx)
            newly: list[TrajectoryStep] = []
            remaining: list[int] = []
            for j in pending:
                if idx >= j + cfg.horizon:
                    # 持有路径 entry..exit 逐日成员(days_seen[j+1 .. j+horizon];均已录制)
                    mems = [record.get(days_seen[j + h]) for h in range(1, cfg.horizon + 1)]
                    assert all(m is not None for m in mems), \
                        f"BUG: {cursor} 持有路径有交易日未录成员"
                    outcomes = self._scorer.score_step(
                        drafts[j]["decision"], mems,
                        days_seen[j + 1], days_seen[j + cfg.horizon], engine.guarded_source,
                        decision_mem=record.get(days_seen[j]))   # 决策日(≤t)池成员 → day_baseline
                    drafts[j]["outcomes"] = outcomes
                    drafts[j]["scored"] = True
                    step_j = TrajectoryStep(**drafts[j])
                    scored_steps.append(step_j)
                    newly.append(step_j)
                else:
                    remaining.append(j)
            pending = remaining
            for step in newly:
                if not frozen:
                    # B2 ④ frozen 真冻结:冻结后停 apply_credit(H 的 skill.stats 不再漂移,
                    # 与"冻结基线"语义一致);trajectory/打分照常记录,只是不回注 H。
                    # frozen 是终态且门死 refine → per_step_credits 与 scored_steps 长度
                    # 分叉后无消费者,对齐不变量只需在未冻结期间成立。
                    cr = apply_credit(Trajectory(steps=[step], horizon=cfg.horizon), self._mgr.harness)
                    per_step_credits.append(cr)
                    # B2 ① 日级武装证据:每个已评分决策日一个值=当日已评分候选 advantage
                    # 均值(空仓日 0.0;与 eval.stats.daily_series 同口径)。advantage=
                    # score−同日池基线,自带零点 → 两路判定天然 scorer 无关。
                    cands = list(step.outcomes.values())
                    v = sum(c.advantage for c in cands) / len(cands) if cands else 0.0
                    breaker_days.append((step.date, v))
            # ── B2 能力地板熔断(日级武装:已评分决策日数达 breaker_min_days 才评估)──
            if not frozen and len(breaker_days) >= cfg.breaker_min_days:
                trip = False
                rolling = 0.0
                thr = 0.0
                reason = ""
                window_start: Date | None = None
                if self._shadow_daily is not None:
                    # ② 影子配对地板(主判定)。防前视:严格只消费 ≤ 当前已评分决策日的
                    # 影子条目(整窗注入安全);ε_abs 也只用过滤后的影子序列标定。
                    cur_max = breaker_days[-1][0]
                    shadow = {d: s for d, s in self._shadow_daily.items() if d <= cur_max}
                    own = dict(breaker_days)
                    common = sorted(set(own) & set(shadow))
                    assert all(d <= cur_max for d in common), \
                        "防前视违例:影子配对消费了 > 当前已评分日的条目"
                    if len(common) >= cfg.breaker_min_days:
                        k = min(len(common), cfg.breaker_k_max)
                        diffs = [own[d] - shadow[d] for d in common]
                        eps = _shadow_eps_abs(list(shadow.values()),
                                              cfg.breaker_shadow_eps_c,
                                              cfg.breaker_shadow_eps_floor)
                        trip, rolling, thr, reason = _shadow_trip(
                            diffs, k, cfg.breaker_shadow_lambda, eps)
                        window_start = common[-k]
                else:
                    # ③ fallback 自标定地板(无影子):最近 k 日 rolling vs 全历史 median−c·MAD
                    k = min(len(breaker_days), cfg.breaker_k_max)
                    trip, rolling, thr, reason = _fallback_trip(
                        [v for _, v in breaker_days], k, cfg.breaker_mad_c, cfg.floor_abs)
                    window_start = breaker_days[-k][0]
                if trip:
                    assert window_start is not None
                    breaker_trips += 1
                    # ⑤ 回滚目标=退化窗(最近 k 日)起点**之前**的最近 checkpoint:撤销整段
                    # 退化期编辑而非只撤最后一刀(manager.rollback_to 支持任意版本)。
                    target = max((v for v, d in ckpts if d < window_start), default=None)
                    if breaker_trips == 1 and target is not None:
                        # 首次触发:整段回滚 + 再武装(清空退化窗证据继续跑;
                        # 同一窗口第二次触发才永久 frozen)。
                        self._mgr.rollback_to(target)
                        self._rebind()
                        # 弃时间线(> target 版本)的 ckpt 含退化期编辑,不再作未来回滚目标
                        ckpts = [(v, d) for v, d in ckpts if v <= target]
                        breaker_days.clear()   # 再武装:需再积 breaker_min_days 个新已评分日才评估
                        breaker_events.append(BreakerEvent(
                            date=cursor, rolling=rolling, baseline=thr, reason=reason,
                            rolled_back_to=target, mode="rollback"))
                    else:
                        # 第二次触发 / 无 ckpt 可回滚 → 永久 frozen;有目标 ckpt 时仍先回滚
                        # 撤销本段退化(保留旧"回滚+冻结"的保护语义)。
                        rolled: int | None = None
                        if target is not None:
                            self._mgr.rollback_to(target)
                            self._rebind()
                            rolled = target
                        frozen = True
                        frozen_from = cursor
                        breaker_events.append(BreakerEvent(
                            date=cursor, rolling=rolling, baseline=thr, reason=reason,
                            rolled_back_to=rolled, mode="frozen"))
            # refine 触发(A3 水位线非重叠窗):enable_refine(C4 消融门,False=Hcredit 臂)
            # AND 未冻结 AND 水位线后新增已打分候选数 ≥ evidence_min
            # AND 到节奏(refine_every 保留作节奏上限门)。候选按 outcomes 计(非按步):
            # 空仓步 outcomes={} 不算证据 → 零证据日天然跳过,省 LLM/磁盘(旧行为保留)。
            fresh = scored_steps[self._last_refined_idx:]
            n_fresh = sum(len(s.outcomes) for s in fresh)
            if cfg.enable_refine and not frozen and n_fresh >= cfg.evidence_min and (idx % cfg.refine_every == 0):
                ver = self._mgr.checkpoint(label=f"pre-refine {cursor}")
                ckpts.append((ver, cursor))   # B2 ⑤:记(版本, 日期)供"退化窗起点前最近 ckpt"检索
                # 证据 = 水位线后全部新增(非重叠,同一签名不跨 refine 重现);
                # scored_steps 与 per_step_credits 同步追加,同切片天然对齐。
                win_traj = Trajectory(steps=fresh, horizon=cfg.horizon)
                credit = merge_credit_reports(per_step_credits[self._last_refined_idx:])
                sigs = extract_signatures(win_traj, self._mgr.harness)
                report = self._refiner.refine(win_traj, credit, sigs)
                refine_events.append(RefineEvent(date=cursor, checkpoint_version=ver, report=report))
                self._last_refined_idx = len(scored_steps)   # refine 成功 → 推进水位线,下窗不重叠
            idx += 1
            if not engine.step():
                break
        traj = Trajectory(steps=[TrajectoryStep(**d) for d in drafts], horizon=cfg.horizon)
        return LoopReport(trajectory=traj, refine_events=refine_events,
                          breaker_events=breaker_events, frozen_from=frozen_from,
                          n_edits=len(self._mgr.log))
