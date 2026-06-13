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
