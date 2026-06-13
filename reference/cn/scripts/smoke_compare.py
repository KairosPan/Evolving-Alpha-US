# scripts/smoke_compare.py
"""手动冒烟:真实数据三方度量对比 HCH(自精炼内环) vs Hexpert(冻结种子 H) vs Hmin(裸基线)。

Run: DEEPSEEK_API_KEY=... python scripts/smoke_compare.py 20240601 20240607 [horizon] [--ablate]

--ablate(C4):多跑第五臂 Hcredit(enable_refine=False:只回注战绩、无结构编辑),
把 HCH−Hexpert 合效应拆成编辑通道(HCH−Hcredit)+ stats 通道(Hcredit−Hexpert)。
成本 +N 次 agent 调用("LLM 缓存免费重放"依赖未建缓存,youzi/llm 现无,见 C4 spec)。

需要:openai 已装、网络、akshare 可拉数、seeds/ 在位、DEEPSEEK_API_KEY。
先跑 scripts/smoke_akshare.py 核真实列名、scripts/smoke_deepseek_agent.py 验单日 agent,再跑本脚本。

成本提示:小窗口(3–5 交易日)起步。DeepSeek 调用 ≈ HCH(N 次 agent + 每 refine 3 次 p/K/M)+ Hexpert(N 次 agent);
akshare ≈ 3×N(已 memoize:四路共享同一真实数据,公平性硬保证 + 砍重复取数)。

⚠ 这是真实"自进化是否胜 frozen"的见真章脚本:读 hch_beats_hexpert + HCH−Hexpert delta。
单窗口、单次 LLM 采样,结论是信号不是定论;多窗口/多 episode 聚合见 1b-3b 债务。
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import date as Date, datetime
from pathlib import Path

import pandas as pd

from youzi.data.source import AkshareSource
from youzi.harness.loader import load_seeds
from youzi.harness.snapshot import SnapshotStore
from youzi.llm.client import DeepSeekClient
from youzi.loop.compare import compare_harnesses
from youzi.loop.inner_loop import LoopConfig


class _MemoizedSource:
    """包装 MarketDataSource,记忆 trading_calendar 与每个 (池, 日) 取数。

    四路(HCH/Hexpert/Hmin_hb/Hmin_nt)各自重建引擎会重复拉同一天——memoize 让它们共享
    完全相同的真实数据(公平对比的硬保证)并把 akshare 调用砍 ~4×。
    防火墙不受影响:ReplayEngine 在本对象外层套 GuardedSource,guard.check(day) 仍先于取数。
    """

    def __init__(self, inner) -> None:
        self._inner = inner
        self._cal: list[Date] | None = None
        self._pools: dict[tuple[str, Date], pd.DataFrame] = {}
        self._ohlcv: dict[tuple[str, Date, Date], pd.DataFrame] = {}

    def trading_calendar(self) -> list[Date]:
        if self._cal is None:
            self._cal = self._inner.trading_calendar()
        return self._cal

    def _pool(self, kind: str, fn, day: Date) -> pd.DataFrame:
        key = (kind, day)
        if key not in self._pools:
            self._pools[key] = fn(day)
        return self._pools[key]

    def zt_pool(self, day: Date) -> pd.DataFrame:
        return self._pool("zt", self._inner.zt_pool, day)

    def zt_pool_previous(self, day: Date) -> pd.DataFrame:
        return self._pool("prev", self._inner.zt_pool_previous, day)

    def zt_pool_blowup(self, day: Date) -> pd.DataFrame:
        return self._pool("blowup", self._inner.zt_pool_blowup, day)

    def dt_pool(self, day: Date) -> pd.DataFrame:
        return self._pool("dt", self._inner.dt_pool, day)

    def daily_ohlcv(self, code: str, start: Date, end: Date) -> pd.DataFrame:
        key = (code, start, end)                  # ReturnScorer 收益打分用;memoize 砍四路重复取数
        if key not in self._ohlcv:
            self._ohlcv[key] = self._inner.daily_ohlcv(code, start, end)
        return self._ohlcv[key]


def _fmt_arm(name: str, arm) -> str:
    r = arm.report
    line = (f"  {name:<14} 决策={r.n_decisions:<3} 空仓={r.n_no_trade:<3} 候选={r.n_candidates:<3} "
            f"命中率={r.hit_rate:+.3f} 被砸率={r.nuke_rate:.3f} 期望分={r.mean_score:+.4f} "
            f"超额={r.mean_excess:+.4f}")
    if arm.n_refines is not None:
        line += f"  [refine={arm.n_refines} 熔断={arm.n_breaker_trips} 冻结起={arm.frozen_from or '-'}]"
    return line


def main(start_ymd: str, end_ymd: str, horizon: int = 1, temperature: float = 0.3,
         scorer_kind: str = "pool", ablate: bool = False) -> None:
    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("缺少 DEEPSEEK_API_KEY(export 或 inline 传入)。"); sys.exit(1)
    start = datetime.strptime(start_ymd, "%Y%m%d").date()
    end = datetime.strptime(end_ymd, "%Y%m%d").date()
    seeds = Path(__file__).resolve().parent.parent / "seeds"
    tmp = tempfile.mkdtemp(prefix="youzi_compare_")

    from youzi.eval.scorer import PoolScorer, ReturnScorer
    scorer = ReturnScorer() if scorer_kind == "return" else PoolScorer()

    snap = os.environ.get("YOUZI_SNAPSHOT")
    if snap:
        from youzi.data.cache import PITStore
        from youzi.data.snapshot_source import SnapshotSource
        src = SnapshotSource(PITStore(Path(snap)))
        print(f"[离线] 用 PIT 快照 {snap}(零 akshare)。")
    else:
        src = _MemoizedSource(AkshareSource())
    n_days = sum(1 for d in src.trading_calendar() if start <= d <= end)
    extra = f" + Hcredit({n_days} agent,C4 消融)" if ablate else ""
    print(f"区间 {start}~{end} 内交易日 {n_days} 个,horizon={horizon},temperature={temperature},"
          f"scorer={scorer_kind}(return 模式下期望分读作平均收益),ablate={ablate}。"
          f"\n预计 DeepSeek 调用 ≈ HCH({n_days} agent + ~{max(0, n_days - horizon) * 3} refiner) "
          f"+ Hexpert({n_days} agent){extra}。开始(慢且花钱)…\n")

    rep = compare_harnesses(
        lambda: load_seeds(seeds), src, start, end,
        agent_llm_factory=lambda: DeepSeekClient(temperature=temperature),
        refiner_llm_factory=lambda: DeepSeekClient(temperature=temperature),
        store_factory=lambda: SnapshotStore(Path(tmp)),
        loop_config=LoopConfig(horizon=horizon),
        scorer=scorer,
        ablate=ablate,
    )

    from youzi.loop.run_store import RunStore
    run_id = f"{start_ymd}_{end_ymd}_{scorer_kind}_{datetime.now().strftime('%H%M%S')}"
    RunStore(Path(os.environ.get("YOUZI_RUNS_DIR", "runs"))).save(run_id, rep, {
        "window": f"{start}~{end}", "scorer": scorer_kind, "horizon": horizon,
        "temperature": temperature, "ablate": ablate,
        "created": datetime.now().isoformat(timespec="seconds")})
    print(f"[run-store] 已存 run: {run_id}")

    print("=== 三方度量对比(同窗同 oracle)===")
    for name in ("HCH", "Hcredit", "Hexpert", "Hmin_highest", "Hmin_notrade"):
        if name in rep.arms:                       # Hcredit 仅 --ablate 时存在
            print(_fmt_arm(name, rep.arms[name]))
    print("\n=== HCH − Hexpert ===")
    print(f"  Δ期望分={rep.hch_minus_hexpert_mean_score:+.4f}  "
          f"Δ超额={rep.hch_minus_hexpert_mean_excess:+.4f}  "
          f"Δ命中率={rep.hch_minus_hexpert_hit_rate:+.4f}  "
          f"Δ被砸率={rep.hch_minus_hexpert_nuke_rate:+.4f}")
    verdict = "✅ HCH 胜 frozen" if rep.hch_beats_hexpert else "❌ HCH 未胜 frozen(持平或退化)"
    print(f"  verdict(超额口径 advantage=score−当日池基线): {verdict}")
    sv = rep.stat_verdict
    if sv is not None:   # C1 统计裁决一行摘要(日级配对差;insufficient=样本不足保守不下结论)
        label = {"win": "✅ 显著胜出", "loss": "❌ 显著退化",
                 "flat": "≈ 持平(无法区分)", "insufficient": "⚠ 样本不足"}[sv.verdict]
        ci = (f"CI95=[{sv.ci_low:+.4f},{sv.ci_high:+.4f}]"
              if sv.ci_low is not None else "CI95=—")
        p = f"p={sv.p_value:.4f}" if sv.p_value is not None else "p=—"
        m = f"MDE≈{sv.mde:.4f}" if sv.mde is not None else "MDE=—"
        print(f"  stat_verdict(C1): {label}  配对日={sv.n_days}  "
              f"日均差={sv.mean_diff:+.4f}  {ci}  {p}  {m}  "
              f"(seed={sv.seed} block={sv.block_len} B={sv.n_boot})")

    # C4 消融归因:把 HCH−Hexpert 合效应拆成编辑通道与战绩回注通道(仅 --ablate 时有)
    if rep.hch_minus_hcredit_verdict is not None:
        print("\n=== C4 消融归因(Hcredit=只回注战绩、无结构编辑)===")
        labels = {"win": "✅ 显著为正", "loss": "❌ 显著为负",
                  "flat": "≈ 持平(无法区分)", "insufficient": "⚠ 样本不足"}
        for tag, asv in (("编辑通道   HCH−Hcredit    ", rep.hch_minus_hcredit_verdict),
                         ("战绩通道   Hcredit−Hexpert", rep.hcredit_minus_hexpert_verdict)):
            if asv is None:
                continue
            ci2 = (f"CI95=[{asv.ci_low:+.4f},{asv.ci_high:+.4f}]"
                   if asv.ci_low is not None else "CI95=—")
            print(f"  {tag} {labels[asv.verdict]}  配对日={asv.n_days}  "
                  f"日均差={asv.mean_diff:+.4f}  {ci2}")
        trips_hch = rep.arms["HCH"].n_breaker_trips or 0
        trips_hcr = (rep.arms["Hcredit"].n_breaker_trips or 0) if "Hcredit" in rep.arms else 0
        if trips_hch or trips_hcr:   # 熔断不对称:HCH rollback 连 stats 回滚,Hcredit 不回滚
            print(f"  ⚠ 熔断不对称(HCH={trips_hch}/Hcredit={trips_hcr}):HCH rollback 连战绩回滚"
                  f"而 Hcredit 无 checkpoint 只冻结——编辑通道归因失真,慎读。")

    # HCH 自进化到底改了啥(诊断:看 refine 每次的 applied/rejected 编辑)
    lr = rep.hch_loop_report
    if lr is not None:
        print("\n=== HCH 自进化轨迹(每次 refine 改了什么)===")
        if not lr.refine_events:
            print("  (无 refine)")
        for ev in lr.refine_events:
            r = ev.report
            print(f"  [{ev.date} ckpt={ev.checkpoint_version}] applied={len(r.applied)} rejected={len(r.rejected)}")
            for e in r.applied:
                print(f"      ✓ {e.pass_kind}:{e.tool} → {e.target_id}  «{e.rationale}»")
            for e in r.rejected:
                print(f"      ✗ {e.pass_kind}:{e.tool} → {e.target_id}  拒因:{e.reason}")
            for n in r.notes:
                print(f"      · {n}")
        for be in lr.breaker_events:
            print(f"  [熔断 {be.date}] {be.reason} rolling={be.rolling:+.3f} baseline={be.baseline} "
                  f"→ rollback={be.rolled_back_to}")
    print("\n⚠ 单窗口单次采样=信号非定论;多窗口/多 episode 聚合见 1b-3b 债务。")


if __name__ == "__main__":
    # C4:--ablate 旗标可混在任意位置(续用位置参数约定,最小侵入,不引 argparse)
    args = [a for a in sys.argv[1:] if a != "--ablate"]
    ablate_flag = len(args) != len(sys.argv) - 1
    if len(args) < 2:
        print("用法: DEEPSEEK_API_KEY=... python scripts/smoke_compare.py <start_ymd> <end_ymd> [horizon] [temperature] [scorer:pool|return] [--ablate]")
        print("例:  DEEPSEEK_API_KEY=sk-... python scripts/smoke_compare.py 20240601 20240607 2 0.0 return --ablate")
        sys.exit(1)
    main(args[0], args[1],
         int(args[2]) if len(args) > 2 else 1,
         float(args[3]) if len(args) > 3 else 0.3,
         args[4] if len(args) > 4 else "pool",
         ablate=ablate_flag)
