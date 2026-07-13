# alpha/data/corp_actions.py
#
# Source-agnostic PIT helpers over the normalized corp-actions frame (COLUMNS below). The `announce_date`
# column is the point-in-time availability key — the day the action became known to us. For the Alpaca
# source it is populated from `process_date` (the day Alpaca processed/published the action): Alpaca's
# corporate-actions feed exposes NO real announcement date, and process_date is the earliest day an action
# is retrievable, so keying on it is conservative against announcement latency and never leaks the future
# (see alpha/data/alpaca.py:_normalize_corp). The dilution kinds (atm/shelf/offering) are NOT in Alpaca's
# feed — they are EDGAR filings, deferred to a real EDGAR source; Alpaca supplies reverse_split / delist.
from __future__ import annotations

from datetime import date as Date

import pandas as pd

COLUMNS = ["symbol", "announce_date", "ex_date", "kind", "ratio"]


def known_corporate_actions(corp: pd.DataFrame, as_of: Date) -> pd.DataFrame:
    """Corporate actions whose ANNOUNCEMENT is known by as_of (never keyed on ex_date).

    `announce_date` is the availability key (Alpaca: process_date), so this is the true PIT set of
    actions retrievable as of as_of, including those whose ex_date is still in the future (pending)."""
    if corp is None or corp.empty:
        return pd.DataFrame(columns=COLUMNS)
    return corp[corp["announce_date"] <= as_of].reset_index(drop=True)


def has_reverse_split_pending(corp: pd.DataFrame, symbol: str, as_of: Date) -> bool:
    """True iff a reverse split for `symbol` is announced (<=as_of) but not yet executed (ex_date>as_of)."""
    known = known_corporate_actions(corp, as_of)
    if known.empty:
        return False
    rs = known[(known["symbol"] == symbol) & (known["kind"] == "reverse_split")
               & (known["ex_date"] > as_of)]
    return not rs.empty


DILUTION_KINDS = ("atm", "shelf", "offering")   # ATM program / shelf registration / secondary offering


def has_dilution_filing(corp: pd.DataFrame, symbol: str, as_of: Date) -> bool:
    """True iff a dilution filing (ATM / shelf / secondary offering) for `symbol` is announced by as_of.

    Unlike a reverse split (a scheduled event gated on ex_date), an ATM/shelf is an open-ended dilution
    overhang once filed, so this reports ANY announced dilution-kind filing — i.e. it vetoes FOREVER once
    announced. This is the explicit fail-closed **default** when the offerings lifecycle feed (P5b) is
    ABSENT: with no withdrawal/expiry data we conservatively assume the overhang persists (no-connector =
    conservative). When the lifecycle feed IS present, `alpha/data/offerings.is_dilution_overhang` is the
    lifecycle-aware successor — it lets a withdrawn/expired shelf stop vetoing as of its own lifecycle date.
    PIT-safe: keyed on announce_date <= as_of via known_corporate_actions."""
    known = known_corporate_actions(corp, as_of)
    if known.empty:
        return False
    dil = known[(known["symbol"] == symbol) & (known["kind"].isin(DILUTION_KINDS))]
    return not dil.empty
