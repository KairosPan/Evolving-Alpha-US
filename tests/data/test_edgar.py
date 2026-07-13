# tests/data/test_edgar.py
from __future__ import annotations

from datetime import date

import pytest

from alpha.data.edgar import EdgarNotFound, EdgarSource

# EPS diluted: a clean Q1 quarter (keep), a 6-month YTD row (DROP by duration filter), an FY annual (keep).
_EPS = {"units": {"USD/shares": [
    {"start": "2026-01-01", "end": "2026-03-31", "val": 1.2, "fy": 2026, "fp": "Q1",
     "form": "10-Q", "filed": "2026-05-06"},
    {"start": "2026-01-01", "end": "2026-06-30", "val": 2.5, "fy": 2026, "fp": "Q2",   # 6-mo YTD
     "form": "10-Q", "filed": "2026-08-05"},
    {"start": "2025-01-01", "end": "2025-12-31", "val": 4.0, "fy": 2025, "fp": "FY",
     "form": "10-K", "filed": "2026-02-10"},
]}}
_REV = {"units": {"USD": [
    {"start": "2026-01-01", "end": "2026-03-31", "val": 5.0e8, "fy": 2026, "fp": "Q1",
     "form": "10-Q", "filed": "2026-05-06"},
]}}

# Backtest fixture: FY2025 filed 2/10 and Q1 2026 filed 5/20 (a 99-day gap), so a backtest as_of of 5/10
# is (a) before the 5/20 report and (b) 2 days before the 2/10+91d=5/12 cadence estimate — inside T-3.
_EPS_BT = {"units": {"USD/shares": [
    {"start": "2025-01-01", "end": "2025-12-31", "val": 4.0, "fy": 2025, "fp": "FY",
     "form": "10-K", "filed": "2026-02-10"},
    {"start": "2026-01-01", "end": "2026-03-31", "val": 1.2, "fy": 2026, "fp": "Q1",
     "form": "10-Q", "filed": "2026-05-20"},
]}}


def _fake_get_json(payloads):
    """Dispatch by concept substring in the URL; missing concept -> EdgarNotFound (models 'not reported')."""
    def fake(url: str):
        for concept, payload in payloads.items():
            if concept in url:
                if payload is None:
                    raise EdgarNotFound(url)
                return payload
        raise EdgarNotFound(url)
    return fake


def _src(monkeypatch, payloads):
    src = EdgarSource(cik_map={"ACME": 111})
    monkeypatch.setattr(src, "_get_json", _fake_get_json(payloads))
    return src


def test_maps_edgar_facts_merging_eps_and_revenue(monkeypatch):
    # RevenueFromContract... 404s -> falls back to "Revenues" (concept fallback order).
    src = _src(monkeypatch, {"EarningsPerShareDiluted": _EPS,
                             "RevenueFromContractWithCustomerExcludingAssessedTax": None,
                             "Revenues": _REV})
    facts = src.earnings_known("ACME", date(2026, 12, 31))
    by_period = {f.fiscal_period: f for f in facts}
    assert set(by_period) == {"2026Q1", "2025FY"}                # 6-mo YTD row dropped by duration filter
    q1 = by_period["2026Q1"]
    assert q1.filing_date == date(2026, 5, 6)                    # PIT key = `filed`
    assert q1.period_end == date(2026, 3, 31)                    # informational only
    assert q1.actual_eps == 1.2 and q1.actual_revenue == 5.0e8  # EPS+revenue merged into one fact
    assert q1.form == "10-Q" and q1.source == "edgar"
    assert by_period["2025FY"].actual_revenue is None            # annual had no matching revenue row


