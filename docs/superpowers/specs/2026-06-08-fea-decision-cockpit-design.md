# FE-A 设计:决策驾驶舱(离线渲染已存决策 + join 技能计划)

> 日期:2026-06-08 · 分支 `fea-decision-cockpit`(待建)· brainstorming + 可视化辅助(cockpit 布局已确认)产出的设计冻结(spec)。下一步交 `writing-plans`。
>
> 先读:`youzi/eval/decision.py`(Candidate/DecisionPackage)· `youzi/eval/trajectory.py`(TrajectoryStep)· `youzi/schemas/market.py`(MarketState/EchelonRung)· `youzi/refine/credit.py`(`resolve_skill`)· `youzi/harness/skill.py`(Skill 计划字段)· FE-0/FE-B(web 地基 + run-store)。

---

## 0. 一句话

研究侧(FE-B)已全。FE-A 是**产品侧旗舰页**:点亮 `decision` 模块(🎯,现占位)的**决策驾驶舱**——选某次 run 某天 → 渲染那天 TrajectoryStep 的完整决策(**市场态面板 + 排序候选卡[理由/置信/join技能的计划/结果]**)。**离线**(读 run-store,复用 FE-B),零依赖 akshare/LLM。

## 1. 已锁定决策(brainstorming + 可视化,用户确认)

1. **数据 = 渲染已存决策**(run-store 的 `hch_loop_report.trajectory.steps[].decision`),离线;live 按需跑留债务。
2. **计划 = join 技能**:候选 `pattern` 经 `resolve_skill` 折种子 H 的 Skill → 展示 `trigger/entry/exit_stop/taboo`;**join 不到(None)→ 降级只显候选自带**(reason/confidence/pattern)。
3. **人工确认 = v1 只展示**(决策支持=人读;确认持久化留后续)。
4. cockpit 布局(已确认):顶栏 run+日期选择器 → 市场态横条(+连板梯队)→ 排序候选卡 → 空仓日显 `no_trade_reason`。

## 2. 不变量

1. **领域单向**:web 经 data_access 只读领域(run-store + `resolve_skill`/`seed_harness`),不写;`youzi/` 零改。
2. **FE-0 契约**:`decision` 是又一个 Feature(加进 FEATURES,外壳零改);TemplateResponse 新签名 `(request, name, ctx)`。
3. **离线**:测试 TestClient + YOUZI_RUNS_DIR 写样本 run + 种子 H,不触网。
4. **降级不崩**:join 不到技能、无 run、空仓日、未评分步 → 都优雅渲染。

## 3. 模块布局

| 文件 | 动作 | 内容 |
|---|---|---|
| `youzi_web/data_access.py` | 改 | 加 `skill_plan(pattern, harness) -> dict | None`(经 `resolve_skill`) |
| `youzi_web/features/decision/__init__.py` | **新增** | `feature = Feature(id="decision", label="决策", icon="🎯", router, subnav=[决策驾驶舱])` |
| `youzi_web/features/decision/router.py` | **新增** | `GET /decision/cockpit?run=&day=` |
| `youzi_web/features/decision/service.py` | **新增** | `cockpit_context(run, day)`:取 run+步 + 逐候选 enrich(plan+outcome) |
| `youzi_web/features/decision/templates/cockpit.html` | **新增** | 驾驶舱(extends base) |
| `youzi_web/features/__init__.py` | 改 | `FEATURES = [research_feature, decision_feature]` |
| `tests/test_web_decision.py` | **新增** | skill_plan + cockpit 渲染/选择器/空态/空仓/降级 |

## 4. 接口与数据流(精确)

### 4.1 `data_access.py`:`skill_plan`

```python
from youzi.refine.credit import resolve_skill

def skill_plan(pattern: str, harness) -> dict | None:
    """候选 pattern → 种子技能的"计划"。join 不到 → None(模板降级)。"""
    sk = resolve_skill(pattern, harness)
    if sk is None:
        return None
    return {"name_cn": sk.name_cn, "trigger": sk.trigger, "entry": sk.entry,
            "exit_stop": sk.exit_stop, "taboo": list(sk.taboo)}
```
(`resolve_skill(pattern, harness) -> Skill | None`:skill_id→name_cn→None,已验证真实技能名可解析。)

### 4.2 `decision/service.py`:`cockpit_context`

