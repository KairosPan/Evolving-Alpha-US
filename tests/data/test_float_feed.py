"""FloatSource — the live float-capability-only backend (P5b; spec 2026-07-13-p5b-float-feed-design.md).
Mirrors FinraSource: a stdlib-urllib `_get_json` mockable seam (offline-testable), a vendor record ->
FloatFact mapping keyed on the disclosure date (PIT), and pure-swap NotImplementedError elsewhere."""
from datetime import date

import pytest

from alpha.data.float_feed import FloatSource


class _StubFloatSource(FloatSource):
    def __init__(self, payload):
        super().__init__()
        self._payload = payload

    def _get_json(self, url):          # the ONE mocked seam (no network)
        return self._payload


def _payload(rows):
    return {"data": rows}


def test_maps_vendor_record_and_keys_on_disclosure_date():
    src = _StubFloatSource(_payload([
        {"symbol": "ACME", "freeFloat": 8_000_000, "sharesOutstanding": 10_000_000,
         "restrictedShares": 2_000_000, "disclosureDate": "2026-05-01", "periodDate": "2026-03-31"}]))
    facts = src.float_known("ACME", date(2026, 5, 1))
    assert len(facts) == 1
    f = facts[0]
    assert f.free_float == 8_000_000.0 and f.shares_outstanding == 10_000_000.0
    assert f.knowable_date == date(2026, 5, 1) and f.as_of_period == date(2026, 3, 31)
    assert f.source == "vendor"


def test_pit_filters_on_disclosure_date():
    src = _StubFloatSource(_payload([
        {"symbol": "ACME", "freeFloat": 8_000_000, "disclosureDate": "2026-05-01", "periodDate": "2026-03-31"}]))
    assert src.float_known("ACME", date(2026, 4, 15)) == []      # measured 3/31, not knowable until 5/1
    assert len(src.float_known("ACME", date(2026, 5, 1))) == 1


def test_period_only_record_is_dropped_no_lookahead_safe_key():
    # a record with ONLY a measurement period (no disclosure/filing/effective date) has NO lookahead-safe
    # key -> DROPPED. Keying on the period would admit the float ~40 days before its real filing (a leak);
    # unlike FINRA's fixed dissemination schedule, the SEC filing lag is variable/unbounded so no finite
    # offset is provably never-early. Mirrors EdgarSource dropping filed=None rows.
    src = _StubFloatSource(_payload([
        {"symbol": "ACME", "freeFloat": 8_000_000, "periodDate": "2026-03-31"},               # dropped (no key)
        {"symbol": "ACME", "freeFloat": 5_000_000, "disclosureDate": "2026-05-01",
         "periodDate": "2026-03-31"}]))                                                        # kept (has key)
    facts = src.float_known("ACME", date(2027, 1, 1))                                          # far-future as_of
    assert [f.free_float for f in facts] == [5_000_000.0]                                      # only the disclosed one
    assert facts[0].knowable_date == date(2026, 5, 1) and facts[0].as_of_period == date(2026, 3, 31)


def test_period_only_never_visible_before_disclosure_leak_regression():
    # LEAK REGRESSION (adversarial-review finding): a period-only fact must be invisible at EVERY as_of —
    # never at its period date (before it was measured/filed), never mid filing-lag, never ever. If keying
    # ever falls back to the period, this fires (a period-dated 10-Q is not filed until ~40 days later).
    src = _StubFloatSource(_payload([
        {"symbol": "ACME", "freeFloat": 8_000_000, "periodDate": "2026-03-31"}]))
    for as_of in (date(2026, 3, 31), date(2026, 4, 15), date(2026, 5, 1), date(2027, 1, 1)):
        assert src.float_known("ACME", as_of) == []      # never leaks in early, at any horizon


def test_skips_rows_missing_load_bearing_fields():
    src = _StubFloatSource(_payload([
        {"symbol": "ACME", "disclosureDate": "2026-05-01"},                       # no free_float -> skip
        {"symbol": "ACME", "freeFloat": 8_000_000},                               # no date at all -> skip
        {"symbol": "ACME", "freeFloat": 5_000_000, "disclosureDate": "2026-05-01"}]))  # valid
    facts = src.float_known("ACME", date(2026, 6, 1))
    assert [f.free_float for f in facts] == [5_000_000.0]


def test_float_available_true():
    assert FloatSource().float_available() is True     # live feed is always checkable (a fetch or raises)


def test_pure_swap_other_methods_raise():
    src = FloatSource()
    for call in (lambda: src.trading_calendar(),
                 lambda: src.daily_bars("A", date(2026, 1, 1), date(2026, 1, 2)),
                 lambda: src.daily_snapshot(date(2026, 1, 1)),
                 lambda: src.corporate_actions(date(2026, 1, 1), date(2026, 1, 2)),
                 lambda: src.corporate_actions_known(date(2026, 1, 1)),
                 lambda: src.corp_actions_available(),
                 lambda: src.earnings_known("A", date(2026, 1, 1)),
                 lambda: src.earnings_available(),
                 lambda: src.short_interest_known("A", date(2026, 1, 1)),
                 lambda: src.offerings_available()):
        with pytest.raises(NotImplementedError):
            call()
