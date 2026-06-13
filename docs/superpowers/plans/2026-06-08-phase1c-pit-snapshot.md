# Phase-1c-PIT:PIT 数据快照 + 离线打分 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 唤醒休眠的 `PITStore` 并扩展(OHLCV+日历)+ 加 `SnapshotSource`(离线 MarketDataSource)+ `capture_window`(一次性节流预取 akshare→store)+ 离线 runner,让收益对比**离线跑**(akshare 出局,治 findings §10 限流)。

**Architecture:** `capture_window` 把窗口内 4 池/日 + universe 各 code OHLCV + 日历预取进 `PITStore`(parquet,幂等+throttle+复用 `_retry_ak`);`SnapshotSource` 从 store 读、实现 6 方法协议(池缺报错/OHLCV 缺返空/date 归一);eval 用 `GuardedSource(SnapshotSource)`,防火墙+打分链路零改。

**Tech Stack:** Python · pandas · pyarrow(已装) · pytest(全离线:FakeSource→PITStore→SnapshotSource 往返,不触网)。

**分支:** `phase1c-pit-snapshot`(执行时建)。**先读** spec:`docs/superpowers/specs/2026-06-08-phase1c-pit-snapshot-design.md`。

**全量回归基线:** `.venv/bin/python -m pytest -q` 当前 **265 passed**。

**Bundle 分组:** A=Task 1-2(store 扩展 + SnapshotSource)· B=Task 3-4(capture + 端到端)· C=Task 5(runner)。

---

## Bundle A

### Task 1: `PITStore` 扩展(OHLCV + 日历)

**Files:**
- Modify: `youzi/data/cache.py`
- Test: `tests/test_cache.py`(追加)

- [ ] **Step 1: 追加失败测试**

```python
# tests/test_cache.py 追加
def test_ohlcv_roundtrip_and_missing(tmp_path):
    store = PITStore(root=tmp_path)
    assert store.get_ohlcv("000001") is None and not store.has_ohlcv("000001")
    df = pd.DataFrame([(date(2026, 6, 2), 10.0, 11, 9, 10.5, 100)],
                      columns=["date", "open", "high", "low", "close", "volume"])
    store.put_ohlcv("000001", df)
    assert store.has_ohlcv("000001")
    got = store.get_ohlcv("000001")
    assert len(got) == 1 and float(got["close"].iloc[0]) == 10.5


def test_calendar_roundtrip_and_missing(tmp_path):
    store = PITStore(root=tmp_path)
    assert store.get_calendar() is None
    days = [date(2026, 6, 1), date(2026, 6, 2), date(2026, 6, 3)]
    store.put_calendar(days)
    assert store.get_calendar() == days        # date 对象,顺序保持
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_cache.py -q`
Expected: FAIL(`PITStore` 无 `put_ohlcv`/`get_calendar`)

- [ ] **Step 3: 扩展 `cache.py`**

在 `PITStore` 类内(`put` 方法之后)追加:

```python
    def _ohlcv_path(self, code: str) -> Path:
        return self._root / "ohlcv" / f"{code}.parquet"

    def has_ohlcv(self, code: str) -> bool:
        return self._ohlcv_path(code).exists()

    def get_ohlcv(self, code: str) -> pd.DataFrame | None:
        p = self._ohlcv_path(code)
        return pd.read_parquet(p) if p.exists() else None

    def put_ohlcv(self, code: str, df: pd.DataFrame) -> None:
        p = self._ohlcv_path(code)
        p.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(p, index=False)

    def put_calendar(self, days: list[Date]) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({"date": [d.isoformat() for d in days]}).to_parquet(
            self._root / "calendar.parquet", index=False)

    def get_calendar(self) -> list[Date] | None:
        p = self._root / "calendar.parquet"
        if not p.exists():
            return None
        return [pd.to_datetime(s).date() for s in pd.read_parquet(p)["date"]]
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_cache.py -q`
Expected: PASS(既有 3 + 新 2 = 5 passed)

- [ ] **Step 5: 提交**

```bash
git add youzi/data/cache.py tests/test_cache.py
git commit -m "feat(data): PITStore 加 OHLCV(per-code parquet)+ calendar 存取"
```

---

### Task 2: `SnapshotSource`(离线 MarketDataSource)