def test_filing_date_is_the_pit_key(monkeypatch):
    src = _src(monkeypatch, {"EarningsPerShareDiluted": _EPS, "Revenues": _REV})
    # 2026-04-15: after Q1's period_end (3/31) but before its filing (5/6) -> Q1 INVISIBLE; only 2025FY
    # (filed 2/10) is known. The no-lookahead core.
    early = src.earnings_known("ACME", date(2026, 4, 15))
    assert [f.fiscal_period for f in early] == ["2025FY"]
    assert {f.fiscal_period for f in src.earnings_known("ACME", date(2026, 5, 6))} == {"2026Q1", "2025FY"}


def test_unknown_ticker_returns_empty(monkeypatch):
    src = _src(monkeypatch, {"EarningsPerShareDiluted": _EPS})
    assert src.earnings_known("ZZZZ", date(2026, 12, 31)) == []   # not in cik_map -> empty, no crash


def test_derived_calendar_past_confirmed_plus_forward_estimate(monkeypatch):
    src = _src(monkeypatch, {"EarningsPerShareDiluted": _EPS, "Revenues": _REV})
    cal = src.earnings_calendar(date(2026, 6, 1))
    # past report dates (the distinct filings 2/10, 5/6) are confirmed; one forward estimate (5/6 + 91d).
    confirmed = sorted(e.expected_date for e in cal if e.is_confirmed)
    assert confirmed == [date(2026, 2, 10), date(2026, 5, 6)]
    est = [e for e in cal if not e.is_confirmed]
    assert len(est) == 1 and est[0].source == "edgar_estimate"
    assert est[0].expected_date > date(2026, 5, 6) and est[0].known_asof == date(2026, 5, 6)


def test_calendar_is_pit_on_known_asof(monkeypatch):
    src = _src(monkeypatch, {"EarningsPerShareDiluted": _EPS, "Revenues": _REV})
    # as_of 2026-03-01 (between the 2/10 and 5/6 filings): the 2/10 filing is a confirmed report; the 5/6
    # filing is NOT yet knowable (invisible, no leak); a forward estimate off 2/10 (+91d = 5/12) is visible
    # so the calendar reports an upcoming report in backtest — not silently empty until the historical file day.
    cal = src.earnings_calendar(date(2026, 3, 1))
    assert all(e.known_asof <= date(2026, 3, 1) for e in cal)          # every entry PIT-knowable
    assert not any(e.known_asof == date(2026, 5, 6) for e in cal)      # the 5/6 filing does not leak
    assert [e.expected_date for e in cal if e.is_confirmed] == [date(2026, 2, 10)]   # only 2/10 confirmed
    est = [e for e in cal if not e.is_confirmed]
    assert len(est) == 1 and est[0].expected_date == date(2026, 5, 12)  # 2/10 + 91d cadence
    assert est[0].known_asof == date(2026, 2, 10)                       # off a PAST filing -> no lookahead


def test_backtest_between_filings_shows_cadence_estimate(monkeypatch):
    # The reviewer's probe: a walk-forward as_of BETWEEN two filings must still see an upcoming report
    # (off the prior quarter's cadence), which the old last-EVER-filing estimate dropped for all past as_ofs.
    from alpha.features.earnings import days_to_earnings
    src = _src(monkeypatch, {"EarningsPerShareDiluted": _EPS, "Revenues": _REV})
    asof = date(2026, 5, 3)                                            # between 2/10 and 5/6 filings
    cal = src.earnings_calendar(asof)
    assert not any(e.known_asof == date(2026, 5, 6) for e in cal)      # 5/6 filing not yet knowable (no leak)
    est = [e for e in cal if not e.is_confirmed]
    assert len(est) == 1 and est[0].expected_date == date(2026, 5, 12)  # 2/10 + 91d
    assert est[0].known_asof == date(2026, 2, 10) and est[0].known_asof <= asof
    assert days_to_earnings(cal, "ACME", asof) == 9                    # 5/3 -> 5/12, NOT None (the bug)


