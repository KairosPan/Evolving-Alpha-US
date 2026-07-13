"""Offline smoke for scripts/daily_loop.py: the scheduled daily production loop that turns one logical
date + one captured PIT window into all three console artifacts (DecisionStore / VerdictStore / evolution
JSON) — atomically, all-or-nothing. Drives the orchestrator with a FakeSource + injected MockLLM
factories (the sibling producers' idiom, no keys/data needed) and pins the loud-failure contract: a
mid-run failure finalizes NOTHING, a corp-blind day reaches the persisted run record, a checksum mismatch
aborts fail-closed, and a re-run overwrites cleanly."""
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from alpha.data.source import FakeSource
from alpha.eval.decision_store import DecisionStore
from alpha.guard.screen import CORP_BLIND_NOTE
from alpha.llm.client import MockLLMClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import daily_loop as dl   # noqa: E402

_AGENT = lambda: MockLLMClient('{"candidates": [{"symbol": "RUN", "pattern": "gap_and_go"}]}')
_REFINER = lambda: MockLLMClient('{"ops": []}')


def _fake(n=12, *, corp_available=True):
    cal = [date(2026, 6, d) for d in range(1, 1 + n)]
    snaps, px, closes = {}, 10.0, []
    for d in cal:
        prev = px; px = px * 1.15; closes.append(px)
        snaps[d] = pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [prev], "high": [px],
                                 "low": [prev], "close": [px], "volume": [1], "prev_close": [prev]})
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10.0] + closes[:-1], "high": closes,
                                 "low": [10.0] + closes[:-1], "close": closes, "volume": [1] * n})}
    src = FakeSource(calendar=cal, bars=bars, snapshots=snaps, corp_actions_available=corp_available)
    return src, cal[0], cal[-1]


def _dests(tmp_path):
    out = tmp_path / "out"
    return dict(decisions_dir=out / "decisions", verdicts_dir=out / "verdicts",
                evolution_path=out / "evolution.json", manifests_dir=out / "manifests")


def _run(tmp_path, src, start, end, **kw):
    d = _dests(tmp_path)
    return dl.run_daily_loop(src, start, end, agent_llm_factory=_AGENT, refiner_llm_factory=_REFINER,
                             **d, **kw), d


def _no_finalized(d):
    """No destination carries a finalized artifact (a failed run must touch nothing)."""
    return (not list(Path(d["decisions_dir"]).glob("*.json")) if Path(d["decisions_dir"]).is_dir() else True) \
        and (not list(Path(d["verdicts_dir"]).glob("*.json")) if Path(d["verdicts_dir"]).is_dir() else True) \
        and (not Path(d["evolution_path"]).exists()) \
        and (not list(Path(d["manifests_dir"]).glob("*.json")) if Path(d["manifests_dir"]).is_dir() else True)


# ---------------------------------------------------------------------------
# (a) a full successful run finalizes all three artifacts + a manifest
# ---------------------------------------------------------------------------

def test_full_run_finalizes_all_three_artifacts(tmp_path):
    src, start, end = _fake()
    manifest, d = _run(tmp_path, src, start, end)

    # decisions: one browsable package per trading day (+ its prompt sidecar)
    store = DecisionStore(d["decisions_dir"])
    assert store.dates() == src.trading_calendar()
    for day in store.dates():
        assert (Path(d["decisions_dir"]) / f"{day.isoformat()}.prompt.json").exists()
    # verdict: one labelled view dict the console reads
    verdicts = list(Path(d["verdicts_dir"]).glob("*.json"))
    assert len(verdicts) == 1
    view = json.loads(verdicts[0].read_text())
    assert {"window", "arms", "headline", "stat_verdict"} <= set(view)
    # evolution: the single latest-trajectory file
    evo = json.loads(Path(d["evolution_path"]).read_text())
    assert {"window", "summary", "edits"} <= set(evo)
    # manifest: the run's own durable record
    man_path = Path(d["manifests_dir"]) / f"{end.isoformat()}.json"
    assert man_path.exists()
    on_disk = json.loads(man_path.read_text())
    assert on_disk == manifest
    assert manifest["status"] == "ok"
    assert manifest["logical_date"] == end.isoformat()
    assert manifest["artifacts"]["n_decisions"] == len(src.trading_calendar())
    assert manifest["corp_blind"]["blind"] is False


