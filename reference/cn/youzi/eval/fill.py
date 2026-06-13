# youzi/eval/fill.py
"""入场成交可行性 + 交易成本(C3 可成交收益尺的入场半边)。

qfq 复权价不可绝对取整,涨停/一字板一律用**比值**判定;成本走可配 CostModel。
纯函数 + frozen 值对象,无副作用、不取数。
"""
from __future__ import annotations

from dataclasses import dataclass

# 一字板"open≈high≈low"判定:全天价差 ≤ prev_close 的 0.1%(qfq 下用比值容差)
_FLAT_EPS = 1e-3
# 开盘视作"封在涨停板上":开盘涨幅 ≥ 阈值 − 50bp(qfq 复权价模糊,比值容差)
_AT_LIMIT_TOL = 0.005


@dataclass(frozen=True)
class CostModel:
    """A 股往返交易成本(可配,C3 revision 2)。

    commission_bp=佣金(买卖**双边各**收,默认 3bp);stamp_tax_bp=印花税
    (**卖侧单**收,2023-08-28 起 5bp);slippage_bp=滑点(往返合计,默认 30bp)。
    """
    commission_bp: float = 3.0
    stamp_tax_bp: float = 5.0
    slippage_bp: float = 30.0

    def round_trip_cost(self) -> float:
        """一买一卖总成本率(从前向收益里扣)。"""
        return (2 * self.commission_bp + self.stamp_tax_bp + self.slippage_bp) / 10000.0


@dataclass(frozen=True)
class FillResult:
    """入场成交判定结果。

    fillable=能否买到;fill_price=成交价(买不到=None);reason∈
    {one_word_board, opened_board, normal};threshold=所用涨停阈值;
    name_missing=名称缺失回退(revision 6,按非 ST 处理并标记)。
    """
    fillable: bool
    fill_price: float | None
    reason: str
    threshold: float
    name_missing: bool = False


def limit_threshold(code: str, name: str = "") -> float:
    """按板块定涨停幅,**先板块后 ST**(C3 revision 1)。

    北交所(4/8/92 段)30%;创业板/科创板(30/68)20%;主板(60/00)10%;
    仅当**主板**且名称含 ST/*ST 才降为 5%——创业板/科创板/北交所 ST 不降
    (游资域 300xxx ST 连板常见,错杀会系统性低估)。
    """
    if code.startswith(("4", "8", "92")):
        return 0.30
    if code.startswith(("30", "68")):
        return 0.20
    # 主板 60/00(及未知前缀兜底按主板处理)
    if "ST" in name.upper():
        return 0.05
    return 0.10


def _get(row, key: str) -> float:
    """row-agnostic 取值:支持 dict 与 pandas Series。"""
    return float(row[key])


def fill_check(entry_row, prev_close: float, code: str, name: str = "") -> FillResult:
    """入场日能否买到 + 成交价(C3 proposal 2 + revision 1/6)。

    entry_row=入场日 OHLCV 行(含 open/high/low,dict 或 pd.Series);
    prev_close=决策日(t)收盘,作涨停基准。一律比值判定:
      · 一字板(开盘 ≥ 阈值−50bp 且 open≈high≈low)→ 买不进(fillable=False);
      · 开盘顶板盘中开板(开盘 ≥ 阈值−50bp 但非一字)→ 以涨停价成交(诚实"买在打开的板上");
      · 否则正常 → 开盘价成交。
    """
    name_missing = not name
    thr = limit_threshold(code, name)
    open_ = _get(entry_row, "open")
    high = _get(entry_row, "high")
    low = _get(entry_row, "low")

    open_ratio = open_ / prev_close - 1.0
    at_limit_open = open_ratio >= thr - _AT_LIMIT_TOL
    flat = (high - low) <= prev_close * _FLAT_EPS

    if at_limit_open and flat:
        return FillResult(fillable=False, fill_price=None, reason="one_word_board",
                          threshold=thr, name_missing=name_missing)
    if at_limit_open:
        return FillResult(fillable=True, fill_price=prev_close * (1.0 + thr),
                          reason="opened_board", threshold=thr, name_missing=name_missing)
    return FillResult(fillable=True, fill_price=open_, reason="normal",
                      threshold=thr, name_missing=name_missing)
