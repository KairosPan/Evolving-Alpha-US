# FE-B:研究驾驶舱全量 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 点亮 research 的另外 3 个子页(三方对比/refine 时间线/trajectory)。先做 **run-store**(把 `ComparisonReport` 落盘,治"跑完即没")+ 离线 `sample_run` 造数,再 web 渲染。一份 `ComparisonReport` 驱动全部 3 视图。

**Architecture:** `youzi/loop/run_store.py`(领域层,save/list/load ComparisonReport JSON,原子写);`scripts/sample_run.py` 离线造 run + `smoke_compare` 跑完落盘;`youzi_web/data_access` 经 `YOUZI_RUNS_DIR`(默认 `runs/`)读;research 模块 3 路由/模板渲染 + 顶栏运行选择器。领域单向、FE-0 H 查看器不破。

**Tech Stack:** Python · FastAPI · Jinja2 · pytest(TestClient,离线)。

**分支:** `feb-research-dashboard`(执行时建)。**先读** spec:`docs/superpowers/specs/2026-06-08-feb-research-dashboard-design.md`。

**全量回归基线:** `.venv/bin/python -m pytest -q` 当前 **284 passed**。

**已验证**:`ComparisonReport.model_dump_json()` ↔ `model_validate_json()` 完美往返(arms/mean_score/hch_loop_report.trajectory+refine_events 全保)。离线 `compare_harnesses(MockLLM+FakeSource)` 产 2 refine_events + 3 步轨迹。

**Bundle:** A=Task 1-2(run-store + 持久化)· B=Task 3-4(data_access + 3 视图)。

---

## Bundle A

### Task 1: `youzi/loop/run_store.py`

**Files:**
- Create: `youzi/loop/run_store.py`
- Modify: `.gitignore`(加 `runs/`)
- Test: `tests/test_run_store.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_run_store.py
import tempfile
from pathlib import Path

from youzi.harness.snapshot import SnapshotStore
from youzi.loop.compare import compare_harnesses
from youzi.loop.inner_loop import LoopConfig
from youzi.loop.run_store import RunStore
from tests.test_compare import _w_src, _SeqFactory, _CountFactory, _PICK_W, _NO_TRADE
from tests.test_inner_loop import _seed_h


def make_report():
    src = _w_src()
    return compare_harnesses(
        _CountFactory(_seed_h), src, src.trading_calendar()[0], src.trading_calendar()[-1],
        agent_llm_factory=_SeqFactory([_PICK_W, _NO_TRADE]),
        refiner_llm_factory=_SeqFactory(['{"ops": []}']),
        store_factory=_CountFactory(lambda: SnapshotStore(tempfile.mkdtemp())),
        loop_config=LoopConfig(horizon=1))


def test_save_load_roundtrip(tmp_path):
    store = RunStore(tmp_path)
    rep = make_report()
    store.save("r1", rep, {"window": "w", "scorer": "pool"})
    got, meta = store.load("r1")
    assert set(got.arms) == {"HCH", "Hexpert", "Hmin_highest", "Hmin_notrade"}
    assert got.arms["HCH"].report.mean_score == rep.arms["HCH"].report.mean_score
    assert len(got.hch_loop_report.refine_events) == len(rep.hch_loop_report.refine_events)
    assert meta["run_id"] == "r1" and meta["window"] == "w"


def test_list_newest_first_and_atomic(tmp_path):
    store = RunStore(tmp_path)
    rep = make_report()
    store.save("aaa", rep, {"window": "1"})
    store.save("bbb", rep, {"window": "2"})
    ids = [m["run_id"] for m in store.list()]
    assert ids == ["bbb", "aaa"]                 # 新→旧(run_id 倒序)
    assert list(tmp_path.glob("*.tmp")) == []    # 原子写不留临时
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_run_store.py -q`
Expected: FAIL(`youzi.loop.run_store` 不存在)

- [ ] **Step 3: 实现 `youzi/loop/run_store.py`**

