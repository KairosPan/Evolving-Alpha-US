"""The book's accounting: the five rules applied to a book, the ledger chain, verify."""
from __future__ import annotations

import json
from datetime import timedelta

import pytest

from alpaca_kit.paper import BookError, PaperBook
from alpaca_kit.paper.book import INTENTS_DIR, LEDGER_FILE, NAV_FILE, STATE_FILE, SUMMARY_FILE
from tests.paper.fakes import CAL, D0, D1, D2, D3, D4, D5, by_day, constant, flat, ledger, source_from


def _book(tmp_path, clock, **kw):
    return PaperBook.open(tmp_path / "b", strategy="demo", clock=clock, **kw)


# ── files and lifecycle ────────────────────────────────────────────────────────────────────

def test_open_creates_the_files_and_refuses_twice(tmp_path, clock):
    book = _book(tmp_path, clock, initial_cash=1_000.0)
    d = tmp_path / "b"
    assert {p.name for p in d.iterdir()} == {LEDGER_FILE, STATE_FILE, SUMMARY_FILE, INTENTS_DIR}
    assert ledger(d) [0]["kind"] == "open" and book.nav == 1_000.0 and book.seq == 1
    with pytest.raises(BookError, match="already exists"):
        PaperBook.open(d, strategy="demo", clock=clock)


def test_open_validates_its_parameters(tmp_path, clock):
    for kw in ({"initial_cash": 0}, {"params": {"fees_bps": -1}}, {"params": {"presume_delisted_after": 0}},
               {"params": {"presume_delisted_after": True}}):
        with pytest.raises(BookError):
            PaperBook.open(tmp_path / "x", strategy="demo", clock=clock, **kw)


def test_load_needs_a_book_and_the_ledger_must_agree(tmp_path, clock):
    with pytest.raises(BookError, match="no book"):
        PaperBook.load(tmp_path / "nothing")
    book = _book(tmp_path, clock)
    book.walk(source_from({"A": flat(10)}), start=D0, end=D1, signal=constant({"A": 0.5}))
    again = PaperBook.load(tmp_path / "b", clock=clock)
    assert again.nav == book.nav and again.holdings() == book.holdings() and again.head == book.head
    # a ledger the state does not describe (an interrupted step) is refused, never stepped on
    path = tmp_path / "b" / LEDGER_FILE
    lines = path.read_text("utf-8").splitlines()
    path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
    with pytest.raises(BookError, match="disagree"):
        PaperBook.load(tmp_path / "b")


# ── rule 4: the next open, never the same close ────────────────────────────────────────────

def test_an_intent_fills_at_the_next_open_never_the_deciding_close(tmp_path, clock):
    src = source_from({"A": [(10.0, 12.0), (11.0, 11.5)] + [None] * 6})
    book = _book(tmp_path, clock)
    book.walk(src, start=D0, end=D1, signal=constant({"A": 0.5}))
    fills = ledger(tmp_path / "b", "fill")
    assert len(fills) == 1 and fills[0]["day"] == D1.isoformat() and fills[0]["price"] == 11.0
    assert fills[0]["qty"] == 4545                       # floor(0.5 * 100000 / 11)
    assert book.cash == pytest.approx(100_000 - 4545 * 11.0)
    assert book.nav == pytest.approx(book.cash + 4545 * 11.5)
    marks = ledger(tmp_path / "b", "mark")
    assert marks[0]["n_positions"] == 0 and marks[0]["nav"] == 100_000.0      # nothing on the deciding day
    intents = ledger(tmp_path / "b", "intent")
    assert [r["day"] for r in intents] == [D0.isoformat(), D1.isoformat()] and book.pending is not None


def test_rebalance_sells_first_then_buys_and_drops_names_left_out(tmp_path, clock):
    src = source_from({"A": flat(10), "B": flat(20), "C": flat(5)})
    rule = by_day({D0: {"A": 0.5, "B": 0.3}}, default={"A": 0.2, "C": 0.5})
    book = _book(tmp_path, clock)
    book.walk(src, start=D0, end=D2, signal=rule)
    d2 = [r for r in ledger(tmp_path / "b") if r["day"] == D2.isoformat() and r["kind"] == "fill"]
    assert [(r["symbol"], r["side"], r["qty"]) for r in d2] == [("A", "sell", 3000), ("B", "sell", 1500), ("C", "buy", 10000)]
    assert book.holdings() == {"A": {"qty": 2000.0, "avg_cost": 10.0}, "C": {"qty": 10000.0, "avg_cost": 5.0}}
    assert book.cash == pytest.approx(30_000.0) and book.nav == pytest.approx(100_000.0)
    assert book.counts["fills"] == 5


