"""The paper book: one strategy's simulated account, kept by the engine outside the workspace.

The five honest-eval rules (docs/backtest-rules.md), applied to a book instead of a backtest:

  rule 1  every market read goes through the GuardedSource ``step`` is handed; ``walk`` builds
          it from ``replay_days`` exactly as a backtest does, and bounds the replay;
  rule 2  a delisting is a terminal loss: a ``delist`` row in the corp frame, or a held name
          with no bar for ``presume_delisted_after`` consecutive trading days, is written to
          zero and counted — never dropped;
  rule 3  returns are gross: ``fees_bps`` defaults to 0 and is a declared parameter when not;
  rule 4  an intent decided at day t's close fills at the NEXT trading day's open, never at t;
  rule 5  a leg with no bar on its fill day is skipped and counted; a held name with no bar
          keeps its last mark and counts a stale day; nothing is interpolated.

Files under ``<home>/<strategy>/``: ``ledger.jsonl`` (append-only rows, each carrying the sha256
of the previous row — the truth), ``book.json`` (the current state, rewritten atomically after
every step, carrying the chain head), ``nav.jsonl`` (one row per stepped day), ``intents/<day>.json``
(each intent as validated, with when it arrived and the value it was sized on), ``summary.json``
(the headline the face's landing page reads). ``verify`` recomputes the chain, the cash and the
positions from the ledger alone and compares them with ``book.json``.

Nothing here imports the trading host: a book never places an order (a test greps for it).
"""
from __future__ import annotations

import json
import math
import os
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import date as Date
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from alpaca_kit.integrity import canonical_json, sha256_bytes
from alpaca_kit.paper.intent import IntentError, Signal, call_signal, validate_intent

LEDGER_FILE = "ledger.jsonl"
STATE_FILE = "book.json"
NAV_FILE = "nav.jsonl"
SUMMARY_FILE = "summary.json"
INTENTS_DIR = "intents"
GENESIS = "0" * 64
DEFAULT_PARAMS: dict[str, float | int] = {"fees_bps": 0.0, "presume_delisted_after": 5, "min_trade_weight": 0.0}
COUNT_KEYS = (
    "steps", "intents", "intents_rejected", "signal_errors", "fills", "discarded", "small_skipped",
    "cash_short", "corp_applied", "corp_ignored", "days_corp_unchecked", "dividends", "delisted",
    "presumed_delisted", "stale_marks",
)
SPLIT_KINDS = frozenset({"forward_split", "reverse_split"})
DELIST_KINDS = frozenset({"delist"})
DIVIDEND_KINDS = frozenset({"cash_dividend"})
QTY_EPS = 1e-9
CASH_EPS = 1e-6
ERROR_CHARS = 500

Clock = Callable[[], datetime]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class BookError(RuntimeError):
    """The book refused: no book, a book already there, a day out of order, a rule that failed."""


@dataclass
class Position:
    qty: float
    avg_cost: float
    last_mark: float | None = None
    last_mark_day: str | None = None
    stale_days: int = 0

    @property
    def value(self) -> float:
        return self.qty * self.last_mark if self.last_mark is not None else 0.0


Bar = tuple[float, float]


