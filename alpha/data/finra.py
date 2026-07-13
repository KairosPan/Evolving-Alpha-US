# alpha/data/finra.py
#
# FinraSource — the live SHORT-INTEREST backend for the `short_interest` capability group (P5b; spec
# docs/superpowers/specs/2026-07-13-p5b-shortinterest-offerings-design.md). FINRA publishes a public
# bi-monthly consolidated short-interest product; this reads it via a stdlib-urllib `_get_json` seam copied
# from EdgarSource, so it is fully offline-testable by mocking that one method. It implements ONLY the
# short-interest methods; every other MarketDataSource method raises NotImplementedError (pure-swap: a
# per-capability backend, composed for `short_interest` via CompositeSource, never a whole-source vendor).
#
# PIT key = the FINRA dissemination date (ShortInterest.publication_date), NOT the settlement date the
# position is measured as-of. The dissemination date can only LAG the settlement, never precede it, so it
# never leaks the future (see alpha/data/short_interest.py). When a raw record carries no dissemination
# field, publication_date is derived from the settlement date by a CALENDAR-day cushion chosen to provably
# EXCEED FINRA's ~8-business-day dissemination in any holiday window — so a fallback-derived key is always
# >= the true dissemination (never early), even across the Christmas/New-Year double-holiday span. Being
# LATE is a safe under-claim of knowability; being early would leak, which the firewall forbids.
#
# NOTE: FINRA's concrete dissemination endpoint/auth is a documented live-integration stub — the API shape
# is public, but the exact URL/OAuth is finalized at live time. The built + tested core is the
# record->ShortInterest mapping, the settlement->publication PIT keying, and the symbol/PIT filter.
from __future__ import annotations

import os
from datetime import date as Date
from datetime import timedelta

from alpha.data.short_interest import ShortInterest, known_short_interest

# FINRA disseminates ~8 business days after settlement. Absent a per-record dissemination field, derive
# publication_date = settlement + this many CALENDAR days. 8 business days spans at most ~14 calendar days
# even across the Christmas/New-Year double-holiday window (8 business days + up to two weekends + up to two
# market holidays); 16 keeps a safety margin so the derived key is ALWAYS >= the true dissemination — never
# early (a leak), only conservatively late (a safe under-claim). Constructor-overridable at live time.
_DISSEMINATION_LAG_DAYS = 16

# Live endpoint is a documented stub (see module header); the fixed host keeps the seam offline-testable.
_SHORT_INTEREST_URL = ("https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest"
                       "?symbol={symbol}")


def _to_date(s) -> Date | None:
    return Date.fromisoformat(s[:10]) if isinstance(s, str) and s else None


def _opt_float(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _first_present(record: dict, *keys):
    """First key whose value is not None — preserves a legitimate 0/0.0 that an `or` chain would drop
    (short interest, days-to-cover, and prior position can all be a real 0)."""
    for k in keys:
        v = record.get(k)
        if v is not None:
            return v
    return None


class FinraSource:
    """FINRA consolidated short-interest backend (short_interest capability only).

    `_get_json(url)` is the one mockable seam (stdlib urllib; fixed FINRA host). FINRA fair-access wants a
    descriptive User-Agent; read `ALPHA_FINRA_USER_AGENT` (never fails at construction, so
    make_source("finra") works keyless — the UA only matters on an actual fetch).
    """

    def __init__(self, *, user_agent: str | None = None,
                 dissemination_lag_days: int | None = None) -> None:
        self._user_agent = (user_agent or os.environ.get("ALPHA_FINRA_USER_AGENT")
                            or "evolving-alpha research (set ALPHA_FINRA_USER_AGENT to a contact email)")
        self._lag_days = (_DISSEMINATION_LAG_DAYS if dissemination_lag_days is None
                          else dissemination_lag_days)

    # ── the mockable REST seam (stdlib urllib; fixed FINRA host) ────────────────────────────────────
    def _get_json(self, url: str) -> dict:
        import json
        import urllib.error
        import urllib.request
        req = urllib.request.Request(url, headers={
            "User-Agent": self._user_agent, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:   # nosec - fixed FINRA host
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode("utf-8", "replace")[:300]
            except Exception:
                body = ""
            hint = (" — FINRA gates its data API behind OAuth; set ALPHA_FINRA_USER_AGENT / credentials"
                    if e.code in (401, 403)
                    else " — rate limited, back off" if e.code == 429 else "")
            raise RuntimeError(f"FINRA GET {url} failed: HTTP {e.code} {e.reason}{hint}. "
                               f"Response: {body}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"FINRA GET {url} failed: network error ({e.reason}).") from e

    def _publication_date(self, settlement: Date, record: dict) -> Date | None:
        """Prefer a per-record dissemination field; else derive from the settlement date by the calendar-day
        cushion (provably >= the true ~8-business-day dissemination in any holiday window — never early)."""
        for key in ("disseminationDate", "publicationDate", "publication_date"):
            d = _to_date(record.get(key))
            if d is not None:
                return d
        return settlement + timedelta(days=self._lag_days) if settlement is not None else None

    def _symbol_records(self, symbol: str) -> list[ShortInterest]:
        payload = self._get_json(_SHORT_INTEREST_URL.format(symbol=symbol.upper()))
        rows = payload if isinstance(payload, list) else (payload.get("data") or payload.get("records") or [])
        out: list[ShortInterest] = []
        for r in rows:
            settlement = _to_date(_first_present(r, "settlementDate", "settlement_date"))
            publication = self._publication_date(settlement, r)
            shares_short = _opt_float(_first_present(r, "currentShortPositionQuantity", "shares_short"))
            if settlement is None or publication is None or shares_short is None:
                continue                                    # a row without the load-bearing fields -> skip
            out.append(ShortInterest(
                symbol=symbol.upper(), settlement_date=settlement, publication_date=publication,
                shares_short=shares_short,
                avg_daily_volume=_opt_float(_first_present(r, "averageDailyVolumeQuantity", "avg_daily_volume")),
                days_to_cover=_opt_float(_first_present(r, "daysToCoverQuantity", "days_to_cover")),
                shares_short_prior=_opt_float(_first_present(r, "previousShortPositionQuantity",
                                                             "shares_short_prior")),
                source="finra"))
        return sorted(out, key=lambda x: x.publication_date)

    # ── short_interest capability ────────────────────────────────────────────────────────────────────
    def short_interest_known(self, symbol: str, as_of: Date) -> list[ShortInterest]:
        return known_short_interest(self._symbol_records(symbol), as_of)

    def short_interest_available(self) -> bool:
        return True         # live feed always checkable (a fetch returns data or raises), like Alpaca corp

    # ── pure-swap: FinraSource serves ONLY short_interest; everything else raises NotImplementedError ──
    def _only_short_interest(self, *_a, **_k):
        raise NotImplementedError("FinraSource serves only the `short_interest` capability; compose it via "
                                  "CompositeSource(base, {'short_interest': FinraSource(...)})")

    trading_calendar = _only_short_interest
    daily_bars = _only_short_interest
    daily_snapshot = _only_short_interest
    corporate_actions = _only_short_interest
    corporate_actions_known = _only_short_interest
    corp_actions_available = _only_short_interest
    earnings_known = _only_short_interest
    earnings_calendar = _only_short_interest
    earnings_available = _only_short_interest
    offering_events_known = _only_short_interest
    offerings_available = _only_short_interest
