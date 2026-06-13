# tests/test_run_store.py
import tempfile
from pathlib import Path

from youzi.harness.snapshot import SnapshotStore
from youzi.loop.compare import compare_harnesses
from youzi.loop.inner_loop import LoopConfig
from youzi.loop.run_store import RunStore
from tests.test_compare import _w_src, _SeqFactory, _CountFactory, _PICK_W, _NO_TRADE
from tests.test_inner_loop import _seed_h


def make_report(ablate=False):
    src = _w_src()
    # C4:ablate 时三脚本对位 factory 顺序 HCH→Hcredit→Hexpert(HCH/Hcredit 选 W,Hexpert 空仓)
    scripts = [_PICK_W, _PICK_W, _NO_TRADE] if ablate else [_PICK_W, _NO_TRADE]
    return compare_harnesses(
        _CountFactory(_seed_h), src, src.trading_calendar()[0], src.trading_calendar()[-1],
        agent_llm_factory=_SeqFactory(scripts),
        refiner_llm_factory=_SeqFactory(['{"ops": []}']),
        store_factory=_CountFactory(lambda: SnapshotStore(tempfile.mkdtemp())),
        # A3:evidence_min=1 保持原意(夹具 run 要带 refine_events 供研究看板/往返测试用)
        loop_config=LoopConfig(horizon=1, evidence_min=1), ablate=ablate)


def test_save_load_roundtrip(tmp_path):
    store = RunStore(tmp_path)
    rep = make_report()
    store.save("r1", rep, {"window": "w", "scorer": "pool"})
    got, meta = store.load("r1")
    assert set(got.arms) == {"HCH", "Hexpert", "Hmin_highest", "Hmin_notrade"}
    assert got.arms["HCH"].report.mean_score == rep.arms["HCH"].report.mean_score
    assert len(got.hch_loop_report.refine_events) == len(rep.hch_loop_report.refine_events)
    assert got.stat_verdict == rep.stat_verdict      # C1:统计裁决随 run 持久化往返不丢
    assert meta["run_id"] == "r1" and meta["window"] == "w"


def test_save_load_roundtrip_ablate(tmp_path):
    # C4:消融 run(五臂 + 两组 verdict + hcredit_loop_report)持久化往返不丢
    store = RunStore(tmp_path)
    rep = make_report(ablate=True)
    store.save("abl", rep, {"window": "w", "scorer": "pool"})
    got, _ = store.load("abl")
    assert "Hcredit" in got.arms and got.arms["Hcredit"].n_refines == 0
    assert got.hch_minus_hcredit_verdict == rep.hch_minus_hcredit_verdict
    assert got.hcredit_minus_hexpert_verdict == rep.hcredit_minus_hexpert_verdict
    assert got.hcredit_loop_report is not None
    assert got.hcredit_loop_report.n_edits == 0


def test_list_newest_first_and_atomic(tmp_path):
    store = RunStore(tmp_path)
    rep = make_report()
    store.save("aaa", rep, {"window": "1"})
    store.save("bbb", rep, {"window": "2"})
    ids = [m["run_id"] for m in store.list()]
    assert ids == ["bbb", "aaa"]                 # 新→旧(run_id 倒序)
    assert list(tmp_path.glob("*.tmp")) == []    # 原子写不留临时


def test_sample_run_writes_a_run(tmp_path, monkeypatch):
    monkeypatch.setenv("YOUZI_RUNS_DIR", str(tmp_path))
    import scripts.sample_run as sr
    sr.main()
    metas = RunStore(tmp_path).list()
    assert any(m["run_id"] == "sample" for m in metas)
    rep, _ = RunStore(tmp_path).load("sample")
    assert "HCH" in rep.arms


def test_load_old_json_without_c2_fields(tmp_path):
    """C2/C1/C4 旧 JSON 兼容:存量 run(无 mean_excess/advantage/day_baseline/
    hch_minus_hexpert_mean_excess/stat_verdict/C4 消融字段)反序列化不崩,新字段走默认/回退。"""
    import json

    _NEW_KEYS = {"mean_excess", "advantage", "day_baseline",
                 "hch_minus_hexpert_mean_excess", "expectancy_raw",
                 "stat_verdict",                     # C1:旧 run 无统计裁决 → None
                 "hch_minus_hcredit_verdict", "hcredit_minus_hexpert_verdict",
                 "hcredit_loop_report"}              # C4:旧 run 无消融臂 → None

    def _strip(obj):
        if isinstance(obj, dict):
            return {k: _strip(v) for k, v in obj.items() if k not in _NEW_KEYS}
        if isinstance(obj, list):
            return [_strip(v) for v in obj]
        return obj

    store = RunStore(tmp_path)
    store.save("new", make_report(), {"window": "w"})
    p = tmp_path / "old.json"
    payload = _strip(json.loads((tmp_path / "new.json").read_text(encoding="utf-8")))
    payload["meta"]["run_id"] = "old"
    p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    got, meta = store.load("old")
    assert meta["run_id"] == "old"
    assert got.hch_minus_hexpert_mean_excess == 0.0             # 缺省默认
    assert got.arms["HCH"].report.mean_excess == 0.0
    assert got.stat_verdict is None                             # C1 缺省:旧 run 无统计裁决
    assert got.hch_minus_hcredit_verdict is None                # C4 缺省:旧 run 无消融臂
    assert got.hcredit_minus_hexpert_verdict is None
    assert got.hcredit_loop_report is None
    # ScoredCandidate.advantage 回退=score(基线缺失)
    for step in got.hch_loop_report.trajectory.scored_steps():
        for sc in step.outcomes.values():
            assert sc.day_baseline is None and sc.advantage == sc.score


def test_list_skips_foreign_corrupt_binary_and_dotfiles(tmp_path):
    # 逐文件守卫:外来(无 meta)/截断 json / 二进制(macOS ._AppleDouble)/ 隐藏文件 都跳过,不拖垮整列(否则看板全 500)
    store = RunStore(tmp_path)
    store.save("good", make_report(), {"window": "w"})
    (tmp_path / "foreign.json").write_text('{"hello": "world"}', encoding="utf-8")
    (tmp_path / "broken.json").write_text('{"meta": {', encoding="utf-8")
    (tmp_path / "binary.json").write_bytes(b"\x00Mac OS X\xb0\xb0bad utf8")   # 非 UTF-8(/Volumes 上 ._*.json 之患)
    (tmp_path / "._good.json").write_bytes(b"\x00\xb0AppleDouble")            # 隐藏 ._ 文件
    assert [m["run_id"] for m in store.list()] == ["good"]
