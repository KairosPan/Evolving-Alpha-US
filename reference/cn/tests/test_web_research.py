# tests/test_web_research.py
from fastapi.testclient import TestClient

from youzi_web.app import create_app


def _seed_run(tmp_path, monkeypatch):
    monkeypatch.setenv("YOUZI_RUNS_DIR", str(tmp_path))
    from youzi.loop.run_store import RunStore
    from tests.test_run_store import make_report
    RunStore(tmp_path).save("sample", make_report(), {"window": "w", "scorer": "pool"})


def test_views_resilient_to_no_loop_report_and_foreign_file(tmp_path, monkeypatch):
    # hch_loop_report=None + stat_verdict=None(模拟旧 run)+ 目录混入外来 json:三视图都 200(不 500)
    monkeypatch.setenv("YOUZI_RUNS_DIR", str(tmp_path))
    from youzi.loop.run_store import RunStore
    from tests.test_run_store import make_report
    rep = make_report().model_copy(update={"hch_loop_report": None, "stat_verdict": None})
    RunStore(tmp_path).save("noloop", rep, {"window": "w", "scorer": "pool"})
    (tmp_path / "foreign.json").write_text('{"hello": "x"}', encoding="utf-8")
    c = TestClient(create_app())
    for p in ("/research/compare", "/research/refine", "/research/trajectory"):
        assert c.get(p).status_code == 200
    assert "旧运行无统计裁决" in c.get("/research/compare").text   # C1:模板守 None


def test_compare_view(tmp_path, monkeypatch):
    _seed_run(tmp_path, monkeypatch)
    r = TestClient(create_app()).get("/research/compare")
    assert r.status_code == 200
    assert "HCH" in r.text and "Hexpert" in r.text
    assert "胜" in r.text or "未胜" in r.text          # verdict
    assert "sample" in r.text                          # 运行选择器
    # C1 统计裁决块:夹具 run 仅 2 配对日 → 样本不足;CI/p 仍展示
    assert "统计裁决" in r.text
    assert "样本不足" in r.text
    assert "配对日 2" in r.text
    assert "95% CI" in r.text and "p=" in r.text
    # C4:普通(非消融)run 不渲染 Hcredit 行/消融归因卡
    assert "Hcredit" not in r.text
    assert "消融归因" not in r.text


def test_compare_view_renders_hcredit_when_ablated(tmp_path, monkeypatch):
    # C4:消融 run → 臂表多 Hcredit 行 + 消融归因卡(两通道 verdict)
    monkeypatch.setenv("YOUZI_RUNS_DIR", str(tmp_path))
    from youzi.loop.run_store import RunStore
    from tests.test_run_store import make_report
    RunStore(tmp_path).save("abl", make_report(ablate=True), {"window": "w", "scorer": "pool"})
    r = TestClient(create_app()).get("/research/compare")
    assert r.status_code == 200
    assert "Hcredit" in r.text
    assert "消融归因" in r.text
    assert "编辑通道 HCH−Hcredit" in r.text
    assert "战绩回注通道 Hcredit−Hexpert" in r.text
    # 夹具窗无熔断 → 不渲染熔断不对称警示
    assert "熔断不对称" not in r.text and "本窗有熔断" not in r.text


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