**Files:**
- Create: `youzi/data/snapshot_source.py`
- Test: `tests/test_snapshot_source.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_snapshot_source.py
from datetime import date

import pandas as pd
import pytest

from youzi.data.cache import PITStore
from youzi.data.snapshot_source import SnapshotSource, SnapshotMissingError


def test_pools_roundtrip_and_missing_raises(tmp_path):
    store = PITStore(tmp_path)
    store.put_calendar([date(2026, 6, 2)])
    store.put("zt", date(2026, 6, 2), pd.DataFrame({"code": ["A"], "boards": [2]}))
    src = SnapshotSource(store)
    assert src.trading_calendar() == [date(2026, 6, 2)]
    assert list(src.zt_pool(date(2026, 6, 2))["code"]) == ["A"]
    with pytest.raises(SnapshotMissingError):
        src.dt_pool(date(2026, 6, 2))                  # 未存 → 报错(不完整快照大声抓住)


def test_missing_calendar_raises(tmp_path):
    with pytest.raises(SnapshotMissingError):
        SnapshotSource(PITStore(tmp_path)).trading_calendar()


def test_ohlcv_slice_date_objects_and_missing_empty(tmp_path):
    store = PITStore(tmp_path)
    df = pd.DataFrame([(date(2026, 6, 2), 10.0, 11, 9, 10.5, 100),
                       (date(2026, 6, 3), 10.6, 12, 10, 12.0, 200),
                       (date(2026, 6, 4), 12.1, 13, 12, 12.5, 300)],
                      columns=["date", "open", "high", "low", "close", "volume"])
    store.put_ohlcv("A", df)
    src = SnapshotSource(store)
    got = src.daily_ohlcv("A", date(2026, 6, 2), date(2026, 6, 3))
    assert list(got["date"]) == [date(2026, 6, 2), date(2026, 6, 3)]   # 切片 + date 对象
    assert isinstance(got["date"].iloc[0], date)
    assert src.daily_ohlcv("MISSING", date(2026, 6, 2), date(2026, 6, 3)).empty   # 缺 code → 空
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_snapshot_source.py -q`
Expected: FAIL(`ModuleNotFoundError: youzi.data.snapshot_source`)

- [ ] **Step 3: 实现 `youzi/data/snapshot_source.py`**

```python
# youzi/data/snapshot_source.py
from __future__ import annotations

from datetime import date as Date

import pandas as pd

from youzi.data.cache import PITStore

_EMPTY_OHLCV = ["date", "open", "high", "low", "close", "volume"]


class SnapshotMissingError(RuntimeError):
    """快照缺池数据(不完整 capture)——大声失败,别静默当 no-trade。"""


class SnapshotSource:
    """从 PITStore 读的离线 MarketDataSource(零 akshare)。eval 时仍被 GuardedSource 套。"""

    def __init__(self, store: PITStore) -> None:
        self._store = store

    def trading_calendar(self) -> list[Date]:
        cal = self._store.get_calendar()
        if cal is None:
            raise SnapshotMissingError("快照缺 calendar.parquet")
        return cal

    def _pool(self, kind: str, day: Date) -> pd.DataFrame:
        df = self._store.get(kind, day)
        if df is None:
            raise SnapshotMissingError(f"快照缺池 {kind}@{day}(capture 不完整?)")
        return df

    def zt_pool(self, day: Date) -> pd.DataFrame:
        return self._pool("zt", day)

    def zt_pool_previous(self, day: Date) -> pd.DataFrame:
        return self._pool("prev", day)

    def zt_pool_blowup(self, day: Date) -> pd.DataFrame:
        return self._pool("blowup", day)

    def dt_pool(self, day: Date) -> pd.DataFrame:
        return self._pool("dt", day)

    def daily_ohlcv(self, code: str, start: Date, end: Date) -> pd.DataFrame:
        df = self._store.get_ohlcv(code)
        if df is None or df.empty:
            return pd.DataFrame(columns=_EMPTY_OHLCV)     # 停牌/退市/未捕获 → 空(ReturnScorer 丢弃)
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"]).dt.date   # parquet 往返稳健:归一回 date 对象
        return df[(df["date"] >= start) & (df["date"] <= end)]
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_snapshot_source.py -q`
Expected: PASS(3 passed)

- [ ] **Step 5: 提交**

```bash
git add youzi/data/snapshot_source.py tests/test_snapshot_source.py
git commit -m "feat(data): SnapshotSource 离线读 PITStore(池缺报错/OHLCV缺返空/date归一)"
```

