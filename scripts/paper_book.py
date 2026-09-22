"""paper_book - the operator's command over a strategy's paper book.

    python scripts/paper_book.py open   <strategy> [--cash 100000] [--fees-bps 0] [--presume-delisted-after 5]
    python scripts/paper_book.py walk   <strategy> --start YYYY-MM-DD --end YYYY-MM-DD
    python scripts/paper_book.py step   <strategy> [--day YYYY-MM-DD]
    python scripts/paper_book.py verify <strategy>
    python scripts/paper_book.py show   <strategy>

Every command prints one JSON object and exits 0 iff it says `ok` (the face_data contract).
`walk` and `step` read the market through `make_source()` - `ALPHA_DATA_SOURCE` /
`ALPHA_PIT_ROOT` (or `--source` / `--pit-root`) pick the bed or the live adapter, exactly as a
backtest does - wrapped day by day in the replay guard, and ask the strategy's `signal.py`
(loaded by path) once per day. `step` with no `--day` takes the source's last trading day up to
today. The book lives under `--home` (default `ALPHA_PAPER_HOME`, then `$DSH_HOME/face/paper`),
never inside the strategy directory; the strategy directory must exist under `--root/strategies`.

Read-only toward the account by construction: neither this script nor `alpaca_kit.paper` imports
an order path (a test greps both for it).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date as Date
from pathlib import Path

from alpaca_kit.paper import BookError, IntentError, PaperBook, book_dir, load_signal, paper_home
from alpaca_kit.registry import make_source

REPO_ROOT = Path(__file__).resolve().parents[1]


def _date(text: str) -> Date:
    try:
        return Date.fromisoformat(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"not a YYYY-MM-DD date: {text!r}") from exc


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("strategy", help="the strategy directory's name under strategies/")
    common.add_argument("--home", help="where books live (default ALPHA_PAPER_HOME, then $DSH_HOME/face/paper)")
    common.add_argument("--root", help="the workbench repo root (default: this checkout)")
    market = argparse.ArgumentParser(add_help=False)
    market.add_argument("--source", help="data source name (default ALPHA_DATA_SOURCE, then alpaca)")
    market.add_argument("--pit-root", help="the bed for the snapshot source (default ALPHA_PIT_ROOT)")

    parser = argparse.ArgumentParser(prog="paper_book.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("open", parents=[common], help="start a book for a strategy")
    p.add_argument("--cash", type=float, default=100_000.0, help="initial cash (default 100000)")
    p.add_argument("--fees-bps", type=float, default=0.0, help="per-side fee in basis points (default 0: gross, rule 3)")
    p.add_argument("--presume-delisted-after", type=int, default=5,
                   help="consecutive bar-less days before a held name is written to zero (rule 2)")
    p.add_argument("--min-trade-weight", type=float, default=0.0,
                   help="leave a drift smaller than this fraction of the book alone (default 0: trade every difference)")
    p = sub.add_parser("walk", parents=[common, market], help="step every trading day in a window")
    p.add_argument("--start", type=_date, required=True)
    p.add_argument("--end", type=_date, required=True)
    p = sub.add_parser("step", parents=[common, market], help="step one trading day")
    p.add_argument("--day", type=_date, help="the day (default: the source's last trading day up to today)")
    sub.add_parser("verify", parents=[common], help="recompute the chain, the cash and the positions from the ledger")
    sub.add_parser("show", parents=[common], help="print the book's summary")
    return parser


def _paths(args: argparse.Namespace) -> tuple[Path, Path]:
    root = Path(args.root).resolve() if args.root else REPO_ROOT
    strategy_dir = root / "strategies" / args.strategy
    home = Path(args.home).expanduser() if args.home else paper_home()
    directory = book_dir(home, args.strategy)          # refuses anything that is not a strategy name
    if not strategy_dir.is_dir():
        raise BookError(f"no strategy directory at {strategy_dir}")
    return strategy_dir, directory


def _last_day_up_to_today(source) -> Date:
    today = Date.today()
    days = [d for d in source.trading_calendar() if d <= today]
    if not days:
        raise BookError("the source's calendar has no trading day up to today")
    return days[-1]


def run(args: argparse.Namespace) -> dict:
    strategy_dir, directory = _paths(args)
    if args.command == "open":
        book = PaperBook.open(directory, strategy=args.strategy, initial_cash=args.cash,
                              params={"fees_bps": args.fees_bps,
                                      "presume_delisted_after": args.presume_delisted_after,
                                      "min_trade_weight": args.min_trade_weight})
        return {**book.summary(), "home": str(directory)}
    if args.command == "show":
        return {**PaperBook.load(directory).summary(), "home": str(directory)}
    if args.command == "verify":
        return {**PaperBook.load(directory).verify(), "home": str(directory)}
    # walk / step: the rule first, so a strategy without one fails before any market read
    signal = load_signal(strategy_dir)
    book = PaperBook.load(directory)
    source = make_source(args.source, pit_root=args.pit_root)
    if args.command == "walk":
        start, end = args.start, args.end
    else:
        start = end = args.day or _last_day_up_to_today(source)
    report = book.walk(source, start=start, end=end, signal=signal)
    return {"ok": True, "command": args.command, "window": [start.isoformat(), end.isoformat()],
            **report, "summary": book.summary(), "home": str(directory)}


def main(argv: list[str]) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:                    # argparse already printed why
        return int(exc.code or 0)
    try:
        payload = run(args)
    except (BookError, IntentError, ValueError, OSError, RuntimeError) as exc:
        sys.stdout.write(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False) + "\n")
        return 1
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
