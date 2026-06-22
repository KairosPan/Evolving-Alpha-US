# tests/data/test_alpaca_corp.py
"""Offline contract for the Alpaca corporate-actions wiring.

Payload fragments mirror the authoritative `/v1/corporate-actions` schema (verified against Alpaca's
own OpenAPI spec). The live methods are exercised through the `_get_json` seam so the pagination / PIT
windowing logic is testable with zero network and without the optional `alpaca-py` dependency.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

import pytest

from alpha.data.alpaca import _KNOWN_LOOKBACK_DAYS, AlpacaSource, _normalize_corp

NORM_COLS = ["symbol", "announce_date", "ex_date", "kind", "ratio"]

# --- nested typed-action fragments (subset of the documented fields) ---------------------------------
REVERSE_SPLIT = {  # 50 -> 1 reverse split; Alpaca exposes NO announce date, only process_date
    "ex_date": "2026-06-20", "id": "rs1", "new_cusip": "x", "new_rate": 1,
    "old_cusip": "y", "old_rate": 50, "process_date": "2026-06-09",
    "record_date": "2026-06-20", "symbol": "RUN",
}
FORWARD_SPLIT = {  # 1 -> 2 forward split
    "cusip": "z", "ex_date": "2026-06-18", "new_rate": 2, "old_rate": 1,
    "process_date": "2026-06-18", "symbol": "FWD",
}
CASH_DIV = {
    "cusip": "c", "ex_date": "2026-05-04", "process_date": "2026-05-19",
    "rate": 0.125, "symbol": "DIV", "special": False, "foreign": False, "id": "d1",
}
WORTHLESS = {"cusip": "w", "id": "wr1", "process_date": "2026-06-15", "symbol": "DEAD"}
CASH_MERGER = {
    "acquiree_cusip": "m", "acquiree_symbol": "TGT", "effective_date": "2026-07-17",
    "id": "cm1", "payable_date": "2026-07-17", "process_date": "2026-07-10", "rate": 5.37,
}


def _payload(**types) -> dict:
    return {"corporate_actions": types, "next_page_token": None}


# ---------------------------------------------------------------------------------------------------- #
# _normalize_corp: nested Alpaca JSON -> the flat normalized frame consumed everywhere downstream
# ---------------------------------------------------------------------------------------------------- #
def test_normalize_reverse_split_maps_process_to_announce_and_ratio():
    out = _normalize_corp(_payload(reverse_splits=[REVERSE_SPLIT]))
    assert list(out.columns) == NORM_COLS
    row = out.iloc[0]
    assert row["symbol"] == "RUN"
    assert row["kind"] == "reverse_split"
    assert row["announce_date"] == date(2026, 6, 9)        # := process_date (no announce date in Alpaca)
    assert row["ex_date"] == date(2026, 6, 20)
    assert row["ratio"] == pytest.approx(1 / 50)           # new_rate/old_rate < 1 => reverse


def test_normalize_forward_split_ratio_gt_one():
    out = _normalize_corp(_payload(forward_splits=[FORWARD_SPLIT]))
    row = out.iloc[0]
    assert row["kind"] == "forward_split"
    assert row["ratio"] == pytest.approx(2.0)              # new_rate/old_rate > 1 => forward


def test_normalize_cash_dividend_rate_is_ratio():
    out = _normalize_corp(_payload(cash_dividends=[CASH_DIV]))
    row = out.iloc[0]
    assert row["kind"] == "cash_dividend"
    assert row["announce_date"] == date(2026, 5, 19)       # process_date
    assert row["ex_date"] == date(2026, 5, 4)
    assert row["ratio"] == pytest.approx(0.125)            # cash rate


def test_normalize_worthless_removal_is_delist_exdate_falls_back_to_process():
    out = _normalize_corp(_payload(worthless_removals=[WORTHLESS]))
    row = out.iloc[0]
    assert row["symbol"] == "DEAD"
    assert row["kind"] == "delist"                         # consumed by return_oracle._delisted_between
    assert row["announce_date"] == date(2026, 6, 15)
    assert row["ex_date"] == date(2026, 6, 15)             # no ex_date -> process_date fallback
    assert math.isnan(row["ratio"])


def test_normalize_cash_merger_uses_acquiree_symbol_and_effective_date():
    out = _normalize_corp(_payload(cash_mergers=[CASH_MERGER]))
    row = out.iloc[0]
    assert row["symbol"] == "TGT"                          # the absorbed/delisted side, not the acquirer
    assert row["kind"] == "cash_merger"
    assert row["ex_date"] == date(2026, 7, 17)             # effective_date (no ex_date on mergers)
    assert row["announce_date"] == date(2026, 7, 10)       # process_date


def test_normalize_merges_multiple_types():
    out = _normalize_corp(_payload(reverse_splits=[REVERSE_SPLIT], cash_dividends=[CASH_DIV]))
    assert set(out["kind"]) == {"reverse_split", "cash_dividend"}
    assert len(out) == 2


def test_normalize_empty_and_missing():
    for payload in ({}, {"corporate_actions": {}}, {"corporate_actions": {"reverse_splits": []}}):
        out = _normalize_corp(payload)
        assert out.empty and list(out.columns) == NORM_COLS


def test_normalize_feeds_firewall_pit_primitives():
    # announce_date:=process_date must satisfy the announce-keyed firewall unchanged: a reverse split
    # processed 6/09 (ex 6/20) is "known & pending" as of 6/12 but "unknown" as of 6/08 (no lookahead).
    from alpha.data.corp_actions import has_reverse_split_pending, known_corporate_actions
    corp = _normalize_corp(_payload(reverse_splits=[REVERSE_SPLIT]))
    assert list(known_corporate_actions(corp, date(2026, 6, 12))["symbol"]) == ["RUN"]
    assert known_corporate_actions(corp, date(2026, 6, 8)).empty
    assert has_reverse_split_pending(corp, "RUN", date(2026, 6, 12)) is True
    assert has_reverse_split_pending(corp, "RUN", date(2026, 6, 8)) is False


# ---------------------------------------------------------------------------------------------------- #
# AlpacaSource live methods through the _get_json seam (no network, no alpaca-py needed)
# ---------------------------------------------------------------------------------------------------- #
@pytest.fixture
def alpaca(monkeypatch):
    monkeypatch.setenv("APCA_API_KEY_ID", "k")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "s")
    return AlpacaSource()


def test_corporate_actions_known_returns_pending_future_ex(alpaca):
    calls = []

    def fake(path, params):
        calls.append((path, dict(params)))
        return _payload(reverse_splits=[REVERSE_SPLIT])

    alpaca._get_json = fake
    known = alpaca.corporate_actions_known(date(2026, 6, 12))
    assert list(known["symbol"]) == ["RUN"]                # ex 6/20 future, still known (announce 6/9)
    assert calls[0][0] == "/v1/corporate-actions"
    assert calls[0][1]["end"] == "2026-06-12"              # query end == as_of: never reads the future
    # the lookback horizon is explicit: fetch start = as_of - _KNOWN_LOOKBACK_DAYS (bounds the known set)
    assert calls[0][1]["start"] == (date(2026, 6, 12) - timedelta(days=_KNOWN_LOOKBACK_DAYS)).isoformat()


def test_corporate_actions_is_ex_date_windowed(alpaca):
    # The ex-windowed accessor (oracle: splits/delists during a holding window) must DROP the RUN
    # reverse split whose ex_date 6/20 is outside [5/1, 5/31] -> matches FakeSource/SnapshotSource.
    def fake(path, params):
        return _payload(reverse_splits=[REVERSE_SPLIT], cash_dividends=[CASH_DIV])

    alpaca._get_json = fake
    out = alpaca.corporate_actions(date(2026, 5, 1), date(2026, 5, 31))
    assert list(out["kind"]) == ["cash_dividend"]          # ex 5/4 in window; reverse ex 6/20 dropped


def test_corporate_actions_excludes_future_processed_in_window_ex(alpaca):
    # PIT clamp: an action whose ex_date is INSIDE [start, end] but whose process_date (== announce_date,
    # the availability key) is AFTER end was not knowable at the as-of -> must NOT surface (no forward
    # leak), even though a naive ex_date-only filter would keep it.
    future_processed = {"ex_date": "2026-06-05", "process_date": "2026-06-20", "old_rate": 50,
                        "new_rate": 1, "symbol": "LATE", "id": "lp1"}

    def fake(path, params):
        return _payload(reverse_splits=[future_processed])

    alpaca._get_json = fake
    out = alpaca.corporate_actions(date(2026, 6, 1), date(2026, 6, 10))
    assert out.empty                                       # ex 6/05 in window, but processed 6/20 > end


def test_fetch_corp_actions_paginates(alpaca):
    pages = {
        None: {"corporate_actions": {"reverse_splits": [REVERSE_SPLIT]}, "next_page_token": "t2"},
        "t2": {"corporate_actions": {"cash_dividends": [CASH_DIV]}, "next_page_token": None},
    }

    def fake(path, params):
        return pages[params.get("page_token")]

    alpaca._get_json = fake
    known = alpaca.corporate_actions_known(date(2026, 7, 1))
    assert set(known["kind"]) == {"reverse_split", "cash_dividend"}   # both pages merged


def test_resolve_feed_defaults_iex_and_env_override(monkeypatch):
    from alpha.data.alpaca import _resolve_feed
    monkeypatch.delenv("ALPHA_DATA_FEED", raising=False)
    assert _resolve_feed() == "iex"                         # free/paper default — avoids the SIP 403
    monkeypatch.setenv("ALPHA_DATA_FEED", "SIP")
    assert _resolve_feed() == "sip"                         # normalized; set when subscribed
    monkeypatch.setenv("ALPHA_DATA_FEED", "")
    assert _resolve_feed() == "iex"                         # empty falls back


def test_init_requires_keys(monkeypatch):
    monkeypatch.delenv("APCA_API_KEY_ID", raising=False)
    monkeypatch.delenv("APCA_API_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError):
        AlpacaSource()


def test_get_json_http_error_is_actionable(alpaca, monkeypatch):
    # a 403 (e.g. key not entitled to the corp-actions data product) must surface an actionable
    # RuntimeError naming the status + endpoint, NOT a bare urllib traceback.
    import io
    import urllib.error
    import urllib.request

    def boom(*a, **k):
        raise urllib.error.HTTPError("https://data.alpaca.markets/v1/corporate-actions", 403,
                                     "Forbidden", {}, io.BytesIO(b'{"message":"not subscribed"}'))

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    with pytest.raises(RuntimeError) as ei:
        alpaca._get_json("/v1/corporate-actions", {"symbols": "AAPL"})
    msg = str(ei.value)
    assert "403" in msg and "/v1/corporate-actions" in msg
    assert "entitle" in msg.lower()                              # actionable hint for 401/403


def test_get_json_network_error_is_actionable(alpaca, monkeypatch):
    import urllib.error
    import urllib.request

    def boom(*a, **k):
        raise urllib.error.URLError("name resolution failed")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    with pytest.raises(RuntimeError, match="network"):
        alpaca._get_json("/v1/corporate-actions", {"symbols": "AAPL"})