def _bar_of(source: Any, symbol: str, day: Date) -> Bar | None:
    """(open, close) for one day, or None when there is no usable bar — a missing row, a NaN,
    or a non-positive price all count as 'no bar' (rule 5), never as a number."""
    df = source.daily_bars(symbol, day, day)
    if df is None or getattr(df, "empty", True):
        return None
    row = df.iloc[-1]
    try:
        o, c = float(row["open"]), float(row["close"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (math.isfinite(o) and math.isfinite(c)) or o <= 0.0 or c <= 0.0:
        return None
    return o, c


def _ratio_of(value: Any) -> float:
    try:
        r = float(value)
    except (TypeError, ValueError):
        return math.nan
    return r


def _write_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


class PaperBook:
    """One strategy's book. Construct through ``open`` or ``load``."""

    def __init__(self, directory: Path, state: dict[str, Any], *, clock: Clock = _utcnow) -> None:
        self.dir = Path(directory)
        self._s = state
        self._clock = clock
        self.positions: dict[str, Position] = {
            sym: Position(**p) for sym, p in state.get("positions", {}).items()
        }

    # ── construction ─────────────────────────────────────────────────────────────────────────
    @classmethod
    def open(cls, directory: Path, *, strategy: str, initial_cash: float = 100_000.0,
             params: Mapping[str, Any] | None = None, clock: Clock = _utcnow) -> "PaperBook":
        directory = Path(directory)
        if (directory / STATE_FILE).exists() or (directory / LEDGER_FILE).exists():
            raise BookError(f"a book already exists at {directory}")
        cash = float(initial_cash)
        if not (math.isfinite(cash) and cash > 0.0):
            raise BookError("initial_cash must be a positive number")
        p = cls._params({**DEFAULT_PARAMS, **dict(params or {})})
        directory.mkdir(parents=True, exist_ok=True)
        (directory / INTENTS_DIR).mkdir(exist_ok=True)
        state: dict[str, Any] = {
            "strategy": strategy, "created": _iso(clock()), "initial_cash": cash, "params": p,
            "cash": cash, "positions": {}, "pending": None, "last_day": None,
            "peak_nav": cash, "max_drawdown": 0.0, "realized_pnl": 0.0,
            "counts": {k: 0 for k in COUNT_KEYS}, "seq": 0, "head": GENESIS,
        }
        book = cls(directory, state, clock=clock)
        book._append([{"kind": "open", "day": None, "strategy": strategy,
                       "initial_cash": cash, "params": p}])
        book._save()
        return book

    @classmethod
    def load(cls, directory: Path, *, clock: Clock = _utcnow) -> "PaperBook":
        directory = Path(directory)
        path = directory / STATE_FILE
        if not path.is_file():
            raise BookError(f"no book at {directory} (open one first)")
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise BookError(f"{path} is unreadable: {exc}") from exc
        book = cls(directory, state, clock=clock)
        seq, head = book._ledger_tail()
        if seq != state.get("seq") or head != state.get("head"):
            raise BookError(f"the ledger and {STATE_FILE} disagree at {directory} "
                            "(an interrupted step?) - run verify")
        return book

    @staticmethod
    def _params(p: dict[str, Any]) -> dict[str, float | int]:
        fees = float(p.get("fees_bps", 0.0))
        if not (math.isfinite(fees) and fees >= 0.0):
            raise BookError("fees_bps must be a non-negative number")
        presume = p.get("presume_delisted_after", 5)
        if isinstance(presume, bool) or not isinstance(presume, int) or presume < 1:
            raise BookError("presume_delisted_after must be a positive integer")
        band = float(p.get("min_trade_weight", 0.0))
        if not (math.isfinite(band) and 0.0 <= band < 1.0):
            raise BookError("min_trade_weight must be a fraction in [0, 1)")
        return {"fees_bps": fees, "presume_delisted_after": presume, "min_trade_weight": band}

    # ── views ────────────────────────────────────────────────────────────────────────────────
    @property
    def strategy(self) -> str:
        return str(self._s["strategy"])

    @property
    def params(self) -> Mapping[str, Any]:
        return self._s["params"]

    @property
    def counts(self) -> Mapping[str, int]:
        return self._s["counts"]

    @property
    def cash(self) -> float:
        return float(self._s["cash"])

    @property
    def invested(self) -> float:
        return float(sum(p.value for p in self.positions.values()))

    @property
    def nav(self) -> float:
        return self.cash + self.invested

    @property
    def pending(self) -> dict[str, Any] | None:
        return self._s.get("pending")

    @property
    def last_day(self) -> Date | None:
        d = self._s.get("last_day")
        return Date.fromisoformat(d) if d else None

    @property
    def head(self) -> str:
        return str(self._s["head"])

    @property
    def seq(self) -> int:
        return int(self._s["seq"])

    def holdings(self) -> dict[str, dict[str, float]]:
        """What a rule may know about the book: quantity and entry, nothing else."""
        return {sym: {"qty": p.qty, "avg_cost": p.avg_cost} for sym, p in sorted(self.positions.items())}

    # ── the day ──────────────────────────────────────────────────────────────────────────────
    def step(self, day: Date, source: Any, signal: Signal | None = None) -> dict[str, Any]:
        """One trading day, in this order: corporate actions with ex-date ``day`` on held names;
        the pending intent filled at ``day``'s open; every held name marked at ``day``'s close;
        then the rule asked for the next intent. ``source`` is the GuardedSource for ``day``.

        A rule that raises, or answers with a malformed intent, is recorded and re-raised as
        ``BookError`` after the mark is saved: the day is never silently read as flat."""
        if not isinstance(day, Date):
            raise BookError("step needs a date")
        last = self.last_day
        if last is not None and day <= last:
            raise BookError(f"day {day} is not after the book's last day {last}")
        D = day.isoformat()
        counts = self._s["counts"]
        events: list[dict[str, Any]] = []
        bars: dict[str, Bar | None] = {}

        checked = bool(source.corp_actions_available()) if hasattr(source, "corp_actions_available") else False
        if not checked:
            counts["days_corp_unchecked"] += 1
        if self.positions:
            self._apply_corp_actions(day, D, source, events)
        filled = self._fill_pending(day, D, source, bars, events)
        stale = self._mark(day, D, source, bars, events)

        invested = self.invested
        nav = self.cash + invested
        peak = max(float(self._s["peak_nav"]), nav)
        drawdown = nav / peak - 1.0 if peak > 0 else 0.0
        self._s["peak_nav"] = peak
        self._s["max_drawdown"] = min(float(self._s["max_drawdown"]), drawdown)
        events.append({"kind": "mark", "day": D, "nav": nav, "cash": self.cash, "invested": invested,
                       "n_positions": len(self.positions), "drawdown": drawdown,
                       "corp_checked": checked, "stale": stale})
        counts["steps"] += 1
        self._s["last_day"] = D
        self._append(events)
        with open(self.dir / NAV_FILE, "a", encoding="utf-8") as f:
            f.write(canonical_json({"day": D, "nav": nav, "cash": self.cash, "invested": invested,
                                    "n_positions": len(self.positions), "drawdown": drawdown,
                                    "realized_pnl": float(self._s["realized_pnl"])}) + "\n")
        self._save()

        intent_row: dict[str, Any] | None = None
        if signal is not None:
            intent_row = self._ask(day, D, source, signal, nav)

        return {"day": D, "nav": nav, "cash": self.cash, "invested": invested,
                "n_positions": len(self.positions), "fills": filled, "drawdown": drawdown,
                "intent": intent_row}

    def walk(self, source: Any, *, start: Date | None, end: Date | None,
             signal: Signal | None) -> dict[str, Any]:
        """Step every trading day in [start, end] through ``replay_days`` (rule 1: the bound is
        required, the guard is built per day). Days the book has already stepped are skipped and
        counted, so a walk can extend a book; an error stops it where it stands."""
        from alpaca_kit.replay import replay_days
        if start is None or end is None:
            raise BookError("walk needs start and end - bound the replay (docs/backtest-rules.md rule 1)")
        stepped = skipped = 0
        for day, guarded in replay_days(source, start=start, end=end):
            last = self.last_day
            if last is not None and day <= last:
                skipped += 1
                continue
            self.step(day, guarded, signal)
            stepped += 1
        last_day = self.last_day
        return {"stepped": stepped, "skipped": skipped,
                "last_day": last_day.isoformat() if last_day else None, "nav": self.nav}

    # ── the three phases ─────────────────────────────────────────────────────────────────────
    def _bar_for(self, source: Any, symbol: str, day: Date, bars: dict[str, Bar | None]) -> Bar | None:
        if symbol not in bars:
            bars[symbol] = _bar_of(source, symbol, day)
        return bars[symbol]

    def _apply_corp_actions(self, day: Date, D: str, source: Any, events: list[dict[str, Any]]) -> None:
        counts = self._s["counts"]
        df = source.corporate_actions(day, day)
        if df is None or getattr(df, "empty", True):
            return
        seen: set[tuple[str, str, str]] = set()
        for rec in df.to_dict(orient="records"):
            sym = str(rec.get("symbol", ""))
            pos = self.positions.get(sym)
            if pos is None:
                continue
            kind = str(rec.get("kind", ""))
            ratio = _ratio_of(rec.get("ratio"))
            key = (sym, kind, repr(ratio))
            if key in seen:                      # the same action twice in one frame is one action
                continue
            seen.add(key)
            usable = math.isfinite(ratio) and ratio > 0.0
            if kind in SPLIT_KINDS and usable:
                pos.qty *= ratio
                pos.avg_cost /= ratio
                if pos.last_mark is not None:
                    pos.last_mark /= ratio
                events.append({"kind": "corp_action", "day": D, "symbol": sym, "action": kind,
                               "ratio": ratio, "applied": True, "qty": pos.qty, "avg_cost": pos.avg_cost})
                counts["corp_applied"] += 1
            elif kind in DELIST_KINDS:
                loss = pos.qty * pos.avg_cost
                self._s["realized_pnl"] = float(self._s["realized_pnl"]) - loss
                events.append({"kind": "delist", "day": D, "symbol": sym, "qty": pos.qty,
                               "avg_cost": pos.avg_cost, "last_mark": pos.last_mark, "loss": loss})
                counts["delisted"] += 1
                del self.positions[sym]
            elif kind in DIVIDEND_KINDS and usable:
                amount = pos.qty * ratio
                self._s["cash"] = self.cash + amount
                events.append({"kind": "dividend", "day": D, "symbol": sym, "rate": ratio,
                               "qty": pos.qty, "amount": amount})
                counts["dividends"] += 1
            else:
                reason = "kind not modelled" if kind not in (SPLIT_KINDS | DIVIDEND_KINDS) else "no usable ratio"
                events.append({"kind": "corp_action", "day": D, "symbol": sym, "action": kind,
                               "ratio": ratio if math.isfinite(ratio) else None, "applied": False,
                               "reason": reason})
                counts["corp_ignored"] += 1

    def _fill_pending(self, day: Date, D: str, source: Any, bars: dict[str, Bar | None],
                      events: list[dict[str, Any]]) -> int:
        pending = self._s.get("pending")
        if pending is None:
            return 0
        counts = self._s["counts"]
        intent = pending["intent"]
        nav_ref = float(pending["nav_ref"])
        fees = float(self.params["fees_bps"]) / 10_000.0
        band = float(self.params.get("min_trade_weight", 0.0)) * nav_ref
        targets = {t["symbol"]: float(t["weight"]) for t in intent["targets"]}
        plan: list[tuple[str, float, float]] = []
        for sym in sorted(set(targets) | set(self.positions)):
            wanted = targets.get(sym, 0.0)
            held = self.positions.get(sym)
            held_qty = held.qty if held is not None else 0.0
            bar = self._bar_for(source, sym, day, bars)
            if bar is None:
                if held is None and wanted <= 0.0:
                    continue                     # nothing to do, nothing to count
                events.append({"kind": "discard", "day": D, "symbol": sym, "reason": "no_bar",
                               "weight": wanted, "held_qty": held_qty})
                counts["discarded"] += 1
                continue
            o, _ = bar
            target_qty = float(math.floor(wanted * nav_ref / o))
            delta = target_qty - held_qty
            if abs(delta) < QTY_EPS:
                continue
            # the band: a drift smaller than min_trade_weight of the book is left alone, and
            # counted - but never a leg that empties a position (a 0 target is an exit)
            if target_qty > 0.0 and abs(delta) * o < band:
                counts["small_skipped"] += 1
                continue
            plan.append((sym, delta, o))

        n_fills = 0
        for sym, delta, o in (p for p in plan if p[1] < 0):      # sells first: they fund the buys
            qty = -delta
            pos = self.positions[sym]
            proceeds = qty * o
            fee = proceeds * fees
            realized = (o - pos.avg_cost) * qty - fee
            self._s["cash"] = self.cash + proceeds - fee
            self._s["realized_pnl"] = float(self._s["realized_pnl"]) + realized
            pos.qty -= qty
            events.append({"kind": "fill", "day": D, "symbol": sym, "side": "sell", "qty": qty,
                           "price": o, "fee": fee, "realized": realized})
            n_fills += 1
            if pos.qty < QTY_EPS:
                del self.positions[sym]
        for sym, delta, o in (p for p in plan if p[1] > 0):
            qty = delta
            cash = self.cash
            unit = o * (1.0 + fees)
            if qty * unit > cash + CASH_EPS:
                afford = float(math.floor(cash / unit)) if unit > 0 else 0.0
                events.append({"kind": "cash_short", "day": D, "symbol": sym, "wanted_qty": qty,
                               "filled_qty": afford, "cash": cash, "price": o})
                counts["cash_short"] += 1
                qty = afford
                if qty <= 0.0:
                    continue
            fee = qty * o * fees
            self._s["cash"] = cash - qty * o - fee
            pos = self.positions.get(sym)
            if pos is None:
                self.positions[sym] = Position(qty=qty, avg_cost=o)
            else:
                pos.avg_cost = (pos.qty * pos.avg_cost + qty * o) / (pos.qty + qty)
                pos.qty += qty
            events.append({"kind": "fill", "day": D, "symbol": sym, "side": "buy", "qty": qty,
                           "price": o, "fee": fee})
            n_fills += 1
        counts["fills"] += n_fills
        events.append({"kind": "intent_filled", "day": D, "as_of": intent["as_of"],
                       "fills": n_fills, "nav_ref": nav_ref})
        self._s["pending"] = None
        return n_fills

    def _mark(self, day: Date, D: str, source: Any, bars: dict[str, Bar | None],
              events: list[dict[str, Any]]) -> int:
        counts = self._s["counts"]
        presume = int(self.params["presume_delisted_after"])
        stale = 0
        for sym in sorted(self.positions):
            pos = self.positions[sym]
            bar = self._bar_for(source, sym, day, bars)
            if bar is None:
                pos.stale_days += 1
                counts["stale_marks"] += 1
                stale += 1
                if pos.stale_days >= presume:
                    loss = pos.qty * pos.avg_cost
                    self._s["realized_pnl"] = float(self._s["realized_pnl"]) - loss
                    events.append({"kind": "presumed_delisted", "day": D, "symbol": sym, "qty": pos.qty,
                                   "avg_cost": pos.avg_cost, "last_mark": pos.last_mark,
                                   "last_mark_day": pos.last_mark_day, "stale_days": pos.stale_days,
                                   "loss": loss})
                    counts["presumed_delisted"] += 1
                    del self.positions[sym]
                continue
            _, c = bar
            pos.last_mark = c
            pos.last_mark_day = D
            pos.stale_days = 0
        return stale

    def _ask(self, day: Date, D: str, source: Any, signal: Signal, nav: float) -> dict[str, Any]:
        counts = self._s["counts"]
        try:
            raw = call_signal(signal, source, day, self.holdings())
        except Exception as exc:                # noqa: BLE001 - the rule's failure, whatever it is, is recorded
            msg = f"{type(exc).__name__}: {exc}"[:ERROR_CHARS]
            self._append([{"kind": "signal_error", "day": D, "error": msg}])
            counts["signal_errors"] += 1
            self._save()
            raise BookError(f"signal failed on {D}: {msg}") from exc
        try:
            intent = validate_intent(raw, day)
        except IntentError as exc:
            msg = str(exc)[:ERROR_CHARS]
            self._append([{"kind": "intent_rejected", "day": D, "error": msg}])
            counts["intents_rejected"] += 1
            self._save()
            raise BookError(f"intent rejected on {D}: {msg}") from exc
        received = _iso(self._clock())
        body = {**intent.to_dict(), "received_at": received, "nav_ref": nav}
        _write_atomic(self.dir / INTENTS_DIR / f"{D}.json", json.dumps(body, indent=2, ensure_ascii=False) + "\n")
        self._s["pending"] = {"intent": intent.to_dict(), "received_at": received, "nav_ref": nav}
        row = {"kind": "intent", "day": D, "as_of": D, "n_targets": len(intent.targets),
               "gross": intent.gross, "note": intent.note, "received_at": received, "nav_ref": nav}
        self._append([row])
        counts["intents"] += 1
        self._save()
        return {"as_of": D, "n_targets": len(intent.targets), "gross": intent.gross}

    # ── files ────────────────────────────────────────────────────────────────────────────────
    def _append(self, rows: list[dict[str, Any]]) -> None:
        """Append rows to the ledger, each chained to the previous by hash. The hash is of the
        canonical line exactly as written, so ``verify`` can recompute it from the file."""
        at = _iso(self._clock())
        head = self.head
        seq = self.seq
        with open(self.dir / LEDGER_FILE, "a", encoding="utf-8") as f:
            for row in rows:
                seq += 1
                line = canonical_json({"seq": seq, "prev": head, "at": at, **row})
                head = sha256_bytes(line.encode("utf-8"))
                f.write(line + "\n")
        self._s["seq"] = seq
        self._s["head"] = head

    def _ledger_tail(self) -> tuple[int, str]:
        path = self.dir / LEDGER_FILE
        seq, head = 0, GENESIS
        if not path.is_file():
            return seq, head
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                if not line:
                    continue
                seq += 1
                head = sha256_bytes(line.encode("utf-8"))
        return seq, head

    def _save(self) -> None:
        self._s["positions"] = {sym: asdict(p) for sym, p in sorted(self.positions.items())}
        _write_atomic(self.dir / STATE_FILE, json.dumps(self._s, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
        _write_atomic(self.dir / SUMMARY_FILE, json.dumps(self.summary(), indent=2, ensure_ascii=False) + "\n")

    def summary(self) -> dict[str, Any]:
        """The headline: what the landing page shows, what ``show`` prints."""
        nav = self.nav
        invested = self.invested
        initial = float(self._s["initial_cash"])
        peak = float(self._s["peak_nav"])
        pending = self._s.get("pending")
        positions = []
        for sym, p in sorted(self.positions.items()):
            positions.append({"symbol": sym, "qty": p.qty, "avg_cost": p.avg_cost, "last_mark": p.last_mark,
                              "last_mark_day": p.last_mark_day, "value": p.value,
                              "weight": (p.value / nav) if nav > 0 else 0.0, "stale_days": p.stale_days})
        return {
            "ok": True,
            "strategy": self.strategy,
            "created": self._s["created"],
            "initial_cash": initial,
            "params": dict(self.params),
            "last_day": self._s.get("last_day"),
            "steps": int(self.counts["steps"]),
            "nav": nav,
            "cash": self.cash,
            "invested": invested,
            "return": (nav / initial - 1.0) if initial > 0 else 0.0,
            "peak_nav": peak,
            "drawdown": (nav / peak - 1.0) if peak > 0 else 0.0,
            "max_drawdown": float(self._s["max_drawdown"]),
            "realized_pnl": float(self._s["realized_pnl"]),
            "n_positions": len(self.positions),
            "positions": positions,
            "pending": None if pending is None else {
                "as_of": pending["intent"]["as_of"], "n_targets": len(pending["intent"]["targets"]),
                "gross": float(sum(float(t["weight"]) for t in pending["intent"]["targets"])),
                "received_at": pending["received_at"],
            },
            "counts": dict(self.counts),
            "chain": {"seq": self.seq, "head": self.head},
            "updated_at": _iso(self._clock()),
        }

    # ── verification ─────────────────────────────────────────────────────────────────────────
    def verify(self) -> dict[str, Any]:
        """Recompute the chain, then the cash and the positions from the ledger's own rows, and
        compare with ``book.json`` and ``nav.jsonl``. Reports every disagreement it finds."""
        errors: list[str] = []
        seq, head = 0, GENESIS
        cash: float | None = None
        qty: dict[str, float] = {}
        marks: list[tuple[str, float]] = []
        path = self.dir / LEDGER_FILE
        if not path.is_file():
            return {"ok": False, "rows": 0, "head": head, "errors": [f"no {LEDGER_FILE}"]}
        with open(path, encoding="utf-8") as f:
            for n, raw in enumerate(f, 1):
                line = raw.rstrip("\n")
                try:
                    row = json.loads(line)
                except ValueError:
                    errors.append(f"row {n}: not JSON")
                    break
                if row.get("seq") != n:
                    errors.append(f"row {n}: seq {row.get('seq')!r}")
                if row.get("prev") != head:
                    errors.append(f"row {n}: chain broken")
                if canonical_json(row) != line:
                    errors.append(f"row {n}: not canonical (edited?)")
                head = sha256_bytes(line.encode("utf-8"))
                seq = n
                kind = row.get("kind")
                sym = str(row.get("symbol", ""))
                try:
                    if kind == "open":
                        cash = float(row["initial_cash"])
                    elif kind == "fill":
                        q, price, fee = float(row["qty"]), float(row["price"]), float(row.get("fee", 0.0))
                        if cash is None:
                            errors.append(f"row {n}: fill before open")
                            cash = 0.0
                        if row.get("side") == "buy":
                            cash -= q * price + fee
                            qty[sym] = qty.get(sym, 0.0) + q
                        else:
                            cash += q * price - fee
                            qty[sym] = qty.get(sym, 0.0) - q
                            if abs(qty[sym]) < QTY_EPS:
                                del qty[sym]
                    elif kind == "corp_action" and row.get("applied"):
                        qty[sym] = qty.get(sym, 0.0) * float(row["ratio"])
                    elif kind == "dividend":
                        cash = (cash or 0.0) + float(row["amount"])
                    elif kind in ("delist", "presumed_delisted"):
                        qty.pop(sym, None)
                    elif kind == "mark":
                        marks.append((str(row["day"]), float(row["nav"])))
                except (KeyError, TypeError, ValueError) as exc:
                    errors.append(f"row {n}: {kind} row malformed ({exc})")
        if seq != self.seq or head != self.head:
            errors.append(f"{STATE_FILE} says seq {self.seq} head {self.head[:12]}…, the ledger says {seq} {head[:12]}…")
        if cash is None:
            errors.append("no open row")
        elif abs(cash - self.cash) > CASH_EPS:
            errors.append(f"cash: ledger {cash:.6f} vs {STATE_FILE} {self.cash:.6f}")
        held = {sym: p.qty for sym, p in self.positions.items()}
        for sym in sorted(set(qty) | set(held)):
            a, b = qty.get(sym), held.get(sym)
            if a is None or b is None or abs(a - b) > QTY_EPS:
                errors.append(f"{sym}: ledger qty {a} vs {STATE_FILE} {b}")
        nav_path = self.dir / NAV_FILE
        rows: list[tuple[str, float]] = []
        if nav_path.is_file():
            with open(nav_path, encoding="utf-8") as f:
                for raw in f:
                    if raw.strip():
                        try:
                            r = json.loads(raw)
                            rows.append((str(r["day"]), float(r["nav"])))
                        except (ValueError, KeyError, TypeError):
                            errors.append(f"{NAV_FILE}: a row is malformed")
        if len(rows) != len(marks):
            errors.append(f"{NAV_FILE} has {len(rows)} rows, the ledger {len(marks)} marks")
        else:
            for (d1, n1), (d2, n2) in zip(rows, marks):
                if d1 != d2 or abs(n1 - n2) > CASH_EPS:
                    errors.append(f"{NAV_FILE} {d1} {n1} vs ledger mark {d2} {n2}")
        return {"ok": not errors, "rows": seq, "head": head, "errors": errors}
