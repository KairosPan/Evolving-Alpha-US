"""account_payload, the gate truth table, and the CLI (both modes).

Three concerns, one producer module: the account view is read-only by construction
(a grep test fences the mutating paths); `gate_state` must report the SAME rule the
MCP server registers by (a parity test pins it to `build_tools`); and the CLI owns
`generated_at`, the exit contract, the market disk cache and the NaN/Inf scrub that
keeps the JSON parseable on the face side.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest

from alpaca_kit.mcp.tools import build_tools
from alpaca_kit.pit.pit_store import PITStore

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import face_data  # noqa: E402
from face_data import account_payload, gate_state  # noqa: E402

KEYS = {"APCA_API_KEY_ID": "k", "APCA_API_SECRET_KEY": "s"}


@pytest.fixture(autouse=True)
def cache_dir(tmp_path, monkeypatch):
    """No test may write into the repo's real data/.face_cache."""
    d = tmp_path / "cache"
    monkeypatch.setattr(face_data, "CACHE_DIR", d)
    return d


class _FakeClient:
    def __init__(self):
        self.order_status = []          # what account_payload asked /v2/orders for

    def get_account(self):
        return {"status": "ACTIVE", "equity": "1000.5", "cash": "900.1",
                "buying_power": "2000.2"}

    def get_positions(self):
        return [{"symbol": "AAA", "qty": "10", "avg_entry_price": "9.5",
                 "market_value": "100.0", "unrealized_plpc": "0.05"}]

    def get_orders(self, status=None):
        self.order_status.append(status)
        return [{"symbol": "AAA", "side": "buy", "qty": "10",
                 "status": "filled", "submitted_at": "2026-07-01T13:30:00Z"}]


# ── account_payload ────────────────────────────────────────────────────────────────────────────

def test_no_keys_is_honest_absence_and_never_builds_a_client():
    calls = []
    payload = account_payload(lambda: calls.append(1), env={})
    assert payload == {"ok": True, "available": False,
                       "reason": "no APCA keys in the environment"}
    assert calls == []


def test_with_keys_assembles_read_only_payload():
    payload = account_payload(_FakeClient, env=KEYS)
    assert payload["ok"] is True and payload["available"] is True
    assert payload["account"]["status"] == "ACTIVE"
    assert payload["positions"][0]["symbol"] == "AAA"
    assert len(payload["orders"]) <= 50
    assert payload["orders_gate"]["gate1_registered"] is False  # flag unset


def test_orders_are_asked_for_by_status_all_not_the_open_only_default():
    """Alpaca's /v2/orders defaults to OPEN orders; a settled account would render an
    empty table under a 'recent orders' heading."""
    client = _FakeClient()
    payload = account_payload(lambda: client, env=KEYS)
    assert client.order_status == ["all"]
    assert payload["orders_note"] == "Alpaca's most recent 50 orders, all statuses"


def test_orders_are_capped():
    class _Many(_FakeClient):
        def get_orders(self, status=None):
            return [{"symbol": f"S{i}"} for i in range(face_data.ORDERS_CAP + 5)]

    assert len(account_payload(_Many, env=KEYS)["orders"]) == face_data.ORDERS_CAP


def test_client_errors_propagate_rather_than_faking_an_empty_account():
    class _Broken(_FakeClient):
        def get_account(self):
            raise RuntimeError("HTTP 401. check APCA_API_KEY_ID")

    with pytest.raises(RuntimeError, match="401"):
        account_payload(_Broken, env=KEYS)


# ── the gate ───────────────────────────────────────────────────────────────────────────────────

def test_gate_truth_table():
    assert gate_state({})["gate1_registered"] is False
    assert gate_state(KEYS)["gate1_registered"] is False
    assert gate_state({**KEYS, "ALPACA_KIT_ENABLE_ORDERS": "1"})["gate1_registered"] is True
    assert gate_state({"ALPACA_KIT_ENABLE_ORDERS": "1"})["gate1_registered"] is False
    g = gate_state({})
    assert g["gate2_validated"] is False and "face/README.md" in g["gate2_note"]


def test_gate1_matches_what_the_mcp_server_actually_registers():
    """The page must not display a gate the server does not implement: for every row of
    the truth table, gate1_registered == "are the mutating tools registered?"."""
    for env in ({}, dict(KEYS), {"ALPACA_KIT_ENABLE_ORDERS": "1"},
                {**KEYS, "ALPACA_KIT_ENABLE_ORDERS": "1"}):
        registered = "place_order" in build_tools(env=dict(env))
        assert gate_state(env)["gate1_registered"] is registered, env


def test_paper_pin_names_the_hostname_the_code_actually_enforces():
    """The displayed pin is a safety claim; it must not drift from the enforced constant."""
    from alpaca_kit.account import PAPER_HOSTNAME
    assert PAPER_HOSTNAME in gate_state({})["paper_pin"]