def test_full_run_leaves_no_staging_dir(tmp_path):
    src, start, end = _fake()
    _run(tmp_path, src, start, end)
    assert not list((tmp_path / "out").glob(".daily_loop.*")), "staging dir must be cleaned up on success"


# ---------------------------------------------------------------------------
# (b) a mid-run failure leaves NO partial day — the acceptance-gate core
# ---------------------------------------------------------------------------

def test_failed_verdict_step_finalizes_nothing(tmp_path, monkeypatch):
    src, start, end = _fake()

    def boom(*a, **k):
        raise RuntimeError("verdict blew up")
    monkeypatch.setattr(dl.run_verdict, "run_verdict", boom)

    d = _dests(tmp_path)
    with pytest.raises(RuntimeError, match="verdict blew up"):
        dl.run_daily_loop(src, start, end, agent_llm_factory=_AGENT, refiner_llm_factory=_REFINER, **d)
    # decisions were PRODUCED into staging before verdict ran, yet NOTHING is finalized
    assert _no_finalized(d)
    assert not list((tmp_path / "out").glob(".daily_loop.*")), "staging dir must be cleaned up on failure"


def test_failed_evolution_step_finalizes_nothing(tmp_path, monkeypatch):
    src, start, end = _fake()
    monkeypatch.setattr(dl.save_evolution, "run_evolution",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("evolution blew up")))
    d = _dests(tmp_path)
    with pytest.raises(RuntimeError, match="evolution blew up"):
        dl.run_daily_loop(src, start, end, agent_llm_factory=_AGENT, refiner_llm_factory=_REFINER, **d)
    assert _no_finalized(d)


# ---------------------------------------------------------------------------
# (c) the corp-blind note propagates to the run summary (never swallowed)
# ---------------------------------------------------------------------------

def test_corp_blind_note_reaches_manifest_and_record(tmp_path):
    src, start, end = _fake(corp_available=False)
    manifest, d = _run(tmp_path, src, start, end)
    # the run's persisted record flags the blindness + names the days
    assert manifest["corp_blind"]["blind"] is True
    assert manifest["corp_blind"]["dates"], "blind days must be enumerated"
    assert manifest["status"] == "ok"                      # warn-the-human default: finalizes, doesn't fail
    # the note also survives in the persisted DecisionPackage itself
    pkg = DecisionStore(d["decisions_dir"]).get(date.fromisoformat(manifest["corp_blind"]["dates"][0]))
    assert CORP_BLIND_NOTE in pkg.key_risks


def test_fail_on_corp_blind_aborts_loud_and_finalizes_nothing(tmp_path):
    src, start, end = _fake(corp_available=False)
    d = _dests(tmp_path)
    with pytest.raises(RuntimeError, match="corp"):
        dl.run_daily_loop(src, start, end, agent_llm_factory=_AGENT, refiner_llm_factory=_REFINER,
                          fail_on_corp_blind=True, **d)
    assert _no_finalized(d)


# ---------------------------------------------------------------------------
# (d) re-run semantics: overwrites cleanly, never interleaves old + new
# ---------------------------------------------------------------------------

def test_rerun_overwrites_cleanly(tmp_path):
    src, start, end = _fake()
    m1, d = _run(tmp_path, src, start, end)
    m2, _ = _run(tmp_path, src, start, end)
    # still exactly one package per trading day, one verdict, one manifest — no leftovers
    assert DecisionStore(d["decisions_dir"]).dates() == src.trading_calendar()
    assert len(list(Path(d["verdicts_dir"]).glob("*.json"))) == 1
    assert len(list(Path(d["manifests_dir"]).glob("*.json"))) == 1
    assert m2["status"] == "ok"
    assert not list((tmp_path / "out").glob(".daily_loop.*"))


# ---------------------------------------------------------------------------
# (e) a CHECKSUMS mismatch fails the run closed, before any artifact is written
# ---------------------------------------------------------------------------

def test_checksum_mismatch_aborts_before_any_artifact(tmp_path):
    src, start, end = _fake()

    def raising_verify(root, *, fail_closed):
        assert fail_closed is True                          # the loop verifies fail-CLOSED
        raise RuntimeError("mismatch: bars/RUN.parquet")
    d = _dests(tmp_path)
    with pytest.raises(RuntimeError, match="mismatch"):
        dl.run_daily_loop(src, start, end, agent_llm_factory=_AGENT, refiner_llm_factory=_REFINER,
                          pit_root=tmp_path / "pit", verify=raising_verify, **d)
    assert _no_finalized(d)


