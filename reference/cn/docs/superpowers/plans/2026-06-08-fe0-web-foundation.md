# FE-0:web 地基 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 起 `youzi_web/`(FastAPI+Jinja2+HTMX,纯 Python)web 地基:外壳 C(图标轨+子导航)+ 功能模块插槽(`Feature` 注册表)+ data_access(领域→视图)+ 首模块 `research`/H 查看器(读种子 H,离线),端到端验证"加功能=加模块"的扩展缝。**不碰 `youzi/`。**

**Architecture:** `youzi_web/`(sibling of `youzi/`,单向依赖领域)。`registry.Feature` 声明模块(id/label/icon/router/subnav);`features/__init__.FEATURES` 注册;`app.create_app()` 从注册表装 router + 自动出导航;`data_access` 把 `HarnessState.to_dict()` 转视图(算 hit_rate/nuke_rate);`research` 模块渲染 H 查看器。

**Tech Stack:** Python · FastAPI · Jinja2 · HTMX(CDN)· 手写 CSS · pytest(`TestClient`/httpx,离线)。

**分支:** `fe0-web-foundation`(执行时建)。**先读** spec:`docs/superpowers/specs/2026-06-08-fe0-web-foundation-design.md`。

**全量回归基线:** `.venv/bin/python -m pytest -q` 当前 **277 passed**。

**真实视图结构(已 dump 确认)**:`h.to_dict()` = `{skills:[{skill_id,name_cn,status,stats:{n,wins,nukes,expectancy,...},...}], memory:[{lesson_id,outcome,lesson,...}], doctrine:{entries:[{section,guidance,...}]}, cycle:{...}}`;种子 57 技能/21 记忆,stats 全 0/None。

**Bundle:** 单 bundle(Task 1-3)。

---

### Task 1: 依赖 + `registry.py` + `data_access.py`

**Files:**
- Create: `requirements-web.txt`、`youzi_web/__init__.py`、`youzi_web/registry.py`、`youzi_web/data_access.py`
- Test: `tests/test_web_data_access.py`

- [ ] **Step 1: 装依赖**

Run: `.venv/bin/pip install fastapi jinja2 uvicorn`
Expected: 成功(httpx 已装)。然后写 `requirements-web.txt`:

```
fastapi
jinja2
uvicorn
httpx
```

- [ ] **Step 2: 写失败测试**

```python
# tests/test_web_data_access.py
from youzi_web.data_access import harness_view, seed_harness


def test_seed_harness_view_structure():
    v = harness_view(seed_harness())
    assert {"skills", "memory", "doctrine"} <= set(v)
    assert len(v["skills"]) > 0 and "entries" in v["doctrine"]
    # 种子 stats n=0 → hit_rate/nuke_rate 为 None
    s0 = v["skills"][0]
    assert s0["stats"]["hit_rate"] is None and s0["stats"]["nuke_rate"] is None


def test_harness_view_computes_rates():
    h = seed_harness()
    sk = h.skills.all()[0]
    sk.stats.n = 8; sk.stats.wins = 4; sk.stats.nukes = 2
    v = harness_view(h)
    st = next(s for s in v["skills"] if s["skill_id"] == sk.skill_id)["stats"]
    assert st["hit_rate"] == 0.5 and st["nuke_rate"] == 0.25
```

- [ ] **Step 3: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_web_data_access.py -q`
Expected: FAIL(`ModuleNotFoundError: youzi_web`)

- [ ] **Step 4: 实现 `youzi_web/__init__.py`(空)+ `registry.py` + `data_access.py`**

```python
# youzi_web/__init__.py
```

```python
# youzi_web/registry.py
from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import APIRouter


@dataclass(frozen=True)
class SubNavItem:
    label: str
    path: str
    enabled: bool = True          # False → 灰显占位("以后"的子页)


@dataclass(frozen=True)
class Feature:
    id: str                       # "research"
    label: str                    # "研究"
    icon: str                     # "📊"
    router: APIRouter
    subnav: list[SubNavItem] = field(default_factory=list)
```

```python
# youzi_web/data_access.py
from __future__ import annotations

from pathlib import Path

from youzi.harness.harness import HarnessState
from youzi.harness.loader import load_seeds
from youzi.harness.snapshot import SnapshotStore