def test_no_order_code_path_in_producer():
    src = (Path(__file__).resolve().parents[1] / "scripts" / "face_data.py").read_text()
    assert "place_order" not in src
    assert "cancel_order" not in src


# ── the NaN/Inf scrub ──────────────────────────────────────────────────────────────────────────

def test_clean_replaces_non_finite_floats_with_none():
    dirty = {"a": [1.0, float("nan"), {"b": float("inf")}], "c": float("-inf"),
             "d": "nan", "e": 3, "f": True}
    assert face_data._clean(dirty) == {"a": [1.0, None, {"b": None}], "c": None,
                                       "d": "nan", "e": 3, "f": True}


def test_cli_never_emits_bare_nan_on_the_wire(monkeypatch, capsys):
    """json.dumps writes bare NaN by default and JSON.parse rejects it - the face would
    see a parse error instead of a payload."""
    monkeypatch.setattr(face_data, "_real_market",
                        lambda: {"ok": True, "series": [{"level": float("nan")}]})
    assert face_data.main(["face_data.py", "market"]) == 0
    out = capsys.readouterr().out
    assert "NaN" not in out and "Infinity" not in out
    assert json.loads(out)["series"][0]["level"] is None


# ── _real_market: disk cache + bed-root honesty ────────────────────────────────────────────────

def _bed(root: Path, days=(date(2026, 6, 1), date(2026, 6, 2)), captured=None) -> Path:
    """A minimal captured bed: `days` is the calendar, `captured` the days with a snapshot
    (default: all but the first, so the calendar always outruns the capture)."""
    store = PITStore(root)
    store.put_calendar(list(days))
    for d in (days[1:] if captured is None else captured):
        store.put_snapshot(d, pd.DataFrame({"symbol": ["AAA"], "close": [10.0]}))
    return root


def _counting_payload(calls):
    def _fn(source, days, end, **kw):
        calls.append((tuple(days), end))
        return {"ok": True, "bed": dict(face_data.BED_INFO), "as_of": end.isoformat(),
                "breadth": {"series": []}, "tape": {"series": []}, "screens": {}}
    return _fn


def test_real_market_assembles_once_then_serves_the_disk_cache(tmp_path, monkeypatch, cache_dir):
    bed = _bed(tmp_path / "bed")
    calls = []
    monkeypatch.setenv("ALPHA_PIT_ROOT", str(bed))
    monkeypatch.setattr(face_data, "market_payload", _counting_payload(calls))

    first = face_data._real_market()
    assert calls == [((date(2026, 6, 2),), date(2026, 6, 2))]   # only the CAPTURED day
    cache = face_data._cache_path(bed, date(2026, 6, 2))
    assert cache.exists() and cache.parent == cache_dir
    assert "assembled_at" in first and "generated_at" not in first
    # The cache must never enter the bed: a bed's identity is its CHECKSUMS manifest, and
    # capture_window builds that manifest from an rglob of the bed root.
    assert not any(p.name.startswith(".face") for p in bed.rglob("*"))

    second = face_data._real_market()
    assert len(calls) == 1                                       # assembly skipped
    assert second == first                                       # same assembled_at, byte for byte
    assert json.loads(cache.read_text()) == first


@pytest.mark.parametrize("junk", ["{ not json", "[]", "null"])
def test_a_corrupt_cache_file_is_ignored_and_overwritten(tmp_path, monkeypatch, junk):
    bed = _bed(tmp_path / "bed")
    calls = []
    monkeypatch.setenv("ALPHA_PIT_ROOT", str(bed))
    monkeypatch.setattr(face_data, "market_payload", _counting_payload(calls))
    cache = face_data._cache_path(bed, date(2026, 6, 2))
    cache.parent.mkdir(parents=True)
    cache.write_text(junk)

    payload = face_data._real_market()
    assert len(calls) == 1
    assert json.loads(cache.read_text()) == payload


def test_editing_the_producer_invalidates_the_cache(tmp_path, monkeypatch):
    """The code hash is part of the key, so a changed assembler cannot be served from a
    payload the old code built."""
    bed = _bed(tmp_path / "bed")
    calls = []
    monkeypatch.setenv("ALPHA_PIT_ROOT", str(bed))
    monkeypatch.setattr(face_data, "market_payload", _counting_payload(calls))
    face_data._real_market()
    assert len(calls) == 1

    monkeypatch.setattr(face_data, "_code_hash", lambda: "deadbeef")
    face_data._real_market()
    assert len(calls) == 2                                       # reassembled under a new key


def test_two_beds_do_not_share_a_cache_entry(tmp_path, monkeypatch):
    a, b = _bed(tmp_path / "bed-a"), _bed(tmp_path / "bed-b")
    assert face_data._cache_path(a, date(2026, 6, 2)) != face_data._cache_path(b, date(2026, 6, 2))
    # ...and the same bed spelled two ways is ONE entry (the key hashes the RESOLVED path).
    assert (face_data._cache_path(a, date(2026, 6, 2))
            == face_data._cache_path(tmp_path / "bed-b" / ".." / "bed-a", date(2026, 6, 2)))