def test_verify_skipped_when_no_pit_root(tmp_path):
    # a manifest-less window (pit_root=None) skips verification but still runs — mirrors the offline suite
    src, start, end = _fake()
    sentinel = {"called": False}

    def verify(root, *, fail_closed):
        sentinel["called"] = True
        return []
    manifest, _ = _run(tmp_path, src, start, end, pit_root=None, verify=verify)
    assert sentinel["called"] is False
    assert manifest["checksums_verified"] is False


# ---------------------------------------------------------------------------
# Review round: the all-or-nothing contract holds for DISCOVERABLE failures too
# (empty trading window; a cross-filesystem destination) — abort BEFORE producing,
# never finalize a verdict/evolution with no decision, never clobber a good artifact.
# ---------------------------------------------------------------------------

def test_empty_window_aborts_and_finalizes_nothing(tmp_path):
    src, _s, _e = _fake()                                  # captured calendar lives in June 2026
    start, end = date(2026, 7, 1), date(2026, 7, 2)        # zero trading days in that calendar
    d = _dests(tmp_path)
    # a prior GOOD evolution.json must survive an aborted empty-window run (never clobbered)
    Path(d["evolution_path"]).parent.mkdir(parents=True, exist_ok=True)
    Path(d["evolution_path"]).write_text('{"prior": "keep-me"}')

    with pytest.raises(RuntimeError, match="no trading days"):
        dl.run_daily_loop(src, start, end, agent_llm_factory=_AGENT, refiner_llm_factory=_REFINER, **d)
    # the prior evolution.json is intact, and no verdict / decision / manifest was orphaned
    assert json.loads(Path(d["evolution_path"]).read_text()) == {"prior": "keep-me"}
    for key in ("verdicts_dir", "decisions_dir", "manifests_dir"):
        assert not (Path(d[key]).is_dir() and list(Path(d[key]).glob("*.json")))
    assert not list((tmp_path / "out").glob(".daily_loop.*"))


def test_cross_fs_destination_aborts_before_producing(tmp_path, monkeypatch):
    src, start, end = _fake()
    calls = {"agent": 0}

    def counting_agent():
        calls["agent"] += 1
        return _AGENT()
    # simulate a verdicts destination on a different filesystem than staging/out_root
    monkeypatch.setattr(dl, "_fs_device", lambda p: 999 if "verdicts" in str(p) else 1)

    d = _dests(tmp_path)
    with pytest.raises(RuntimeError, match="cross-device"):
        dl.run_daily_loop(src, start, end, agent_llm_factory=counting_agent,
                          refiner_llm_factory=_REFINER, **d)
    assert calls["agent"] == 0, "must abort at the precondition, BEFORE producing (no LLM calls)"
    assert _no_finalized(d)
    assert not list((tmp_path / "out").glob(".daily_loop.*"))


# ---------------------------------------------------------------------------
# CLI: main() exits non-zero (loud) on failure, zero on success
# ---------------------------------------------------------------------------

def _wire_main(monkeypatch, src, out_root, start, end, extra=()):
    monkeypatch.setattr(sys, "argv", ["daily_loop", "PIT", start.isoformat(), end.isoformat(),
                                      str(out_root), *extra])
    monkeypatch.setattr(dl, "SnapshotSource", lambda *_a, **_k: src)
    monkeypatch.setattr(dl, "PITStore", lambda *_a, **_k: None)
    monkeypatch.setattr(dl, "verify_checksums", lambda *_a, **_k: [])
    monkeypatch.setattr(dl, "make_client", lambda role: _AGENT() if role == "agent" else _REFINER())


def test_main_success_exit_zero_and_writes(tmp_path, monkeypatch):
    src, start, end = _fake()
    out = tmp_path / "prod"
    _wire_main(monkeypatch, src, out, start, end)
    dl.main()                                               # no SystemExit on success
    assert (out / "manifests" / f"{end.isoformat()}.json").exists()
    assert DecisionStore(out / "decisions").dates() == src.trading_calendar()


def test_main_failure_exits_nonzero(tmp_path, monkeypatch):
    src, start, end = _fake()
    out = tmp_path / "prod"
    _wire_main(monkeypatch, src, out, start, end)
    monkeypatch.setattr(dl.save_evolution, "run_evolution",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("evolution blew up")))
    with pytest.raises(SystemExit) as ei:
        dl.main()
    assert ei.value.code != 0
    assert not list((out / "decisions").glob("*.json")) if (out / "decisions").is_dir() else True
