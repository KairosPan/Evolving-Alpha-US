"""VerdictStore: a labeled JSON-dict store for verdict view dicts (run_verdict --json output), so the
console can browse multiple runs by window. Shape-agnostic — it stores/reads dicts by label."""
from __future__ import annotations

from alpha.eval.verdict_store import VerdictStore


def _v(tag):
    return {"window": {"start": "2026-01-02"}, "headline": {"hch_minus_hexpert": 0.0}, "tag": tag}


def test_put_get_roundtrip(tmp_path):
    s = VerdictStore(tmp_path)
    s.put("2026-01-02_2026-03-31", _v("a"))
    got = s.get("2026-01-02_2026-03-31")
    assert got is not None and got["tag"] == "a"


def test_names_sorted_latest_len(tmp_path):
    s = VerdictStore(tmp_path)
    for n in ("2026Q2", "2026Q1", "2026Q3"):
        s.put(n, _v(n))
    assert s.names() == ["2026Q1", "2026Q2", "2026Q3"]
    assert s.latest()["tag"] == "2026Q3"
    assert len(s) == 3


def test_missing_is_none(tmp_path):
    s = VerdictStore(tmp_path / "empty")
    assert s.get("x") is None and s.latest() is None
    assert s.names() == [] and len(s) == 0


def test_overwrite_same_label(tmp_path):
    s = VerdictStore(tmp_path)
    s.put("w", _v("a"))
    s.put("w", _v("b"))
    assert s.get("w")["tag"] == "b" and len(s) == 1


def test_atomic_no_tmp_and_reads_plain_files(tmp_path):
    s = VerdictStore(tmp_path)
    s.put("run1", _v("a"))
    assert not list(tmp_path.glob("*.tmp"))
    # a file written by `run_verdict --json out.json` (not via put) is browsable by its stem
    (tmp_path / "run2.json").write_text('{"window": {}, "tag": "external"}', encoding="utf-8")
    assert "run2" in s.names() and s.get("run2")["tag"] == "external"