SEEDS_DIR = Path(__file__).resolve().parent.parent / "seeds"


def harness_view(h: HarnessState) -> dict:
    """领域 H → 视图 dict;补算 Skill 没有的 hit_rate/nuke_rate(=wins/n、nukes/n;n=0→None)。"""
    d = h.to_dict()
    for s in d["skills"]:
        st = s["stats"]
        n = st["n"]
        st["hit_rate"] = (st["wins"] / n) if n else None
        st["nuke_rate"] = (st["nukes"] / n) if n else None
    return d


def seed_harness() -> HarnessState:
    return load_seeds(SEEDS_DIR)


def snapshot_harness(store: SnapshotStore, version: int) -> HarnessState:
    h, _ = store.load(version)
    return h
```

- [ ] **Step 5: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_web_data_access.py -q`
Expected: PASS(2 passed)

- [ ] **Step 6: 提交**

```bash
git add requirements-web.txt youzi_web/__init__.py youzi_web/registry.py youzi_web/data_access.py tests/test_web_data_access.py
git commit -m "feat(web): youzi_web 地基——registry(Feature/SubNavItem)+ data_access(harness_view/seed_harness)+ 依赖"
```

---

### Task 2: app 外壳(`app.py` + `base.html` + `app.css`,空注册表可启动)

**Files:**
- Create: `youzi_web/app.py`、`youzi_web/templates/base.html`、`youzi_web/static/app.css`、`youzi_web/features/__init__.py`
- Test: `tests/test_web_app.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_web_app.py
from fastapi.testclient import TestClient

from youzi_web.app import create_app


def test_shell_boots():
    client = TestClient(create_app())
    r = client.get("/")
    assert r.status_code == 200
    assert "youzi" in r.text          # 外壳 chrome 渲染(图标轨 logo/标题)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_web_app.py -q`
Expected: FAIL(`youzi_web.app` 不存在)

- [ ] **Step 3: `youzi_web/features/__init__.py`(先空注册表)**

```python
# youzi_web/features/__init__.py
FEATURES = []          # Task 3 改为 [research_feature]
```

- [ ] **Step 4: `youzi_web/app.py`**

```python
# youzi_web/app.py
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import ChoiceLoader, Environment, FileSystemLoader, select_autoescape

WEB_DIR = Path(__file__).resolve().parent
APP_TEMPLATES = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"
FEATURES_DIR = WEB_DIR / "features"


def _make_templates() -> Jinja2Templates:
    dirs = [APP_TEMPLATES] + [p for p in FEATURES_DIR.glob("*/templates") if p.is_dir()]
    env = Environment(loader=ChoiceLoader([FileSystemLoader(str(d)) for d in dirs]),
                      autoescape=select_autoescape())
    return Jinja2Templates(env=env)


def create_app() -> FastAPI:
    from youzi_web.features import FEATURES
    app = FastAPI(title="youzi")
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.state.templates = _make_templates()
    app.state.features = FEATURES
    for f in FEATURES:
        app.include_router(f.router)

    @app.get("/")
    def home(request: Request):
        if FEATURES and FEATURES[0].subnav:
            return RedirectResponse(FEATURES[0].subnav[0].path)
        # 空注册表:渲染外壳 landing
        return app.state.templates.TemplateResponse(
            "base.html",
            {"request": request, "features": FEATURES,
             "active_feature_id": None, "active_path": None})

    return app


app = create_app()          # uvicorn youzi_web.app:app
```

- [ ] **Step 5: `youzi_web/templates/base.html`(外壳 C)**