def test_bed_root_is_the_actual_root_and_warmup_is_dropped_for_a_foreign_bed(tmp_path, monkeypatch):
    bed = _bed(tmp_path / "bed")
    monkeypatch.setenv("ALPHA_PIT_ROOT", str(bed))
    monkeypatch.setattr(face_data, "market_payload", _counting_payload([]))

    out = face_data._real_market()["bed"]
    assert out["root"] == str(bed)
    assert "warmup" not in out
    assert "unknown" in out["warmup_note"]


def test_the_shipped_bed_keeps_its_warmup_block(tmp_path, monkeypatch):
    bed = _bed(tmp_path / "bed")
    monkeypatch.setattr(face_data, "BED_INFO", {**face_data.BED_INFO, "root": str(bed)})
    monkeypatch.setenv("ALPHA_PIT_ROOT", str(bed))
    monkeypatch.setattr(face_data, "market_payload", _counting_payload([]))

    out = face_data._real_market()["bed"]
    assert out["root"] == str(bed)
    assert out["warmup"]["sma200_valid_from"] == "2025-03-20"
    assert "warmup_note" not in out


def test_a_foreign_bed_is_not_truncated_by_the_shipped_beds_window(tmp_path, monkeypatch):
    """The shipped bed's window is a fact about THAT capture; a different bed's snapshot
    files are the only truth we have about it, so a later day must survive."""
    bed = _bed(tmp_path / "bed", days=(date(2026, 6, 1), date(2026, 9, 1)))   # past 2026-07-09
    monkeypatch.setenv("ALPHA_PIT_ROOT", str(bed))
    monkeypatch.setattr(face_data, "market_payload", _counting_payload([]))
    assert face_data._real_market()["as_of"] == "2026-09-01"


def test_the_shipped_beds_window_bounds_the_days_it_walks(tmp_path, monkeypatch):
    """The other direction: on the bed BED_INFO describes, a snapshot past the documented
    usable window is not walked (CLAUDE.md - reads outside it misbehave)."""
    inside, outside = date(2026, 7, 9), date(2026, 7, 10)       # BED_INFO window end is 07-09
    bed = _bed(tmp_path / "bed", days=(inside, outside), captured=(inside, outside))
    monkeypatch.setattr(face_data, "BED_INFO", {**face_data.BED_INFO, "root": str(bed)})
    monkeypatch.setenv("ALPHA_PIT_ROOT", str(bed))
    calls = []
    monkeypatch.setattr(face_data, "market_payload", _counting_payload(calls))

    assert face_data._real_market()["as_of"] == "2026-07-09"
    assert calls == [((inside,), inside)]                        # 07-10 never reached the walk


def test_an_empty_bed_is_an_actionable_error(tmp_path, monkeypatch):
    bed = tmp_path / "bed"
    PITStore(bed).put_calendar([date(2026, 6, 1)])           # calendar, but nothing captured
    monkeypatch.setenv("ALPHA_PIT_ROOT", str(bed))
    with pytest.raises(RuntimeError, match=str(bed)):
        face_data._real_market()


# ── the CLI ────────────────────────────────────────────────────────────────────────────────────

def test_cli_market_stamps_generated_at_and_exits_0(monkeypatch, capsys):
    monkeypatch.setattr(face_data, "_real_market",
                        lambda: {"ok": True, "as_of": "2026-07-09"})
    assert face_data.main(["face_data.py", "market"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["as_of"] == "2026-07-09"
    assert datetime.fromisoformat(payload["generated_at"]).tzinfo is not None


def test_cli_account_without_keys_exits_0_with_the_absence_payload(monkeypatch, capsys):
    for k in ("APCA_API_KEY_ID", "APCA_API_SECRET_KEY"):
        monkeypatch.delenv(k, raising=False)
    assert face_data.main(["face_data.py", "account"]) == 0     # absence is not a failure
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True and payload["available"] is False
    assert "generated_at" in payload


def test_cli_unknown_mode_is_an_error_payload_and_exit_1(capsys):
    assert face_data.main(["face_data.py"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False and "market|account" in payload["error"]


def test_cli_reports_a_producer_exception_as_error_json(monkeypatch, capsys):
    def _boom():
        raise RuntimeError("no captured snapshots under /nope")
    monkeypatch.setattr(face_data, "_real_market", _boom)
    assert face_data.main(["face_data.py", "market"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"ok": False, "error": "no captured snapshots under /nope"}


def test_cli_exit_code_follows_the_payloads_own_ok_flag(monkeypatch, capsys):
    """A returned (not raised) failure payload must still exit 1 - the face maps
    code 1 to a 503, and an ok:false served as 200 would render as an instrument."""
    monkeypatch.setattr(face_data, "_real_market",
                        lambda: {"ok": False, "error": "no captured days"})
    assert face_data.main(["face_data.py", "market"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False and "generated_at" in payload
