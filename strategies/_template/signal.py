"""Intent rule for <strategy>: what the paper book should hold at the close of `day`.

The paper book (`alpaca_kit.paper`, run by the operator) calls `signal(source, day)` once per
trading day with a GuardedSource for that day - read the market through `source` only - and
fills the answer at the NEXT trading day's open (docs/backtest-rules.md rule 4). Return
{"targets": [{"symbol": ..., "weight": ...}, ...], "note": optional}: weights are fractions of
the book's value, each in [0, 1], summing to at most 1; the rest stays in cash. An empty list
means go flat. A name the fill day has no bar for is skipped and counted, never filled at a
made-up price (rule 5). A rule that raises stops the book's day loudly; it is never read as flat.

Optional: `def signal(source, day, holdings)` also receives what the book holds now
({symbol: {"qty", "avg_cost"}}) for rules that depend on the entry (stops, holding periods).

Try it by hand on a bed, from the repo root:
    ALPHA_DATA_SOURCE=snapshot ALPHA_PIT_ROOT=data/pit/2yr \
        python "strategies/<name>/signal.py" 2026-03-02
"""
from __future__ import annotations

from datetime import date


def signal(source, day: date) -> dict:
    raise NotImplementedError("write this strategy's intent rule before opening a paper book for it")


if __name__ == "__main__":
    import json
    import sys

    from alpaca_kit.firewall import AsOfGuard
    from alpaca_kit.registry import make_source
    from alpaca_kit.source import GuardedSource

    as_of = date.fromisoformat(sys.argv[1])
    print(json.dumps(signal(GuardedSource(make_source(), AsOfGuard(as_of)), as_of), indent=2))
