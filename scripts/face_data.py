"""face_data - the face's instrument-data producer.

Two modes, JSON to stdout: `market` (the PIT bed through production code
paths) and `account` (TradingClient read-only). Spawned by face/src/data.ts;
also runnable by hand. Read-only by construction: this module must never
import or call an order-placing code path (tests grep for it).

Exit contract, which the face maps to HTTP: 0 when the payload says `ok`
(including the keyless `available: false` account view - an absence is not a
failure), 1 with `{"ok": false, "error": ...}` on stdout otherwise.

Two stamps, because a market payload can be older than its serve: `assembled_at`
is when the bed walk actually ran, `generated_at` is when this process served it.
They differ whenever the market disk cache hits (see `_real_market`).
"""
from __future__ import annotations

import json
import math
import os
import sys
import tempfile
from datetime import date as Date
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from alpaca_kit.features.breadth import market_breadth
from alpaca_kit.firewall import AsOfGuard
from alpaca_kit.source import GuardedSource
from alpaca_kit.universe import build_universe

# Facts about the SHIPPED 2yr bed (window + maturity boundaries). Constants,
# not measurements: they describe the capture, and the page renders them as
# the maturity rail. A different bed needs different values.
BED_INFO = {
    "root": "data/pit/2yr",
    "window": {"start": "2024-06-03", "end": "2026-07-09"},
    "warmup": {
        "sma200_valid_from": "2025-03-20",
        "week52_valid_from": "2025-06-04",
        "trend_template_valid_from": "2025-06-05",
        "note": "bars start AT the window start; long-indicator readings "
                "before these dates are immature, not missing",
    },
}

SPARK_BARS = 60          # trailing closes per screen-row sparkline
_ALL_HISTORY = Date(1990, 1, 1)   # bar-fetch start: take whatever history the source holds, so the
                                  # 200DMA/52wk windows see it even when `days` covers less


def market_payload(source, days, end, *, breadth_days=60, tape_days=250,
                   screen_limit=40):
    """Assemble the /market payload. `source` implements daily_snapshot +
    daily_bars; `days` = ascending captured trading days <= end. Pure w.r.t.
    its inputs; the CLI supplies the real bed. `days` empty -> an honest
    failure payload rather than an IndexError on the tape window."""
    if not days:
        return {"ok": False, "error": "no captured days"}
    guard = GuardedSource(source, AsOfGuard(end))
    snap = guard.daily_snapshot(end)
    symbols = [] if snap is None or snap.empty else snap["symbol"].tolist()

    # One full-history fetch per symbol, guard-checked (end == as_of), reused by every window below.
    bars = {}
    for sym in symbols:
        df = guard.daily_bars(sym, _ALL_HISTORY, end)
        if df is not None and not df.empty:
            df = df.copy()
            df["date"] = pd.to_datetime(df["date"]).dt.date
            bars[sym] = df.sort_values("date").reset_index(drop=True)

    breadth_series = []
    for day in days[-breadth_days:]:
        # market_breadth is trailing-only by contract; the pre-slice is defense in depth so a past
        # day's reading can never see a later bar even if that contract ever loosened.
        sliced = {s: df[df["date"] <= day] for s, df in bars.items()}
        r = market_breadth(sliced, day)
        breadth_series.append({"date": day.isoformat(),
                               "pct_above_200dma": r.pct_above_200dma,
                               "net_new_highs": r.net_new_highs,
                               "advances": r.advances, "declines": r.declines})

    tape_days_list = days[-tape_days:]
    start_day = tape_days_list[0]
    # Membership rule: a symbol joins the composite only if it has a bar ON the window start day
    # (that close is its base). A symbol whose history starts mid-window would otherwise enter at
    # ratio 1.0 and print a phantom composite move on its entry day, so it is excluded outright.
    base = {}
    for s, df in bars.items():
        d0 = df[df["date"] == start_day]
        if not d0.empty and float(d0.iloc[0]["close"]) > 0:
            base[s] = float(d0.iloc[0]["close"])
    tape = []
    for day in tape_days_list:
        vals = []
        for s, df in bars.items():
            if s not in base:
                continue
            rows = df[df["date"] == day]
            if not rows.empty:
                vals.append(float(rows.iloc[0]["close"]) / base[s])
        tape.append({"date": day.isoformat(),
                     "level": round(100 * sum(vals) / len(vals), 2) if vals else None,
                     "n": len(vals)})

    def screen_rows(kind):
        uni = build_universe(guard, end, screen=kind)
        out = []
        for s in uni.all()[:screen_limit]:
            d = s.model_dump(mode="json")
            df = bars.get(s.symbol)
            closes = ([] if df is None
                      else df[df["date"] <= end].tail(SPARK_BARS)["close"].tolist())
            # Always a `spark` key (a screened symbol with no bars gets [], not a missing field).
            # No fabricated baseline either: a zero first close means no spark, not a 1.0 divisor.
            d["spark"] = ([round(c / closes[0], 4) for c in closes]
                          if closes and closes[0] > 0 else [])
            out.append(d)
        return out

    return {
        "ok": True,
        # BED_INFO's constants + what this assembly actually measured (merged into a fresh dict;
        # the module constant is never mutated).
        "bed": {**BED_INFO, "symbols": len(symbols), "captured_days": len(days)},
        "as_of": end.isoformat(),
        "breadth": {"series": breadth_series,
                    "note": "cross-section fixed at the as-of day's snapshot - the history is "
                            "survivorship-composed, not the cross-section that traded each day",
                    "raw": "alpaca_kit.features.breadth.market_breadth"},
        "tape": {"series": tape,
                 "note": "equal-weight composite, 100 = window start; members are the as-of day's "
                         "symbols that already had a bar on the window start day (late entrants "
                         "excluded, never spliced in at 1.0) - so it is survivorship-composed too",
                 "raw": "derived from the bed's bars"},
        "screens": {
            kind: {"rows": screen_rows(kind),
                   "raw": f"alpaca_kit.universe.build_universe(screen='{kind}')"}
            for kind in ("trend_template", "gainer")
        },
    }