```python
# youzi/loop/run_store.py
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from youzi.loop.compare import ComparisonReport


class RunStore:
    """持久化 compare 运行结果(ComparisonReport JSON,原子写)。root/<run_id>.json = {meta, report}。"""

    def __init__(self, root) -> None:
        self._root = Path(root)

    def _path(self, run_id: str) -> Path:
        return self._root / f"{run_id}.json"

    def save(self, run_id: str, report: ComparisonReport, meta: dict) -> str:
        self._root.mkdir(parents=True, exist_ok=True)
        payload = {"meta": {**meta, "run_id": run_id},
                   "report": report.model_dump(mode="json")}
        fd, tmp = tempfile.mkstemp(dir=self._root, suffix=".json.tmp")
        os.close(fd)
        try:
            Path(tmp).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self._path(run_id))         # 原子写
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        return run_id

    def list(self) -> list[dict]:
        if not self._root.exists():
            return []
        metas = [json.loads(p.read_text(encoding="utf-8"))["meta"]
                 for p in self._root.glob("*.json")]
        return sorted(metas, key=lambda m: m["run_id"], reverse=True)   # 新→旧

    def load(self, run_id: str) -> tuple[ComparisonReport, dict]:
        d = json.loads(self._path(run_id).read_text(encoding="utf-8"))
        return ComparisonReport.model_validate(d["report"]), d["meta"]
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_run_store.py -q`
Expected: PASS(2 passed)

- [ ] **Step 5: `.gitignore` 加 `runs/`**(若无)

- [ ] **Step 6: 提交**

```bash
git add youzi/loop/run_store.py tests/test_run_store.py .gitignore
git commit -m "feat(loop): RunStore 持久化 ComparisonReport(save/list/load JSON,原子写)"
```

---

### Task 2: `sample_run.py` + smoke 持久化 hook

**Files:**
- Create: `scripts/sample_run.py`
- Modify: `scripts/smoke_compare.py`
- Test: `tests/test_run_store.py`(追加)

- [ ] **Step 1: 追加失败测试**

```python
def test_sample_run_writes_a_run(tmp_path, monkeypatch):
    monkeypatch.setenv("YOUZI_RUNS_DIR", str(tmp_path))
    import scripts.sample_run as sr
    sr.main()
    metas = RunStore(tmp_path).list()
    assert any(m["run_id"] == "sample" for m in metas)
    rep, _ = RunStore(tmp_path).load("sample")
    assert "HCH" in rep.arms
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_run_store.py::test_sample_run_writes_a_run -q`
Expected: FAIL(`scripts.sample_run` 不存在)

- [ ] **Step 3: 实现 `scripts/sample_run.py`**(复用 tests 的离线 compare 套路造夹具)

```python
# scripts/sample_run.py
"""离线造一个样本 run(MockLLM+FakeSource)存进 run-store,让研究看板有真东西看 + 当夹具。
Run: python scripts/sample_run.py   → runs/sample.json(或 YOUZI_RUNS_DIR)。不触网。"""
import os
import tempfile
from datetime import datetime
from pathlib import Path

from youzi.harness.snapshot import SnapshotStore
from youzi.loop.compare import compare_harnesses
from youzi.loop.inner_loop import LoopConfig
from youzi.loop.run_store import RunStore
from tests.test_compare import _w_src, _SeqFactory, _CountFactory, _PICK_W, _NO_TRADE
from tests.test_inner_loop import _seed_h


def main() -> None:
    src = _w_src()
    rep = compare_harnesses(
        _CountFactory(_seed_h), src, src.trading_calendar()[0], src.trading_calendar()[-1],
        agent_llm_factory=_SeqFactory([_PICK_W, _NO_TRADE]),
        refiner_llm_factory=_SeqFactory(['{"ops": []}']),
        store_factory=_CountFactory(lambda: SnapshotStore(tempfile.mkdtemp())),
        loop_config=LoopConfig(horizon=1))
    root = Path(os.environ.get("YOUZI_RUNS_DIR", "runs"))
    RunStore(root).save("sample", rep, {
        "window": "sample(离线)", "scorer": "pool", "horizon": 1,
        "created": datetime.now().isoformat(timespec="seconds")})
    print(f"已存 sample run → {root}/sample.json(HCH vs Hexpert,含 refine/trajectory)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: smoke 持久化 hook（改 `scripts/smoke_compare.py`）**

在 `main` 里 `rep = compare_harnesses(...)` 之后、打印之前(或末尾)插入持久化:

```python
    from youzi.loop.run_store import RunStore
    run_id = f"{start_ymd}_{end_ymd}_{scorer_kind}_{datetime.now().strftime('%H%M%S')}"
    RunStore(Path(os.environ.get("YOUZI_RUNS_DIR", "runs"))).save(run_id, rep, {
        "window": f"{start}~{end}", "scorer": scorer_kind, "horizon": horizon,
        "temperature": temperature, "created": datetime.now().isoformat(timespec="seconds")})
    print(f"[run-store] 已存 run: {run_id}")
