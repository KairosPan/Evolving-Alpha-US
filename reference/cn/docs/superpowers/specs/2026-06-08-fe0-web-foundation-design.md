# FE-0 设计:web 地基(成长型平台外壳 + 功能模块插槽 + H 查看器首模块)

> 日期:2026-06-08 · 分支 `fe0-web-foundation`(待建)· brainstorming 产出的设计冻结(spec),含可视化 mockup(`.superpowers/brainstorm/` 已选:外壳 C + 模块插槽 + H 查看器)。下一步交 `writing-plans`。
>
> 先读:`youzi/harness/{loader,harness,skill,doctrine,memory_item}.py`(领域模型)· `youzi/harness/snapshot.py`(`SnapshotStore`)· `seeds/`(种子 H)。

---

## 0. 一句话

给 youzi 起一个**会成长的 web 平台**的地基:`youzi_web/`(FastAPI + Jinja2 + HTMX,纯 Python),**app 外壳 C**(图标轨 + 上下文子导航 + 顶栏 + 内容)+ **功能模块插槽**(`features/<name>/` 自包含,注册即进导航)+ **data_access**(领域 pydantic→视图,读种子/快照,离线优先)+ **首模块 `research`/H 查看器**端到端验证整条缝。**不碰 `youzi/` 领域层。**

## 1. 已锁定决策(brainstorming + 可视化,用户确认)

1. 方向 **C**(研究驾驶舱 + 决策驾驶舱都要),**增量建**:FE-0 地基 → FE-B 研究全量 → FE-A 决策驾驶舱 → 以后 news/agents 模块。本 spec 只做 **FE-0**。
2. 技术栈 **FastAPI + HTMX + Jinja2 + 手写精简 CSS**(纯 Python 单语言、真 API 地基、加功能=加模块);稀有富交互界面以后用 JS island,不污染主体。
3. 外壳 **C**(图标轨 + 子导航,VS Code/Linear 式)。
4. **首模块 = `research`/H 查看器**(读种子 H,纯离线,端到端验证外壳+契约+data_access)。
5. **离线优先**:data_access 读已存产物;live(akshare/DeepSeek)是以后末端可换适配器,不在 FE-0。

## 2. 不变量

1. **领域零改**:`youzi/` 不动;`youzi_web/` **单向依赖** `youzi/`(领域不知道 web)。
2. **模块契约统一**:每个 `features/<name>/` 暴露一个 `Feature(id, label, icon, router, subnav)`;外壳从注册表自动出导航。**加功能=注册一个 Feature**,外壳零改。
3. **离线可测**:测试用 FastAPI `TestClient`(httpx,已装),读 `seeds/` 真实种子 H,不触网、不需 akshare/DeepSeek。
4. **只读不侵入**:FE-0 web 只读领域产物(`load_seeds`/`SnapshotStore`),不写、不触发跑批。

## 3. 模块布局(新增 `youzi_web/`,sibling of `youzi/`)

```
youzi_web/
  __init__.py
  app.py              # create_app():装 Jinja2(多模板目录)+ static + 注册所有 Feature 的 router + 外壳路由;模块级 app=create_app()(uvicorn 用)
  registry.py         # Feature / SubNavItem 数据类 + collect_features() 汇总
  data_access.py      # harness_view(h)->dict(算 hit_rate/nuke_rate)、seed_harness()、snapshot_harness(store,ver)
  templates/
    base.html         # 外壳 C:图标轨(遍历 features)+ 子导航(active feature 的 subnav)+ 顶栏 + {% block content %}
  static/
    app.css           # 手写精简 CSS(外壳 C 深色 app 风)
  features/
    __init__.py       # FEATURES = [research.feature]  ← 注册表(以后 append news.feature/agents.feature)
    research/
      __init__.py     # feature = Feature(id="research", label="研究", icon="📊", router=router, subnav=[...])
      router.py       # APIRouter:GET /research/harness → 渲染 harness.html
      service.py      # 取 H 视图(data_access)
      templates/
        harness.html  # H 查看器(extends base):技能表 + 纪律 + 记忆
tests/web/
  test_app.py         # TestClient:app 启动、导航含 research、H 查看器渲染种子 H、注册表
scripts/
  serve_web.py        # 便捷启动(uvicorn youzi_web.app:app --reload 的封装),可选
```

依赖:**新增 `fastapi`、`jinja2`、`uvicorn`**(`httpx` 已装,TestClient 用)。计划含 `pip install`。仓库目前无 requirements 文件(deps 在 venv);FE-0 可顺带建 `requirements-web.txt` 记录(可选)。

## 4. 接口与数据流(精确)

### 4.1 `registry.py`:模块契约

```python
from dataclasses import dataclass, field
from fastapi import APIRouter

@dataclass(frozen=True)
class SubNavItem:
    label: str
    path: str                 # "/research/harness"
    enabled: bool = True       # False → 灰显占位(refine 时间线/三方对比 等"以后")

@dataclass(frozen=True)
class Feature:
    id: str                    # "research"
    label: str                 # "研究"
    icon: str                  # "📊"(emoji/字形,FE-0 够用)
    router: APIRouter
    subnav: list[SubNavItem] = field(default_factory=list)
```

### 4.2 `features/__init__.py`:注册表

```python
from youzi_web.features.research import feature as research
FEATURES = [research]          # 以后:append news.feature / agents.feature —— 外壳零改
```

### 4.3 `app.py`:装配

