# alpha/data/corp_actions.py
from __future__ import annotations

from datetime import date as Date

import pandas as pd

COLUMNS = ["symbol", "announce_date", "ex_date", "kind", "ratio"]


def known_corporate_actions(corp: pd.DataFrame, as_of: Date) -> pd.DataFrame:
    """Corporate actions whose ANNOUNCEMENT is known by as_of (never keyed on ex_date)."""
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
    overhang once filed, so this reports ANY announced dilution-kind filing (withdrawal/expiry lifecycle
    is deferred to a real EDGAR feed). PIT-safe: keyed on announce_date <= as_of via known_corporate_actions."""
    known = known_corporate_actions(corp, as_of)
    if known.empty:
        return False
    dil = known[(known["symbol"] == symbol) & (known["kind"].isin(DILUTION_KINDS))]
    return not dil.empty
