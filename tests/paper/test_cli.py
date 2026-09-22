"""scripts/paper_book.py end to end on a fake source, the order-path fence, and the two shipped
signal.py files (the template's, which refuses, and paper-drill's, which answers)."""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from alpaca_kit.firewall import AsOfGuard
from alpaca_kit.paper import load_signal
from alpaca_kit.source import FakeSource, GuardedSource
from tests.paper.fakes import CAL, D0, D2, D4, flat, source_from

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import paper_book  # noqa: E402

RULE = ("def signal(source, day):\n"
        "    return {'targets': [{'symbol': 'A', 'weight': 0.5}], 'note': 'half in A'}\n")


@pytest.fixture
def workbench(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    (root / "strategies" / "demo").mkdir(parents=True)
    (root / "strategies" / "demo" / "signal.py").write_text(RULE, encoding="utf-8")
    (root / "strategies" / "mute").mkdir()
    home = tmp_path / "home"
    monkeypatch.setattr(paper_book, "make_source", lambda name=None, *, pit_root=None: source_from({"A": flat(10)}))
    return root, home


def _run(capsys, *argv):
    code = paper_book.main(list(argv))
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 1, out
    return code, json.loads(out[0])


def test_open_walk_show_verify(workbench, capsys):
    root, home = workbench
    common = ["--root", str(root), "--home", str(home)]
    code, out = _run(capsys, "open", "demo", "--cash", "1000", *common)
    assert (code, out["ok"], out["nav"], out["home"]) == (0, True, 1000.0, str(home / "demo"))

    code, out = _run(capsys, "walk", "demo", "--start", D0.isoformat(), "--end", D2.isoformat(), *common)
    assert code == 0 and out["stepped"] == 3 and out["skipped"] == 0
    assert out["summary"]["positions"][0]["symbol"] == "A" and out["summary"]["positions"][0]["qty"] == 50

    code, out = _run(capsys, "step", "demo", "--day", D4.isoformat(), *common)
    assert code == 0 and out["window"] == [D4.isoformat(), D4.isoformat()] and out["stepped"] == 1

    code, out = _run(capsys, "show", "demo", *common)
    assert code == 0 and out["steps"] == 4 and out["last_day"] == D4.isoformat()

    code, out = _run(capsys, "verify", "demo", *common)
    assert code == 0 and out["ok"] is True and out["errors"] == []


def test_step_defaults_to_the_last_trading_day_up_to_today(workbench, capsys):
    root, home = workbench
    common = ["--root", str(root), "--home", str(home)]
    _run(capsys, "open", "demo", *common)
    code, out = _run(capsys, "step", "demo", *common)
    assert code == 0 and out["window"] == [CAL[-1].isoformat()] * 2       # 2026-06-10 < today


def test_refusals_are_json_and_exit_one(workbench, capsys):
    root, home = workbench
    common = ["--root", str(root), "--home", str(home)]
    code, out = _run(capsys, "show", "demo", *common)
    assert code == 1 and "no book" in out["error"]
    code, out = _run(capsys, "open", "nosuch", *common)
    assert code == 1 and "no strategy directory" in out["error"]
    code, out = _run(capsys, "open", "../etc", *common)
    assert code == 1 and "not a strategy name" in out["error"]
    _run(capsys, "open", "mute", *common)
    code, out = _run(capsys, "walk", "mute", "--start", D0.isoformat(), "--end", D0.isoformat(), *common)
    assert code == 1 and "no signal.py" in out["error"]
    _run(capsys, "open", "demo", *common)
    code, out = _run(capsys, "open", "demo", *common)
    assert code == 1 and "already exists" in out["error"]


def test_no_order_code_path_in_the_book_or_the_script():
    files = list((REPO / "alpaca_kit" / "paper").glob("*.py")) + [REPO / "scripts" / "paper_book.py"]
    for path in files:
        src = path.read_text(encoding="utf-8")
        assert "place_order" not in src and "cancel_order" not in src, path
        assert "alpaca_kit.account" not in src and "TradingClient" not in src, path


def test_the_template_signal_refuses_until_written():
    fn = load_signal(REPO / "strategies" / "_template")
    with pytest.raises(NotImplementedError, match="intent rule"):
        fn(None, date(2026, 6, 1))


def test_paper_drill_answers_top_names_by_dollar_volume_equal_weight():
    day = date(2026, 6, 12)
    snap = pd.DataFrame({
        "symbol": ["RUN", "FLOP", "TINY", "GAP"], "name": ["", "", "", ""],
        "open": [16.0, 18.0, 1.0, 5.0], "high": [18.0, 18.5, 1.0, 5.0], "low": [15.0, 16.0, 1.0, 5.0],
        "close": [17.0, 16.5, 1.0, float("nan")], "volume": [5_000_000, 700_000, 100, 9_000_000],
        "prev_close": [14.0, 18.0, 1.0, 5.0],
    })
    src = GuardedSource(FakeSource(calendar=[day], bars={}, snapshots={day: snap}), AsOfGuard(day))
    out = load_signal(REPO / "strategies" / "paper-drill")(src, day)
    assert [t["symbol"] for t in out["targets"]] == ["RUN", "FLOP", "TINY"]     # GAP has no close: dropped
    assert all(t["weight"] == pytest.approx(0.98 / 3) for t in out["targets"])
    assert "top 3" in out["note"]
