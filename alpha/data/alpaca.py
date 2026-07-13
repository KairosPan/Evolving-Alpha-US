# alpha/data/alpaca.py
from __future__ import annotations

import os
from datetime import date as Date
from datetime import timedelta

import pandas as pd

from alpha.data.corp_actions import known_corporate_actions

_DATA_BASE = "https://data.alpaca.markets"
_BARS_COLS = ["date", "open", "high", "low", "close", "volume"]
_SNAP_COLS = ["symbol", "name", "open", "high", "low", "close", "volume", "prev_close"]
_CORP_COLS = ["symbol", "announce_date", "ex_date", "kind", "ratio"]

# corporate_actions[_known]: how far back to scan process_date for "still-known/pending" actions.
# BOUND / EXPLICIT ASSUMPTION: a pending action whose process_date precedes as_of by more than this
# window is omitted from the known set. 730d is generous (Alpaca processes corp actions within
# days/weeks of the event), but it IS a finite horizon — a reverse split processed >2y before its
# still-future ex_date would be missed. Widen here if that ever matters.
_KNOWN_LOOKBACK_DAYS = 730


def _resolve_feed() -> str:
    """Stock-bars data feed: 'iex' (free/paper default), 'sip' (paid), 'otc'/'boats'. Env override so
    free keys work out of the box without a code change."""
    return os.environ.get("ALPHA_DATA_FEED", "iex").strip().lower() or "iex"


def _normalize_bars(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=_BARS_COLS)
    out = df.copy()
    if "date" not in out.columns:                    # rename one source column, never two -> "date"
        for src in ("timestamp", "t"):
            if src in out.columns:
                out = out.rename(columns={src: "date"})
                break
    out["date"] = pd.to_datetime(out["date"]).dt.date
    for c in ("open", "high", "low", "close", "volume"):
        out[c] = pd.to_numeric(out[c], errors="coerce")
    return out[_BARS_COLS].reset_index(drop=True)


def _normalize_snapshot(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=_SNAP_COLS)
    out = df.copy()
    out["symbol"] = out["symbol"].astype(str)
    if "name" not in out.columns:
        out["name"] = ""
    for c in ("open", "high", "low", "close", "volume", "prev_close"):
        out[c] = pd.to_numeric(out[c], errors="coerce")
    return out[_SNAP_COLS].reset_index(drop=True)


# Alpaca's /v1/corporate-actions returns nested typed arrays (one list per action type), NOT a flat
# table. Map each plural type key -> the codebase's normalized `kind`. announce_date is ALWAYS the
# process_date: Alpaca exposes no announcement date, and process_date is the first day an action is
# retrievable via the API — the honest point-in-time availability key (it can only lag the real-world
# announcement, never precede it, so it never leaks the future). worthless_removal == terminal
# delisting, which the return oracle reads as "delist".
_CORP_KIND = {
    "reverse_splits": "reverse_split",
    "forward_splits": "forward_split",
    "unit_splits": "unit_split",
    "cash_dividends": "cash_dividend",
    "stock_dividends": "stock_dividend",
    "spin_offs": "spin_off",
    "cash_mergers": "cash_merger",
    "stock_mergers": "stock_merger",
    "stock_and_cash_mergers": "stock_and_cash_merger",
    "redemptions": "redemption",
    "name_changes": "name_change",
    "worthless_removals": "delist",
    "rights_distributions": "rights_distribution",
    "partial_calls": "partial_call",
    "reorganizations": "reorganization",
}
# the held/affected ticker, in priority order: acquiree for a merger, source for a spin-off / rights
# distribution, old_symbol for a unit split / name change.
_SYMBOL_KEYS = ("symbol", "acquiree_symbol", "source_symbol", "old_symbol")
# date used for `ex_date`, in priority order: mergers/reorgs key on effective_date; the rest fall back
# to process_date so the column is never null and `ex_date > as_of` (pending detection) stays meaningful.
_EXDATE_KEYS = ("ex_date", "effective_date", "process_date")


def _to_date(s) -> Date | None:
    return Date.fromisoformat(s[:10]) if isinstance(s, str) and s else None


