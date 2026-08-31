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


class _FakeClient:
    def get_account(self):
        return {"status": "ACTIVE", "equity": "1000.5", "cash": "900.1",
                "buying_power": "2000.2"}

    def get_positions(self):
        return [{"symbol": "AAA", "qty": "10", "avg_entry_price": "9.5",
                 "market_value": "100.0", "unrealized_plpc": "0.05"}]

    def get_orders(self, status=None):
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


def test_orders_are_capped_and_the_truncation_is_disclosed():
    """Dropping orders past the cap silently would be a lie by omission."""
    class _Many(_FakeClient):
        def get_orders(self, status=None):
            return [{"symbol": f"S{i}"} for i in range(face_data.ORDERS_CAP + 5)]

    payload = account_payload(_Many, env=KEYS)
    assert len(payload["orders"]) == face_data.ORDERS_CAP
    assert payload["orders_truncated"] is True
    assert account_payload(_FakeClient, env=KEYS)["orders_truncated"] is False


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

def _bed(root: Path, day: date = date(2026, 6, 2)) -> Path:
    """A minimal captured bed: a two-day calendar, a snapshot on the later day only."""
    store = PITStore(root)
    store.put_calendar([date(2026, 6, 1), day])
    store.put_snapshot(day, pd.DataFrame({"symbol": ["AAA"], "close": [10.0]}))
    return root


def _counting_payload(calls):
    def _fn(source, days, end, **kw):
        calls.append((tuple(days), end))
        return {"ok": True, "bed": dict(face_data.BED_INFO), "as_of": end.isoformat(),
                "breadth": {"series": []}, "tape": {"series": []}, "screens": {}}
    return _fn


def test_real_market_assembles_once_then_serves_the_disk_cache(tmp_path, monkeypatch):
    _bed(tmp_path)
    calls = []
    monkeypatch.setenv("ALPHA_PIT_ROOT", str(tmp_path))
    monkeypatch.setattr(face_data, "market_payload", _counting_payload(calls))

    first = face_data._real_market()
    assert calls == [((date(2026, 6, 2),), date(2026, 6, 2))]   # only the CAPTURED day
    cache = tmp_path / ".face_cache" / "market-2026-06-02.json"
    assert cache.exists()
    assert "assembled_at" in first and "generated_at" not in first

    second = face_data._real_market()
    assert len(calls) == 1                                       # assembly skipped
    assert second == first                                       # same assembled_at, byte for byte
    assert json.loads(cache.read_text()) == first


@pytest.mark.parametrize("junk", ["{ not json", "[]", "null"])
def test_a_corrupt_cache_file_is_ignored_and_overwritten(tmp_path, monkeypatch, junk):
    _bed(tmp_path)
    calls = []
    monkeypatch.setenv("ALPHA_PIT_ROOT", str(tmp_path))
    monkeypatch.setattr(face_data, "market_payload", _counting_payload(calls))
    cache = tmp_path / ".face_cache" / "market-2026-06-02.json"
    cache.parent.mkdir(parents=True)
    cache.write_text(junk)

    payload = face_data._real_market()
    assert len(calls) == 1
    assert json.loads(cache.read_text()) == payload


def test_bed_root_is_the_actual_root_and_warmup_is_dropped_for_a_foreign_bed(tmp_path, monkeypatch):
    _bed(tmp_path)
    monkeypatch.setenv("ALPHA_PIT_ROOT", str(tmp_path))
    monkeypatch.setattr(face_data, "market_payload", _counting_payload([]))

    bed = face_data._real_market()["bed"]
    assert bed["root"] == str(tmp_path)
    assert "warmup" not in bed
    assert "unknown" in bed["warmup_note"]


def test_the_shipped_bed_keeps_its_warmup_block(tmp_path, monkeypatch):
    _bed(tmp_path)
    monkeypatch.setattr(face_data, "BED_INFO", {**face_data.BED_INFO, "root": str(tmp_path)})
    monkeypatch.setenv("ALPHA_PIT_ROOT", str(tmp_path))
    monkeypatch.setattr(face_data, "market_payload", _counting_payload([]))

    bed = face_data._real_market()["bed"]
    assert bed["root"] == str(tmp_path)
    assert bed["warmup"]["sma200_valid_from"] == "2025-03-20"
    assert "warmup_note" not in bed


def test_a_foreign_bed_is_not_truncated_by_the_shipped_beds_window(tmp_path, monkeypatch):
    """The shipped bed's window is a fact about THAT capture; a different bed's snapshot
    files are the only truth we have about it, so a later day must survive."""
    _bed(tmp_path, day=date(2026, 9, 1))     # past BED_INFO's 2026-07-09 end
    monkeypatch.setenv("ALPHA_PIT_ROOT", str(tmp_path))
    monkeypatch.setattr(face_data, "market_payload", _counting_payload([]))
    assert face_data._real_market()["as_of"] == "2026-09-01"


def test_an_empty_bed_is_an_actionable_error(tmp_path, monkeypatch):
    PITStore(tmp_path).put_calendar([date(2026, 6, 1)])       # calendar, but nothing captured
    monkeypatch.setenv("ALPHA_PIT_ROOT", str(tmp_path))
    with pytest.raises(RuntimeError, match=str(tmp_path)):
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