def test_backtest_t3_gate_fires_off_prior_cadence(monkeypatch):
    # A real backtest T-3 window (as_of 5/10, 2 days before the 5/12 cadence estimate, 10 days before the
    # actual 5/20 report): the §4.5 has_upcoming_earnings gate fires in backtest, with zero lookahead.
    from alpha.features.earnings import days_to_earnings, has_upcoming_earnings
    src = _src(monkeypatch, {"EarningsPerShareDiluted": _EPS_BT})       # revenue 404 -> EPS-only (calendar ok)
    asof = date(2026, 5, 10)
    cal = src.earnings_calendar(asof)
    assert all(e.known_asof <= asof for e in cal)                      # PIT: nothing knowable after as_of
    assert not any(e.known_asof == date(2026, 5, 20) for e in cal)     # the 5/20 report is INVISIBLE (no leak)
    est = [e for e in cal if not e.is_confirmed]
    assert len(est) == 1 and est[0].expected_date == date(2026, 5, 12)  # off the last KNOWN filing (2/10)
    assert est[0].known_asof == date(2026, 2, 10)                       # a PAST date -> no lookahead
    assert days_to_earnings(cal, "ACME", asof) == 2
    assert has_upcoming_earnings(cal, "ACME", asof) is True             # default T-3 window, in BACKTEST


def test_no_pre_filing_leak_at_any_as_of(monkeypatch):
    # Pin the invariant across a sweep of pre-filing as_ofs: a filing NEVER surfaces (confirmed or via a
    # future-stamped estimate) at any as_of strictly before it — the fix stays fail-SAFE.
    src = _src(monkeypatch, {"EarningsPerShareDiluted": _EPS_BT})
    for asof in (date(2026, 2, 9), date(2026, 3, 1), date(2026, 5, 10), date(2026, 5, 19)):
        cal = src.earnings_calendar(asof)
        assert all(e.known_asof <= asof for e in cal), f"leak at {asof}"          # no known_asof in the future
        assert not any(e.known_asof == date(2026, 5, 20) for e in cal), f"5/20 leak at {asof}"
    # before the first filing there is nothing to project from -> empty (not a fabricated future date)
    assert src.earnings_calendar(date(2026, 2, 9)) == []


def test_edgar_available_is_true(monkeypatch):
    assert EdgarSource(cik_map={"ACME": 111}).earnings_available() is True


def test_non_earnings_methods_raise_not_implemented():
    src = EdgarSource(cik_map={"ACME": 111})
    for call in (lambda: src.trading_calendar(),
                 lambda: src.daily_bars("ACME", date(2026, 1, 1), date(2026, 2, 1)),
                 lambda: src.daily_snapshot(date(2026, 1, 1)),
                 lambda: src.corporate_actions(date(2026, 1, 1), date(2026, 2, 1)),
                 lambda: src.corporate_actions_known(date(2026, 1, 1)),
                 lambda: src.corp_actions_available()):
        with pytest.raises(NotImplementedError):
            call()


def test_corp_actions_available_is_callable_for_p3_conformance():
    # registered in _SOURCES -> the P3 sorted(_SOURCES) parametrization asserts callability (never calls it).
    assert callable(getattr(EdgarSource(cik_map={}), "corp_actions_available", None))


# ── the _get_json seam error surfaces (no network; fake urlopen) ────────────────────────────────────

def test_get_json_404_raises_edgar_not_found(monkeypatch):
    import urllib.error
    import urllib.request
    from io import BytesIO
    src = EdgarSource(cik_map={"ACME": 111})

    def boom(req, timeout=30):
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, BytesIO(b""))
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    with pytest.raises(EdgarNotFound):
        src._get_json("https://data.sec.gov/api/xbrl/companyconcept/CIK0000000111/us-gaap/X.json")


def test_get_json_403_hints_user_agent(monkeypatch):
    import urllib.error
    import urllib.request
    from io import BytesIO
    src = EdgarSource(cik_map={"ACME": 111})

    def boom(req, timeout=30):
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, BytesIO(b"blocked"))
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    with pytest.raises(RuntimeError, match="User-Agent"):
        src._get_json("https://data.sec.gov/whatever.json")
