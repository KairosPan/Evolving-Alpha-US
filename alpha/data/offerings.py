# alpha/data/offerings.py
#
# EDGAR offering-lifecycle typed events + the source-agnostic dilution-overhang REDUCER (P5b; spec
# docs/superpowers/specs/2026-07-13-p5b-shortinterest-offerings-design.md; design input: kairos-mining §3
# "Dilution lifecycle as typed update events"). This EXTENDS corp_actions' dilution mechanism: today ANY
# announced ATM/shelf/offering vetoes FOREVER (corp_actions.has_dilution_filing). Here an offering is an
# `updates_since`-shaped append-only log of typed lifecycle events — announce / effective / withdrawn /
# expired — each keyed on its OWN process_date (PIT). The CURRENT overhang state is a fold over the events
# known by as_of, so a withdrawn or expired shelf STOPS vetoing as of its lifecycle date, while an announce
# with no close event still vetoes (veto-forever until a close arrives).
#
#   OfferingEvent.process_date  — PIT KEY, the day THIS transition became knowable (its EDGAR filing/index
#                                 date, or a Rule-415 shelf's scheduled expiry date). A withdrawal keyed on
#                                 the RW-filing date lifts the veto exactly then and no earlier.
#
# veto-forever (corp_actions.has_dilution_filing) stays the explicit fail-closed default when this
# lifecycle feed is ABSENT — no-connector = conservative. Lifecycle data can only LIFT a veto it can prove
# is closed; it never introduces a veto the corp-actions path missed (safety-only-tightens).
from __future__ import annotations

from collections.abc import Iterable
from datetime import date as Date

import pandas as pd
from pydantic import BaseModel, ConfigDict

from alpha.data.corp_actions import DILUTION_KINDS  # noqa: F401 — the shared dilution kind vocabulary

OFFERING_EVENTS = ("announce", "effective", "withdrawn", "expired")   # the lifecycle transitions
_CLOSED_EVENTS = frozenset({"withdrawn", "expired"})                  # terminal -> the veto lifts


class OfferingEvent(BaseModel):
    """One typed lifecycle transition of one offering, PIT-keyed on its own `process_date`."""
    model_config = ConfigDict(frozen=True)
    symbol: str
    offering_id: str                    # groups one offering's events across its lifecycle (EDGAR accession/file no.)
    event: str                          # one of OFFERING_EVENTS
    kind: str                           # dilution kind: "atm" | "shelf" | "offering" (corp_actions.DILUTION_KINDS)
    process_date: Date                  # PIT KEY — when THIS event became knowable (EDGAR filing / expiry date)
    form: str | None = None             # provenance: "S-3" | "424B5" | "RW" | "EFFECT" | ...
    source: str | None = None           # "edgar" | "snapshot"


# ── source-layer PIT primitive + lifecycle reducer ──────────────────────────────────────────────────

def known_offering_events(events: Iterable[OfferingEvent], as_of: Date) -> list[OfferingEvent]:
    """Lifecycle events knowable by as_of (process_date <= as_of) — the append-only PIT log at as_of."""
    return [e for e in events if e.process_date <= as_of]


def offering_states(events: Iterable[OfferingEvent], symbol: str, as_of: Date) -> dict[str, str]:
    """Per offering_id (for `symbol`), the reduced state over events known by as_of: "closed" iff any known
    event is terminal (withdrawn/expired), else "active". A close event alone (no known announce) is still
    "closed" — no veto. This is the fold that makes a withdrawn/expired shelf drop out of the overhang."""
    known = [e for e in known_offering_events(events, as_of) if e.symbol == symbol]
    states: dict[str, str] = {}
    for e in known:
        if states.get(e.offering_id) == "closed":
            continue                                    # terminal is sticky — a later re-announce doesn't reopen
        states[e.offering_id] = "closed" if e.event in _CLOSED_EVENTS else "active"
    return states


def is_dilution_overhang(events: Iterable[OfferingEvent], symbol: str, as_of: Date) -> bool:
    """True iff any offering for `symbol` reduces to "active" at as_of — the lifecycle-aware successor to
    corp_actions.has_dilution_filing (a withdrawn/expired shelf drops out as of its own lifecycle date)."""
    return "active" in offering_states(events, symbol, as_of).values()


# ── frame <-> model converters (persistence + EDGAR normalization target) ───────────────────────────

OFFERING_COLUMNS = ["symbol", "offering_id", "event", "kind", "process_date", "form", "source"]

_OFFERING_DATE_COLS = ("process_date",)


def _clean(v):
    try:
        return None if pd.isna(v) else v
    except (TypeError, ValueError):
        return v


def events_to_frame(events: Iterable[OfferingEvent]) -> pd.DataFrame:
    rows = [e.model_dump() for e in events]
    return pd.DataFrame(rows, columns=OFFERING_COLUMNS)


def events_from_frame(df: pd.DataFrame | None) -> list[OfferingEvent]:
    if df is None or df.empty:
        return []
    out: list[OfferingEvent] = []
    for rec in df.to_dict("records"):
        data = {k: _clean(rec.get(k)) for k in OFFERING_COLUMNS}
        for c in _OFFERING_DATE_COLS:
            if data[c] is not None:
                data[c] = pd.to_datetime(data[c]).date()
        out.append(OfferingEvent(**data))
    return out
