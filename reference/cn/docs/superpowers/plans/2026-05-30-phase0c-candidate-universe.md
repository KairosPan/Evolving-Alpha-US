# Phase-0c 候选 universe / 个股快照层 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在观测 `o_t` 里补上**个股级候选 universe**——把每个交易日的涨停/炸板/跌停股做成按 code 索引、可查询的 `StockSnapshot` 集合(`CandidateUniverse`)。这是任何"选股策略/Agent"挑标的、以及评测 oracle 按 code 追踪结果的前置;Phase-0a 的 `MarketState` 只有聚合量(情绪值/连板梯队/炸板率)与代表票名字,挑不了具体标的。

**Architecture:** 复用 Phase-0a 的数据层。扩展 `data/source.py` 的列归一以保留个股字段(封板资金/换手率/所属行业/流通市值)→ 新 `StockSnapshot`(frozen PIT 模型)→ `CandidateUniverse`(按 code 索引 + 多维查询)→ `build_universe(source, day)`(把当日三池合成 universe,状态来自所属池)。纯 pandas + pydantic,**全程离线可测**(FakeSource fixtures);经 `GuardedSource` 取数时天然受未来函数防火墙保护。**不改 `MarketState`**——universe 作为 `o_t` 的并列组件,由调用方(评测/Agent)在同一游标处单独构建。

**Tech Stack:** Python 3.11+ · pandas · pydantic v2 · pytest。无新依赖,沿用 `.venv`。

**范围边界:** 不做 L2/逐笔/分时(本阶段只用日级三池能给的个股字段)、不做题材线/概念成分归属(题材线特征是后续数据补强)、不做评测/oracle(Phase-0d)、不做 Agent(Phase-1)。`MarketState` 不变。

**关键设计点:**
- **PIT 个股快照**:`StockSnapshot` frozen;`status` ∈ {limit_up, blowup, limit_down} 来自所属池(收盘时三池互斥)。缺失字段用 `None`(不臆造)。
- **复用防火墙**:`build_universe(guarded_source, day)` 经 `GuardedSource` 取数,请求未来日期 → `LookaheadError`(与回放引擎同一道闸)。
- **杀 falsy-trap**(沿用 0b-3 教训):`CandidateUniverse.__bool__ = True`。
- **列归一向后兼容**:扩展 `_RENAME` 只新增映射,不破坏已有 `_normalize` 去重/空兜底行为;真实 akshare 列名以 `scripts/smoke_akshare.py` 核验为准(离线测试用 FakeSource 的英文列,不依赖真实列名)。

---

## File Structure

```
youzi/data/
  source.py          # MODIFY: _RENAME 增个股字段映射(封板资金/换手率/首次封板时间/所属行业/流通市值)
youzi/universe/
  __init__.py        # NEW
  stock.py           # NEW: StockSnapshot(frozen)
  universe.py        # NEW: CandidateUniverse(按 code 索引+查询) + build_universe(source, day)
tests/
  test_source_normalize.py     # + 新字段归一
  test_stock.py                # NEW
  test_universe.py             # NEW
  test_universe_firewall.py    # NEW: 经 GuardedSource 取未来日期 -> LookaheadError
```

**全局类型契约:**
- `StockSnapshot` 字段:`code/name/status/boards/pct/seal_amount/turnover_rate/first_seal_time/blowup_count/industry/float_mcap`。
- `CandidateUniverse`:`get(code)`、`all()`、`by_status(s)`、`by_min_boards(n)`、`by_industry(ind)`、`__len__`、`__bool__`。
- `build_universe(source, day) -> CandidateUniverse`(source 为 MarketDataSource;回放时传 GuardedSource)。

---

## Task 1: `source._RENAME` 扩展(保留个股字段)

**Files:** Modify `youzi/data/source.py`; Modify `tests/test_source_normalize.py`

- [ ] **Step 1: 追加失败测试到 `tests/test_source_normalize.py`**

