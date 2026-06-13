# Phase-1b-3e-1:OHLCV 数据 + 前向收益 oracle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给数据源加日线 OHLCV 取数 + 一个前向收益纯计算 oracle(次日开盘买→t+N 收盘卖),为后续把"收益幅度"接进打分/信用/评测(片 2)打底。自包含、离线可测,不碰现有打分链路。

**Architecture:** `youzi/data/source.py` 加 `daily_ohlcv`(协议 + Akshare qfq + Guarded 守 `end≤as_of`)+ `_normalize_ohlcv` 列归一;新增 `youzi/eval/return_oracle.py`(`forward_return` 纯函数 + `ReturnOracle`)。`ReturnOracle` 是打分时刻消费已实现数据的角色,不进 ≤t 决策路径。

**Tech Stack:** Python · pandas · pytest(全离线:`FakeSource` 内存 OHLCV,不触网)。

**分支:** `phase-1b3e1-return-oracle`(执行时建)。**先读** spec:`docs/superpowers/specs/2026-06-08-phase1b3e1-return-oracle-design.md`。

**全量回归基线:** `.venv/bin/python -m pytest -q` 当前 **246 passed**。

**Bundle:** 单 bundle(Task 1-2)。

---

### Task 1: `daily_ohlcv`(source 协议 + Akshare + Guarded + 归一)+ FakeSource

**Files:**
- Modify: `youzi/data/source.py`(协议加方法、`_normalize_ohlcv`、`AkshareSource.daily_ohlcv`、`GuardedSource.daily_ohlcv`)
- Modify: `tests/conftest.py`(`FakeSource` 加 `ohlcv` 入参 + `daily_ohlcv`)
- Test: `tests/test_return_oracle.py`(本任务建,放 normalize + guard 用例)

- [ ] **Step 1: 写失败测试**

```python
# tests/test_return_oracle.py
from datetime import date

import pandas as pd
import pytest

from youzi.data.source import _normalize_ohlcv, GuardedSource
from youzi.replay.firewall import AsOfGuard, LookaheadError
from tests.conftest import FakeSource


def _ohlcv(rows):
    """rows: list[(date, open, high, low, close, volume)]"""
    return pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])


def test_normalize_ohlcv_renames_and_types():
    raw = pd.DataFrame({"日期": ["2026-06-01", "2026-06-02"], "开盘": [10.0, 11.0],
                        "收盘": [11.0, 12.0], "最高": [11.5, 12.5], "最低": [9.5, 10.5],
                        "成交量": [1000, 2000]})
    out = _normalize_ohlcv(raw)
    assert {"date", "open", "high", "low", "close", "volume"}.issubset(out.columns)
    assert out.iloc[0]["date"] == date(2026, 6, 1)
    assert out.iloc[0]["open"] == 10.0 and out.iloc[1]["close"] == 12.0


def test_normalize_ohlcv_empty():
    out = _normalize_ohlcv(pd.DataFrame())
    assert list(out.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert out.empty


def test_fake_source_daily_ohlcv_range_filter():
    df = _ohlcv([(date(2026, 6, 1), 10, 11, 9, 10.5, 100),
                 (date(2026, 6, 2), 10.5, 12, 10, 11.5, 200),
                 (date(2026, 6, 3), 11.5, 13, 11, 12.5, 300)])
    src = FakeSource({}, [], ohlcv={"000001": df})
    got = src.daily_ohlcv("000001", date(2026, 6, 2), date(2026, 6, 3))
    assert list(got["date"]) == [date(2026, 6, 2), date(2026, 6, 3)]
    assert src.daily_ohlcv("999999", date(2026, 6, 2), date(2026, 6, 3)).empty


def test_guarded_daily_ohlcv_blocks_future():
    df = _ohlcv([(date(2026, 6, 2), 10, 11, 9, 10.5, 100)])
    gs = GuardedSource(FakeSource({}, [], ohlcv={"000001": df}), AsOfGuard(date(2026, 6, 2)))
    # end <= as_of:正常
    assert not gs.daily_ohlcv("000001", date(2026, 6, 2), date(2026, 6, 2)).empty
    # end > as_of:拦截
    with pytest.raises(LookaheadError):
        gs.daily_ohlcv("000001", date(2026, 6, 2), date(2026, 6, 5))
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_return_oracle.py -q`
Expected: FAIL(`_normalize_ohlcv` 不存在 / `GuardedSource` 无 `daily_ohlcv` / `FakeSource` 无 `ohlcv`)

- [ ] **Step 3a: `source.py` 加 `_normalize_ohlcv`(放在现有 `_normalize` 之后)**

