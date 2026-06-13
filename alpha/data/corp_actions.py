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
