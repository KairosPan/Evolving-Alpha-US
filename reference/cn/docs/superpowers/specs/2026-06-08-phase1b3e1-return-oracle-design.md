# Phase-1b-3e-1 设计:OHLCV 数据 + 前向收益 oracle(收益幅度信号,片 1/2)

> 日期:2026-06-08 · 分支 `phase-1b3e1-return-oracle`(待建)· 本文是 brainstorming 产出的设计冻结(spec),下一步交 `writing-plans`。
>
> 先读:`docs/findings/2026-06-06-real-data-hch-vs-hexpert.md`(为何要更细信号)· `PROJECT_STATE.md` §4(akshare `stock_zh_a_hist` qfq)· `youzi/eval/oracle.py`(现池成员制 oracle)· `youzi/data/source.py`(数据源)。

---

## 0. 一句话

现评测全靠**池成员制 oracle**(continued/faded/nuked,`SCORE∈{1,0,−1}`,horizon=1 单日),信号太粗——真实数据显示自精炼到 frozen 持平、学不到真东西。**A = 上收益幅度 oracle** 让信号更细。A 拆 2 片;**本 spec 只做片 1:OHLCV 取数 + 前向收益纯计算**(自包含、离线可测,不碰打分链路)。片 2(接入 `ScoredCandidate`/credit/eval/循环)另起。

## 1. 已锁定决策(brainstorming,用户确认)

1. **A 拆 2 片,先做片 1**(OHLCV 数据 + 收益 oracle,独立可测);片 2 = 接入(可配置 oracle,保留池成员制路径)。
2. **收益口径 = 次日开盘买 → t+N 收盘卖**:`(close@exit_day − open@entry_day) / open@entry_day`。
3. **N=2(默认,可配置)**:`entry_day=t+1`、`exit_day=t+N`,由**调用方(片 2)**按交易日历算;片 1 的 oracle **对天数无知**,只认 `(entry_day, exit_day)` 两个日期。

## 2. 不变量(沿用 `后续开发文档.md` §2)

1. **未来函数防火墙**:`ReturnOracle` 是**打分时刻**消费已实现数据的角色(同 `PoolRecord`)——决策日 t 永不取它;打分在游标到 t+N 时做,用 t+1..t+N 的已实现 OHLCV。`GuardedSource.daily_ohlcv` 守 `end ≤ as_of`(越界抛 `LookaheadError`)。片 1 不进打分循环、不碰 ≤t 决策路径。
2. **缺失值诚实 `None`**:停牌/退市/缺数/`open` 缺或 ≤0 → `forward_return` 返回 `None`,不臆造 0。
3. **离线可测**:`FakeSource.daily_ohlcv` + 构造 df,永不触网;真实 akshare 仅 smoke。
4. **代码约定**:照抄现有 `source.py` 列归一风格(中文列→英文,`pd.to_numeric(errors="coerce")`,缺列优雅默认)。

## 3. 模块布局

| 文件 | 动作 | 内容 |
|---|---|---|
| `youzi/data/source.py` | 加方法 | `MarketDataSource` 协议 + `AkshareSource` + `GuardedSource` 各加 `daily_ohlcv(code, start, end)` + `_normalize_ohlcv` 列归一 |
| `youzi/eval/return_oracle.py` | **新增** | `forward_return(ohlcv, entry_day, exit_day) -> float | None` · `ReturnOracle(source).score(code, entry_day, exit_day)` |
| `tests/conftest.py` | 加方法 | `FakeSource.daily_ohlcv`(从内存帧返回) |
| `tests/test_return_oracle.py` | **新增** | forward_return 边界 + ReturnOracle + GuardedSource 越界,全离线 |

## 4. 数据模型与接口(精确)

### 4.1 `source.py`:`daily_ohlcv`

```python
# 协议
class MarketDataSource(Protocol):
    ...
    def daily_ohlcv(self, code: str, start: Date, end: Date) -> pd.DataFrame: ...
    # 归一列:date(date 对象) / open / high / low / close / volume

_OHLCV_RENAME = {"日期": "date", "开盘": "open", "收盘": "close",
                 "最高": "high", "最低": "low", "成交量": "volume"}

def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """中文列→英文;date→date 对象;open/high/low/close/volume→数值。空→空带列 df。"""
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

# AkshareSource
def daily_ohlcv(self, code: str, start: Date, end: Date) -> pd.DataFrame:
    return _normalize_ohlcv(self._ak.stock_zh_a_hist(
        symbol=code, period="daily", start_date=_ymd(start), end_date=_ymd(end), adjust="qfq"))

# GuardedSource
def daily_ohlcv(self, code: str, start: Date, end: Date) -> pd.DataFrame:
    self._guard.check(end)                 # 打分时刻 as_of≥t+N 合法;越界(end>as_of)→ LookaheadError
    return self._inner.daily_ohlcv(code, start, end)
```

