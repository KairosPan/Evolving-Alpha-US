# alpha/data/float_feed.py
#
# FloatSource — the live FREE-FLOAT backend for the `float` capability group (P5b; spec
# docs/superpowers/specs/2026-07-13-p5b-float-feed-design.md). Reads a vendor free-float product via a
# stdlib-urllib `_get_json` seam copied from FinraSource/EdgarSource, so it is fully offline-testable by
# mocking that one method. It implements ONLY the float methods; every other MarketDataSource method raises
# NotImplementedError (pure-swap: a per-capability backend, composed for `float` via CompositeSource, never
# a whole-source vendor).
#
# PIT key = the DISCLOSURE date the float figure became knowable (FloatFact.knowable_date), NOT the period
# it measures. A per-record disclosure/filing/effective date IS the key; a record carrying ONLY its
# measurement period (no disclosure date) has NO lookahead-safe key and is DROPPED. The period ALWAYS
# precedes its disclosure (a 10-Q dated 3/31 is filed ~5/1, ~40 days later), so keying on the period would
# admit the float ~40 days EARLY = a lookahead leak. And unlike FINRA's FIXED ~8-business-day dissemination
# schedule (which lets FinraSource derive a provably-late key by a bounded calendar cushion), the SEC filing
# lag is VARIABLE/unbounded (30-90+ days by filer class, plus late NT filings), so no finite period-offset
# is provably never-early. Dropping mirrors EdgarSource dropping filed=None rows and corp_actions'
# announce_date:=process_date — always key on the LATER, knowable date (see alpha/data/float_shares.py:14).
#
# NOTE: free float has no single canonical free API — it is vendor-derived, or reconstructed from EDGAR
# cover-page shares outstanding minus Forms 3/4/5 + Rule-144 restricted. The concrete vendor endpoint/auth
# is a documented live-integration stub (the API shape is illustrative; the exact URL/auth is finalized at
# live time). The built + tested core is the record->FloatFact mapping, the disclosure->knowable PIT keying,
# and the symbol/PIT filter.
from __future__ import annotations

import os
from datetime import date as Date

from alpha.data.float_shares import FloatFact, known_float

# Live endpoint is a documented stub (see module header); the fixed host keeps the seam offline-testable.
_FLOAT_URL = "https://api.example-float-vendor.com/v1/free-float?symbol={symbol}"


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
    """First key whose value is not None — preserves a legitimate 0 an `or` chain would drop."""
    for k in keys:
        v = record.get(k)
        if v is not None:
            return v
    return None


class FloatSource:
    """Vendor free-float backend (float capability only).

    `_get_json(url)` is the one mockable seam (stdlib urllib; fixed vendor host). Reads an optional
    descriptive User-Agent from `ALPHA_FLOAT_USER_AGENT` (never fails at construction, so
    make_source("float_feed") works keyless — the UA only matters on an actual fetch).
    """

    def __init__(self, *, user_agent: str | None = None) -> None:
        self._user_agent = (user_agent or os.environ.get("ALPHA_FLOAT_USER_AGENT")
                            or "evolving-alpha research (set ALPHA_FLOAT_USER_AGENT to a contact email)")

    # ── the mockable REST seam (stdlib urllib; fixed vendor host) ───────────────────────────────────
    def _get_json(self, url: str) -> dict:
        import json
        import urllib.error
        import urllib.request
        req = urllib.request.Request(url, headers={
            "User-Agent": self._user_agent, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:   # nosec - fixed vendor host
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode("utf-8", "replace")[:300]
            except Exception:
                body = ""
            hint = (" — the float vendor gates its API behind a key; set ALPHA_FLOAT_USER_AGENT / credentials"
                    if e.code in (401, 403)
                    else " — rate limited, back off" if e.code == 429 else "")
            raise RuntimeError(f"float-vendor GET {url} failed: HTTP {e.code} {e.reason}{hint}. "
                               f"Response: {body}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"float-vendor GET {url} failed: network error ({e.reason}).") from e

    def _knowable_date(self, record: dict) -> Date | None:
        """The DISCLOSURE date this figure became knowable — the first present per-record filing/effective
        date. Returns None when the record carries NO such date: the measurement period ALONE is NOT a
        lookahead-safe key (it precedes its disclosure by the ~40-day filing lag, so keying on it would leak),
        and no finite period-offset is provably never-early (the SEC filing lag is variable/unbounded). A
        record with no disclosure date therefore has no PIT key and is dropped by _symbol_records."""
        for key in ("disclosureDate", "filingDate", "effectiveDate", "knowable_date"):
            d = _to_date(record.get(key))
            if d is not None:
                return d
        return None

    def _symbol_records(self, symbol: str) -> list[FloatFact]:
        payload = self._get_json(_FLOAT_URL.format(symbol=symbol.upper()))
        rows = payload if isinstance(payload, list) else (payload.get("data") or payload.get("records") or [])
        out: list[FloatFact] = []
        for r in rows:
            period = _to_date(_first_present(r, "periodDate", "as_of_period"))  # informational only, never the key
            knowable = self._knowable_date(r)
            free_float = _opt_float(_first_present(r, "freeFloat", "free_float"))
            if knowable is None or free_float is None:
                # No lookahead-safe disclosure date (a period alone would leak the ~40-day filing lag) or no
                # float -> DROP this row (mirrors EdgarSource dropping filed=None; PIT is fail-closed).
                continue
            out.append(FloatFact(
                symbol=symbol.upper(), free_float=free_float, knowable_date=knowable, as_of_period=period,
                shares_outstanding=_opt_float(_first_present(r, "sharesOutstanding", "shares_outstanding")),
                restricted_shares=_opt_float(_first_present(r, "restrictedShares", "restricted_shares")),
                source="vendor"))
        return sorted(out, key=lambda x: x.knowable_date)

    # ── float capability ────────────────────────────────────────────────────────────────────────────
    def float_known(self, symbol: str, as_of: Date) -> list[FloatFact]:
        return known_float(self._symbol_records(symbol), as_of)

    def float_available(self) -> bool:
        return True         # live feed always checkable (a fetch returns data or raises), like Alpaca corp

    # ── pure-swap: FloatSource serves ONLY float; everything else raises NotImplementedError ──────────
    def _only_float(self, *_a, **_k):
        raise NotImplementedError("FloatSource serves only the `float` capability; compose it via "
                                  "CompositeSource(base, {'float': FloatSource(...)})")

    trading_calendar = _only_float
    daily_bars = _only_float
    daily_snapshot = _only_float
    corporate_actions = _only_float
    corporate_actions_known = _only_float
    corp_actions_available = _only_float
    earnings_known = _only_float
    earnings_calendar = _only_float
    earnings_available = _only_float
    short_interest_known = _only_float
    short_interest_available = _only_float
    offering_events_known = _only_float
    offerings_available = _only_float