---

## Bundle B

### Task 3: `capture_window`(节流 akshare→store)

**Files:**
- Create: `youzi/data/capture.py`
- Test: `tests/test_capture.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_capture.py
from datetime import date

import pandas as pd

from youzi.data.cache import PITStore
from youzi.data.capture import capture_window
from tests.conftest import FakeSource


def _src():
    days = [date(2026, 6, 1), date(2026, 6, 2), date(2026, 6, 3)]
    frames = {("zt", d): pd.DataFrame({"code": ["A"], "name": ["甲"], "boards": [2]}) for d in days}
    ohlcv = {"A": pd.DataFrame([(date(2026, 6, 2), 10.0, 11, 9, 10.5, 100)],
                               columns=["date", "open", "high", "low", "close", "volume"])}
    return FakeSource(frames, days, ohlcv=ohlcv)


def test_capture_writes_pools_ohlcv_calendar(tmp_path):
    store = PITStore(tmp_path)
    summ = capture_window(_src(), store, date(2026, 6, 1), date(2026, 6, 3), sleep=lambda d: None)
    assert summ.n_days == 3 and summ.n_codes == 1
    assert store.get_calendar() == [date(2026, 6, 1), date(2026, 6, 2), date(2026, 6, 3)]
    assert list(store.get("zt", date(2026, 6, 2))["code"]) == ["A"]    # 池每日落
    assert store.has("dt", date(2026, 6, 1))                          # 空池也落(不缺)
    assert store.has_ohlcv("A")                                       # universe 各 code OHLCV 落


def test_capture_idempotent_skips(tmp_path):
    store = PITStore(tmp_path)
    capture_window(_src(), store, date(2026, 6, 1), date(2026, 6, 3), sleep=lambda d: None)
    calls = []
    summ2 = capture_window(_src(), store, date(2026, 6, 1), date(2026, 6, 3),
                           sleep=lambda d: calls.append(d))
    assert calls == []                # 全 has 命中 → 不再取数/sleep


def test_capture_blowup_valueerror_stored_empty(tmp_path):
    class _BlowupRaises(FakeSource):
        def zt_pool_blowup(self, day):
            raise ValueError("炸板股池只能获取最近 30 个交易日的数据")
    store = PITStore(tmp_path)
    capture_window(_BlowupRaises({}, [date(2026, 6, 1)], ohlcv={}),
                   store, date(2026, 6, 1), date(2026, 6, 1), sleep=lambda d: None)
    assert store.has("blowup", date(2026, 6, 1))     # 存空帧,不崩、不缺
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_capture.py -q`
Expected: FAIL(`ModuleNotFoundError: youzi.data.capture`)

- [ ] **Step 3: 实现 `youzi/data/capture.py`**

```python
# youzi/data/capture.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date

import pandas as pd

from youzi.data.cache import PITStore

_POOLS = [("zt", "zt_pool"), ("prev", "zt_pool_previous"),
          ("blowup", "zt_pool_blowup"), ("dt", "dt_pool")]


@dataclass(frozen=True)
class CaptureSummary:
    n_days: int
    n_codes: int
    n_calls: int


def capture_window(ak_source, store: PITStore, start: Date, end: Date,
                   *, throttle: float = 0.3, sleep=None) -> CaptureSummary:
    """一次性把窗口内 4 池(每日)+ universe 各 code OHLCV + 日历预取进 PITStore。
    幂等(has 跳过);blowup 超 30 日 ValueError → 存空帧;唯一碰 akshare 的部分。"""
    import time as _t
    slp = sleep if sleep is not None else _t.sleep
    calls = 0
    cal = ak_source.trading_calendar()
    store.put_calendar(cal)
    window = [d for d in cal if start <= d <= end]
    codes: set[str] = set()
    for day in window:
        for kind, fname in _POOLS:
            if not store.has(kind, day):
                try:
                    df = getattr(ak_source, fname)(day)
                except ValueError:                       # blowup 30 日限制等确定性错 → 存空帧
                    df = pd.DataFrame(columns=["code"])
                store.put(kind, day, df)
                calls += 1
                slp(throttle)
            df = store.get(kind, day)
            if df is not None and "code" in df.columns:
                codes.update(str(c) for c in df["code"])
    for code in sorted(codes):
        if not store.has_ohlcv(code):
            store.put_ohlcv(code, ak_source.daily_ohlcv(code, start, end))
            calls += 1
            slp(throttle)
    return CaptureSummary(n_days=len(window), n_codes=len(codes), n_calls=calls)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_capture.py -q`
