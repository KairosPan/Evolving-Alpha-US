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
    assert "未在种子 H 找到" in r.text                        # 样本 pattern「龙头接力」join 不到 → 降级提示(不渲染 plan 块)


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