# ── the account view ───────────────────────────────────────────────────────────────────────────

ORDERS_CAP = 50


def gate_state(env) -> dict:
    """The two order gates as computed fact, never as decoration.

    Gate 1 is reported the REGISTRATION way: `alpaca_kit.mcp.tools.build_tools` registers
    the mutating tools under `orders_on and has_keys`, so the flag alone (or keys alone)
    leaves them unregistered and this says so. Gate 2 - per-order human approval - is
    intent until the drill in face/README.md passes on a live face, so it reports False
    and points at the drill rather than claiming a validation nobody has run.
    """
    has_keys = bool(env.get("APCA_API_KEY_ID")) and bool(env.get("APCA_API_SECRET_KEY"))
    return {
        "gate1_registered": env.get("ALPACA_KIT_ENABLE_ORDERS") == "1" and has_keys,
        "gate1_rule": "ALPACA_KIT_ENABLE_ORDERS=1 AND APCA keys present",
        "gate2_validated": False,
        "gate2_note": "per-order human approval - intent until the drill in "
                      "face/README.md passes on a live face",
        # Mirrors alpaca_kit.account.PAPER_HOSTNAME; a test fences the two against drift.
        "paper_pin": "hostname == paper-api.alpaca.markets enforced in code",
    }


def account_payload(client_factory, env) -> dict:
    """Read-only account view. Missing keys is an honest absence, not an error, and the
    client is never constructed without them. Anything else the trading host raises
    (401, network) propagates: the CLI turns it into the error payload rather than
    dressing a broken read up as an empty account."""
    has_keys = bool(env.get("APCA_API_KEY_ID")) and bool(env.get("APCA_API_SECRET_KEY"))
    if not has_keys:
        return {"ok": True, "available": False,
                "reason": "no APCA keys in the environment"}
    client = client_factory()
    orders = client.get_orders() or []
    return {
        "ok": True,
        "available": True,
        "account": client.get_account() or {},
        "positions": client.get_positions() or [],
        # Capped, and the truncation is disclosed - dropping rows in silence would be a
        # lie by omission. The order is the trading API's own, not a claim of recency.
        "orders": orders[:ORDERS_CAP],
        "orders_truncated": len(orders) > ORDERS_CAP,
        "orders_gate": gate_state(env),
        "raw": "alpaca_kit.account.TradingClient - read methods only",
    }


# ── the CLI ────────────────────────────────────────────────────────────────────────────────────

def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(obj):
    """Replace non-finite floats (NaN/Inf) with None, recursively.

    `json.dumps` writes them as bare `NaN`/`Infinity`, which is not JSON: `JSON.parse`
    rejects it and the face would see a parse error instead of a payload. None is the
    same "no reading" the assembler already emits, and the page renders it as an em-dash.
    """
    if isinstance(obj, float):                      # numpy floats subclass float too
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    return obj


def _same_dir(a, b) -> bool:
    """Same directory, not the same string: ALPHA_PIT_ROOT is typically absolute while
    BED_INFO's root is repo-relative (resolved against the CLI's cwd, the repo root)."""
    return Path(a).resolve() == Path(b).resolve()