```python
_OHLCV_RENAME = {"日期": "date", "开盘": "open", "收盘": "close",
                 "最高": "high", "最低": "low", "成交量": "volume"}


def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """akshare 日线中文列 -> 英文;date->date 对象;OHLCV->数值。空 -> 带列空 df。"""
    if df is None or df.empty:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
    out = df.rename(columns=_OHLCV_RENAME).copy()
    out = out.loc[:, ~out.columns.duplicated()]
    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"]).dt.date
    for c in ("open", "high", "low", "close", "volume"):
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")
    return out
```

- [ ] **Step 3b: `MarketDataSource` 协议加方法(在 `dt_pool` 之后)**

```python
    def daily_ohlcv(self, code: str, start: Date, end: Date) -> pd.DataFrame: ...
```

- [ ] **Step 3c: `AkshareSource.daily_ohlcv`(在 `dt_pool` 方法之后)**

```python
    def daily_ohlcv(self, code: str, start: Date, end: Date) -> pd.DataFrame:
        return _normalize_ohlcv(self._ak.stock_zh_a_hist(
            symbol=code, period="daily", start_date=_ymd(start),
            end_date=_ymd(end), adjust="qfq"))
```

- [ ] **Step 3d: `GuardedSource.daily_ohlcv`(在 `dt_pool` 方法之后)**

```python
    def daily_ohlcv(self, code: str, start: Date, end: Date) -> pd.DataFrame:
        self._guard.check(end)            # 打分时刻 as_of≥t+N 合法;越界(end>as_of)→ LookaheadError
        return self._inner.daily_ohlcv(code, start, end)
```

- [ ] **Step 3e: `tests/conftest.py` 的 `FakeSource` 加 `ohlcv` + `daily_ohlcv`**

把 `FakeSource.__init__` 改为接受可选 `ohlcv`,并加 `daily_ohlcv` 方法:

```python
    def __init__(self, frames: dict[tuple[str, date], pd.DataFrame],
                 calendar: list[date], ohlcv: dict[str, pd.DataFrame] | None = None):
        self._frames = frames
        self._calendar = calendar
        self._ohlcv = ohlcv or {}

    def daily_ohlcv(self, code: str, start: date, end: date) -> pd.DataFrame:
        df = self._ohlcv.get(code)
        if df is None or df.empty:
            return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
        return df[(df["date"] >= start) & (df["date"] <= end)].copy()
```

- [ ] **Step 4: 跑测试确认通过 + 回归既有 source 测试**

Run: `.venv/bin/python -m pytest tests/test_return_oracle.py tests/test_source_guard.py tests/test_source_normalize.py -q`
Expected: PASS(新 4 例 + 既有 source 测试全绿)

- [ ] **Step 5: 提交**

```bash
git add youzi/data/source.py tests/conftest.py tests/test_return_oracle.py
git commit -m "feat(data): daily_ohlcv 取数(协议/Akshare qfq/Guarded守界)+ _normalize_ohlcv + FakeSource"
```

---

### Task 2: `return_oracle.py`(`forward_return` 纯函数 + `ReturnOracle`)

**Files:**
- Create: `youzi/eval/return_oracle.py`
- Test: `tests/test_return_oracle.py`(追加)

- [ ] **Step 1: 追加失败测试**

```python
from youzi.eval.return_oracle import forward_return, ReturnOracle


def test_forward_return_normal_and_negative():
    df = _ohlcv([(date(2026, 6, 2), 10.0, 11, 9.5, 10.5, 100),
                 (date(2026, 6, 3), 10.6, 12.5, 10.4, 12.0, 200)])
    # entry open@6/2=10.0, exit close@6/3=12.0 → +0.20
    assert forward_return(df, date(2026, 6, 2), date(2026, 6, 3)) == 0.20
    # 负收益:entry open=10.0, exit close=8.0
    df2 = _ohlcv([(date(2026, 6, 2), 10.0, 11, 9, 10, 100),
                  (date(2026, 6, 3), 9.0, 9.5, 7.5, 8.0, 200)])
    assert forward_return(df2, date(2026, 6, 2), date(2026, 6, 3)) == -0.20


def test_forward_return_missing_returns_none():
    df = _ohlcv([(date(2026, 6, 2), 10.0, 11, 9.5, 10.5, 100)])
    assert forward_return(df, date(2026, 6, 1), date(2026, 6, 2)) is None   # entry 不在
    assert forward_return(df, date(2026, 6, 2), date(2026, 6, 9)) is None   # exit 不在
    assert forward_return(pd.DataFrame(), date(2026, 6, 2), date(2026, 6, 3)) is None  # 空 df


def test_forward_return_bad_open_returns_none():
    nan_open = _ohlcv([(date(2026, 6, 2), float("nan"), 11, 9, 10, 100),
                       (date(2026, 6, 3), 10, 12, 10, 11, 200)])
    assert forward_return(nan_open, date(2026, 6, 2), date(2026, 6, 3)) is None
    zero_open = _ohlcv([(date(2026, 6, 2), 0.0, 11, 9, 10, 100),
                        (date(2026, 6, 3), 10, 12, 10, 11, 200)])
    assert forward_return(zero_open, date(2026, 6, 2), date(2026, 6, 3)) is None


def test_return_oracle_score():
    df = _ohlcv([(date(2026, 6, 2), 10.0, 11, 9.5, 10.5, 100),
                 (date(2026, 6, 3), 10.6, 12.5, 10.4, 12.0, 200)])
    o = ReturnOracle(FakeSource({}, [], ohlcv={"000001": df}))
    assert o.score("000001", date(2026, 6, 2), date(2026, 6, 3)) == 0.20
    assert o.score("999999", date(2026, 6, 2), date(2026, 6, 3)) is None    # 缺该 code → None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_return_oracle.py -q`