```html
<!DOCTYPE html>
<html lang="zh">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>youzi · {% block title %}{% endblock %}</title>
  <link rel="stylesheet" href="/static/app.css">
  <script src="/static/htmx.min.js" defer></script>   <!-- 本地 vendor,无外链/无 SRI 顾虑、离线可用 -->

</head>
<body>
<div class="shell">
  <nav class="rail">
    <div class="rail-logo" title="youzi">⚡</div>
    {% for f in features %}
    <a class="rail-item {% if f.id == active_feature_id %}active{% endif %}"
       href="{{ f.subnav[0].path if f.subnav else '/' }}" title="{{ f.label }}">{{ f.icon }}</a>
    {% endfor %}
  </nav>
  {% set active = (features | selectattr('id', 'equalto', active_feature_id) | list | first) %}
  <aside class="subnav">
    <div class="subnav-title">{{ active.label if active else 'youzi' }}</div>
    {% if active %}
      {% for item in active.subnav %}
      <a class="subnav-item {% if item.path == active_path %}active{% endif %} {% if not item.enabled %}disabled{% endif %}"
         {% if item.enabled %}href="{{ item.path }}"{% endif %}>{{ item.label }}</a>
      {% endfor %}
    {% endif %}
  </aside>
  <main class="main">
    <header class="topbar">{% block topbar %}{% endblock %}</header>
    <div class="content">{% block content %}{% endblock %}</div>
  </main>
</div>
</body>
</html>
```

- [ ] **Step 6: `youzi_web/static/app.css`(外壳 C 深色风)**

```css
* { box-sizing: border-box; }
body { margin: 0; font-family: ui-sans-serif, system-ui, "PingFang SC", sans-serif; color: #1f2430; }
.shell { display: flex; height: 100vh; }
.rail { width: 48px; background: #0e0e16; color: #aab; display: flex; flex-direction: column;
        align-items: center; padding-top: 8px; gap: 4px; }
.rail-logo { font-size: 18px; margin-bottom: 10px; }
.rail-item { width: 38px; height: 36px; display: flex; align-items: center; justify-content: center;
             font-size: 18px; border-radius: 8px; text-decoration: none; color: #aab; }
.rail-item:hover { background: #1c1c2c; }
.rail-item.active { background: #2a2a3f; color: #fff; }
.subnav { width: 168px; background: #1a1a26; color: #cdd; padding: 14px 10px; }
.subnav-title { font-size: 11px; color: #889; text-transform: uppercase; letter-spacing: .6px; margin-bottom: 12px; }
.subnav-item { display: block; padding: 7px 9px; border-radius: 6px; color: #cdd; text-decoration: none; margin-bottom: 3px; font-size: 13px; }
.subnav-item:hover { background: #23233a; }
.subnav-item.active { background: #2a2a3f; color: #fff; }
.subnav-item.disabled { color: #667; pointer-events: none; }
.subnav-item.disabled::after { content: " ⁺"; color: #556; }
.main { flex: 1; display: flex; flex-direction: column; background: #f7f7fb; min-width: 0; }
.topbar { height: 44px; background: #fff; border-bottom: 1px solid #e6e6ef; display: flex;
          align-items: center; padding: 0 16px; gap: 10px; }
.content { flex: 1; overflow: auto; padding: 16px; }
.muted { color: #889; }
.label { font-size: 11px; color: #889; text-transform: uppercase; letter-spacing: .6px; margin: 4px 0 8px; }
table.data { width: 100%; border-collapse: collapse; font-size: 13px; background: #fff; border: 1px solid #e8e8f0; border-radius: 8px; overflow: hidden; }
table.data th { text-align: left; color: #889; font-weight: 600; padding: 7px 10px; border-bottom: 1px solid #ececf4; background: #fafafc; }
table.data td { padding: 7px 10px; border-bottom: 1px solid #f1f1f7; }
.status-active { color: #1f7a50; }
.status-incubating { color: #b8860b; }
.status-retired { color: #999; }
.cols { display: flex; gap: 14px; margin-top: 16px; align-items: flex-start; }
.cols > section { flex: 1; min-width: 0; }
.card { background: #fff; border: 1px solid #e8e8f0; border-radius: 8px; padding: 10px 12px; margin-bottom: 8px; font-size: 13px; line-height: 1.55; }
.card p { margin: 4px 0 0; color: #444; }
```

- [ ] **Step 6b: 本地 vendor htmx(去掉 CDN 外链,无 SRI 顾虑 + 离线)**

Run: `curl -sL https://cdn.jsdelivr.net/npm/htmx.org@2.0.3/dist/htmx.min.js -o youzi_web/static/htmx.min.js && wc -c youzi_web/static/htmx.min.js`
Expected: 下载 ~40-50KB 的 htmx.min.js。**非阻塞**:FE-0 页面纯服务端渲染、不依赖 JS,测试也不加载 JS;若 curl 失败,创建占位 `youzi_web/static/htmx.min.js`(内容 `/* htmx vendoring 待补 */`)让 `/static/` 路径存在,登记债务。

