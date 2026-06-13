# FE-A:决策驾驶舱 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 点亮 `decision` 模块(🎯)的**决策驾驶舱**:选某次 run 某天 → 离线渲染那天 TrajectoryStep 的完整决策(市场态面板 + 排序候选卡[理由/置信/join技能的计划/结果])。复用 run-store,零依赖 akshare/LLM。

**Architecture:** 新 `youzi_web/features/decision/` 模块(Feature 进 FEATURES,外壳零改);`cockpit_context` 取 run+步 + 逐候选 enrich(`skill_plan` 经 `resolve_skill` 折种子 H 取计划,join 不到降级;outcome 取 `step.outcomes`)。领域单向只读、`youzi/` 零改。

**Tech Stack:** Python · FastAPI · Jinja2 · pytest(TestClient,离线)。

**分支:** `fea-decision-cockpit`(执行时建)。**先读** spec:`docs/superpowers/specs/2026-06-08-fea-decision-cockpit-design.md`。

**全量回归基线:** `.venv/bin/python -m pytest -q` 当前 **294 passed**。

**已验证**:`resolve_skill(pattern, harness)→Skill|None`(skill_id→name_cn→None);真实技能名(如种子 `name_cn`)可解析出 trigger/entry/exit_stop/taboo;样本 run 的 pattern "龙头接力" → None(降级)。Candidate=`{code,name,pattern,reason,confidence}`;TrajectoryStep=`{date,market,decision,outcomes}`;MarketState.echelon=`[{height,count,representatives}]`。

**Bundle:** 单 bundle(Task 1-2)。

---

### Task 1: `data_access.skill_plan` + `decision/service.cockpit_context`

**Files:**
- Modify: `youzi_web/data_access.py`
- Create: `youzi_web/features/decision/__init__.py`(空,占位包)、`youzi_web/features/decision/service.py`
- Test: `tests/test_web_decision.py`

> 注:`decision/__init__.py` 本任务先建**空文件**(让 service 可 import);Task 2 再填 `feature = Feature(...)`。避免 Task 1 引入 router 未建的循环。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_web_decision.py
def test_skill_plan_resolves_and_degrades():
    from youzi_web.data_access import skill_plan, seed_harness
    h = seed_harness()
    name = h.skills.all()[0].name_cn
    plan = skill_plan(name, h)
    assert plan is not None and "trigger" in plan and "taboo" in plan
    assert skill_plan("不存在的模式xyz", h) is None         # join 不到 → None


def test_cockpit_context_enriches(tmp_path, monkeypatch):
    monkeypatch.setenv("YOUZI_RUNS_DIR", str(tmp_path))
    from youzi.loop.run_store import RunStore
    from tests.test_run_store import make_report
    RunStore(tmp_path).save("sample", make_report(), {"window": "w", "scorer": "pool"})
    from youzi_web.features.decision.service import cockpit_context
    ctx = cockpit_context(None, None)
    assert ctx["run_id"] == "sample" and ctx["step"] is not None
    assert ctx["days"]                                       # 有日期可选
    assert ctx["candidates"] and "cand" in ctx["candidates"][0]   # 候选 enrich(cand/plan/outcome)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_web_decision.py -q`
Expected: FAIL(`skill_plan` / `youzi_web.features.decision.service` 不存在)

- [ ] **Step 3: `data_access.py` 加 `skill_plan`**(顶部 import + 末尾函数)

顶部加:`from youzi.refine.credit import resolve_skill`。末尾追加:

```python
def skill_plan(pattern: str, harness) -> dict | None:
    """候选 pattern → 种子技能的"计划"。join 不到 → None(模板降级)。"""
    sk = resolve_skill(pattern, harness)
    if sk is None:
        return None
    return {"name_cn": sk.name_cn, "trigger": sk.trigger, "entry": sk.entry,
            "exit_stop": sk.exit_stop, "taboo": list(sk.taboo)}
```

- [ ] **Step 4: 建空 `youzi_web/features/decision/__init__.py`**(本任务空文件;Task 2 填 feature)

```python
# youzi_web/features/decision/__init__.py
```

- [ ] **Step 5: `youzi_web/features/decision/service.py`**