def _corp_symbol(rec: dict) -> str | None:
    for k in _SYMBOL_KEYS:
        v = rec.get(k)
        if v:
            return str(v)
    return None


def _corp_exdate(rec: dict) -> Date | None:
    for k in _EXDATE_KEYS:
        d = _to_date(rec.get(k))
        if d is not None:
            return d
    return None


def _corp_ratio(rec: dict) -> float:
    """Informational only (no consumer keys on its value): post-split shares per pre-split share for
    splits, the cash/stock rate for rate-bearing distributions/mergers, NaN otherwise (e.g. spin_off)."""
    old, new = rec.get("old_rate"), rec.get("new_rate")
    if old not in (None, 0) and new is not None:          # split: post-split shares per pre-split share
        return float(new) / float(old)                    # <1 reverse, >1 forward
    for k in ("rate", "cash_rate", "acquirer_rate"):      # distributions/mergers: cash or stock rate
        v = rec.get(k)
        if v is not None:
            return float(v)
    return float("nan")


def _normalize_corp(payload) -> pd.DataFrame:
    """Flatten the nested Alpaca corporate-actions payload into the normalized PIT frame.

    Accepts the full `/v1/corporate-actions` response or just its `corporate_actions` object (a mapping
    of plural type name -> list of records). Output columns: symbol, announce_date (:=process_date),
    ex_date, kind, ratio. Records missing a symbol or process_date are skipped (never mislabeled).
    """
    actions = payload.get("corporate_actions", payload) if isinstance(payload, dict) else {}
    if not isinstance(actions, dict):
        actions = {}
    rows = []
    for plural, kind in _CORP_KIND.items():
        for rec in actions.get(plural, []) or []:
            symbol = _corp_symbol(rec)
            announce = _to_date(rec.get("process_date"))
            if symbol is None or announce is None:
                continue
            rows.append({"symbol": symbol, "announce_date": announce,
                         "ex_date": _corp_exdate(rec) or announce, "kind": kind,
                         "ratio": _corp_ratio(rec)})
    if not rows:
        return pd.DataFrame(columns=_CORP_COLS)
    return pd.DataFrame(rows, columns=_CORP_COLS)