- [ ] **Step 7: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_web_app.py -q`
Expected: PASS(1 passed —— 空注册表外壳启动)

- [ ] **Step 8: 提交**

```bash
git add youzi_web/app.py youzi_web/templates/base.html youzi_web/static/ youzi_web/features/__init__.py tests/test_web_app.py
git commit -m "feat(web): app 外壳 C(create_app + base.html 图标轨/子导航 + app.css + 本地htmx),空注册表可启动"
```

---

### Task 3: `research` 模块(H 查看器)插进注册表 + 端到端

**Files:**
- Create: `youzi_web/features/research/__init__.py`、`router.py`、`service.py`、`templates/harness.html`、`scripts/serve_web.py`
- Modify: `youzi_web/features/__init__.py`(注册 research)
- Test: `tests/test_web_app.py`(追加)

- [ ] **Step 1: 追加失败测试**

```python
# tests/test_web_app.py 追加
def test_home_redirects_to_research():
    client = TestClient(create_app())
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert r.headers["location"] == "/research/harness"


def test_harness_page_renders_seed_h():
    client = TestClient(create_app())
    r = client.get("/research/harness")
    assert r.status_code == 200
    assert "命中率" in r.text and "纪律" in r.text and "记忆" in r.text
    assert "弱转强" in r.text              # 种子真实技能 name_cn(seeds 第一个)


def test_nav_shows_research_and_disabled_subitem():
    client = TestClient(create_app())
    r = client.get("/research/harness")
    assert "📊" in r.text                  # 图标轨有 research
    assert "refine 时间线" in r.text       # 子导航占位(disabled)渲染
    assert "disabled" in r.text            # 灰显占位类
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_web_app.py -q`
Expected: FAIL(home 落 landing 非 redirect / `/research/harness` 404)

- [ ] **Step 3: `youzi_web/features/research/service.py`**

```python
# youzi_web/features/research/service.py
from youzi_web.data_access import harness_view, seed_harness


def get_seed_harness_view() -> dict:
    return harness_view(seed_harness())
```

- [ ] **Step 4: `youzi_web/features/research/router.py`**

```python
# youzi_web/features/research/router.py
from fastapi import APIRouter, Request

from youzi_web.features.research.service import get_seed_harness_view

router = APIRouter()


@router.get("/research/harness")
def harness_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        "harness.html",
        {"request": request, "features": request.app.state.features,
         "active_feature_id": "research", "active_path": "/research/harness",
         "h": get_seed_harness_view()})
```

- [ ] **Step 5: `youzi_web/features/research/__init__.py`**

```python
# youzi_web/features/research/__init__.py
from youzi_web.registry import Feature, SubNavItem
from youzi_web.features.research.router import router

feature = Feature(
    id="research", label="研究", icon="📊", router=router,
    subnav=[
        SubNavItem("H 查看器", "/research/harness"),
        SubNavItem("refine 时间线", "/research/refine", enabled=False),
        SubNavItem("三方对比", "/research/compare", enabled=False),
        SubNavItem("trajectory", "/research/trajectory", enabled=False),
    ],
)
```

- [ ] **Step 6: 注册 research(改 `youzi_web/features/__init__.py`)**

```python
# youzi_web/features/__init__.py
from youzi_web.features.research import feature as research_feature

