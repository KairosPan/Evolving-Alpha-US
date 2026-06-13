# FE-B 设计:研究驾驶舱全量(run-store + 三方对比/refine 时间线/trajectory)

> 日期:2026-06-08 · 分支 `feb-research-dashboard`(待建)· brainstorming 产出的设计冻结(spec)。下一步交 `writing-plans`。
>
> 先读:`youzi/loop/{compare,inner_loop}.py`(ComparisonReport/LoopReport/RefineEvent/BreakerEvent)· `youzi/refine/refiner.py`(RefineReport/AppliedEdit/RejectedEdit)· `youzi/eval/trajectory.py`(TrajectoryStep)· `youzi_web/`(FE-0 地基)· FE-0 spec。

---

## 0. 一句话

FE-0 给了 web 地基 + research/H 查看器。**FE-B 点亮 research 的另外 3 个子页**(三方对比 / refine 时间线 / trajectory)。前提:compare/eval 结果当前**临时打印、跑完即没** → 先做 **run-store**(把 `ComparisonReport` 落盘),再渲染。**一份 `ComparisonReport`(内嵌 `hch_loop_report`=LoopReport,含 trajectory/refine_events/breaker_events)驱动全部 3 视图**(已验证 JSON 完美往返)。

## 1. 已锁定决策(brainstorming,用户确认)

1. **一个切片全做**(run-store + 持久化 hook + sample_run + 3 视图)。
2. run-store 落 `youzi/loop/run_store.py`(与 ComparisonReport 同层,无循环依赖);存 `ComparisonReport` JSON。
3. **一份 ComparisonReport 驱动 3 视图**(arms→三方对比;hch_loop_report.refine_events→refine 时间线;hch_loop_report.trajectory+breaker_events→trajectory)。
4. `scripts/sample_run.py` 离线(MockLLM+FakeSource)造一个 run,让看板现在就有真东西看 + 当测试夹具。
5. 顶栏运行选择器选看哪次 run;无 run → 空态提示。

## 2. 不变量

1. **领域单向**:`youzi_web` 仍只读领域(经 data_access 读 run-store);`youzi/loop/run_store.py` 是领域层(smoke 脚本写、web 读)。
2. **离线优先**:sample_run 用 MockLLM+FakeSource(不触网);web 测试读 run-store 里的样本 JSON;真实 run 由 smoke_compare 跑完落盘。
3. **JSON 往返**:`ComparisonReport.model_dump(mode="json")` ↔ `model_validate`(已验证保 arms/mean_score/trajectory/refine_events)。
4. **FE-0 契约不破**:research 模块仍是一个 Feature;新增 3 路由 + 3 模板,subnav 3 占位项 `enabled=True`。

## 3. 模块布局

| 文件 | 动作 | 内容 |
|---|---|---|
| `youzi/loop/run_store.py` | **新增** | `RunStore`(save/list/load `ComparisonReport` JSON,原子写) |
| `scripts/sample_run.py` | **新增** | 离线 MockLLM+FakeSource 跑 compare → 存 run-store |
| `scripts/smoke_compare.py` | 改 | 跑完 `RunStore("runs").save(...)` 持久化 |
| `youzi_web/data_access.py` | 改 | `RUNS_DIR` + `list_runs()` + `load_run(run_id)` |
| `youzi_web/features/research/router.py` | 改 | 加 `/research/{compare,refine,trajectory}` 路由 |
| `youzi_web/features/research/__init__.py` | 改 | 3 个 subnav 项 `enabled=True` |
| `youzi_web/features/research/service.py` | 改 | 取 run + 选择器数据 |
| `youzi_web/features/research/templates/{compare,refine,trajectory}.html` | **新增** | 3 视图(extends base) |
| `tests/test_run_store.py`、`tests/test_web_research.py` | **新增** | run_store 往返 + 3 视图渲染/选择器/空态 |
| `.gitignore` | 改 | 加 `runs/` |

## 4. 接口与数据流(精确)

### 4.1 `youzi/loop/run_store.py`

```python
import json, os, tempfile
from pathlib import Path
from youzi.loop.compare import ComparisonReport

class RunStore:
    def __init__(self, root) -> None:
        self._root = Path(root)

    def _path(self, run_id: str) -> Path:
        return self._root / f"{run_id}.json"

    def save(self, run_id: str, report: ComparisonReport, meta: dict) -> str:
        self._root.mkdir(parents=True, exist_ok=True)
        payload = {"meta": {**meta, "run_id": run_id},
                   "report": report.model_dump(mode="json")}
        p = self._path(run_id)
        fd, tmp = tempfile.mkstemp(dir=self._root, suffix=".json.tmp"); os.close(fd)
        try:
            Path(tmp).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, p)            # 原子写
        except BaseException:
            try: os.unlink(tmp)
            except OSError: pass
            raise
        return run_id

    def list(self) -> list[dict]:
        if not self._root.exists():
            return []
        out = []
        for p in self._root.glob("*.json"):
            out.append(json.loads(p.read_text(encoding="utf-8"))["meta"])
        return sorted(out, key=lambda m: m["run_id"], reverse=True)   # 新→旧

    def load(self, run_id: str) -> tuple[ComparisonReport, dict]:
        d = json.loads(self._path(run_id).read_text(encoding="utf-8"))
        return ComparisonReport.model_validate(d["report"]), d["meta"]
```

### 4.2 持久化 hook