Expected: PASS(3 passed)

- [ ] **Step 5: 提交**

```bash
git add youzi/data/capture.py tests/test_capture.py
git commit -m "feat(data): capture_window 一次性节流预取(4池/日+universe OHLCV+日历,幂等,blowup容错)"
```

---

### Task 4: 端到端离线收益对比(capture→SnapshotSource→compare)

**Files:**
- Test: `tests/test_pit_e2e.py`

- [ ] **Step 1: 写失败测试**(应直接通过——验证整链路;先跑确认绿,再提交)

```python
# tests/test_pit_e2e.py
from youzi.data.cache import PITStore
from youzi.data.capture import capture_window
from youzi.data.snapshot_source import SnapshotSource
from youzi.eval.scorer import ReturnScorer
from youzi.loop.compare import compare_harnesses
from youzi.loop.inner_loop import LoopConfig
from youzi.harness.snapshot import SnapshotStore
from tests.test_compare import _w_src, _SeqFactory, _CountFactory, _PICK_W, _NO_TRADE
from tests.test_inner_loop import _seed_h


def test_offline_return_scoring_via_snapshot(tmp_path):
    # 1) capture 真实 live(FakeSource)→ PITStore
    live = _w_src()
    store = PITStore(tmp_path / "snap")
    capture_window(live, store, live.trading_calendar()[0], live.trading_calendar()[-1],
                   sleep=lambda d: None)
    # 2) 离线 SnapshotSource 跑四路收益对比(零 akshare)
    snap = SnapshotSource(store)
    rep = compare_harnesses(
        _CountFactory(_seed_h), snap, snap.trading_calendar()[0], snap.trading_calendar()[-1],
        agent_llm_factory=_SeqFactory([_PICK_W, _NO_TRADE]),
        refiner_llm_factory=_SeqFactory(['{"ops": []}']),
        store_factory=_CountFactory(lambda: SnapshotStore(tmp_path / "h")),
        loop_config=LoopConfig(horizon=1), scorer=ReturnScorer())
    assert set(rep.arms) == {"HCH", "Hexpert", "Hmin_highest", "Hmin_notrade"}
    assert rep.arms["HCH"].report.n_candidates >= 1     # W continued + OHLCV → 收益打分(候选>0)
```

- [ ] **Step 2: 跑测试**

Run: `.venv/bin/python -m pytest tests/test_pit_e2e.py -q`
Expected: PASS(1 passed)。若 FAIL,核对 capture/SnapshotSource 接线(应为整链路真实可跑)。

- [ ] **Step 3: 提交**

```bash
git add tests/test_pit_e2e.py
git commit -m "test(data): 端到端 capture→SnapshotSource→compare 离线收益对比跑通"
```

---

## Bundle C

### Task 5: runner(capture 脚本 + smoke 快照分支)

**Files:**
- Create: `scripts/capture_window.py`
- Modify: `scripts/smoke_compare.py`

- [ ] **Step 1: 新建 `scripts/capture_window.py`**

```python
# scripts/capture_window.py
"""一次性建 PIT 快照:把窗口内 4 池/日 + universe OHLCV + 日历预取进 PITStore(parquet)。

Run: python scripts/capture_window.py <start_ymd> <end_ymd> <out_dir>
之后离线跑:YOUZI_SNAPSHOT=<out_dir> DEEPSEEK_API_KEY=... python scripts/smoke_compare.py <s> <e> 2 0.0 return
慢、节流(默认 0.3s/调用)、幂等(可中断重跑)。唯一碰 akshare 的步骤。
"""
import sys
from datetime import datetime
from pathlib import Path

from youzi.data.cache import PITStore
from youzi.data.capture import capture_window
from youzi.data.source import AkshareSource


def main(start_ymd: str, end_ymd: str, out_dir: str) -> None:
    start = datetime.strptime(start_ymd, "%Y%m%d").date()
    end = datetime.strptime(end_ymd, "%Y%m%d").date()
    store = PITStore(Path(out_dir))
    print(f"capture {start}~{end} → {out_dir}(节流 0.3s/调用,幂等)…")
    summ = capture_window(AkshareSource(), store, start, end)
    print(f"完成:交易日 {summ.n_days}、code {summ.n_codes}、akshare 调用 {summ.n_calls}。")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("用法: python scripts/capture_window.py <start_ymd> <end_ymd> <out_dir>")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2], sys.argv[3])
```

