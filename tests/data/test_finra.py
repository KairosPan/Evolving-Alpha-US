# tests/data/test_finra.py
from __future__ import annotations

from datetime import date

import pytest

from alpha.data.finra import FinraSource

# A FINRA-shaped payload: two settlements, the later one carrying an explicit disseminationDate, the
# earlier one relying on the derived settlement+lag publication date.
_PAYLOAD = {"data": [
    {"symbolCode": "RUN", "settlementDate": "2026-05-30", "currentShortPositionQuantity": 9.0e6,
     "previousShortPositionQuantity": 8.0e6, "averageDailyVolumeQuantity": 3.0e6,
     "daysToCoverQuantity": 3.0},
    {"symbolCode": "RUN", "settlementDate": "2026-06-14", "disseminationDate": "2026-06-25",
     "currentShortPositionQuantity": 1.2e7, "averageDailyVolumeQuantity": 2.0e6,
     "daysToCoverQuantity": 6.0},
]}


def _src(monkeypatch, payload=_PAYLOAD):
    src = FinraSource(dissemination_lag_days=12)
    monkeypatch.setattr(src, "_get_json", lambda url: payload)
    return src


def test_maps_finra_records(monkeypatch):
    src = _src(monkeypatch)
    recs = src.short_interest_known("RUN", date(2026, 12, 31))
    by_settle = {r.settlement_date: r for r in recs}
    assert set(by_settle) == {date(2026, 5, 30), date(2026, 6, 14)}
    jun = by_settle[date(2026, 6, 14)]
    assert jun.publication_date == date(2026, 6, 25)                 # explicit disseminationDate preferred
    assert jun.shares_short == 1.2e7 and jun.days_to_cover == 6.0
    assert jun.source == "finra"
    may = by_settle[date(2026, 5, 30)]
    assert may.publication_date == date(2026, 6, 11)                 # derived: 5/30 + 12-day lag


def test_publication_date_is_the_pit_key(monkeypatch):
    src = _src(monkeypatch)
    # 2026-06-20: after the 6/14 settlement but before its 6/25 dissemination -> that observation INVISIBLE;
    # only the 5/30 settlement (published 6/11) is known. The no-lookahead core.
    early = src.short_interest_known("RUN", date(2026, 6, 20))
    assert [r.settlement_date for r in early] == [date(2026, 5, 30)]
    assert len(src.short_interest_known("RUN", date(2026, 6, 25))) == 2


def test_derived_publication_lag_conservative(monkeypatch):
    # No disseminationDate -> derived settlement+lag; a larger lag delays (never advances) knowability.
    payload = {"data": [{"symbolCode": "RUN", "settlementDate": "2026-06-14",
                         "currentShortPositionQuantity": 5.0e6}]}
    src = FinraSource(dissemination_lag_days=20)
    monkeypatch.setattr(src, "_get_json", lambda url: payload)
    assert src.short_interest_known("RUN", date(2026, 6, 30)) == []   # 6/14 + 20d = 7/4 > 6/30, invisible
    got = src.short_interest_known("RUN", date(2026, 7, 4))
    assert got and got[0].publication_date == date(2026, 7, 4)


def test_rows_missing_load_bearing_fields_skipped(monkeypatch):
    payload = {"data": [{"symbolCode": "RUN", "settlementDate": "2026-06-14"}]}   # no shares_short
    src = _src(monkeypatch, payload)
    assert src.short_interest_known("RUN", date(2026, 12, 31)) == []


def test_fallback_lag_never_early_in_holiday_window(monkeypatch):
    # Settlement 2024-12-20 (Fri) with NO disseminationDate -> the derived fallback must land ON OR AFTER
    # FINRA's true ~8-business-day dissemination, which the Christmas+New-Year holidays push out to
    # 2025-01-03 (skip Sat/Sun, Christmas 12/25, New Year 1/1). The DEFAULT 16-day cushion -> 2025-01-05,
    # so the record is INVISIBLE at the true dissemination date (never early) and visible thereafter.
    payload = {"data": [{"symbolCode": "RUN", "settlementDate": "2024-12-20",
                        "currentShortPositionQuantity": 5.0e6}]}
    src = FinraSource()                                             # default cushion (16 calendar days)
    monkeypatch.setattr(src, "_get_json", lambda url: payload)
    true_dissemination = date(2025, 1, 3)                           # 8 business days incl. the two holidays
    assert src.short_interest_known("RUN", true_dissemination) == []          # not early — no leak
    got = src.short_interest_known("RUN", date(2025, 1, 5))
    assert got and got[0].publication_date == date(2025, 1, 5)
    assert got[0].publication_date >= true_dissemination                       # the pinned invariant


def test_zero_valued_fields_preserved_not_dropped(monkeypatch):
    # A legitimate 0 (fully covered short / zero days-to-cover) must round-trip as 0.0, not None — the
    # falsy-`or` idiom would have dropped it.
    payload = {"data": [{"symbolCode": "RUN", "settlementDate": "2026-06-14",
                        "disseminationDate": "2026-06-25", "currentShortPositionQuantity": 0,
                        "daysToCoverQuantity": 0, "previousShortPositionQuantity": 0,
                        "averageDailyVolumeQuantity": 0}]}
    src = _src(monkeypatch, payload)
    got = src.short_interest_known("RUN", date(2026, 12, 31))
    assert len(got) == 1                                            # shares_short==0 must NOT skip the row
    r = got[0]
    assert r.shares_short == 0.0 and r.days_to_cover == 0.0
    assert r.shares_short_prior == 0.0 and r.avg_daily_volume == 0.0   # all real zeros, not None


def test_short_interest_available_is_true():
    assert FinraSource().short_interest_available() is True


def test_non_short_interest_methods_raise_not_implemented():
    src = FinraSource()
    for call in (lambda: src.trading_calendar(),
                 lambda: src.daily_bars("RUN", date(2026, 1, 1), date(2026, 2, 1)),
                 lambda: src.daily_snapshot(date(2026, 1, 1)),
                 lambda: src.corporate_actions(date(2026, 1, 1), date(2026, 2, 1)),
                 lambda: src.corporate_actions_known(date(2026, 1, 1)),
                 lambda: src.earnings_known("RUN", date(2026, 1, 1)),
                 lambda: src.offering_events_known("RUN", date(2026, 1, 1))):
        with pytest.raises(NotImplementedError):
            call()


def test_corp_actions_available_is_callable_for_p3_conformance():
    # registered in _SOURCES -> the P3 sorted(_SOURCES) parametrization asserts callability (never calls it).
    assert callable(getattr(FinraSource(), "corp_actions_available", None))


# ── the _get_json seam error surfaces (no network; fake urlopen) ────────────────────────────────────

def test_get_json_403_hints_credentials(monkeypatch):
    import urllib.error
    import urllib.request
    from io import BytesIO
    src = FinraSource()

    def boom(req, timeout=30):
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, BytesIO(b"blocked"))
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    with pytest.raises(RuntimeError, match="OAuth"):
        src._get_json("https://api.finra.org/whatever")