- **`smoke_compare.py`**:`main` 末尾(打印后)`RunStore(Path("runs")).save(run_id, rep, meta)`;`run_id = f"{start_ymd}_{end_ymd}_{scorer_kind}_{HHMMSS}"`(datetime 在脚本可用);`meta = {"window": f"{start}~{end}", "scorer": scorer_kind, "horizon": horizon, "temperature": temperature, "created": iso}`。打印"已存 run: <id>"。
- **`scripts/sample_run.py`**:离线——复用 `compare_harnesses(MockLLM 脚本, FakeSource)` 产 ComparisonReport(参 tests/test_compare 套路:种子 H + W 续板 + 一个 refine),`RunStore("runs").save("sample", rep, {"window":"sample(离线)","scorer":"pool","horizon":1,"created":...})`。打印路径。

### 4.3 `data_access.py`(读)

```python
RUNS_DIR = Path(__file__).resolve().parent.parent / "runs"

def _store() -> RunStore:
    return RunStore(RUNS_DIR)

def list_runs() -> list[dict]:           # [{run_id, window, scorer, ...}]  新→旧
    return _store().list()

def load_run(run_id: str):               # -> (ComparisonReport, meta) | (None, None)
    try:
        return _store().load(run_id)
    except FileNotFoundError:
        return None, None
```
- 视图直接消费 `ComparisonReport` 对象(pydantic,Jinja 属性访问):`report.arms[name]`、`report.hch_minus_hexpert_mean_score`、`report.hch_beats_hexpert`、`report.hch_loop_report.{refine_events,trajectory,breaker_events}`。**不另造视图 dict 层**(YAGNI)。

### 4.4 路由(`research/router.py`)+ 选择器

每个研究视图路由(以 compare 为例):
```python
@router.get("/research/compare")
def compare_page(request: Request, run: str | None = None):
    runs = list_runs()
    run_id = run or (runs[0]["run_id"] if runs else None)
    report, meta = load_run(run_id) if run_id else (None, None)
    return request.app.state.templates.TemplateResponse(
        request, "compare.html",
        {"request": request, "features": request.app.state.features,
         "active_feature_id": "research", "active_path": "/research/compare",
         "runs": runs, "run_id": run_id, "meta": meta, "report": report})
```
refine/trajectory 同形(active_path 各自;模板各自)。**选择器**:各视图 `{% block topbar %}` 渲染 `<select onchange="location.href='?run='+this.value">`(列 `runs`,选中 `run_id`)。**空态**:`report is None` → 模板显示"还没有运行结果;跑 `python scripts/sample_run.py` 或 `smoke_compare`"。

### 4.5 三视图模板(extends base.html)

- **compare.html**:固定序 `['HCH','Hexpert','Hmin_highest','Hmin_notrade']` 取 `report.arms[name]` → 表(name·候选 `report.n_candidates`·期望分 `report.mean_score`·命中率·被砸率;HCH 额外 `n_refines`/`n_breaker_trips`/`frozen_from`)+ Δ(`hch_minus_hexpert_*`)+ verdict(`hch_beats_hexpert` → ✅胜/❌未胜)。
- **refine.html**:`report.hch_loop_report.refine_events` 时序;每条 `ev.date` `ckpt=ev.checkpoint_version`;applied:`✓ {pass_kind}:{tool} → {target_id} «{rationale}»`(绿);rejected:`✗ {pass_kind}:{tool} → {target_id} 拒因:{reason}`(灰);notes 列出。无 refine → 提示。
- **trajectory.html**:`report.hch_loop_report.trajectory.steps` 每步 `step.date` + 市场摘要(`step.market.{max_board_height,limit_up_count,blowup_rate,sentiment_norm}`)+ 选股(`step.outcomes.values()` 的 `code/outcome/score`,scored=False 标"未评分")+ 末尾 `breaker_events`(date/reason/rolling/rolled_back_to)。

### 4.6 subnav 点亮(`research/__init__.py`)

3 个 `SubNavItem(..., enabled=False)` 改 `enabled=True`,path 对应 `/research/{compare,refine,trajectory}`。

## 5. 测试(全离线)

- `test_run_store.py`:① save→load 往返(用 4.2 的离线 compare 产 ComparisonReport,断言 arms/mean_score/refine_events 保)+ list 倒序;② 原子写不留 .tmp;③ load 不存在 → FileNotFoundError(data_access 兜成 None)。
- `test_web_research.py`(TestClient,先用 sample_run 或夹具往 RUNS_DIR 写一个 run):① /research/compare 渲染 4 路 + verdict;② /research/refine 渲染 applied/rejected;③ /research/trajectory 渲染步/选股;④ 运行选择器含 run_id;⑤ **空态**(空 RUNS_DIR)→ 3 视图都 200 + "还没有运行结果"。
- `test_web_data_access.py`(扩展):list_runs/load_run。
- 回归:既有 284 全绿(run-store/sample_run 纯新增;data_access/research 扩展不破 H 查看器)。
- **人工**:`python scripts/sample_run.py` 造样本 → `serve_web.py` 浏览器看三视图。

## 6. 验收标准(DoD)

1. `RunStore` 存/读/列 `ComparisonReport`(原子写);sample_run 离线造 run;smoke 持久化。
2. data_access list_runs/load_run;3 路由 + 3 模板渲染样本 run + 运行选择器 + 空态;subnav 点亮。
3. 领域单向、JSON 往返成立;FE-0 H 查看器不破。
4. 新测试 + 全量回归(284+新)绿;离线不触网。
5. subagent-driven 两段评审 + opus 终审通过。
6. 文档:更新 PROJECT_STATE/后续开发文档/memory(FE-B✅;⏭ FE-A)。

## 7. 显式 out-of-scope(后续)

- **从 UI 触发跑批**(在网页里跑 compare/capture)—— 跑批慢 + 需 LLM/数据,属 FE-A/"runs"功能。
- **FE-A 决策驾驶舱**(每日决策展示)。
- live 接线;run-store 清理/分页/搜索;trajectory 深钻(单步详情/逐技能信用/签名页);多 run 对比。