def test_an_unchanged_target_is_not_traded(tmp_path, clock):
    book = _book(tmp_path, clock)
    book.walk(source_from({"A": flat(10)}), start=D0, end=D3, signal=constant({"A": 0.5}))
    assert len(ledger(tmp_path / "b", "fill")) == 1        # bought once, held since


def test_the_band_leaves_a_small_drift_alone_but_never_an_exit(tmp_path, clock):
    # A drifts up 1% a day: the target quantity shrinks by a few shares each day
    drift = [(10.0 * 1.01 ** i, 10.0 * 1.01 ** (i + 1)) for i in range(len(CAL))]
    rule = by_day({D0: {"A": 0.5}, D1: {"A": 0.5}, D2: {"A": 0.5}}, default={})
    banded = _book(tmp_path, clock, params={"min_trade_weight": 0.01})
    banded.walk(source_from({"A": drift}), start=D0, end=D4, signal=rule)
    fills = ledger(tmp_path / "b", "fill")
    assert [r["side"] for r in fills] == ["buy", "sell"]           # the entry, then the exit on D4
    assert banded.counts["small_skipped"] == 2 and banded.positions == {}
    plain = PaperBook.open(tmp_path / "p", strategy="demo", clock=clock)
    plain.walk(source_from({"A": drift}), start=D0, end=D4, signal=rule)
    assert [r["side"] for r in ledger(tmp_path / "p", "fill")] == ["buy", "sell", "sell", "sell"]
    with pytest.raises(BookError, match="min_trade_weight"):
        PaperBook.open(tmp_path / "x", strategy="demo", clock=clock, params={"min_trade_weight": 1.0})


# ── rule 5: no bar means skipped and counted ───────────────────────────────────────────────

def test_no_bar_on_the_fill_day_is_discarded_and_counted_then_filled_later(tmp_path, clock):
    src = source_from({"A": flat(10), "B": [(20, 20), None, (20, 20)] + [None] * 5})
    book = _book(tmp_path, clock)
    book.walk(src, start=D0, end=D1, signal=constant({"A": 0.5, "B": 0.3}))
    discards = ledger(tmp_path / "b", "discard")
    assert [(r["day"], r["symbol"], r["reason"]) for r in discards] == [(D1.isoformat(), "B", "no_bar")]
    assert "B" not in book.holdings() and book.counts["discarded"] == 1
    book.walk(src, start=D2, end=D2, signal=constant({"A": 0.5, "B": 0.3}))
    assert book.holdings()["B"]["qty"] == 1500.0             # the D1 intent, filled at D2's open


def test_a_bar_of_zero_or_nan_is_no_bar(tmp_path, clock):
    src = source_from({"A": [(10, 10), (0.0, 10.0), (float("nan"), 10.0), (10, 10)] + [None] * 4})
    book = _book(tmp_path, clock)
    book.walk(src, start=D0, end=D3, signal=constant({"A": 0.5}))
    assert [r["day"] for r in ledger(tmp_path / "b", "discard")] == [D1.isoformat(), D2.isoformat()]
    assert ledger(tmp_path / "b", "fill")[0]["day"] == D3.isoformat()


# ── rule 2: delisting is a terminal loss ───────────────────────────────────────────────────

def test_stale_marks_then_a_presumed_delisting(tmp_path, clock):
    src = source_from({"A": flat(10), "C": [(5, 5), (5, 5)] + [None] * 6})
    book = _book(tmp_path, clock, params={"presume_delisted_after": 2})
    book.walk(src, start=D0, end=D2, signal=constant({"A": 0.5, "C": 0.1}))
    c = book.positions["C"]
    assert c.qty == 2000 and c.stale_days == 1 and c.last_mark == 5.0 and c.last_mark_day == D1.isoformat()
    nav_stale = book.nav
    assert nav_stale == pytest.approx(book.cash + 5000 * 10 + 2000 * 5)   # the last mark, not zero, not a guess
    book.walk(src, start=D3, end=D3, signal=constant({"A": 0.5, "C": 0.1}))
    assert "C" not in book.positions and book.counts["presumed_delisted"] == 1 and book.counts["stale_marks"] == 2
    gone = ledger(tmp_path / "b", "presumed_delisted")[0]
    assert gone["symbol"] == "C" and gone["loss"] == pytest.approx(10_000.0) and gone["stale_days"] == 2
    assert book.summary()["realized_pnl"] == pytest.approx(-10_000.0)
    assert book.nav == pytest.approx(nav_stale - 10_000.0)


