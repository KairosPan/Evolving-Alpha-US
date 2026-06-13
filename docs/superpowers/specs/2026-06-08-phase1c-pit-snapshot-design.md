# Phase-1c-PIT 设计:PIT 数据快照 + 离线打分(唤醒 PITStore + SnapshotSource + capture)

> 日期:2026-06-08 · 分支 `phase1c-pit-snapshot`(待建)· 本文是 brainstorming 产出的设计冻结(spec),下一步交 `writing-plans`。
>
> 先读:`docs/findings/2026-06-06-real-data-hch-vs-hexpert.md` §10(为何要 PIT)· `youzi/data/cache.py`(已有休眠 `PITStore`)· `youzi/data/source.py`(`MarketDataSource` 协议 + `AkshareSource`/`GuardedSource`/`_retry_ak`)· `scripts/smoke_compare.py`(`_MemoizedSource` + source 接线)。

---

## 0. 一句话

真实收益跑被 akshare 限流挡住(逐候选 OHLCV 吞吐撞墙,findings §10)。**唤醒已有但从未接线的 `PITStore`**:扩展它存 OHLCV+日历,加 `SnapshotSource`(实现 `MarketDataSource` 协议、离线零 akshare)+ `capture_window`(一次性节流预取 akshare→store)。于是**一次慢速 capture 建库,之后离线无限次跑收益对比**(akshare 出局,只剩有 retry 的 DeepSeek),防火墙原样保留(SnapshotSource 仍被 GuardedSource 套)。

## 1. 已锁定决策(brainstorming,用户确认)

1. **一个切片全做**(PITStore 扩展 + SnapshotSource + capture_window + runner 接线)。
2. **SnapshotSource 缺数语义**:**池(zt/prev/blowup/dt)某 (kind,day) 缺 → 报错 `SnapshotMissingError`**(不完整快照大声抓住;缺池日 ≠ 当天无涨停,防静默误判 no-trade);**某 code 的 OHLCV 缺 → 返空带列 df**(停牌/退市本就无 OHLCV → ReturnScorer 丢弃该候选)。
3. **OHLCV 布局** = per-code 单 parquet `root/ohlcv/{code}.parquet`(存捕获到的全历史,SnapshotSource 按 [start,end] 切片)。

## 2. 不变量

1. **未来函数防火墙原样**:`SnapshotSource` 是又一个 `MarketDataSource`,eval 时仍被 `GuardedSource` 套(`guard.check(day/end)` 先于读)。capture 是**一次性建库(非 eval)**,取全量无防火墙问题——防火墙只在 eval 读取时生效。
2. **PIT 语义**:池用 akshare `date=` 取(当日 as-of);**写入即视为该日快照,不被未来修订覆盖**(PITStore 既有契约;capture 幂等 `has` 跳过)。
3. **date 列 dtype 稳健**:parquet 往返可能把 date 列变 datetime64;**SnapshotSource 读 OHLCV/日历时把 date 列归一回 `date` 对象**(否则 `forward_return` 的 `== entry_day` 失配)。
4. **离线可测**:全程 `FakeSource`(含 OHLCV)→ PITStore → SnapshotSource 往返,**capture 测试也用 FakeSource 替身**,永不触网。
5. **代码零改于打分链路**:scorer/credit/loop/compare 消费 `MarketDataSource` 不变,只换注入的 source。

## 3. 模块布局

| 文件 | 动作 | 内容 |
|---|---|---|
| `youzi/data/cache.py` | 扩展 `PITStore` | `put_ohlcv/get_ohlcv/has_ohlcv(code)` + `put_calendar/get_calendar()` |
| `youzi/data/snapshot_source.py` | **新增** | `SnapshotSource`(实现 6 方法)+ `SnapshotMissingError` |
| `youzi/data/capture.py` | **新增** | `capture_window(ak_source, store, start, end, *, throttle, sleep) -> CaptureSummary` |
| `scripts/capture_window.py` | **新增** | CLI:`AkshareSource → capture_window → PITStore(out_dir)` |
| `scripts/smoke_compare.py` | 改 | env `YOUZI_SNAPSHOT=<dir>` → `SnapshotSource(PITStore(dir))` 替代 `_MemoizedSource(AkshareSource())` |
| `tests/test_cache.py` | 扩展 | OHLCV/calendar 往返 |
| `tests/test_snapshot_source.py` | **新增** | 协议 + 缺数(池报错/OHLCV 返空)+ date 归一 |
| `tests/test_capture.py` | **新增** | FakeSource→store 全落 + 幂等 + blowup 容错 |