- [ ] **Step 2: 改 `scripts/smoke_compare.py`(快照分支)**

在 `main` 里构造 `src` 处(现 `src = _MemoizedSource(AkshareSource())`)替换为读 env 分支:

```python
    snap = os.environ.get("YOUZI_SNAPSHOT")
    if snap:
        from youzi.data.cache import PITStore
        from youzi.data.snapshot_source import SnapshotSource
        src = SnapshotSource(PITStore(Path(snap)))
        print(f"[离线] 用 PIT 快照 {snap}(零 akshare)。")
    else:
        src = _MemoizedSource(AkshareSource())
```

(`os`、`Path`、`AkshareSource` 已在 smoke_compare 顶部导入;无需改其它。)

- [ ] **Step 3: 语法检查 + 全量回归**

Run: `.venv/bin/python -m py_compile scripts/capture_window.py scripts/smoke_compare.py && .venv/bin/python -m pytest -q`
Expected: `syntax ok`;全量 PASS(265 + 本阶段新增,目标 ≈273)

- [ ] **Step 4: 提交**

```bash
git add scripts/capture_window.py scripts/smoke_compare.py
git commit -m "feat(scripts): capture_window 建库脚本 + smoke YOUZI_SNAPSHOT 离线分支"
```

---

## 收尾(Task 5 之后,subagent-driven 终审前)

- [ ] 更新 `PROJECT_STATE.md`/`后续开发文档.md`(1c-PIT 完成,离线收益对比解锁)+ memory。
- [ ] **(人工)** `python scripts/capture_window.py <s> <e> snap`(建库一次,慢)→ `YOUZI_SNAPSHOT=snap DEEPSEEK_API_KEY=... python scripts/smoke_compare.py <s> <e> 2 0.0 return`(离线跑真实收益对比),记 findings。

**本阶段债务**:OHLCV qfq 事后除权精化;LLM 响应缓存(DeepSeek 仍 live);快照增量/过期刷新 + `verify`;幸存者偏差;熔断 scorer-aware 重标定(承前)。

---

## Self-Review(写计划后自查,已执行)

**1. Spec coverage:** §4.1 PITStore OHLCV/calendar → Task 1 ✅;§4.2 SnapshotSource(协议+缺数+date归一)→ Task 2 ✅;§4.3 capture_window(幂等+blowup容错+throttle/sleep注入)→ Task 3 ✅;§4.4 runner(capture脚本+smoke YOUZI_SNAPSHOT)→ Task 5 ✅;§6 防火墙(SnapshotSource 经 GuardedSource)→ Task 4 端到端走 compare_harnesses→InnerLoop/WalkForwardEval→ReplayEngine(GuardedSource)验证;§7 测试(往返/缺数/幂等/blowup/端到端)→ Task 1-4 全覆盖;§8 DoD + 全量回归 → Task 5 Step 3;人工建库+离线跑 → 收尾。

**2. Placeholder scan:** 无 TBD/TODO;每步完整代码 + 确切命令/预期。

**3. Type consistency:** `PITStore.{put_ohlcv,get_ohlcv,has_ohlcv,put_calendar,get_calendar}`、`SnapshotSource(store).{6 协议方法}`、`SnapshotMissingError`、`capture_window(ak_source, store, start, end, *, throttle, sleep)→CaptureSummary{n_days,n_codes,n_calls}`、kind 串 `zt/prev/blowup/dt`(capture/SnapshotSource/FakeSource 三处一致)跨 Task 一致;复用 `PITStore(root)`(既有)、`MarketDataSource` 协议、`compare_harnesses(..., scorer=)`/`ReturnScorer`(1b-3e-2)、`FakeSource(frames,calendar,ohlcv=)`、`_w_src`/`_seed_h`/`_SeqFactory`/`_CountFactory`/`_PICK_W`/`_NO_TRADE`(既有测试)均与源一致。date 列归一(`pd.to_datetime(...).dt.date`)在 SnapshotSource 读侧 + get_calendar,保 `forward_return` 的 `== entry_day` 成立。