```

(`os`、`datetime`、`Path` 已在 smoke_compare 顶部导入。)

- [ ] **Step 5: 跑测试确认通过 + 语法 + 回归**

Run: `.venv/bin/python -m pytest tests/test_run_store.py -q && .venv/bin/python -m py_compile scripts/sample_run.py scripts/smoke_compare.py`
Expected: PASS(3 passed)+ `syntax ok`

- [ ] **Step 6: 提交**

```bash
git add scripts/sample_run.py scripts/smoke_compare.py tests/test_run_store.py
git commit -m "feat(scripts): sample_run 离线造样本 run + smoke_compare 跑完持久化到 run-store"
```

---

## Bundle B

### Task 3: `data_access` 读 run-store

**Files:**
- Modify: `youzi_web/data_access.py`
- Test: `tests/test_web_data_access.py`(追加)

- [ ] **Step 1: 追加失败测试**

```python
def test_list_and_load_runs(tmp_path, monkeypatch):
    monkeypatch.setenv("YOUZI_RUNS_DIR", str(tmp_path))
    from youzi_web.data_access import list_runs, load_run
    from youzi.loop.run_store import RunStore
    from tests.test_run_store import make_report
    RunStore(tmp_path).save("sample", make_report(), {"window": "w", "scorer": "pool"})
    runs = list_runs()
    assert runs and runs[0]["run_id"] == "sample"
    rep, meta = load_run("sample")
    assert "HCH" in rep.arms and meta["window"] == "w"
    assert load_run("nope") == (None, None)       # 不存在 → (None, None)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_web_data_access.py::test_list_and_load_runs -q`
Expected: FAIL(`list_runs` 不存在)

- [ ] **Step 3: 扩展 `youzi_web/data_access.py`**(顶部加 import + 文件末尾加)

顶部加:`import os` + `from youzi.loop.run_store import RunStore`。文件末尾追加:

```python
def _runs_dir() -> Path:
    return Path(os.environ.get("YOUZI_RUNS_DIR",
                               str(Path(__file__).resolve().parent.parent / "runs")))


def list_runs() -> list[dict]:
    return RunStore(_runs_dir()).list()


def load_run(run_id: str):
    """-> (ComparisonReport, meta);不存在 → (None, None)。"""
    try:
        return RunStore(_runs_dir()).load(run_id)
    except FileNotFoundError:
        return None, None
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_web_data_access.py -q`
Expected: PASS(既有 3 + 新 1 = 4 passed)

- [ ] **Step 5: 提交**

```bash
git add youzi_web/data_access.py tests/test_web_data_access.py
git commit -m "feat(web): data_access 读 run-store(list_runs/load_run,YOUZI_RUNS_DIR 可覆盖)"
```

---

### Task 4: 3 研究视图(三方对比/refine/trajectory)+ 选择器 + 点亮 subnav