```python
def test_normalize_maps_per_stock_fields():
    import pandas as pd
    from youzi.data.source import _normalize
    df = pd.DataFrame({"代码": ["000001"], "名称": ["甲"], "连板数": [3],
                       "涨跌幅": [10.0], "封板资金": [8.0e8], "换手率": [5.5],
                       "首次封板时间": ["09:31:00"], "所属行业": ["银行"], "流通市值": [1.2e10]})
    out = _normalize(df)
    for col in ["code", "name", "boards", "pct", "seal_amount",
                "turnover_rate", "first_seal_time", "industry", "float_mcap"]:
        assert col in out.columns, f"缺列 {col}"
    assert out["seal_amount"].iloc[0] == 8.0e8
    assert out["industry"].iloc[0] == "银行"
```

- [ ] **Step 2: 运行,确认失败**

Run: `cd "/Volumes/kairos/引力场量化/youzi-自进化版" && source .venv/bin/activate && pytest tests/test_source_normalize.py -v`
Expected: FAIL（新字段未映射,缺列）

- [ ] **Step 3: 扩展 `youzi/data/source.py` 的 `_RENAME`**

在 `_RENAME` 字典里追加(保留已有项):
```python
    "封板资金": "seal_amount",
    "换手率": "turnover_rate",
    "首次封板时间": "first_seal_time",
    "所属行业": "industry",
    "流通市值": "float_mcap",
```
并在 `_normalize` 的数值列强制转换里,把数值型字段一并 coerce(找到现有的 `for col in (...)` 数值转换循环,把 `"seal_amount", "turnover_rate", "float_mcap"` 加进去;`first_seal_time`/`industry` 保持字符串):
```python
    for col in ("boards", "pct", "blowups", "seal_amount", "turnover_rate", "float_mcap"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
```

- [ ] **Step 4: 运行,确认通过**

Run: `pytest tests/test_source_normalize.py -v`
Expected: PASS（已有 dedupe/空兜底测试仍绿)

- [ ] **Step 5: Commit**

```bash
git add youzi/data/source.py tests/test_source_normalize.py
git commit -m "feat(data): _RENAME 保留个股字段(封单/换手/行业/流通市值)"
```

---

## Task 2: `StockSnapshot` 模型

**Files:** Create `youzi/universe/__init__.py`, `youzi/universe/stock.py`; Test `tests/test_stock.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_stock.py
from youzi.universe.stock import StockSnapshot


def test_stock_snapshot_minimal_and_full():
    s = StockSnapshot(code="000001", name="甲", status="limit_up", boards=3)
    assert s.code == "000001" and s.status == "limit_up" and s.boards == 3
    assert s.pct is None and s.seal_amount is None      # 缺失为 None, 不臆造
    full = StockSnapshot(code="300xxx", name="乙", status="blowup", boards=0,
                         pct=-2.0, seal_amount=None, turnover_rate=12.3,
                         first_seal_time="09:31:00", blowup_count=2,
                         industry="芯片", float_mcap=5.0e9)
    assert full.status == "blowup" and full.blowup_count == 2


def test_stock_snapshot_is_frozen():
    import pytest
    from pydantic import ValidationError
    s = StockSnapshot(code="1", name="甲", status="limit_up")
    with pytest.raises(ValidationError):
        s.boards = 9            # PIT 快照不可变


def test_stock_snapshot_status_validated():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        StockSnapshot(code="1", name="甲", status="不存在的状态")
```

- [ ] **Step 2: 运行,确认失败**

Run: `pytest tests/test_stock.py -v`
Expected: FAIL（`ModuleNotFoundError: youzi.universe.stock`）

- [ ] **Step 3: 实现 `youzi/universe/__init__.py` 与 `youzi/universe/stock.py`**

`youzi/universe/__init__.py`:
```python
"""个股候选 universe 层:per-stock PIT 快照 + 当日候选集合。"""
```

`youzi/universe/stock.py`:
```python
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

StockStatus = Literal["limit_up", "blowup", "limit_down"]


class StockSnapshot(BaseModel):
    """个股当日 PIT 快照(frozen)。status 来自所属池(收盘三池互斥)。缺失字段 None。"""
    model_config = ConfigDict(frozen=True)
    code: str
    name: str
    status: StockStatus
    boards: int = 0                       # 连板数(跌停/炸板可能为 0)
    pct: float | None = None              # 今涨跌幅(%)
    seal_amount: float | None = None      # 封板资金
    turnover_rate: float | None = None    # 换手率(%)
    first_seal_time: str | None = None    # 首次封板时间
    blowup_count: int | None = None       # 炸板次数
    industry: str | None = None           # 所属行业
    float_mcap: float | None = None       # 流通市值
```