```python
# youzi_web/features/decision/service.py
from youzi_web.data_access import list_runs, load_run, seed_harness, skill_plan


def cockpit_context(run: str | None, day: str | None) -> dict:
    runs = list_runs()
    run_id = run or (runs[0]["run_id"] if runs else None)
    report, meta = load_run(run_id) if run_id else (None, None)
    lr = report.hch_loop_report if report else None
    steps = lr.trajectory.steps if lr else []
    days = [s.date.isoformat() for s in steps]
    idx = next((i for i, s in enumerate(steps) if s.date.isoformat() == day), 0) if day else 0
    step = steps[idx] if steps else None
    cands = []
    if step is not None:
        h = seed_harness()
        for c in step.decision.candidates:
            cands.append({"cand": c, "plan": skill_plan(c.pattern, h),
                          "outcome": step.outcomes.get(c.code)})
    return {"runs": runs, "run_id": run_id, "meta": meta, "days": days,
            "day": (step.date.isoformat() if step else None), "step": step, "candidates": cands}
```

- [ ] **Step 6: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_web_decision.py -q`
Expected: PASS(2 passed)

- [ ] **Step 7: 提交**

```bash
git add youzi_web/data_access.py youzi_web/features/decision/__init__.py youzi_web/features/decision/service.py tests/test_web_decision.py
git commit -m "feat(web): data_access.skill_plan(join技能计划)+ decision.cockpit_context(取run+步,逐候选enrich)"
```

---

### Task 2: `decision` 模块(cockpit 路由/模板)进 FEATURES

**Files:**
- Create: `youzi_web/features/decision/router.py`、`youzi_web/features/decision/templates/cockpit.html`
- Modify: `youzi_web/features/decision/__init__.py`(填 feature)、`youzi_web/features/__init__.py`(注册)
- Test: `tests/test_web_decision.py`(追加)

- [ ] **Step 1: 追加失败测试**

```python
from fastapi.testclient import TestClient
from youzi_web.app import create_app


def _seed(tmp_path, monkeypatch):
    monkeypatch.setenv("YOUZI_RUNS_DIR", str(tmp_path))
    from youzi.loop.run_store import RunStore
    from tests.test_run_store import make_report
    RunStore(tmp_path).save("sample", make_report(), {"window": "w", "scorer": "pool"})


