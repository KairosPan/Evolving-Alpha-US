# alpha/data/short_interest.py
#
# FINRA short-interest data model + source-agnostic PIT primitive (P5b; spec
# docs/superpowers/specs/2026-07-13-p5b-shortinterest-offerings-design.md). FINRA collects each security's
# short position as of a bi-monthly SETTLEMENT date (mid-month + end-of-month), then DISSEMINATES it ~8
# business days later on a fixed public schedule.
#
#   ShortInterest.publication_date  — PIT KEY, the FINRA dissemination date. The settlement snapshot
#                                     describes a position in the past, but you could not have acted on it
#                                     until it was published; the dissemination date can only LAG the
#                                     settlement it describes, never precede it, so it never leaks the
#                                     future — the analog of corp_actions' `announce_date := process_date`.
#   ShortInterest.settlement_date   — INFORMATIONAL, *not* the PIT key (keying on it would leak ~8 trading
#                                     days of hindsight — the classic short-interest backtest trap).
#
# This is the feed that activates the dormant `short_squeeze` skill (seeds/skills.json depends_on
# ["short_interest", "days_to_cover"]) once the consume path populates MarketStock from it.
from __future__ import annotations

from collections.abc import Iterable
from datetime import date as Date

import pandas as pd
from pydantic import BaseModel, ConfigDict


class ShortInterest(BaseModel):
    """One bi-monthly FINRA short-interest observation, PIT-keyed on `publication_date`."""
    model_config = ConfigDict(frozen=True)
    symbol: str
    settlement_date: Date                   # position measured as-of — INFORMATIONAL, *not* the PIT key
    publication_date: Date                  # PIT KEY — FINRA dissemination date (knowable-as-of)
    shares_short: float                     # current short position (shares)
    avg_daily_volume: float | None = None
    days_to_cover: float | None = None      # shares_short / avg_daily_volume (FINRA supplies "daysToCover")
    shares_short_prior: float | None = None  # previous settlement's position (change% context)
    percent_of_float: float | None = None    # shares_short / float — needs the (deferred) float feed; else None
    source: str | None = None               # "finra" | "snapshot"


# ── source-layer PIT primitive (mirror corp_actions.known_corporate_actions / earnings.known_earnings) ──

def known_short_interest(records: Iterable[ShortInterest], as_of: Date) -> list[ShortInterest]:
    """Observations DISSEMINATED by as_of (publication_date <= as_of) — never keyed on settlement_date."""
    return [r for r in records if r.publication_date <= as_of]


# ── frame <-> model converters (persistence + FINRA normalization target) ───────────────────────────

SI_COLUMNS = ["symbol", "settlement_date", "publication_date", "shares_short", "avg_daily_volume",
              "days_to_cover", "shares_short_prior", "percent_of_float", "source"]

_SI_DATE_COLS = ("settlement_date", "publication_date")


def _clean(v):
    """pandas -> python: NaN/NaT -> None, leave everything else (dates already python via parse)."""
    try:
        return None if pd.isna(v) else v
    except (TypeError, ValueError):
        return v


def si_to_frame(records: Iterable[ShortInterest]) -> pd.DataFrame:
    rows = [r.model_dump() for r in records]
    return pd.DataFrame(rows, columns=SI_COLUMNS)


def si_from_frame(df: pd.DataFrame | None) -> list[ShortInterest]:
    if df is None or df.empty:
        return []
    out: list[ShortInterest] = []
    for rec in df.to_dict("records"):
        data = {k: _clean(rec.get(k)) for k in SI_COLUMNS}
        for c in _SI_DATE_COLS:
            if data[c] is not None:
                data[c] = pd.to_datetime(data[c]).date()
        out.append(ShortInterest(**data))
    return out