- [ ] **Step 4: 运行,确认通过**

Run: `pytest tests/test_stock.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add youzi/universe/__init__.py youzi/universe/stock.py tests/test_stock.py
git commit -m "feat(universe): StockSnapshot 个股 PIT 快照模型"
```

---

## Task 3: `CandidateUniverse` 容器 + 查询

**Files:** Create `youzi/universe/universe.py`; Test `tests/test_universe.py`

- [ ] **Step 1: 写失败测试(只测容器与查询,build 在 Task 4)**

```python
# tests/test_universe.py
from youzi.universe.stock import StockSnapshot
from youzi.universe.universe import CandidateUniverse


def _stocks():
    return [
        StockSnapshot(code="1", name="龙", status="limit_up", boards=7, industry="芯片"),
        StockSnapshot(code="2", name="中", status="limit_up", boards=3, industry="芯片"),
        StockSnapshot(code="3", name="炸", status="blowup", boards=0, industry="军工"),
        StockSnapshot(code="4", name="跌", status="limit_down", boards=0, industry="军工"),
    ]


def test_universe_queries():
    u = CandidateUniverse.from_stocks(_stocks())
    assert u.get("1").name == "龙" and u.get("zzz") is None
    assert {s.code for s in u.by_status("limit_up")} == {"1", "2"}
    assert {s.code for s in u.by_min_boards(3)} == {"1", "2"}       # 连板>=3
    assert {s.code for s in u.by_min_boards(7)} == {"1"}
    assert {s.code for s in u.by_industry("芯片")} == {"1", "2"}
    assert len(u) == 4


def test_universe_rejects_duplicate_code():
    import pytest
    with pytest.raises(ValueError):
        CandidateUniverse.from_stocks([_stocks()[0], _stocks()[0]])


def test_empty_universe_is_truthy():
    u = CandidateUniverse.from_stocks([])
    assert bool(u) is True and len(u) == 0          # 杀 falsy-trap(0b-3 教训)
```

- [ ] **Step 2: 运行,确认失败**

Run: `pytest tests/test_universe.py -v`
Expected: FAIL（`ModuleNotFoundError` / 无 from_stocks）

- [ ] **Step 3: 实现 `youzi/universe/universe.py`(先只放容器;build 在 Task 4 追加)**

```python
from __future__ import annotations

from youzi.universe.stock import StockSnapshot


class CandidateUniverse:
    """某交易日按 code 索引的候选个股集合(涨停/炸板/跌停)。"""

    def __init__(self, stocks: dict[str, StockSnapshot]) -> None:
        self._stocks = dict(stocks)          # 防御性拷贝

    @classmethod
    def from_stocks(cls, stocks: list[StockSnapshot]) -> "CandidateUniverse":
        index: dict[str, StockSnapshot] = {}
        for s in stocks:
            if s.code in index:
                raise ValueError(f"重复 code: {s.code}")
            index[s.code] = s
        return cls(index)

    def get(self, code: str) -> StockSnapshot | None:
        return self._stocks.get(code)

    def all(self) -> list[StockSnapshot]:
        return list(self._stocks.values())

    def by_status(self, status: str) -> list[StockSnapshot]:
        return [s for s in self._stocks.values() if s.status == status]

    def by_min_boards(self, n: int) -> list[StockSnapshot]:
        return [s for s in self._stocks.values() if s.boards >= n]

    def by_industry(self, industry: str) -> list[StockSnapshot]:
        return [s for s in self._stocks.values() if s.industry == industry]

    def __len__(self) -> int:
        return len(self._stocks)

    def __bool__(self) -> bool:
        return True              # 空但存在的 universe 仍为真(杀 falsy-trap)
```

- [ ] **Step 4: 运行,确认通过**

Run: `pytest tests/test_universe.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add youzi/universe/universe.py tests/test_universe.py
git commit -m "feat(universe): CandidateUniverse 按 code 索引与查询"
```

---

## Task 4: `build_universe(source, day)`