## 4. 数据模型与接口(精确)

### 4.1 `cache.py`:`PITStore` 扩展(沿用现有 parquet 路子)

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

_CAL = "calendar.parquet"

def put_calendar(self, days: list[Date]) -> None:
    self._root.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"date": [d.isoformat() for d in days]}).to_parquet(self._root / _CAL, index=False)

def get_calendar(self) -> list[Date] | None:
    p = self._root / _CAL
    if not p.exists():
        return None
    return [pd.to_datetime(s).date() for s in pd.read_parquet(p)["date"]]
```

### 4.2 `snapshot_source.py`:`SnapshotSource`

```python
class SnapshotMissingError(RuntimeError):
    """快照缺池数据(不完整 capture)——大声失败,别静默当 no-trade。"""

_EMPTY_OHLCV = ["date", "open", "high", "low", "close", "volume"]

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

    def zt_pool(self, day): return self._pool("zt", day)
    def zt_pool_previous(self, day): return self._pool("prev", day)
    def zt_pool_blowup(self, day): return self._pool("blowup", day)
    def dt_pool(self, day): return self._pool("dt", day)

    def daily_ohlcv(self, code: str, start: Date, end: Date) -> pd.DataFrame:
        df = self._store.get_ohlcv(code)
        if df is None or df.empty:
            return pd.DataFrame(columns=_EMPTY_OHLCV)     # 停牌/退市/未捕获 → 空(ReturnScorer 丢弃)
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"]).dt.date   # 归一回 date 对象(parquet 往返稳健)
        return df[(df["date"] >= start) & (df["date"] <= end)]
```
- **kind 串** `zt/prev/blowup/dt` 与 capture 一致(内部约定;沿用 smoke `_MemoizedSource` 命名)。

### 4.3 `capture.py`:`capture_window`

```python
@dataclass(frozen=True)
class CaptureSummary:
    n_days: int
    n_codes: int
    n_calls: int

_POOLS = [("zt", "zt_pool"), ("prev", "zt_pool_previous"),
          ("blowup", "zt_pool_blowup"), ("dt", "dt_pool")]

def capture_window(ak_source, store: PITStore, start: Date, end: Date,
                   *, throttle: float = 0.3, sleep=None) -> CaptureSummary:
    """一次性把窗口内 4 池(每日)+ universe 各 code 的 OHLCV + 日历 预取进 PITStore。
    幂等(has 跳过);blowup 超 30 日 ValueError → 存空;唯一碰 akshare 的部分。"""
    import time as _t
    slp = sleep if sleep is not None else _t.sleep
    calls = 0
    cal = ak_source.trading_calendar(); calls += 1
    store.put_calendar(cal)
    window = [d for d in cal if start <= d <= end]
    codes: set[str] = set()
    for day in window:
        for kind, fname in _POOLS:
            if not store.has(kind, day):
                try:
                    df = getattr(ak_source, fname)(day)
                except ValueError:                 # blowup 30 日限制等确定性错 → 存空帧
                    df = pd.DataFrame(columns=["code"])
                store.put(kind, day, df); calls += 1; slp(throttle)
            df = store.get(kind, day)
            if df is not None and "code" in df.columns:
                codes.update(str(c) for c in df["code"])
    for code in sorted(codes):
        if not store.has_ohlcv(code):
            store.put_ohlcv(code, ak_source.daily_ohlcv(code, start, end)); calls += 1; slp(throttle)
    return CaptureSummary(n_days=len(window), n_codes=len(codes), n_calls=calls)
