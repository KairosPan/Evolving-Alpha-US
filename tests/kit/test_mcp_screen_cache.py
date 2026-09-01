"""The screen-family disk cache (alpaca_kit/mcp/cache.py + its wiring in tools.py).

Modeled on scripts/face_data.py's market cache: one JSON file per (bed, producer code
version, day, screen kind) under data/.screen_cache — OUTSIDE any bed, because a bed's
identity is its CHECKSUMS manifest (an rglob of the bed root). The cache must never weaken
the tool contracts: the lookahead check runs BEFORE the cache read (a cached day must never
leak past an earlier as_of cursor), an error result is never cached (fail-soft must not
become fail-sticky), and an injected source is never cached at all (the bed path does not
name it, so nothing on disk keys it).

Every test here reads through a REAL mini-bed; the suite-wide `screen_cache_isolation`
fixture (tests/conftest.py) already points CACHE_DIR at a per-test tmp dir.
"""
from __future__ import annotations

import json
from datetime import date

import pandas as pd
import pytest

import alpaca_kit.features.breadth
import alpaca_kit.mcp.cache as screen_cache
import alpaca_kit.universe
from alpaca_kit.mcp.tools import build_tools
from alpaca_kit.pit.pit_store import PITStore

DAY = date(2026, 6, 12)


def _bed(root, snapshot_days=(DAY,)):
    """A minimal captured bed: calendar plus one snapshot row per requested day."""
    store = PITStore(root)
    store.put_calendar([date(2026, 6, 10), date(2026, 6, 11), DAY])
    for d in snapshot_days:
        store.put_snapshot(d, pd.DataFrame({
            "symbol": ["RUN"], "name": ["Runner"], "open": [16.0], "high": [18.0],
            "low": [15.0], "close": [17.0], "volume": [5e6], "prev_close": [14.0]}))
    return root


class _FakeUniverse:
    """Just enough of CandidateUniverse for the tool body: .all() of model_dump-ables."""
    class _Row:
        def model_dump(self, mode=None):
            return {"symbol": "RUN", "status": "gainer"}

    def all(self):
        return [self._Row()]


def _counting_universe(calls):
    def _fn(source, day, *, screen=None, **kw):
        calls.append((day, screen))
        return _FakeUniverse()
    return _fn


def _bed_tools(bed):
    return build_tools(env={"ALPHA_PIT_ROOT": str(bed)})


# ── screen ─────────────────────────────────────────────────────────────────────────────────────

def test_screen_computes_once_then_serves_the_disk_cache(
        tmp_path, monkeypatch, screen_cache_isolation):
    bed = _bed(tmp_path / "bed")
    calls = []
    monkeypatch.setattr(alpaca_kit.universe, "build_universe", _counting_universe(calls))
    tools = _bed_tools(bed)

    first = tools["screen"].fn(date=DAY.isoformat())
    assert first["ok"] is True and [r["symbol"] for r in first["rows"]] == ["RUN"]
    assert calls == [(DAY, "gainer")]
    files = list(screen_cache_isolation.rglob("*.json"))
    assert len(files) == 1
    # The cache must never enter the bed: a bed's identity is its CHECKSUMS manifest.
    assert not list(bed.rglob("*.json"))

    second = tools["screen"].fn(date=DAY.isoformat())
    assert len(calls) == 1                                   # walk skipped
    assert second == first                                   # byte for byte, computed_at included
    assert json.loads(files[0].read_text()) == first


def test_screen_kind_is_part_of_the_key(tmp_path, monkeypatch, screen_cache_isolation):
    bed = _bed(tmp_path / "bed")
    calls = []
    monkeypatch.setattr(alpaca_kit.universe, "build_universe", _counting_universe(calls))
    tools = _bed_tools(bed)

    tools["screen"].fn(date=DAY.isoformat(), kind="gainer")
    tools["screen"].fn(date=DAY.isoformat(), kind="trend_template")
    assert calls == [(DAY, "gainer"), (DAY, "trend_template")]
    assert len(list(screen_cache_isolation.rglob("*.json"))) == 2

    tools["screen"].fn(date=DAY.isoformat(), kind="gainer")  # warm again -> no third walk
    assert len(calls) == 2


def test_each_day_gets_its_own_entry(tmp_path, monkeypatch, screen_cache_isolation):
    other = date(2026, 6, 11)
    bed = _bed(tmp_path / "bed", snapshot_days=(other, DAY))
    calls = []
    monkeypatch.setattr(alpaca_kit.universe, "build_universe", _counting_universe(calls))
    tools = _bed_tools(bed)

    tools["screen"].fn(date=other.isoformat())
    tools["screen"].fn(date=DAY.isoformat())
    assert [d for d, _ in calls] == [other, DAY]
    assert len(list(screen_cache_isolation.rglob("*.json"))) == 2


def test_lookahead_is_checked_before_the_cache(tmp_path, monkeypatch, screen_cache_isolation):
    """PIT: a warm entry for a day must never be served to an as_of cursor EARLIER than
    that day — the guard runs before the cache read, so the caller gets the same
    lookahead error it would get on a cold call."""
    bed = _bed(tmp_path / "bed")
    calls = []
    monkeypatch.setattr(alpaca_kit.universe, "build_universe", _counting_universe(calls))
    tools = _bed_tools(bed)

    assert tools["screen"].fn(date=DAY.isoformat())["ok"] is True   # warm under as_of=today
    out = tools["screen"].fn(date=DAY.isoformat(), as_of="2026-06-10")
    assert out["ok"] is False and "lookahead" in out["error"].lower()
    assert len(calls) == 1                                   # neither served nor recomputed