**Files:** Modify `youzi/universe/universe.py`; Modify `tests/test_universe.py`

> 把当日三池(zt_pool/zt_pool_blowup/dt_pool)合成 universe。同一 code 收盘互斥,但为稳健起见以"涨停优先"(最后写入 limit_up)。每行缺列用 None。

- [ ] **Step 1: 追加失败测试到 `tests/test_universe.py`**

```python
def test_build_universe_merges_three_pools():
    from datetime import date
    import pandas as pd
    from youzi.universe.universe import build_universe
    from tests.conftest import FakeSource

    d = date(2024, 6, 27)
    frames = {
        ("zt", d): pd.DataFrame({"code": ["1", "2"], "name": ["龙", "中"],
                                 "boards": [7, 3], "pct": [10.0, 10.0],
                                 "seal_amount": [8e8, 2e8], "industry": ["芯片", "芯片"]}),
        ("blowup", d): pd.DataFrame({"code": ["3"], "name": ["炸"], "pct": [3.0],
                                     "blowups": [2], "industry": ["军工"]}),
        ("dt", d): pd.DataFrame({"code": ["4"], "name": ["跌"], "pct": [-10.0],
                                 "industry": ["军工"]}),
    }
    u = build_universe(FakeSource(frames, [d]), d)
    assert len(u) == 4
    assert u.get("1").status == "limit_up" and u.get("1").boards == 7
    assert u.get("1").seal_amount == 8e8
    assert u.get("3").status == "blowup" and u.get("3").blowup_count == 2
    assert u.get("4").status == "limit_down"


def test_build_universe_empty_day():
    from datetime import date
    import pandas as pd
    from youzi.universe.universe import build_universe
    from tests.conftest import FakeSource
    d = date(2024, 6, 27)
    empty = {("zt", d): pd.DataFrame(), ("blowup", d): pd.DataFrame(),
             ("dt", d): pd.DataFrame()}
    u = build_universe(FakeSource(empty, [d]), d)
    assert len(u) == 0 and bool(u) is True
```

- [ ] **Step 2: 运行,确认失败**

Run: `pytest tests/test_universe.py -v`
Expected: FAIL（无 build_universe）

- [ ] **Step 3: 在 `youzi/universe/universe.py` 追加 `build_universe`**

```python
import pandas as pd

from youzi.universe.stock import StockSnapshot

_NUM = {"boards": int, "blowup_count": int}


def _to_snapshot(row: dict, status: str) -> StockSnapshot:
    def g(key, cast=None):
        v = row.get(key)
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        return cast(v) if cast else v
    return StockSnapshot(
        code=str(row["code"]).zfill(6),
        name=str(row.get("name", "")),
        status=status,
        boards=int(g("boards") or 0),
        pct=g("pct", float),
        seal_amount=g("seal_amount", float),
        turnover_rate=g("turnover_rate", float),
        first_seal_time=g("first_seal_time", str),
        blowup_count=(int(g("blowups")) if g("blowups") is not None else None),
        industry=g("industry", str),
        float_mcap=g("float_mcap", float),
    )


def build_universe(source, day) -> CandidateUniverse:
    """合成当日候选 universe。顺序 dt→blowup→zt,涨停最后写入(冲突时 limit_up 优先)。"""
    stocks: dict[str, StockSnapshot] = {}
    for fetch, status in ((source.dt_pool, "limit_down"),
                          (source.zt_pool_blowup, "blowup"),
                          (source.zt_pool, "limit_up")):
        df = fetch(day)
        if df is None or df.empty:
            continue
        for rec in df.to_dict("records"):
            snap = _to_snapshot(rec, status)
            stocks[snap.code] = snap
    return CandidateUniverse(stocks)
```

注:`build_universe` 用 `CandidateUniverse(stocks)`(直接构造,允许后写覆盖前写以实现"涨停优先"),不走 `from_stocks`(后者拒重复)。

- [ ] **Step 4: 运行,确认通过**

Run: `pytest tests/test_universe.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add youzi/universe/universe.py tests/test_universe.py
git commit -m "feat(universe): build_universe 合成当日三池候选集"
```

---

## Task 5: universe 经防火墙 + 集成

**Files:** Create `tests/test_universe_firewall.py`