```
- universe = **全 4 池 code 并集**(pickable 候选的超集,安全)。`_retry_ak`(已在 AkshareSource 内)+ `throttle` 双保险防限流。

### 4.4 runner 接线

- `scripts/capture_window.py <start_ymd> <end_ymd> <out_dir>`:`capture_window(AkshareSource(), PITStore(out_dir), start, end)`,打印 summary。**跑一次,慢、节流。**
- `scripts/smoke_compare.py`:`main` 开头读 `snap = os.environ.get("YOUZI_SNAPSHOT")`;`src = SnapshotSource(PITStore(Path(snap)))` if snap else `_MemoizedSource(AkshareSource())`。其余不变。于是 `YOUZI_SNAPSHOT=snap DEEPSEEK_API_KEY=... python scripts/smoke_compare.py <s> <e> 2 0.0 return` **离线跑收益对比**。

## 5. 关键边界

- **capture 只读 akshare、只写 store**;**SnapshotSource 只读 store**;两者经 PITStore 解耦,各自单测。
- **缺数**:池缺=报错(抓不完整 capture);OHLCV 缺=空(停牌正常)。
- **date 归一**在 SnapshotSource 读侧(forward_return 的 `== entry_day` 才成立)。
- 防火墙、打分链路**零改**。

## 6. 防火墙论证(终审会查)

- SnapshotSource 是纯读 store 的 MarketDataSource;eval 用 `GuardedSource(SnapshotSource)`,`guard.check` 仍先于每次读 → ≤as_of 不变。
- capture 在 eval 之外一次性建库,无 ≤t 决策路径;OHLCV/池都是事后落盘的已实现数据,经防火墙在 eval 读取时受 as_of 约束。

## 7. 测试(全离线)

- `test_cache.py`(扩展):`put_ohlcv/get_ohlcv/has_ohlcv` 往返 + 缺返 None;`put_calendar/get_calendar` 往返(date 对象)+ 缺返 None。
- `test_snapshot_source.py`:① 池往返(put→SnapshotSource 读);② 池缺 → `SnapshotMissingError`;③ OHLCV 往返 + 按 [start,end] 切片 + date 列是 date 对象(`forward_return` 可用);④ OHLCV 缺 code → 空带列;⑤ calendar 缺 → 报错。
- `test_capture.py`:FakeSource(4 池 + OHLCV + calendar)→ `capture_window` → 断言 store 落齐(池每日、universe 各 code OHLCV、calendar);幂等(再跑 calls 不增取数,用注入 sleep 计数或 has 验证);blowup 抛 ValueError → 存空帧不崩;`sleep` 注入(不真睡)。
- **端到端**:capture(FakeSource)→ `SnapshotSource` → `compare_harnesses(..., scorer=ReturnScorer())` 跑通,mean_score=平均收益(复用 1b-3e-2 的真实种子/Mock 套路,全离线)。
- 回归:既有 265 全绿。
- **人工(收尾)**:`python scripts/capture_window.py <s> <e> snap` 建库一次,再 `YOUZI_SNAPSHOT=snap ... smoke_compare <s> <e> 2 0.0 return` 离线跑真实收益对比,记 findings。

## 8. 验收标准(DoD)

1. PITStore 扩展(OHLCV/calendar)+ SnapshotSource(协议 + 缺数语义 + date 归一)+ capture_window(幂等 + blowup 容错 + throttle/sleep 注入)实现。
2. runner:capture_window 脚本 + smoke `YOUZI_SNAPSHOT` 分支。
3. 防火墙 §6 成立(SnapshotSource 经 GuardedSource)。
4. 新测试 + 端到端离线收益对比 + 全量回归绿;离线不触网。
5. subagent-driven 两段评审 + opus 终审通过。
6. 文档:更新 PROJECT_STATE/后续开发文档/memory;**人工建库 + 离线跑真实收益对比记 findings**。

## 9. 显式 out-of-scope(债务)

- OHLCV qfq **事后除权修订**的 PIT 精化(当前=捕获时点);**LLM 响应缓存**(本切片只治 akshare,DeepSeek 仍 live);快照**增量/过期刷新**与完整性 `verify`;**幸存者偏差**根治;熔断 **scorer-aware 重标定**(承 1b-3e-2 债务)。