def test_editing_the_producer_invalidates_the_cache(tmp_path, monkeypatch, screen_cache_isolation):
    """The package-source hash is part of the key: a changed producer cannot serve a
    payload the old code built."""
    bed = _bed(tmp_path / "bed")
    calls = []
    monkeypatch.setattr(alpaca_kit.universe, "build_universe", _counting_universe(calls))
    tools = _bed_tools(bed)

    tools["screen"].fn(date=DAY.isoformat())
    assert len(calls) == 1
    monkeypatch.setattr(screen_cache, "code_hash", lambda: "deadbeef")
    tools["screen"].fn(date=DAY.isoformat())
    assert len(calls) == 2                                   # recomputed under a new key


def test_two_beds_do_not_share_an_entry(tmp_path):
    a = screen_cache.cache_path(tmp_path / "bed-a", "screen-gainer", DAY)
    b = screen_cache.cache_path(tmp_path / "bed-b", "screen-gainer", DAY)
    assert a != b
    # ...and the same bed spelled two ways is ONE entry (the key hashes the RESOLVED path).
    assert a == screen_cache.cache_path(tmp_path / "bed-b" / ".." / "bed-a",
                                        "screen-gainer", DAY)


@pytest.mark.parametrize("junk", ["{ not json", "[]", "null"])
def test_a_corrupt_cache_file_is_ignored_and_overwritten(
        tmp_path, monkeypatch, screen_cache_isolation, junk):
    bed = _bed(tmp_path / "bed")
    calls = []
    monkeypatch.setattr(alpaca_kit.universe, "build_universe", _counting_universe(calls))
    path = screen_cache.cache_path(bed, "screen-gainer", DAY)
    path.parent.mkdir(parents=True)
    path.write_text(junk)

    out = _bed_tools(bed)["screen"].fn(date=DAY.isoformat())
    assert out["ok"] is True and len(calls) == 1
    assert json.loads(path.read_text()) == out


def test_failures_are_never_cached(tmp_path, monkeypatch, screen_cache_isolation):
    """Fail-soft must not become fail-sticky: an ok=False result never lands on disk, so
    the next call retries the walk instead of replaying the error (or worse, a blank)."""
    bed = _bed(tmp_path / "bed")

    def _boom(*a, **kw):
        raise RuntimeError("boom")
    monkeypatch.setattr(alpaca_kit.universe, "build_universe", _boom)
    tools = _bed_tools(bed)
    out = tools["screen"].fn(date=DAY.isoformat())
    assert out["ok"] is False and "boom" in out["error"]
    assert not list(screen_cache_isolation.rglob("*.json"))

    calls = []
    monkeypatch.setattr(alpaca_kit.universe, "build_universe", _counting_universe(calls))
    assert tools["screen"].fn(date=DAY.isoformat())["ok"] is True
    assert len(calls) == 1                                   # the retry actually ran


def test_an_injected_source_is_never_cached(tmp_path, monkeypatch, screen_cache_isolation,
                                            fake_source):
    """An injected factory supplies a source the bed path does not name — a path-keyed
    entry would collide across different injected sources, so injection disables the
    cache entirely (and the pre-existing injected-source tests stay byte-identical)."""
    calls = []
    monkeypatch.setattr(alpaca_kit.universe, "build_universe", _counting_universe(calls))
    tools = build_tools(env={"ALPHA_PIT_ROOT": str(tmp_path / "no-bed")},
                        source_factory=lambda: fake_source)
    tools["screen"].fn(date=DAY.isoformat())
    tools["screen"].fn(date=DAY.isoformat())
    assert len(calls) == 2
    assert not list(screen_cache_isolation.rglob("*"))


def test_a_cache_that_cannot_be_written_never_fails_the_call(
        tmp_path, monkeypatch, screen_cache_isolation, capsys):
    """An unwritable cache dir is logged to stderr and otherwise ignored — the computed
    payload in hand is good, and failing the tool over the cache is the worse trade."""
    bed = _bed(tmp_path / "bed")
    monkeypatch.setattr(alpaca_kit.universe, "build_universe", _counting_universe([]))
    screen_cache_isolation.write_text("a file where the cache dir should be")

    out = _bed_tools(bed)["screen"].fn(date=DAY.isoformat())
    assert out["ok"] is True
    assert "cache" in capsys.readouterr().err


# ── breadth ────────────────────────────────────────────────────────────────────────────────────

class _Reading:
    def model_dump(self, mode=None):
        return {"pct_above_200dma": 50.0, "net_new_highs": 1}


def test_breadth_computes_once_then_serves_the_disk_cache(
        tmp_path, monkeypatch, screen_cache_isolation):
    bed = _bed(tmp_path / "bed")
    calls = []

    def _counting_breadth(bars, day):
        calls.append(day)
        return _Reading()
    monkeypatch.setattr(alpaca_kit.features.breadth, "market_breadth", _counting_breadth)
    tools = _bed_tools(bed)

    first = tools["breadth"].fn(date=DAY.isoformat())
    assert first["ok"] is True and first["pct_above_200dma"] == 50.0
    assert calls == [DAY]
    files = list(screen_cache_isolation.rglob("*.json"))
    assert len(files) == 1

    second = tools["breadth"].fn(date=DAY.isoformat())
    assert calls == [DAY]                                    # walk skipped
    assert second == first
    assert json.loads(files[0].read_text()) == first


def test_breadth_failures_are_never_cached(tmp_path, monkeypatch, screen_cache_isolation):
    bed = _bed(tmp_path / "bed")
    out = _bed_tools(bed)["breadth"].fn(date="2026-06-11")   # calendar day, snapshot never captured
    assert out["ok"] is False and "missing" in out["error"].lower()
    assert not list(screen_cache_isolation.rglob("*.json"))