```python
def create_app() -> FastAPI:
    app = FastAPI(title="youzi")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    # Jinja2:模板目录 = app templates + 各 feature 的 templates(ChoiceLoader)
    templates = make_templates([APP_TEMPLATES, *feature_template_dirs(FEATURES)])
    app.state.templates = templates
    app.state.features = FEATURES
    for f in FEATURES:
        app.include_router(f.router)
    @app.get("/")
    def home():
        return RedirectResponse(FEATURES[0].subnav[0].path)   # 默认进首模块首页
    return app

app = create_app()             # uvicorn youzi_web.app:app
```
- 模板渲染统一从 `request.app.state.templates`;每个 router 渲染时传 `{request, features, active_feature_id, active_path, ...页面数据}`,`base.html` 据此高亮图标轨 + 子导航。

### 4.4 `data_access.py`:领域→视图

```python
SEEDS_DIR = Path(__file__).resolve().parent.parent / "seeds"

def harness_view(h: HarnessState) -> dict:
    d = h.to_dict()                      # {skills:[...], memory:[...], doctrine:{...}, cycle:{...}}
    for s in d["skills"]:
        st = s["stats"]; n = st["n"]
        st["hit_rate"] = (st["wins"] / n) if n else None     # Skill 无 hit_rate 字段,这里算
        st["nuke_rate"] = (st["nukes"] / n) if n else None
    return d

def seed_harness() -> HarnessState:
    return load_seeds(SEEDS_DIR)

def snapshot_harness(store: SnapshotStore, version: int) -> HarnessState:
    h, _ = store.load(version)
    return h
```

### 4.5 `features/research`:H 查看器

- `router.py`:`GET /research/harness` → `view = harness_view(seed_harness())` → `templates.TemplateResponse("harness.html", {request, features, active_feature_id:"research", active_path:"/research/harness", h:view})`。
- `harness.html`(extends base):
  - **技能表**:每技能 `name_cn` · `status`(active/incubating 着色)· `stats.n` · `hit_rate`(%)· `expectancy`(±)· `nukes`;空 stats(n=0)显示 "—"。
  - **纪律 Doctrine**:`doctrine` 各 entry 的 `section` + `guidance`。
  - **记忆 Memory**:各 lesson 的 `lesson_id` + 文案。
- `__init__.py`:`feature = Feature(id="research", label="研究", icon="📊", router=router, subnav=[SubNavItem("H 查看器","/research/harness"), SubNavItem("refine 时间线","/research/refine",enabled=False), SubNavItem("三方对比","/research/compare",enabled=False), SubNavItem("trajectory","/research/trajectory",enabled=False)])`。

## 5. 外壳 C(`base.html` + `app.css`)

- **图标轨**(最左,深色):遍历 `features` 渲染图标;`active_feature_id` 高亮。
- **子导航**(图标轨右侧):渲染 active feature 的 `subnav`;`enabled=False` 灰显不可点;`active_path` 高亮。
- **顶栏**:页面标题 + 上下文(如"种子 playbook")+ 右侧占位(快照选择等以后)。
- **内容**:`{% block content %}`。
- **HTMX**:`base.html` 引 `htmx`(CDN script;FE-0 页面纯服务端渲染、不依赖 JS,HTMX 为以后交互预留)。CSS 手写(无构建步骤)。

## 6. 测试(全离线,TestClient)

`tests/web/test_app.py`:
- `client = TestClient(create_app())`。
- `GET /` → 302/最终 200,落到 `/research/harness`。
- `GET /research/harness` → 200;正文含**某个种子技能的 `name_cn`**(从 `load_seeds("seeds/")` 实际读到的)+ 表头"命中率"/"期望";含纪律/记忆区块。
- **注册表→导航**:响应含 research 的 icon/label;含一个 `enabled=False` 子项(灰显占位)渲染但标记 disabled。
- `harness_view` 单测:对构造的 HarnessState 算 hit_rate=wins/n、n=0→None。
- 回归:既有 277 全绿(纯新增 `youzi_web/`,不碰 `youzi/`)。

## 7. 验收标准(DoD)

1. `youzi_web/` 起得来(`create_app()`/`app`),外壳 C 渲染、图标轨+子导航来自注册表。
2. `research`/H 查看器读种子 H 渲染(技能表+纪律+记忆),纯离线。
3. 模块契约 `Feature/SubNavItem` + 注册表成立(加模块=append 一个 Feature)。
4. 领域零改、web 单向依赖;`pip install fastapi jinja2 uvicorn`。
5. 新测试 + 全量回归(277 + 新)绿;离线不触网。
6. subagent-driven 两段评审 + opus 终审通过。
7. 文档:更新 PROJECT_STATE/后续开发文档/memory(FE 路线:FE-0✅ / FE-B / FE-A / news / agents)。

## 8. 显式 out-of-scope(后续切片)

- **FE-B 研究全量**:refine 时间线(EditLog)、三方对比、trajectory/信用/签名 —— **需先做"运行结果持久化"(run-store:把 LoopReport/ComparisonReport 落盘)**,因当前 compare/eval 结果是临时打印的。
- **FE-A 决策驾驶舱**:每日决策(市场状态+排序候选+理由+计划+人工确认),对 `SnapshotSource`+(Mock/live)LLM 跑。
- **live 接线**(akshare/DeepSeek 实时)、**触发跑批**(从 UI 跑 compare/capture)、快照选择器。
- **news 分类 / agents 编排**模块(以后各自作为新 `features/` 模块)。
- 鉴权/多用户、HTMX 富交互、JS island(拖拽编排画布)、CSS 框架/构建步骤、htmx 本地 vendoring(FE-0 用 CDN)。
