"""The intent shape and the signal loader."""
from __future__ import annotations

import math
from datetime import date

import pytest

from alpaca_kit.paper.intent import (
    MAX_NOTE_CHARS,
    MAX_TARGETS,
    IntentError,
    call_signal,
    load_signal,
    validate_intent,
    wants_holdings,
)

DAY = date(2026, 6, 1)


def test_a_good_intent_is_normalized():
    it = validate_intent({"targets": [{"symbol": " aapl ", "weight": 0.5}, {"symbol": "BRK.B", "weight": 0.25}],
                          "note": "x" * (MAX_NOTE_CHARS + 10), "extra": "ignored"}, DAY)
    assert [t.symbol for t in it.targets] == ["AAPL", "BRK.B"]
    assert it.gross == pytest.approx(0.75)
    assert len(it.note) == MAX_NOTE_CHARS
    assert it.to_dict() == {"as_of": "2026-06-01", "note": it.note,
                            "targets": [{"symbol": "AAPL", "weight": 0.5}, {"symbol": "BRK.B", "weight": 0.25}]}


def test_flat_is_an_empty_list_and_a_weight_of_exactly_one_is_fine():
    assert validate_intent({"targets": []}, DAY).targets == ()
    assert validate_intent({"targets": [{"symbol": "A", "weight": 1}]}, DAY).gross == 1.0
    assert validate_intent({"targets": [{"symbol": "A", "weight": 1.0 + 1e-12}]}, DAY).gross == 1.0


@pytest.mark.parametrize("raw, msg", [
    ("nope", "mapping"),
    ({}, "targets"),
    ({"targets": {"symbol": "A"}}, "targets"),
    ({"targets": ["A"]}, "mapping"),
    ({"targets": [{"symbol": "", "weight": 0.1}]}, "symbol"),
    ({"targets": [{"symbol": "bad ticker", "weight": 0.1}]}, "ticker"),
    ({"targets": [{"symbol": "A", "weight": 0.1}, {"symbol": "a", "weight": 0.1}]}, "twice"),
    ({"targets": [{"symbol": "A", "weight": "0.5"}]}, "number"),
    ({"targets": [{"symbol": "A", "weight": True}]}, "number"),
    ({"targets": [{"symbol": "A", "weight": -0.1}]}, "outside"),
    ({"targets": [{"symbol": "A", "weight": 1.5}]}, "outside"),
    ({"targets": [{"symbol": "A", "weight": math.nan}]}, "finite"),
    ({"targets": [{"symbol": "A", "weight": 0.6}, {"symbol": "B", "weight": 0.6}]}, "sum"),
    ({"targets": [{"symbol": f"S{i}", "weight": 0.001} for i in range(MAX_TARGETS + 1)]}, "MAX_TARGETS"),
    ({"targets": [], "note": 7}, "note"),
])
def test_refusals_name_the_reason(raw, msg):
    with pytest.raises(IntentError, match=msg):
        validate_intent(raw, DAY)


def _strategy(tmp_path, name, body, sibling=None):
    d = tmp_path / "strategies" / name
    d.mkdir(parents=True)
    (d / "signal.py").write_text(body, encoding="utf-8")
    if sibling is not None:
        (d / "helper.py").write_text(sibling, encoding="utf-8")
    return d


def test_load_signal_by_path_with_the_strategy_dir_importable(tmp_path):
    d = _strategy(tmp_path, "one",
                  "from helper import WEIGHT\n"
                  "def signal(source, day):\n    return {'targets': [{'symbol': 'A', 'weight': WEIGHT}]}\n",
                  sibling="WEIGHT = 0.3\n")
    fn = load_signal(d)
    assert fn(None, DAY) == {"targets": [{"symbol": "A", "weight": 0.3}]}


def test_two_strategies_do_not_shadow_each_other(tmp_path):
    a = _strategy(tmp_path, "a", "TAG = 'a'\ndef signal(source, day):\n    return TAG\n")
    b = _strategy(tmp_path, "b", "TAG = 'b'\ndef signal(source, day):\n    return TAG\n")
    fa, fb = load_signal(a), load_signal(b)
    assert (fa(None, DAY), fb(None, DAY)) == ("a", "b")


def test_load_signal_refusals(tmp_path):
    with pytest.raises(IntentError, match="no signal.py"):
        load_signal(tmp_path / "strategies" / "missing")
    with pytest.raises(IntentError, match="defines no signal"):
        load_signal(_strategy(tmp_path, "nosig", "x = 1\n"))
    with pytest.raises(IntentError, match="failed to import.*no_such_module"):
        load_signal(_strategy(tmp_path, "broken", "import no_such_module_xyz\n"))


def test_wants_holdings_and_call_signal():
    def plain(source, day):
        return ("plain", day)

    def rich(source, day, holdings):
        return ("rich", holdings)

    def kw(source, day, **rest):
        return ("kw", rest)

    assert not wants_holdings(plain)
    assert wants_holdings(rich)
    assert wants_holdings(kw)
    holdings = {"A": {"qty": 1.0, "avg_cost": 2.0}}
    assert call_signal(plain, None, DAY, holdings) == ("plain", DAY)
    assert call_signal(rich, None, DAY, holdings) == ("rich", holdings)
    assert call_signal(kw, None, DAY, holdings) == ("kw", {"holdings": holdings})
