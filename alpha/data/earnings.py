# alpha/data/earnings.py
#
# Earnings feed data models + source-agnostic PIT primitives (P5a; spec
# docs/superpowers/specs/2026-07-13-p5a-earnings-feed-design.md). Two record kinds with two lookahead-safe
# availability keys, both the analog of corp_actions' `announce_date := process_date`:
#
#   EarningsFact.filing_date        — the SEC filing (10-Q/10-K) acceptance date. A company's quarterly
#                                     numbers are knowable only as of when it FILES, never as of the fiscal
#                                     `period_end`. `filed` can only lag the real-world earnings release
#                                     (an 8-K press release may precede the 10-Q), never precede it, so it
#                                     never leaks the future. `period_end` is INFORMATIONAL, not the PIT key.
#   EarningsCalendarEntry.known_asof — the day an EXPECTED report date became knowable (a company confirms
#                                     its next date ~2-4 weeks ahead). `expected_date` may be future
#                                     (pending, like a corp action with a future ex_date); a future
#                                     `known_asof` is invisible (no lookahead).
#
# Restatements are PIT-native: the same (fiscal_year, fiscal_period) can be filed more than once (original
# 10-Q, later 10-K/A), each with its own filing_date; we keep one fact per datapoint, so `known_earnings`
# returns exactly the versions filed by any as_of. Dedup-to-latest is a read-side concern (see
# alpha/features/earnings.py::latest_actual), never baked into the PIT primitive.
from __future__ import annotations

from collections.abc import Iterable
from datetime import date as Date

import pandas as pd
from pydantic import BaseModel, ConfigDict


class EarningsFact(BaseModel):
    """One reported (or restated) quarterly result, PIT-keyed on `filing_date`."""
    model_config = ConfigDict(frozen=True)
    symbol: str
    fiscal_period: str                      # "2026Q1" / "2026FY" (fy+fp) — grouping/display
    period_end: Date                        # fiscal period end — INFORMATIONAL, *not* the PIT key
    filing_date: Date                       # PIT KEY — SEC acceptance/filed date (knowable-as-of)
    form: str | None = None                 # "10-Q" / "10-K" / "10-K/A" — provenance
    actual_eps: float | None = None         # us-gaap EarningsPerShareDiluted (fallback Basic)
    actual_revenue: float | None = None     # us-gaap Revenue* (see edgar.py mapping)
    estimate_eps: float | None = None       # analyst consensus — VENDOR only (EDGAR has none -> None)
    estimate_revenue: float | None = None
    eps_surprise: float | None = None       # actual - estimate (or vendor-supplied); None if a leg absent
    revenue_surprise: float | None = None
    source: str | None = None               # "edgar" | "vendor" | "snapshot"


class EarningsCalendarEntry(BaseModel):
    """A scheduled/expected report date, PIT-keyed on `known_asof`."""
    model_config = ConfigDict(frozen=True)
    symbol: str
    expected_date: Date                     # scheduled/expected (may be past or future vs as_of)
    known_asof: Date                        # PIT KEY — when this expected_date became knowable
    is_confirmed: bool = False              # company-confirmed vs estimated
    session: str | None = None              # "bmo" / "amc" — before/after market (vendor)
    source: str | None = None


# ── source-layer PIT primitives (mirror corp_actions.known_corporate_actions) ───────────────────────

def known_earnings(facts: Iterable[EarningsFact], as_of: Date) -> list[EarningsFact]:
    """Earnings facts whose filing is known by as_of (filing_date <= as_of) — never keyed on period_end."""
    return [f for f in facts if f.filing_date <= as_of]


def known_calendar(entries: Iterable[EarningsCalendarEntry], as_of: Date) -> list[EarningsCalendarEntry]:
    """Calendar entries knowable by as_of (known_asof <= as_of), including future expected_dates (pending)."""
    return [e for e in entries if e.known_asof <= as_of]


# ── frame <-> model converters (persistence + EDGAR/vendor normalization target) ────────────────────

FACT_COLUMNS = ["symbol", "fiscal_period", "period_end", "filing_date", "form", "actual_eps",
                "actual_revenue", "estimate_eps", "estimate_revenue", "eps_surprise",
                "revenue_surprise", "source"]
CALENDAR_COLUMNS = ["symbol", "expected_date", "known_asof", "is_confirmed", "session", "source"]

_FACT_DATE_COLS = ("period_end", "filing_date")
_CALENDAR_DATE_COLS = ("expected_date", "known_asof")


def _clean(v):
    """pandas -> python: NaN/NaT -> None, leave everything else (dates already python via _parse)."""
    try:
        return None if pd.isna(v) else v
    except (TypeError, ValueError):
        return v


def facts_to_frame(facts: Iterable[EarningsFact]) -> pd.DataFrame:
    rows = [f.model_dump() for f in facts]
    return pd.DataFrame(rows, columns=FACT_COLUMNS)


def facts_from_frame(df: pd.DataFrame | None) -> list[EarningsFact]:
    if df is None or df.empty:
        return []
    out: list[EarningsFact] = []
    for rec in df.to_dict("records"):
        data = {k: _clean(rec.get(k)) for k in FACT_COLUMNS}
        for c in _FACT_DATE_COLS:
            if data[c] is not None:
                data[c] = pd.to_datetime(data[c]).date()
        out.append(EarningsFact(**data))
    return out


def calendar_to_frame(entries: Iterable[EarningsCalendarEntry]) -> pd.DataFrame:
    rows = [e.model_dump() for e in entries]
    return pd.DataFrame(rows, columns=CALENDAR_COLUMNS)


def calendar_from_frame(df: pd.DataFrame | None) -> list[EarningsCalendarEntry]:
    if df is None or df.empty:
        return []
    out: list[EarningsCalendarEntry] = []
    for rec in df.to_dict("records"):
        data = {k: _clean(rec.get(k)) for k in CALENDAR_COLUMNS}
        for c in _CALENDAR_DATE_COLS:
            if data[c] is not None:
                data[c] = pd.to_datetime(data[c]).date()
        data["is_confirmed"] = bool(data["is_confirmed"])
        out.append(EarningsCalendarEntry(**data))
    return out