def test_a_delist_row_is_a_terminal_loss(tmp_path, clock):
    corp = [{"symbol": "A", "announce_date": D1, "ex_date": D2, "kind": "delist", "ratio": None}]
    src = source_from({"A": [(10, 10), (10, 10)] + [None] * 6, "B": flat(20)}, corp=corp)
    book = _book(tmp_path, clock)
    book.walk(src, start=D0, end=D2, signal=constant({"A": 0.5, "B": 0.2}))
    assert "A" not in book.positions and book.counts["delisted"] == 1
    row = ledger(tmp_path / "b", "delist")[0]
    assert row["qty"] == 5000 and row["loss"] == pytest.approx(50_000.0)
    # the D1 intent still names A; with no bar on D2 the leg is discarded, not re-bought at a guess
    assert [r["symbol"] for r in ledger(tmp_path / "b", "discard")] == ["A"]
    assert book.nav == pytest.approx(100_000.0 - 50_000.0) and book.summary()["realized_pnl"] == pytest.approx(-50_000.0)


# ── corporate actions ──────────────────────────────────────────────────────────────────────

def test_a_split_adjusts_qty_and_cost_and_keeps_nav_continuous(tmp_path, clock):
    src = source_from({"A": [(10, 10), (10, 10), (5, 5), (5, 5)] + [None] * 4},
                      corp=[{"symbol": "A", "announce_date": D0, "ex_date": D2, "kind": "forward_split", "ratio": 2.0}])
    book = _book(tmp_path, clock)
    book.walk(src, start=D0, end=D3, signal=constant({"A": 0.5}))
    assert book.holdings() == {"A": {"qty": 10000.0, "avg_cost": 5.0}}
    assert book.nav == pytest.approx(100_000.0) and len(ledger(tmp_path / "b", "fill")) == 1
    action = ledger(tmp_path / "b", "corp_action")[0]
    assert action["applied"] is True and action["ratio"] == 2.0 and book.counts["corp_applied"] == 1
    navs = [json.loads(l)["nav"] for l in (tmp_path / "b" / NAV_FILE).read_text().splitlines()]
    assert navs == pytest.approx([100_000.0] * 4)


def test_a_dividend_credits_cash_and_an_unmodelled_kind_is_recorded(tmp_path, clock):
    corp = [{"symbol": "A", "announce_date": D0, "ex_date": D2, "kind": "cash_dividend", "ratio": 0.5},
            {"symbol": "A", "announce_date": D0, "ex_date": D2, "kind": "name_change", "ratio": None},
            {"symbol": "Z", "announce_date": D0, "ex_date": D2, "kind": "forward_split", "ratio": 3.0}]
    book = _book(tmp_path, clock)
    book.walk(source_from({"A": flat(10)}, corp=corp), start=D0, end=D2, signal=constant({"A": 0.5}))
    assert book.cash == pytest.approx(50_000.0 + 5000 * 0.5)
    assert book.counts["dividends"] == 1 and book.counts["corp_ignored"] == 1
    ignored = [r for r in ledger(tmp_path / "b", "corp_action") if not r["applied"]]
    assert ignored[0]["action"] == "name_change" and ignored[0]["reason"] == "kind not modelled"
    assert book.verify()["ok"]


def test_a_missing_corp_artifact_is_reported_every_day_not_read_as_clean(tmp_path, clock):
    book = _book(tmp_path, clock)
    book.walk(source_from({"A": flat(10)}, corp_available=False), start=D0, end=D2, signal=constant({"A": 0.5}))
    assert all(r["corp_checked"] is False for r in ledger(tmp_path / "b", "mark"))
    assert book.counts["days_corp_unchecked"] == 3
    book2 = PaperBook.open(tmp_path / "c", strategy="demo", clock=clock)
    book2.walk(source_from({"A": flat(10)}), start=D0, end=D0, signal=None)
    assert ledger(tmp_path / "c", "mark")[0]["corp_checked"] is True