FEATURES = [research_feature]
```

- [ ] **Step 7: `youzi_web/features/research/templates/harness.html`**

```html
{% extends "base.html" %}
{% block title %}H 查看器{% endblock %}
{% block topbar %}<b>H 查看器</b> <span class="muted">· 种子 playbook</span>{% endblock %}
{% block content %}
<section>
  <div class="label">技能 Skills (p) · {{ h.skills | length }}</div>
  <table class="data">
    <thead><tr><th>技能</th><th>状态</th><th>n</th><th>命中率</th><th>期望</th><th>nukes</th></tr></thead>
    <tbody>
      {% for s in h.skills %}
      <tr>
        <td>{{ s.name_cn }}</td>
        <td class="status-{{ s.status }}">{{ s.status }}</td>
        <td>{{ s.stats.n }}</td>
        <td>{{ '%.2f' | format(s.stats.hit_rate) if s.stats.hit_rate is not none else '—' }}</td>
        <td>{{ '%+.3f' | format(s.stats.expectancy) if s.stats.expectancy is not none else '—' }}</td>
        <td>{{ s.stats.nukes }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</section>
<div class="cols">
  <section>
    <div class="label">纪律 Doctrine (K) · {{ h.doctrine.entries | length }}</div>
    {% for e in h.doctrine.entries %}
    <div class="card"><b>{{ e.section }}</b><p>{{ e.guidance }}</p></div>
    {% endfor %}
  </section>
  <section>
    <div class="label">记忆 Memory (M) · {{ h.memory | length }}</div>
    {% for m in h.memory %}
    <div class="card"><b>{{ m.lesson_id }}</b> <span class="muted">{{ m.outcome }}</span><p>{{ m.lesson }}</p></div>
    {% endfor %}
  </section>
</div>
{% endblock %}
```

- [ ] **Step 8: `scripts/serve_web.py`(便捷启动)**

```python
# scripts/serve_web.py
"""本地起 web:python scripts/serve_web.py  → http://127.0.0.1:8000(默认进 /research/harness)。"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("youzi_web.app:app", host="127.0.0.1", port=8000, reload=True)
```

- [ ] **Step 9: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_web_app.py -q`
Expected: PASS(4 passed:Task2 的 1 + 本任务 3)

- [ ] **Step 10: 语法检查 + 全量回归**

Run: `.venv/bin/python -m py_compile scripts/serve_web.py && .venv/bin/python -m pytest -q`
Expected: `syntax ok`;全量 PASS(277 + 新增,目标 ≈283)

- [ ] **Step 11: 提交**

```bash
git add youzi_web/features/research scripts/serve_web.py youzi_web/features/__init__.py tests/test_web_app.py
git commit -m "feat(web): research 模块 H 查看器(读种子H渲染技能/纪律/记忆)插进注册表 + serve_web"
```

---

## 收尾(Task 3 之后,subagent-driven 终审前)

- [ ] 更新 `PROJECT_STATE.md`/`后续开发文档.md`(FE 路线:FE-0✅ 地基+H查看器 / FE-B 研究全量 / FE-A 决策驾驶舱 / news / agents 模块)+ memory。
- [ ] **(人工可选)** `.venv/bin/python scripts/serve_web.py` → 浏览器开 http://127.0.0.1:8000 看真实 H 查看器。

**本阶段债务**:FE-B 需"运行结果持久化"run-store(compare/eval 当前临时打印);FE-A 决策驾驶舱(对 SnapshotSource+LLM 跑);live 接线;htmx 本地 vendoring(现 CDN);快照选择器。

---

## Self-Review(写计划后自查,已执行)

**1. Spec coverage:** §3 布局(youzi_web/ 结构)→ Task 1-3 ✅;§4.1 registry → Task 1;§4.2 注册表 → Task 2(空)+Task 3(research);§4.3 app.py 装配 → Task 2;§4.4 data_access → Task 1;§4.5 research/H查看器 → Task 3;§5 外壳 C(base.html+app.css)→ Task 2;§6 测试(TestClient:启动/导航/H查看器/harness_view)→ Task 1-3;§7 DoD + 回归 → Task 3 Step 10。

**2. Placeholder scan:** 无 TBD/TODO;每步完整代码 + 确切命令/预期。字段名(name_cn/status/stats.n/expectancy/nukes、doctrine.entries.{section,guidance}、memory.{lesson_id,outcome,lesson})均按 dump 出的真实结构。

**3. Type consistency:** `Feature(id,label,icon,router,subnav)`/`SubNavItem(label,path,enabled)`、`create_app()`/模块级 `app`、`harness_view`/`seed_harness`/`snapshot_harness`、`FEATURES`、模板上下文键(`features`/`active_feature_id`/`active_path`/`h`)跨 Task 一致;视图 dict 路径 `h.skills[].stats.hit_rate`、`h.doctrine.entries[].section`、`h.memory[].lesson` 与 data_access 输出 + 真实 dump 一致;Jinja `selectattr('id','equalto',...)`、`is not none`、`format` 用法正确;`tests/test_web_*.py` 用 `TestClient(create_app())`(httpx 已装)。