class AlpacaSource:
    """Real Alpaca adapter (smoke/capture only; requires APCA_API_KEY_ID/SECRET env).

    Bars/calendar use the optional `alpaca-py` + `pandas-market-calendars` extras (lazily imported so
    a corporate-actions-only run needs neither). Corporate actions hit the documented REST endpoint
    directly (stdlib `urllib`) so the mapping is anchored to Alpaca's authoritative schema and stays
    fully offline-testable via the `_get_json` seam.
    """

    def __init__(self) -> None:
        self._key = os.environ.get("APCA_API_KEY_ID")
        self._secret = os.environ.get("APCA_API_SECRET_KEY")
        if not self._key or not self._secret:
            raise RuntimeError("missing APCA_API_KEY_ID / APCA_API_SECRET_KEY")
        self._client = None   # alpaca-py StockHistoricalDataClient, created lazily on first bars fetch

    def _bars_client(self):
        # Lazy: a missing `live` extra now raises ImportError here (first bars/calendar access) rather
        # than at construction, so a corporate-actions-only run needs no alpaca-py.
        if self._client is None:
            from alpaca.data.historical import StockHistoricalDataClient
            self._client = StockHistoricalDataClient(self._key, self._secret)
        return self._client

    def trading_calendar(self) -> list[Date]:
        import pandas_market_calendars as mcal  # lazy import
        sched = mcal.get_calendar("XNYS").schedule(start_date="2016-01-01",
                                                   end_date=pd.Timestamp.today().date().isoformat())
        return [d.date() for d in sched.index]

    def daily_bars(self, symbol: str, start: Date, end: Date) -> pd.DataFrame:
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame
        from alpaca.data.enums import Adjustment, DataFeed
        # Free/paper accounts only have the IEX feed; the bars endpoint defaults to SIP server-side and
        # 403s without an entitlement, so pin the feed (ALPHA_DATA_FEED=iex by default, set sip if subscribed).
        req = StockBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame.Day,
                               start=pd.Timestamp(start), end=pd.Timestamp(end),
                               adjustment=Adjustment.RAW, feed=DataFeed(_resolve_feed()))
        df = self._bars_client().get_stock_bars(req).df
        if df is None or df.empty:
            return pd.DataFrame(columns=_BARS_COLS)
        return _normalize_bars(df.reset_index())

    def daily_snapshot(self, day: Date) -> pd.DataFrame:
        # Smoke-only: a full-market gainer cross-section needs a broad symbol list / snapshots API.
        # Built by capture_window for the configured symbol set; not exercised in unit tests.
        raise NotImplementedError("use capture_window to build daily snapshots from bars")

    def _get_json(self, path: str, params: dict) -> dict:
        import json
        import urllib.error
        import urllib.parse
        import urllib.request
        url = f"{_DATA_BASE}{path}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={
            "APCA-API-KEY-ID": self._key, "APCA-API-SECRET-KEY": self._secret,
            "accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:   # nosec - fixed Alpaca host
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:                          # 4xx/5xx with a response body
            try:
                body = e.read().decode("utf-8", "replace")[:300]
            except Exception:
                body = ""
            hint = (" — check the APCA key's entitlement for this data product" if e.code in (401, 403)
                    else " — rate limited, back off and retry" if e.code == 429 else "")
            raise RuntimeError(f"Alpaca GET {path} failed: HTTP {e.code} {e.reason}{hint}. "
                               f"Response: {body}") from e
        except urllib.error.URLError as e:                           # DNS/connection/timeout, no response
            raise RuntimeError(f"Alpaca GET {path} failed: network error ({e.reason}).") from e

    def _fetch_corp_actions(self, start: Date, end: Date) -> dict:
        """All corporate actions with process_date in [start, end], merged across pages."""
        merged: dict[str, list] = {}
        params = {"start": start.isoformat(), "end": end.isoformat(), "limit": 1000, "sort": "asc"}
        while True:
            data = self._get_json("/v1/corporate-actions", params)
            actions = (data.get("corporate_actions") if isinstance(data, dict) else None) or {}
            for k, v in actions.items():
                merged.setdefault(k, []).extend(v or [])
            token = data.get("next_page_token") if isinstance(data, dict) else None
            if not token:
                return merged
            params = {**params, "page_token": token}

    def corporate_actions(self, start: Date, end: Date) -> pd.DataFrame:
        # ex-windowed accessor (the oracle's "split/delist during a holding window" query). PIT-correct:
        # built on corporate_actions_known(end), which bounds announce_date(==process_date) <= end, so an
        # action not yet retrievable at the as-of can never surface (no forward leak) — then keep ex_date
        # in [start, end]. This mirrors SnapshotSource (ex-filter over an announce-PIT-bounded set).
        # By design an action PROCESSED after `end` is excluded even if its ex_date is in window (it was
        # un-knowable at the as-of); so when scoring at as_of==exit this must not be the only delist
        # signal — bar disappearance handles a not-yet-processed delisting.
        corp = self.corporate_actions_known(end)
        if corp.empty:
            return corp
        return corp[(corp["ex_date"] >= start) & (corp["ex_date"] <= end)].reset_index(drop=True)

    def corporate_actions_known(self, as_of: Date) -> pd.DataFrame:
        # announce-keyed accessor: everything Alpaca had PROCESSED by as_of (process_date <= as_of),
        # INCLUDING actions whose ex_date is still in the future (pending splits). This is the
        # firewall's PIT query — never the ex-windowed one, which would drop pending future-ex splits.
        corp = _normalize_corp(self._fetch_corp_actions(as_of - timedelta(days=_KNOWN_LOOKBACK_DAYS), as_of))
        return known_corporate_actions(corp, as_of)

    def corp_actions_available(self) -> bool:
        # The live feed is always checkable: a fetch either returns real actions or raises (fails loud);
        # a successful fetch with zero actions is a true empty, never the silent MISSING the offline
        # snapshot path can hit. So corp availability is unconditionally True here.
        return True