# ── rule 3: gross unless declared; cash is a hard limit ────────────────────────────────────

def test_fees_are_charged_when_declared_and_cash_short_is_recorded(tmp_path, clock):
    book = _book(tmp_path, clock, params={"fees_bps": 100})
    book.walk(source_from({"A": flat(10)}), start=D0, end=D1, signal=constant({"A": 1.0}))
    short = ledger(tmp_path / "b", "cash_short")[0]
    assert short["wanted_qty"] == 10000 and short["filled_qty"] == 9900
    fill = ledger(tmp_path / "b", "fill")[0]
    assert fill["qty"] == 9900 and fill["fee"] == pytest.approx(990.0)
    assert book.cash == pytest.approx(100_000 - 99_000 - 990)
    assert book.counts == {**book.counts, "cash_short": 1, "fills": 1}
    # D2 fills the D1 intent (one more share wanted, none affordable: a second cash_short, no fill);
    # the empty intent decided on D2 sells everything at D3's open
    book.walk(source_from({"A": flat(10)}), start=D2, end=D3, signal=by_day({}, default={}))
    assert book.counts["cash_short"] == 2 and book.counts["fills"] == 2
    sell = [r for r in ledger(tmp_path / "b", "fill") if r["side"] == "sell"][0]
    assert sell["day"] == D3.isoformat() and sell["qty"] == 9900
    assert sell["realized"] == pytest.approx(-990.0)      # flat price: the fee is the whole loss
    assert book.positions == {} and book.verify()["ok"]


# ── the rule fails loudly, never silently flat ─────────────────────────────────────────────

def test_a_failing_rule_is_recorded_raised_and_the_book_goes_on(tmp_path, clock):
    def rule(source, day):
        if day == D1:
            raise RuntimeError("boom")
        return {"targets": [{"symbol": "A", "weight": 0.5}]}
    book = _book(tmp_path, clock)
    with pytest.raises(BookError, match="signal failed on 2026-06-02: RuntimeError: boom"):
        book.walk(source_from({"A": flat(10)}), start=D0, end=D3, signal=rule)
    assert book.last_day == D1 and book.pending is None and book.counts["signal_errors"] == 1
    assert ledger(tmp_path / "b", "signal_error")[0]["error"] == "RuntimeError: boom"
    assert ledger(tmp_path / "b", "mark")[-1]["day"] == D1.isoformat()     # the mark was saved first
    report = book.walk(source_from({"A": flat(10)}), start=D0, end=D3, signal=rule)
    assert report == {"stepped": 2, "skipped": 2, "last_day": D3.isoformat(), "nav": book.nav}
    assert book.verify()["ok"]


def test_a_malformed_intent_is_rejected_loudly(tmp_path, clock):
    book = _book(tmp_path, clock)
    with pytest.raises(BookError, match="intent rejected on 2026-06-01: target A: weight 2.0 outside"):
        book.walk(source_from({"A": flat(10)}), start=D0, end=D0, signal=constant({"A": 2.0}))
    assert ledger(tmp_path / "b", "intent_rejected")[0]["day"] == D0.isoformat()
    assert book.counts["intents_rejected"] == 1 and book.pending is None


def test_the_guard_holds_inside_the_rule(tmp_path, clock):
    def peeking(source, day):
        source.daily_bars("A", day, day + timedelta(days=1))
        return {"targets": []}
    book = _book(tmp_path, clock)
    with pytest.raises(BookError, match="LookaheadError"):
        book.walk(source_from({"A": flat(10)}), start=D0, end=D0, signal=peeking)
    assert "lookahead blocked" in ledger(tmp_path / "b", "signal_error")[0]["error"]


def test_the_rule_is_handed_holdings_when_it_asks(tmp_path, clock):
    seen = {}

    def rule(source, day, holdings):
        seen[day] = holdings
        return {"targets": [{"symbol": "A", "weight": 0.5}]}
    book = _book(tmp_path, clock)
    book.walk(source_from({"A": flat(10)}), start=D0, end=D1, signal=rule)
    assert seen[D0] == {} and seen[D1] == {"A": {"qty": 5000.0, "avg_cost": 10.0}}


# ── days are monotonic; a walk resumes ─────────────────────────────────────────────────────