```python
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
        h = seed_harness()                       # 一次性载入,逐候选 resolve
        for c in step.decision.candidates:
            cands.append({"cand": c, "plan": skill_plan(c.pattern, h),
                          "outcome": step.outcomes.get(c.code)})    # ScoredCandidate | None
    return {"runs": runs, "run_id": run_id, "meta": meta, "days": days,
            "day": (step.date.isoformat() if step else None), "step": step, "candidates": cands}
```

### 4.3 `decision/router.py`

```python
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

### 4.4 `decision/__init__.py`

```python
from youzi_web.registry import Feature, SubNavItem
from youzi_web.features.decision.router import router

feature = Feature(id="decision", label="决策", icon="🎯", router=router,
                  subnav=[SubNavItem("决策驾驶舱", "/decision/cockpit")])
```

### 4.5 `features/__init__.py`

```python
from youzi_web.features.research import feature as research_feature
from youzi_web.features.decision import feature as decision_feature
FEATURES = [research_feature, decision_feature]
```

### 4.6 `cockpit.html`(extends base.html)

- **topbar**:`🎯 决策驾驶舱` + run 选择器(`onchange location.href='?run='+this.value`)+ 日期选择器(`onchange location.href='?run={{run_id}}&day='+this.value`,列 `days`,选中 `day`)。
- **content**:
  - `step is None`(无 run/无步)→ 空态卡"还没有运行结果。跑 `sample_run.py`/`smoke_compare`"。
  - 否则:**市场态面板**(`step.market` 的 `max_board_height/limit_up_count/blowup_count/blowup_rate/limit_down_count`、情绪 `sentiment_norm`(None 则 `sentiment_raw`)、`money_effect_raw`;**连板梯队** `step.market.echelon` 每 rung `height×count` + `representatives`)。
  - `step.decision.candidates` 空 → **空仓卡**(`step.decision.no_trade_reason`)。
  - 否则逐 `candidates` item 渲染**候选卡**:`item.cand.{name,code,pattern,confidence,reason}`;`item.plan`(非 None)→ 触发/进场/出场止损/禁忌(taboo 列表);`item.outcome`(非 None)→ outcome(continued ✅ / faded ○ / nuked ❌)+ `'%+.3f' score`;`item.plan` 为 None → 降级提示。

## 5. 测试(全离线,TestClient + YOUZI_RUNS_DIR + 样本 run)

- `test_web_decision.py`:
  - `skill_plan`:真实技能名(如种子第一个 `name_cn`)→ 返 dict(trigger/entry/exit_stop/taboo);不存在 pattern → None。
  - cockpit 渲染样本 run:`/decision/cockpit` 200,含市场态字段(如"最高板"/"连板梯队")+ 候选(样本 W/赢家)。
  - run+日期选择器:含 run_id + 各 day。
  - 空态:空 YOUZI_RUNS_DIR → 200 + "还没有运行结果"。
  - 降级:样本候选 pattern("龙头接力")join 不到 → 候选卡渲染但无计划块(不崩)。
  - 导航:`decision` 进图标轨(🎯);FE-0/FE-B 不破(/research/* 仍 200)。
- 回归:既有 294 全绿(纯新增 decision 模块 + data_access 一函数)。
- **人工**:`sample_run.py` → `serve_web.py` → 🎯 决策驾驶舱。

## 6. 验收标准(DoD)

1. `decision` 模块(Feature + cockpit 路由/模板)进 FEATURES;cockpit 渲染样本 run 的市场态 + 候选卡 + join 计划 + 结果。
2. `skill_plan` join(resolve_skill);join 不到降级;空仓/空态/未评分优雅。
3. 领域零改、web 单向只读;FE-0/FE-B 不破。
4. 新测试 + 全量回归(294+新)绿;离线不触网。
5. subagent-driven 两段评审 + opus 终审通过。
6. 文档:更新 PROJECT_STATE/后续开发文档/memory/ROADMAP(FE-A✅)。

## 7. 显式 out-of-scope(后续)

- **live 按需跑**(选今天 → agent 对 SnapshotSource+LLM 跑出决策)—— 需 akshare(当前挂)+ DeepSeek + 异步任务。
- **持久化人工确认**(confirmations store)。
- join 用**该 run 当时的 H 快照**(现用种子 H 近似;HCH 演化后技能计划可能变 —— 精化债务)。
- 多候选排序/筛选、决策导出、与实盘对账。