### 4.2 `eval/return_oracle.py`

```python
def forward_return(ohlcv: pd.DataFrame, entry_day: Date, exit_day: Date) -> float | None:
    """次日开盘买→t+N 收盘卖:(close@exit_day − open@entry_day) / open@entry_day。
    entry_day/exit_day 不在 ohlcv、open 缺/≤0、close 缺 → None(诚实缺失)。"""
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
    """前向收益 oracle(打分时刻用已实现 OHLCV)。"""
    def __init__(self, source) -> None:
        self._source = source

    def score(self, code: str, entry_day: Date, exit_day: Date) -> float | None:
        ohlcv = self._source.daily_ohlcv(code, entry_day, exit_day)
        return forward_return(ohlcv, entry_day, exit_day)
```

- `forward_return` 纯函数:只用传入 df,无副作用、不取数。`entry=open`、`exit=close` 口径固化(用户已定)。
- `ReturnOracle.score` 取 `[entry_day, exit_day]` 范围 OHLCV(经传入的 source;片 2 会传 `GuardedSource`,防火墙在 source 层保证)。

## 5. 关键边界

- **片 1 = 数据 + 纯计算**,不接入打分/信用/评测/循环(片 2)。
- **天数策略(t+1 / t+N / N=2)在片 2 的调用方**,oracle 只认两个日期 → oracle 可复用于任意进/出场日。
- `daily_ohlcv` 经 `GuardedSource` 守 `end≤as_of`;`ReturnOracle` 本身不取未来。

## 6. 防火墙论证(终审会查)

- `forward_return` 纯函数,只读传入 df,不取数、不持 source。
- `ReturnOracle.score` 经传入 source 取 `[entry_day, exit_day]`;片 2 传 `GuardedSource` 时 `guard.check(exit_day)` 保证 `exit_day≤as_of`——打分时刻 as_of 已推进到 t+N，合法；任何越界(请求 > as_of)抛 `LookaheadError`。决策日 t 不调用本 oracle。

## 7. 测试(全离线,FakeSource + 构造 df)

- `test_return_oracle.py`:
  - `forward_return`:① 正常(open=10 entry、close=12 exit → +0.20);② entry_day 不在 df → None;③ exit_day 不在 df → None;④ open=NaN → None;⑤ open=0 → None;⑥ 空 df → None;⑦ 负收益(open=10、close=8 → −0.20)。
  - `ReturnOracle.score`:FakeSource 内存 OHLCV,`score(code, entry, exit)` 取数+算正确;缺该 code → None。
  - `GuardedSource.daily_ohlcv`:`AsOfGuard(as_of)`,`end > as_of` → `LookaheadError`;`end ≤ as_of` → 正常返回归一 df。
  - `_normalize_ohlcv`:中文列→英文、date→date 对象、数值化、空 df→带列空。
- 回归:既有 246 测试全绿(只新增,不改既有打分路径)。

## 8. 验收标准(DoD)

1. `daily_ohlcv`(协议+Akshare+Guarded)+ `_normalize_ohlcv` 列归一;`forward_return`/`ReturnOracle` 按签名实现,缺失诚实 None。
2. `GuardedSource.daily_ohlcv` 守 `end≤as_of`(越界 LookaheadError)。
3. 防火墙 §6 论证成立(纯函数不取数、Guarded 守界)。
4. 新测试 + 全量回归绿;离线、不触网。
5. subagent-driven 两段评审 + opus 终审通过。
6. 文档:更新 `PROJECT_STATE.md`/`后续开发文档.md`(片 1 完成,片 2 待做)与 memory。

## 9. 显式 out-of-scope(片 2 及以后)

- **接入打分/信用/评测/循环**:`ScoredCandidate` 加收益字段(或 score 改收益)、`apply_credit` 用收益作 expectancy、`EvalReport.mean_score` = 平均收益、`WalkForwardEval`/`InnerLoop` 打分循环按 t+1/t+N 取收益(可配置 oracle,保留池成员制)。
- **fill-feasibility**(一字涨停次日买不进):进场假设 t+1 open 成交,涨停买不进的折算留债务。
- **成本/滑点**;**N 日池成员变体**;OHLCV 的复权口径细节/历史范围限制(同炸板池 30 日债务)。