> 验证 `build_universe(guarded_source, day)` 与回放引擎同一道未来函数防火墙:请求未来日期被拦截。

- [ ] **Step 1: 写测试**

```python
# tests/test_universe_firewall.py
from datetime import date
import pandas as pd
import pytest
from youzi.replay.firewall import AsOfGuard, LookaheadError
from youzi.data.source import GuardedSource
from youzi.universe.universe import build_universe
from tests.conftest import FakeSource


def _src(days):
    frames = {}
    for d in days:
        frames[("zt", d)] = pd.DataFrame({"code": ["1"], "name": ["龙"],
                                          "boards": [3], "pct": [10.0]})
        frames[("blowup", d)] = pd.DataFrame()
        frames[("dt", d)] = pd.DataFrame()
    return FakeSource(frames, days)


def test_build_universe_today_ok_future_blocked():
    days = [date(2024, 6, 27), date(2024, 6, 28)]
    guard = AsOfGuard(days[0])
    gs = GuardedSource(_src(days), guard)
    u = build_universe(gs, days[0])            # 当日 OK
    assert u.get("1").name == "龙"
    with pytest.raises(LookaheadError):        # 未来日被拦截
        build_universe(gs, days[1])
```

- [ ] **Step 2: 运行,确认通过**

Run: `pytest tests/test_universe_firewall.py -v`
Expected: PASS

- [ ] **Step 3: 跑全量套件**

Run: `pytest -p no:cacheprovider`(`-q` 摘要经管道会空,看退出码;约 105+ 用例)
Expected: exit 0,全绿

- [ ] **Step 4: Commit**

```bash
git add tests/test_universe_firewall.py
git commit -m "test(universe): build_universe 经 GuardedSource 未来函数防火墙"
```

- [ ] **Step 5:(可选,需联网)冒烟核验真实 akshare 个股列名**

更新 `scripts/smoke_akshare.py` 末尾追加一行打印 universe(若实现者愿意),或手动:`python -c "from youzi.data.source import AkshareSource; from youzi.universe.universe import build_universe; from datetime import date; u=build_universe(AkshareSource(), date(2024,6,27)); print(len(u), u.all()[:2])"`。**目的**:核验 `封板资金/换手率/所属行业/流通市值` 的真实 akshare 列名与 `_RENAME` 一致;若列名不符则修 `_RENAME`(离线测试不受影响)。不入 CI。

---

## Self-Review(已自检)

**1. Spec 覆盖(对照本计划 Goal/范围):**
- 个股字段保留 → Task 1(_RENAME 扩展)。✅
- `StockSnapshot`(frozen PIT,status 三态,缺失 None)→ Task 2。✅
- `CandidateUniverse`(按 code 索引 + by_status/by_min_boards/by_industry + __bool__)→ Task 3。✅
- `build_universe`(三池合成,涨停优先,缺列 None)→ Task 4。✅
- 防火墙复用(GuardedSource 未来拦截)→ Task 5。✅
- **明确不在本计划**:题材线/概念成分、L2/分时、评测/oracle(Phase-0d)、Agent(Phase-1)、MarketState 改动。

**2. Placeholder 扫描:** 无 TBD/TODO;每个改代码 step 均给完整代码 + 命令。✅

**3. 类型一致性:** `StockSnapshot` 字段在 Task 2 定义、Task 4 `_to_snapshot` 构造一致;`CandidateUniverse.from_stocks`/直接构造/查询方法在 Task 3 定义、Task 4 `build_universe` 与测试使用一致;`build_universe(source, day)` 签名在 Task 4 定义、Task 5 防火墙测试使用一致;`_RENAME` 英文列名(seal_amount/turnover_rate/...)在 Task 1 定义、Task 4 `_to_snapshot` 读取一致。✅

**4. 回归风险:** Task 1 只**新增** `_RENAME` 映射 + 扩展数值 coerce 列表 → Phase-0a 的 `test_source_normalize`(dedupe/空兜底)与 `test_loader_real_seeds` 不依赖这些新列,保持绿。新增 `youzi/universe/` 包不触碰已有模块。FakeSource(conftest)返回测试自带的英文列帧,与 `build_universe` 期望列一致。✅