def test_cockpit_renders_market_and_candidate(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    r = TestClient(create_app()).get("/decision/cockpit")
    assert r.status_code == 200
    assert "连板梯队" in r.text and "最高板" in r.text       # 市场态面板
    assert "赢家" in r.text                                   # 样本候选 W/赢家
    assert "sample" in r.text                                 # 运行选择器


def test_cockpit_empty_state(tmp_path, monkeypatch):
    monkeypatch.setenv("YOUZI_RUNS_DIR", str(tmp_path))       # 空 runs
    r = TestClient(create_app()).get("/decision/cockpit")
    assert r.status_code == 200 and "还没有运行结果" in r.text


def test_decision_in_nav_and_fe0_fe_b_intact(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    c = TestClient(create_app())
    assert "🎯" in c.get("/decision/cockpit").text             # 图标轨有 decision
    assert c.get("/research/harness").status_code == 200       # FE-0 不破
    assert c.get("/research/compare").status_code == 200       # FE-B 不破
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_web_decision.py -q`
Expected: FAIL(`/decision/cockpit` 404)

- [ ] **Step 3: `youzi_web/features/decision/router.py`**

```python
# youzi_web/features/decision/router.py
from fastapi import APIRouter, Request

from youzi_web.features.decision.service import cockpit_context

router = APIRouter()


@router.get("/decision/cockpit")
def cockpit_page(request: Request, run: str | None = None, day: str | None = None):
    ctx = cockpit_context(run, day)
    return request.app.state.templates.TemplateResponse(
        request, "cockpit.html",
        {"request": request, "features": request.app.state.features,
         "active_feature_id": "decision", "active_path": "/decision/cockpit", **ctx})
```

- [ ] **Step 4: 填 `youzi_web/features/decision/__init__.py`**

```python
# youzi_web/features/decision/__init__.py
from youzi_web.registry import Feature, SubNavItem
from youzi_web.features.decision.router import router

feature = Feature(id="decision", label="决策", icon="🎯", router=router,
                  subnav=[SubNavItem("决策驾驶舱", "/decision/cockpit")])
```

- [ ] **Step 5: 注册(改 `youzi_web/features/__init__.py`)**

```python
# youzi_web/features/__init__.py
from youzi_web.features.research import feature as research_feature
from youzi_web.features.decision import feature as decision_feature

FEATURES = [research_feature, decision_feature]
```

- [ ] **Step 6: `youzi_web/features/decision/templates/cockpit.html`**

```html
{% extends "base.html" %}
{% block title %}决策驾驶舱{% endblock %}
{% block topbar %}<b>🎯 决策驾驶舱</b>
{% if runs %}<span style="margin-left:auto;">run
<select onchange="location.href='?run='+this.value">
  {% for m in runs %}<option value="{{ m.run_id }}" {% if m.run_id == run_id %}selected{% endif %}>{{ m.window }} · {{ m.scorer }}</option>{% endfor %}
</select></span>
{% endif %}
{% if days %}<span>日期
<select onchange="location.href='?run={{ run_id }}&day='+this.value">
  {% for d in days %}<option value="{{ d }}" {% if d == day %}selected{% endif %}>{{ d }}</option>{% endfor %}
</select></span>{% endif %}{% endblock %}
{% block content %}
{% if not step %}<div class="card">还没有运行结果。跑 <code>python scripts/sample_run.py</code> 或 <code>smoke_compare</code> 生成。</div>
{% else %}
<div class="label">盘面 · 市场态</div>
<div class="card">
  最高板 <b>{{ step.market.max_board_height }}</b>　涨停 <b>{{ step.market.limit_up_count }}</b>　炸板 <b>{{ step.market.blowup_count }}</b> <span class="muted">({{ '%.1f' | format(step.market.blowup_rate * 100) }}%)</span>　跌停 <b>{{ step.market.limit_down_count }}</b>　情绪 <b>{{ '%.2f' | format(step.market.sentiment_norm) if step.market.sentiment_norm is not none else '%.2f' | format(step.market.sentiment_raw) }}</b>　赚钱效应 <b>{{ '%+.1f' | format(step.market.money_effect_raw) }}%</b>
  {% if step.market.echelon %}<div style="margin-top:6px;"><span class="muted">连板梯队</span>
    {% for r in step.market.echelon %}<span style="background:#fff3e0; border-radius:4px; padding:2px 8px; margin-right:6px;">{{ r.height }}板×{{ r.count }}{% if r.representatives %} <span class="muted">{{ r.representatives | join('/') }}</span>{% endif %}</span>{% endfor %}
  </div>{% endif %}
</div>

<div class="label" style="margin-top:14px;">决策 · {% if step.decision.candidates %}排序候选 {{ step.decision.candidates | length }}{% else %}空仓{% endif %}</div>
{% if not step.decision.candidates %}
<div class="card"><b>空仓</b>{% if step.decision.no_trade_reason %} <span class="muted">— {{ step.decision.no_trade_reason }}</span>{% endif %}</div>
{% else %}
{% for it in candidates %}
<div class="card" style="border-left:3px solid {% if it.outcome and it.outcome.outcome == 'continued' %}#1f7a50{% elif it.outcome and it.outcome.outcome == 'nuked' %}#b22{% else %}#ccc{% endif %};">
  <div style="display:flex; align-items:baseline; gap:8px;">
    <span class="muted">#{{ loop.index }}</span>
    <b>{{ it.cand.name or it.cand.code }}</b> <span class="muted">{{ it.cand.code }}</span>
    {% if it.cand.pattern %}<span style="background:#eef1ff; color:#3b46c4; border-radius:4px; padding:1px 7px;">{{ it.cand.pattern }}</span>{% endif %}
    <span style="margin-left:auto;" class="muted">置信 {{ '%.2f' | format(it.cand.confidence) }}</span>
    {% if it.outcome %}<span class="status-{{ 'active' if it.outcome.outcome == 'continued' else 'retired' }}">{{ it.outcome.outcome }} {{ '%+.3f' | format(it.outcome.score) }}</span>{% endif %}
  </div>
  {% if it.cand.reason %}<div style="margin-top:6px;"><b class="muted">理由</b> {{ it.cand.reason }}</div>{% endif %}
  {% if it.plan %}
  <div style="margin-top:6px; background:#fafafc; border:1px solid #f0f0f4; border-radius:6px; padding:8px; line-height:1.7;">
    <div><b style="color:#3b46c4;">触发</b> {{ it.plan.trigger }}</div>
    <div><b style="color:#3b46c4;">进场</b> {{ it.plan.entry }}</div>
    <div><b style="color:#3b46c4;">出场/止损</b> {{ it.plan.exit_stop }}</div>
    {% if it.plan.taboo %}<div><b style="color:#b22;">禁忌</b> {{ it.plan.taboo | join('；') }}</div>{% endif %}
  </div>
  {% else %}<div class="muted" style="margin-top:6px; font-size:11px;">(未在种子 H 找到「{{ it.cand.pattern }}」→ 仅显候选自带)</div>{% endif %}
</div>
{% endfor %}
{% endif %}
{% endif %}
{% endblock %}
```

- [ ] **Step 7: 跑测试确认通过 + 全量回归**

Run: `.venv/bin/python -m pytest tests/test_web_decision.py -q && .venv/bin/python -m pytest -q`
Expected: PASS(test_web_decision 5 passed);全量 PASS(294 + 新增,目标 ≈299)

- [ ] **Step 8: 提交**

```bash
git add youzi_web/features/decision youzi_web/features/__init__.py tests/test_web_decision.py
git commit -m "feat(web): decision 决策驾驶舱(市场态面板+候选卡[理由/置信/计划/结果]+空仓)进 FEATURES"
```

---

## 收尾(Task 2 之后,subagent-driven 终审前)

- [ ] 更新 `PROJECT_STATE.md`/`后续开发文档.md`/`ROADMAP.md`(FE-A✅ 决策驾驶舱;⏭ live 按需跑 / news / agents)+ memory。
- [ ] **(人工)** `python scripts/sample_run.py` → `serve_web.py` → 🎯 决策驾驶舱(选 run+日期看决策卡)。

**FE 债务**:live 按需跑(选今天→agent 对 SnapshotSource+LLM 跑);持久化人工确认;join 用 run 当时 H 快照(现种子 H 近似);news/agents 模块。

---

## Self-Review(写计划后自查,已执行)

**1. Spec coverage:** §4.1 skill_plan → Task 1 Step 3 ✅;§4.2 cockpit_context → Task 1 Step 5;§4.3 router → Task 2 Step 3;§4.4/4.5 feature+注册 → Task 2 Step 4-5;§4.6 cockpit.html(市场态/候选卡/计划/降级/空仓/空态/选择器)→ Task 2 Step 6;§5 测试(skill_plan/cockpit_context/渲染/选择器/空态/降级/导航+FE0FEB不破)→ Task 1-2;§6 DoD + 回归 → Task 2 Step 7。

**2. Placeholder scan:** 无 TBD/TODO;每步完整代码 + 命令/预期。字段路径(`step.market.{max_board_height,limit_up_count,blowup_count,blowup_rate,limit_down_count,sentiment_norm,sentiment_raw,money_effect_raw,echelon[].{height,count,representatives}}`、`it.cand.{name,code,pattern,confidence,reason}`、`it.plan.{trigger,entry,exit_stop,taboo}`、`it.outcome.{outcome,score}`)均按真实模型。

**3. Type consistency:** `skill_plan(pattern, harness)→dict|None`、`cockpit_context(run, day)→{runs,run_id,meta,days,day,step,candidates}`、`Feature(id,label,icon,router,subnav)`、`FEATURES=[research,decision]`、模板上下文键(runs/run_id/days/day/step/candidates + FE-0 的 features/active_feature_id/active_path)跨 Task 一致;复用 `resolve_skill`/`seed_harness`/`list_runs`/`load_run`(已存)、TemplateResponse 新签名(同 FE-0/FE-B);decision subnav path `/decision/cockpit` 与路由一致。空 `decision/__init__.py`(Task1)→ 填 feature(Task2)避免 router-未建的循环。