Expected: FAIL(`ModuleNotFoundError: youzi.eval.return_oracle`)

- [ ] **Step 3: 实现 `youzi/eval/return_oracle.py`**

```python
# youzi/eval/return_oracle.py
from __future__ import annotations

from datetime import date as Date

import pandas as pd


def forward_return(ohlcv: pd.DataFrame, entry_day: Date, exit_day: Date) -> float | None:
    """次日开盘买→t+N 收盘卖:(close@exit_day − open@entry_day) / open@entry_day。

    entry_day/exit_day 不在 ohlcv、open 缺/≤0、close 缺 → None(诚实缺失,不臆造)。
    纯函数:只读传入 df,不取数、无副作用。
    """
    if ohlcv is None or ohlcv.empty or "date" not in ohlcv.columns:
        return None
    e = ohlcv.loc[ohlcv["date"] == entry_day]
    x = ohlcv.loc[ohlcv["date"] == exit_day]
    if e.empty or x.empty:
        return None
    op = e.iloc[0].get("open")
    cl = x.iloc[0].get("close")
    if op is None or cl is None or pd.isna(op) or pd.isna(cl) or op <= 0:
        return None
    return float((cl - op) / op)


class ReturnOracle:
    """前向收益 oracle(打分时刻用已实现 OHLCV)。决策日 t 不调用;片 2 传 GuardedSource 守界。"""

    def __init__(self, source) -> None:
        self._source = source

    def score(self, code: str, entry_day: Date, exit_day: Date) -> float | None:
        ohlcv = self._source.daily_ohlcv(code, entry_day, exit_day)
        return forward_return(ohlcv, entry_day, exit_day)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_return_oracle.py -q`
Expected: PASS(8 passed:Task1 的 4 + 本任务 4)

- [ ] **Step 5: 全量回归**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS(246 + 8 = 254,全绿,离线不触网)

- [ ] **Step 6: 提交**

```bash
git add youzi/eval/return_oracle.py tests/test_return_oracle.py
git commit -m "feat(eval): forward_return 纯函数 + ReturnOracle(次日开盘买→t+N收盘卖收益幅度)"
```

---

## 收尾(Task 2 之后,subagent-driven 终审前)

- [ ] 更新 `PROJECT_STATE.md`:1b-3e-1 完成(片 1)+ 片 2 待做。
- [ ] 更新 `后续开发文档.md`:状态表 + §4 路线图 + §5 债务。
- [ ] 更新 memory:下一步 → 1b-3e-2(接入打分/信用/评测)。

**本阶段债务(登记,非阻塞)**:① 接入(片 2);② fill-feasibility(一字涨停次日买不进);③ 成本/滑点;④ akshare `stock_zh_a_hist` 历史范围 / 复权口径细节;⑤ N 日池成员变体。

---

## Self-Review(写计划后自查,已执行)

**1. Spec coverage:** §3 `daily_ohlcv`(协议/Akshare/Guarded)+ `_normalize_ohlcv` + `FakeSource.daily_ohlcv` → Task 1 ✅;`forward_return` + `ReturnOracle` → Task 2 ✅;§6 防火墙(Guarded 守 `end≤as_of`、纯函数不取数)→ Task 1 guard 测试 + Task 2 纯函数 ✅;§7 测试(normalize/range/guard/forward_return 正常·负·缺·NaN·0open·空/oracle)→ Task 1+2 全覆盖;§8 DoD + 全量回归 → Task 2 Step 5。

**2. Placeholder scan:** 无 TBD/TODO;每步完整代码 + 确切命令/预期。

**3. Type consistency:** `daily_ohlcv(code, start, end)`、`_normalize_ohlcv(df)`、`forward_return(ohlcv, entry_day, exit_day)`、`ReturnOracle(source).score(code, entry_day, exit_day)`、`FakeSource(frames, calendar, ohlcv=None).daily_ohlcv` 跨 Task 1/2 一致;复用 `AsOfGuard(as_of).check`/`LookaheadError`、`GuardedSource(inner, guard)`、`_ymd` 均与既有源一致。归一列名 `date/open/high/low/close/volume` 全程一致。
