# alpha/data/float_shares.py
#
# Free-float data model + source-agnostic PIT primitives (P5b; spec
# docs/superpowers/specs/2026-07-13-p5b-float-feed-design.md). Free float (shares outstanding minus
# insider/lockup/restricted) is a POINT-IN-TIME quantity: it changes on lockup expiries, buybacks, and
# secondary offerings, each knowable only when reported/effective.
#
#   FloatFact.knowable_date  — PIT KEY, the day the figure became knowable (the SEC filing / disclosure /
#                              effective date it was first reportable). The exact analog of corp_actions'
#                              `announce_date := process_date`, EarningsFact.filing_date, and
#                              ShortInterest.publication_date. A disclosure date can only LAG the period it
#                              describes, never precede it, so it never leaks the future.
#   FloatFact.as_of_period   — the measurement date the count DESCRIBES (e.g. a 10-Q cover date).
#                              INFORMATIONAL, *not* the PIT key: keying on it would leak the ~40-day filing
#                              lag between measurement and disclosure (the classic fundamentals backtest trap).
#
# Revisions are PIT-native: the same symbol can have several FloatFacts (a fresh count each quarter, an
# intra-quarter revision after a secondary), each with its own knowable_date; known_float returns every
# version knowable by as_of. Dedup-to-latest is a read-side concern (latest_known_float), never baked into
# the PIT primitive — the same split as earnings' latest_actual.
#
# UNIT: free_float is stored in RAW SHARES (like unadjusted prices — the honest source unit). The legacy
# StockSnapshot.free_float (US-3d) is in millions; that state channel is reconciled to shares at exactly one
# seam (SizingPolicy), never here.
from __future__ import annotations

from collections.abc import Iterable
from datetime import date as Date

import pandas as pd
from pydantic import BaseModel, ConfigDict


class FloatFact(BaseModel):
    """One free-float observation, PIT-keyed on `knowable_date` (free_float in RAW shares)."""
    model_config = ConfigDict(frozen=True)
    symbol: str
    free_float: float                       # free float in SHARES (shares outstanding - insider/restricted)
    knowable_date: Date                     # PIT KEY — day this figure became knowable (disclosure/filing)
    shares_outstanding: float | None = None  # total shares outstanding (context)
    restricted_shares: float | None = None   # insider/lockup/restricted = outstanding - free_float (context)
    as_of_period: Date | None = None         # measurement date the count describes — INFORMATIONAL, not the key
    source: str | None = None                # "vendor" | "edgar" | "snapshot"


# ── source-layer PIT primitives (mirror corp_actions.known_corporate_actions / earnings.known_earnings) ──

def known_float(records: Iterable[FloatFact], as_of: Date) -> list[FloatFact]:
    """Float figures knowable by as_of (knowable_date <= as_of) — never keyed on as_of_period."""
    return [r for r in records if r.knowable_date <= as_of]


def latest_known_float(records: Iterable[FloatFact], symbol: str, as_of: Date) -> FloatFact | None:
    """The most-recently-knowable FloatFact for `symbol` at as_of (dedup-to-latest read helper), or None.
    Ties on knowable_date resolve to the last in iteration order (a same-day revision supersedes)."""
    knowable = [r for r in known_float(records, as_of) if r.symbol == symbol]
    if not knowable:
        return None
    return max(knowable, key=lambda r: r.knowable_date)


# ── frame <-> model converters (persistence + vendor/EDGAR normalization target) ────────────────────

FLOAT_COLUMNS = ["symbol", "free_float", "knowable_date", "shares_outstanding", "restricted_shares",
                 "as_of_period", "source"]

_FLOAT_DATE_COLS = ("knowable_date", "as_of_period")


def _clean(v):
    """pandas -> python: NaN/NaT -> None, leave everything else (dates already python via parse)."""
    try:
        return None if pd.isna(v) else v
    except (TypeError, ValueError):
        return v


def float_to_frame(records: Iterable[FloatFact]) -> pd.DataFrame:
    rows = [r.model_dump() for r in records]
    return pd.DataFrame(rows, columns=FLOAT_COLUMNS)


def float_from_frame(df: pd.DataFrame | None) -> list[FloatFact]:
    if df is None or df.empty:
        return []
    out: list[FloatFact] = []
    for rec in df.to_dict("records"):
        data = {k: _clean(rec.get(k)) for k in FLOAT_COLUMNS}
        for c in _FLOAT_DATE_COLS:
            if data[c] is not None:
                data[c] = pd.to_datetime(data[c]).date()
        out.append(FloatFact(**data))
    return out
