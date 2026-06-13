# tests/test_fill.py
import pandas as pd
import pytest

from youzi.eval.fill import CostModel, FillResult, fill_check, limit_threshold


# ── limit_threshold: 先板块后 ST(C3 revision 1)──────────────────────────────

def test_threshold_main_board():
    assert limit_threshold("600000") == 0.10
    assert limit_threshold("000001") == 0.10


def test_threshold_chinext_and_star():
    assert limit_threshold("300750") == 0.20   # 创业板
    assert limit_threshold("688981") == 0.20   # 科创板


def test_threshold_bse():
    assert limit_threshold("830799") == 0.30   # 北交所 8 段
    assert limit_threshold("430047") == 0.30   # 北交所 4 段
    assert limit_threshold("920099") == 0.30   # 北交所 92 段(新)


def test_threshold_st_only_lowers_main_board():
    assert limit_threshold("600000", "ST康美") == 0.05    # 主板 ST → 5%
    assert limit_threshold("000001", "*ST某某") == 0.05   # *ST 同样命中


def test_threshold_st_does_not_lower_chinext_or_star():
    # 创业板/科创板/北交所 ST 仍是各自板块阈值——游资域 300xxx ST 连板常见,不可错杀
    assert limit_threshold("300750", "ST某") == 0.20
    assert limit_threshold("688981", "*ST某") == 0.20
    assert limit_threshold("830799", "ST某") == 0.30


# ── fill_check: 一字板/开盘顶板/正常(C3 proposal 2 + revision 6)─────────────

def _row(open_, high, low, close=None):
    return {"open": open_, "high": high, "low": low, "close": close if close is not None else open_}


def test_one_word_board_not_fillable():
    # 主板 +10% 一字板:open=high=low=涨停价 → 买不进
    r = _row(11.0, 11.0, 11.0)
    res = fill_check(r, prev_close=10.0, code="600000", name="某股份")
    assert res.fillable is False
    assert res.fill_price is None
    assert res.reason == "one_word_board"


def test_opened_board_fills_at_limit_price():
    # 开盘顶板(+10%)盘中开板(low 回到 +3%)→ 以涨停价诚实成交
    r = _row(11.0, 11.0, 10.3)
    res = fill_check(r, prev_close=10.0, code="600000", name="某股份")
    assert res.fillable is True
    assert res.reason == "opened_board"
    assert res.fill_price == pytest.approx(11.0)   # prev_close*(1+0.10)


def test_normal_day_fills_at_open():
    r = _row(10.3, 10.5, 10.1)
    res = fill_check(r, prev_close=10.0, code="600000", name="某股份")
    assert res.fillable is True
    assert res.reason == "normal"
    assert res.fill_price == 10.3          # 开盘价成交


def test_st_main_board_one_word_at_5pct():
    # 主板 ST 阈值 5%:+5% 一字板买不进
    r = _row(10.5, 10.5, 10.5)
    res = fill_check(r, prev_close=10.0, code="600519", name="ST某")
    assert res.fillable is False
    assert res.reason == "one_word_board"


def test_chinext_st_5pct_is_normal_not_limit():
    # 创业板 ST 阈值仍 20%:+5% 只是普通上涨,正常按开盘价成交(证 ST 不降创业板)
    r = _row(10.5, 10.6, 10.4)
    res = fill_check(r, prev_close=10.0, code="300888", name="ST某")
    assert res.fillable is True
    assert res.reason == "normal"
    assert res.fill_price == 10.5


def test_name_missing_flagged_and_treated_non_st():
    # 名称缺失(revision 6):标 name_missing,按非 ST 处理(主板 10% 而非 5%)
    r = _row(10.5, 10.6, 10.4)
    res = fill_check(r, prev_close=10.0, code="600000", name="")
    assert res.name_missing is True
    assert res.threshold == 0.10
    assert res.fillable is True and res.reason == "normal"


def test_fill_check_accepts_pandas_row():
    # scorer 会传 OHLCV df 的一行(pd.Series),fill_check 须 row-agnostic
    df = pd.DataFrame([_row(11.0, 11.0, 11.0)])
    res = fill_check(df.iloc[0], prev_close=10.0, code="600000", name="某")
    assert res.fillable is False and res.reason == "one_word_board"


# ── CostModel(C3 revision 2:可配,默认现行口径)─────────────────────────────

def test_cost_model_default_round_trip():
    # 佣金 3bp×2(双边)+ 印花税 5bp(卖侧,2023-08 现行)+ 滑点 30bp(往返)= 41bp
    assert CostModel().round_trip_cost() == (2 * 3.0 + 5.0 + 30.0) / 10000


def test_cost_model_configurable():
    cm = CostModel(commission_bp=2.5, stamp_tax_bp=10.0, slippage_bp=0.0)
    assert cm.round_trip_cost() == (2 * 2.5 + 10.0 + 0.0) / 10000


def test_fill_result_is_frozen():
    res = FillResult(fillable=True, fill_price=10.0, reason="normal", threshold=0.10)
    try:
        res.fillable = False  # type: ignore[misc]
        raised = False
    except Exception:
        raised = True
    assert raised, "FillResult 应为不可变(frozen)"