def _read_cache(path: Path):
    """The cached payload, or None when it is absent, unreadable, corrupt or not a
    payload-shaped object (in which case the caller reassembles and overwrites it)."""
    try:
        cached = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return cached if isinstance(cached, dict) else None


def _write_cache(path: Path, payload: dict) -> None:
    """Atomic write: a reader must never see a truncated cache file. A cache that cannot
    be written (read-only bed) is logged to stderr and otherwise ignored - the payload in
    hand is good, and failing the serve over the cache would be the worse trade."""
    tmp = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".json.tmp")
        with os.fdopen(fd, "w") as fh:
            json.dump(payload, fh, default=str, allow_nan=False)
        os.replace(tmp, path)
        tmp = None
    except (OSError, ValueError) as exc:
        print(f"face_data: market cache not written ({exc})", file=sys.stderr)
    finally:
        if tmp is not None:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def _real_market():
    """CLI assembly for the real bed. Kept out of the pure functions.

    Assembling the shipped bed walks every captured day through market_breadth and both
    screens - minutes, not seconds - so the result is cached on disk under the bed itself,
    keyed by (pit_root, as_of). A captured bed is static, so the first run pays and every
    later one is a file read. The key assumes market_payload's DEFAULT windows; a future
    caller that varies them has to key on them too.
    """
    from alpaca_kit.pit.pit_store import PITStore
    from alpaca_kit.pit.snapshot_source import SnapshotSource

    pit_root = os.environ.get("ALPHA_PIT_ROOT", BED_INFO["root"])
    store = PITStore(Path(pit_root))
    cal_days = store.get_calendar()
    if cal_days is None:
        raise RuntimeError(f"no calendar.parquet under {pit_root} - is this a captured bed?")

    shipped = _same_dir(pit_root, BED_INFO["root"])
    # The shipped bed's documented usable window is authoritative for THAT bed (CLAUDE.md:
    # reads outside it misbehave). A foreign bed gets no such bound - its snapshot files are
    # the only truth we hold about it, and silently truncating them would be a lie.
    end_bound = Date.fromisoformat(BED_INFO["window"]["end"]) if shipped else None
    days = sorted(d for d in cal_days
                  if (end_bound is None or d <= end_bound) and store.has_snapshot(d))
    if not days:
        raise RuntimeError(f"no captured snapshots under {pit_root}")
    as_of = days[-1]

    # NOTE: this lands INSIDE the bed directory, which carries a CHECKSUMS manifest -
    # `alpaca_kit.pit.integrity_check.verify_checksums` would type it `extra:`. Nothing
    # verifies a bed in this repo today (the fail-closed producers its docstring names are
    # retired), but if one returns, either skip `.face_cache/` there or move this cache
    # out of the bed.
    cache = Path(pit_root) / ".face_cache" / f"market-{as_of.isoformat()}.json"
    cached = _read_cache(cache)
    if cached is not None:
        return cached

    payload = _clean(market_payload(SnapshotSource(store), days, as_of))
    bed = payload.get("bed")
    if isinstance(bed, dict):                    # absent on the assembler's failure payload
        bed = {**bed, "root": pit_root}          # the root we actually read, not the constant
        if not shipped:
            bed.pop("warmup", None)              # BED_INFO's maturity dates describe the 2yr bed
            bed["warmup_note"] = "warmup boundaries unknown for this bed"
        payload["bed"] = bed
    # Stamped at cache-WRITE time and carried by every later hit: assembled_at says when the
    # bed walk happened, generated_at (added by main) says when this serve happened.
    payload["assembled_at"] = _utcnow()
    _write_cache(cache, payload)
    return payload


def main(argv) -> int:
    mode = argv[1] if len(argv) > 1 else ""
    try:
        if mode == "market":
            payload = _real_market()
        elif mode == "account":
            from alpaca_kit.account import TradingClient   # constructs from APCA_* env itself
            payload = account_payload(TradingClient, os.environ)
        else:
            raise RuntimeError("usage: face_data.py market|account")
        payload["generated_at"] = _utcnow()
        # Serialized in full before anything is written: a mid-stream encoder failure would
        # leave a truncated payload followed by the error JSON on the same stdout.
        out = json.dumps(_clean(payload), default=str, allow_nan=False)
    except Exception as exc:      # the face renders this JSON as the 503 body
        sys.stdout.write(json.dumps({"ok": False, "error": str(exc)}) + "\n")
        return 1
    sys.stdout.write(out + "\n")
    # The exit code IS the payload's ok flag: the face maps a nonzero code to a 503, and an
    # ok:false payload served as 200 would render as an instrument.
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