**Files:**
- Modify: `youzi_web/features/research/router.py`、`service.py`、`__init__.py`
- Create: `youzi_web/features/research/templates/{compare,refine,trajectory}.html`
- Test: `tests/test_web_research.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_web_research.py
from fastapi.testclient import TestClient

from youzi_web.app import create_app


def _seed_run(tmp_path, monkeypatch):
    monkeypatch.setenv("YOUZI_RUNS_DIR", str(tmp_path))
    from youzi.loop.run_store import RunStore
    from tests.test_run_store import make_report
    RunStore(tmp_path).save("sample", make_report(), {"window": "w", "scorer": "pool"})


def test_compare_view(tmp_path, monkeypatch):
    _seed_run(tmp_path, monkeypatch)
    r = TestClient(create_app()).get("/research/compare")
    assert r.status_code == 200
    assert "HCH" in r.text and "Hexpert" in r.text
    assert "胜" in r.text or "未胜" in r.text          # verdict
    assert "sample" in r.text                          # 运行选择器


def test_refine_and_trajectory_views(tmp_path, monkeypatch):
    _seed_run(tmp_path, monkeypatch)
    c = TestClient(create_app())
    assert c.get("/research/refine").status_code == 200
    t = c.get("/research/trajectory")
    assert t.status_code == 200 and "W" in t.text       # trajectory 含选股 W


def test_empty_state(tmp_path, monkeypatch):
    monkeypatch.setenv("YOUZI_RUNS_DIR", str(tmp_path))   # 空 runs 目录
    c = TestClient(create_app())
    for path in ("/research/compare", "/research/refine", "/research/trajectory"):
        r = c.get(path)
        assert r.status_code == 200 and "还没有运行结果" in r.text


def test_subnav_enabled():
    r = TestClient(create_app()).get("/research/harness")
    assert "/research/compare" in r.text                 # 子导航点亮(有 href)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_web_research.py -q`
Expected: FAIL(`/research/compare` 404)

- [ ] **Step 3: `research/service.py`(追加取 run + 选择器数据)**

```python
# 追加到 youzi_web/features/research/service.py
from youzi_web.data_access import list_runs, load_run


def run_context(run: str | None):
    runs = list_runs()
    run_id = run or (runs[0]["run_id"] if runs else None)
    report, meta = load_run(run_id) if run_id else (None, None)
    return {"runs": runs, "run_id": run_id, "meta": meta, "report": report}
```

- [ ] **Step 4: `research/router.py`(加 3 路由)**

```python
# 追加 import
from youzi_web.features.research.service import run_context


def _render(request, template, active_path, run):
    ctx = run_context(run)
    return request.app.state.templates.TemplateResponse(
        request, template,
        {"request": request, "features": request.app.state.features,
         "active_feature_id": "research", "active_path": active_path, **ctx})


@router.get("/research/compare")
def compare_page(request: Request, run: str | None = None):
    return _render(request, "compare.html", "/research/compare", run)


@router.get("/research/refine")
def refine_page(request: Request, run: str | None = None):
    return _render(request, "refine.html", "/research/refine", run)


@router.get("/research/trajectory")
def trajectory_page(request: Request, run: str | None = None):
    return _render(request, "trajectory.html", "/research/trajectory", run)
```

- [ ] **Step 5: 点亮 subnav(改 `research/__init__.py`)**

把 3 个 `SubNavItem(..., enabled=False)` 的 `enabled=False` 删掉(默认 True):

```python
    subnav=[
        SubNavItem("H 查看器", "/research/harness"),
        SubNavItem("三方对比", "/research/compare"),
        SubNavItem("refine 时间线", "/research/refine"),
        SubNavItem("trajectory", "/research/trajectory"),
    ],
```

- [ ] **Step 6: 三个模板**

`youzi_web/features/research/templates/compare.html`:

```html
{% extends "base.html" %}
{% block title %}三方对比{% endblock %}
{% block topbar %}<b>三方对比</b>
{% if runs %}<select onchange="location.href='?run='+this.value" style="margin-left:auto;">
  {% for m in runs %}<option value="{{ m.run_id }}" {% if m.run_id == run_id %}selected{% endif %}>{{ m.window }} · {{ m.scorer }}</option>{% endfor %}
</select>{% endif %}{% endblock %}
{% block content %}
{% if not report %}<div class="card">还没有运行结果。跑 <code>python scripts/sample_run.py</code> 或 <code>smoke_compare</code> 生成。</div>
{% else %}
<div class="label">{{ meta.window }} · scorer={{ meta.scorer }}</div>
<table class="data">
  <thead><tr><th>路</th><th>候选</th><th>期望分</th><th>命中率</th><th>被砸率</th><th>refine</th><th>熔断</th></tr></thead>
  <tbody>
  {% for name in ['HCH', 'Hexpert', 'Hmin_highest', 'Hmin_notrade'] %}
    {% set arm = report.arms[name] %}
    <tr><td>{{ name }}</td><td>{{ arm.report.n_candidates }}</td>
      <td>{{ '%+.4f' | format(arm.report.mean_score) }}</td>
      <td>{{ '%.3f' | format(arm.report.hit_rate) }}</td>
      <td>{{ '%.3f' | format(arm.report.nuke_rate) }}</td>
      <td>{{ arm.n_refines if arm.n_refines is not none else '—' }}</td>
      <td>{{ arm.n_breaker_trips if arm.n_breaker_trips is not none else '—' }}</td></tr>
  {% endfor %}
  </tbody>
</table>
<div class="card" style="margin-top:14px;">
  <b>HCH − Hexpert</b>　Δ期望分 {{ '%+.4f' | format(report.hch_minus_hexpert_mean_score) }}　Δ命中率 {{ '%+.4f' | format(report.hch_minus_hexpert_hit_rate) }}　Δ被砸率 {{ '%+.4f' | format(report.hch_minus_hexpert_nuke_rate) }}<br>
  verdict: {% if report.hch_beats_hexpert %}<span class="status-active">✅ HCH 胜 frozen</span>{% else %}<span class="status-retired">❌ HCH 未胜(持平/退化)</span>{% endif %}
</div>
{% endif %}
{% endblock %}
```

`youzi_web/features/research/templates/refine.html`:

```html
{% extends "base.html" %}
{% block title %}refine 时间线{% endblock %}
{% block topbar %}<b>refine 时间线</b>
{% if runs %}<select onchange="location.href='?run='+this.value" style="margin-left:auto;">
  {% for m in runs %}<option value="{{ m.run_id }}" {% if m.run_id == run_id %}selected{% endif %}>{{ m.window }} · {{ m.scorer }}</option>{% endfor %}
</select>{% endif %}{% endblock %}
{% block content %}
{% if not report %}<div class="card">还没有运行结果。跑 <code>python scripts/sample_run.py</code> 或 <code>smoke_compare</code> 生成。</div>
{% else %}
{% set lr = report.hch_loop_report %}
<div class="label">refine · {{ lr.refine_events | length }} 次</div>
{% if not lr.refine_events %}<div class="card">本次无 refine。</div>{% endif %}
{% for ev in lr.refine_events %}
<div class="card">
  <b>{{ ev.date }}</b> <span class="muted">ckpt={{ ev.checkpoint_version if ev.checkpoint_version is not none else '—' }}</span>
  {% for e in ev.report.applied %}<div class="status-active">✓ {{ e.pass_kind }}:{{ e.tool }} → {{ e.target_id }} «{{ e.rationale }}»</div>{% endfor %}
  {% for e in ev.report.rejected %}<div class="muted">✗ {{ e.pass_kind }}:{{ e.tool }} → {{ e.target_id }} 拒因:{{ e.reason }}</div>{% endfor %}
  {% if not ev.report.applied and not ev.report.rejected %}<div class="muted">（无编辑）</div>{% endif %}
  {% for n in ev.report.notes %}<div class="muted">· {{ n }}</div>{% endfor %}
</div>
{% endfor %}
{% endif %}
{% endblock %}
```

`youzi_web/features/research/templates/trajectory.html`:

```html
{% extends "base.html" %}
{% block title %}trajectory{% endblock %}
{% block topbar %}<b>trajectory</b>
{% if runs %}<select onchange="location.href='?run='+this.value" style="margin-left:auto;">
  {% for m in runs %}<option value="{{ m.run_id }}" {% if m.run_id == run_id %}selected{% endif %}>{{ m.window }} · {{ m.scorer }}</option>{% endfor %}
</select>{% endif %}{% endblock %}
{% block content %}
{% if not report %}<div class="card">还没有运行结果。跑 <code>python scripts/sample_run.py</code> 或 <code>smoke_compare</code> 生成。</div>
{% else %}
{% set lr = report.hch_loop_report %}
<div class="label">trajectory · {{ lr.trajectory.steps | length }} 步</div>
{% for s in lr.trajectory.steps %}
<div class="card">
  <b>{{ s.date }}</b> <span class="muted">最高板 {{ s.market.max_board_height }} · 涨停 {{ s.market.limit_up_count }} · 炸板率 {{ '%.2f' | format(s.market.blowup_rate) }}{% if s.market.sentiment_norm is not none %} · 情绪 {{ '%.2f' | format(s.market.sentiment_norm) }}{% endif %}{% if not s.scored %} · 未评分{% endif %}</span>
  {% for sc in s.outcomes.values() %}<div>{{ sc.code }} <span class="muted">{{ sc.pattern }}</span> → {{ sc.outcome }} ({{ '%+.3f' | format(sc.score) }})</div>{% endfor %}
  {% if s.scored and not s.outcomes %}<div class="muted">（空仓/无候选）</div>{% endif %}
</div>
{% endfor %}
{% if lr.breaker_events %}<div class="label" style="margin-top:14px;">熔断</div>
{% for be in lr.breaker_events %}<div class="card status-retired">{{ be.date }} {{ be.reason }} rolling={{ '%+.3f' | format(be.rolling) }} → rollback={{ be.rolled_back_to }}</div>{% endfor %}{% endif %}
{% endif %}
{% endblock %}
```

- [ ] **Step 7: 跑测试确认通过 + 全量回归**

Run: `.venv/bin/python -m pytest tests/test_web_research.py -q && .venv/bin/python -m pytest -q`
Expected: PASS(test_web_research 4 passed);全量 PASS(284 + 新增,目标 ≈292)

- [ ] **Step 8: 提交**

```bash
git add youzi_web/features/research tests/test_web_research.py
git commit -m "feat(web): research 3 视图(三方对比/refine时间线/trajectory)+ 运行选择器 + 点亮 subnav"
```

---

## 收尾(Task 4 之后,subagent-driven 终审前)

- [ ] 更新 `PROJECT_STATE.md`/`后续开发文档.md`(FE-B✅ 研究驾驶舱全量;⏭ FE-A 决策驾驶舱)+ memory。
- [ ] **(人工)** `python scripts/sample_run.py` 造样本 → `serve_web.py` → 浏览器看研究三视图(三方对比/refine/trajectory + 运行选择器)。

**FE 债务**:从 UI 触发跑批(FE-A);FE-A 决策驾驶舱;trajectory 深钻(单步/逐技能信用/签名);多 run 对比;run-store 清理/分页。

---

## Self-Review(写计划后自查,已执行)

**1. Spec coverage:** §4.1 RunStore → Task 1 ✅;§4.2 持久化(smoke+sample_run)→ Task 2;§4.3 data_access(list_runs/load_run,YOUZI_RUNS_DIR)→ Task 3;§4.4 路由+选择器+空态 → Task 4;§4.5 三模板(arm.report.*/refine_events/trajectory 字段)→ Task 4 Step 6;§4.6 点亮 subnav → Task 4 Step 5;§5 测试(往返/sample/data_access/三视图/选择器/空态/subnav)→ Task 1-4;§6 DoD + 回归 → Task 4 Step 7。

**2. Placeholder scan:** 无 TBD/TODO;每步完整代码 + 命令/预期。字段路径(`arm.report.{n_candidates,mean_score,hit_rate,nuke_rate}`、`arm.{n_refines,n_breaker_trips}`、`report.hch_minus_hexpert_*`、`report.hch_beats_hexpert`、`ev.report.applied[].{pass_kind,tool,target_id,rationale}`、`ev.report.rejected[].reason`、`s.market.{max_board_height,limit_up_count,blowup_rate,sentiment_norm}`、`s.outcomes[].{code,pattern,outcome,score}`、`be.{date,reason,rolling,rolled_back_to}`)均按真实模型 dump。

**3. Type consistency:** `RunStore(root).{save(run_id,report,meta),list(),load(run_id)}`、`list_runs()`/`load_run(run_id)→(report|None,meta|None)`、`run_context(run)`、`make_report()`(test 夹具)、`YOUZI_RUNS_DIR` env、模板上下文键(`runs/run_id/meta/report` + FE-0 的 `features/active_feature_id/active_path`)跨 Task 一致;ComparisonReport JSON 往返已验证;TemplateResponse 新签名(request, name, ctx)同 FE-0;research subnav path 与路由一致(/research/{compare,refine,trajectory})。