def test_days_are_monotonic(tmp_path, clock):
    src = source_from({"A": flat(10)})
    book = _book(tmp_path, clock)
    book.walk(src, start=D1, end=D1, signal=None)
    for day in (D1, D0):
        with pytest.raises(BookError, match="not after"):
            book.step(day, src, None)
    with pytest.raises(BookError, match="needs a date"):
        book.step("2026-06-03", src, None)


def test_a_walk_resumes_skipping_stepped_days_and_needs_a_bound(tmp_path, clock):
    src = source_from({"A": flat(10)})
    book = _book(tmp_path, clock)
    assert book.walk(src, start=D0, end=D2, signal=None)["stepped"] == 3
    assert book.walk(src, start=D0, end=D4, signal=None) == {"stepped": 2, "skipped": 3, "last_day": D4.isoformat(), "nav": 100_000.0}
    with pytest.raises(BookError, match="bound the replay"):
        book.walk(src, start=None, end=None, signal=None)


def test_a_step_without_a_rule_only_marks(tmp_path, clock):
    book = _book(tmp_path, clock)
    book.walk(source_from({"A": flat(10)}), start=D0, end=D1, signal=None)
    assert ledger(tmp_path / "b", "intent") == [] and book.pending is None and book.counts["steps"] == 2


# ── the ledger is the truth: chain, nav rows, intent files, summary, verify ────────────────

def test_ledger_rows_chain_and_nav_rows_and_intent_files(tmp_path, clock):
    src = source_from({"A": flat(10), "B": flat(20)})
    book = _book(tmp_path, clock)
    book.walk(src, start=D0, end=D2, signal=constant({"A": 0.5, "B": 0.3}))
    d = tmp_path / "b"
    rows = ledger(d)
    assert [r["seq"] for r in rows] == list(range(1, len(rows) + 1))
    assert rows[0]["prev"] == "0" * 64
    navs = [json.loads(l) for l in (d / NAV_FILE).read_text().splitlines()]
    assert [r["day"] for r in navs] == [D0.isoformat(), D1.isoformat(), D2.isoformat()]
    assert navs[-1]["nav"] == pytest.approx(book.nav)
    intent = json.loads((d / INTENTS_DIR / f"{D2.isoformat()}.json").read_text())
    assert intent["targets"] == book.pending["intent"]["targets"] and intent["nav_ref"] == book.pending["nav_ref"]
    assert intent["received_at"] == book.pending["received_at"]
    summary = json.loads((d / SUMMARY_FILE).read_text())
    assert summary["strategy"] == "demo" and summary["steps"] == 3 and summary["n_positions"] == 2
    assert sum(p["weight"] for p in summary["positions"]) == pytest.approx(book.invested / book.nav)
    assert summary["pending"] == {"as_of": D2.isoformat(), "n_targets": 2, "gross": 0.8,
                                  "received_at": book.pending["received_at"]}
    assert summary["chain"] == {"seq": book.seq, "head": book.head} and summary["return"] == pytest.approx(0.0)


def test_verify_recomputes_the_book_and_catches_an_edited_row(tmp_path, clock):
    src = source_from({"A": flat(10), "B": [(20, 20), (20, 22), (21, 21), (21, 21)] + [None] * 4},
                      corp=[{"symbol": "A", "announce_date": D0, "ex_date": D3, "kind": "cash_dividend", "ratio": 0.1}])
    rule = by_day({D0: {"A": 0.5, "B": 0.3}, D1: {"A": 0.4, "B": 0.3}}, default={"A": 0.4})
    book = _book(tmp_path, clock, params={"fees_bps": 5})
    book.walk(src, start=D0, end=D3, signal=rule)
    report = book.verify()
    assert report == {"ok": True, "rows": book.seq, "head": book.head, "errors": []}

    path = tmp_path / "b" / LEDGER_FILE
    lines = path.read_text("utf-8").splitlines()
    i = next(i for i, l in enumerate(lines) if '"kind":"fill"' in l)
    lines[i] = lines[i].replace('"side":"buy"', '"side":"sell"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    bad = PaperBook(tmp_path / "b", json.loads((tmp_path / "b" / STATE_FILE).read_text()), clock=clock).verify()
    assert bad["ok"] is False
    assert any("chain broken" in e for e in bad["errors"]) and any("cash:" in e for e in bad["errors"])
