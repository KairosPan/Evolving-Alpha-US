# alpha/data/edgar.py
#
# EdgarSource — the live EARNINGS backend for the `earnings` capability group (P5a; spec
# docs/superpowers/specs/2026-07-13-p5a-earnings-feed-design.md). Reads SEC EDGAR's free XBRL
# company-facts API (data.sec.gov, no key) via a stdlib-urllib `_get_json` seam copied from
# AlpacaSource, so it is fully offline-testable by mocking that one method. It implements ONLY the
# earnings methods; every other MarketDataSource method raises NotImplementedError (pure-swap: this is a
# per-capability backend, composed for `earnings` via CompositeSource, never a whole-source vendor).
#
# PIT key = the SEC `filed` date (EarningsFact.filing_date): a company's quarterly numbers are knowable
# only as of when it FILES, never as of the fiscal period `end`. `filed` can only lag the real earnings
# release (an 8-K press release may precede the 10-Q), never precede it — so it never leaks the future.
from __future__ import annotations

import os
from datetime import date as Date
from datetime import timedelta

from alpha.data.earnings import (
    EarningsCalendarEntry,
    EarningsFact,
    known_calendar,
    known_earnings,
)

_FACTS_URL = "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:010d}/us-gaap/{concept}.json"
_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

# Diluted preferred (fallback basic); revenue tag drifted across years, tried in order. First concept
# that yields period rows wins.
_EPS_CONCEPTS = ("EarningsPerShareDiluted", "EarningsPerShareBasic")
_EPS_UNIT = "USD/shares"
_REV_CONCEPTS = ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet")
_REV_UNIT = "USD"

# Duration filter: keep a single-quarter row (~13 weeks) or a full-year row, drop 6-mo/9-mo YTD-cumulative
# rows that share the same us-gaap tag (the classic XBRL flow-period wrinkle). Documented heuristic.
_QUARTER_MIN, _QUARTER_MAX = 75, 100
_ANNUAL_MIN, _ANNUAL_MAX = 350, 380
_NEXT_QUARTER_DAYS = 91                     # naive forward-estimate spacing for the derived calendar


class EdgarNotFound(RuntimeError):
    """A concept/CIK is absent on EDGAR (HTTP 404) — not an error, the caller tries the next concept."""


def _to_date(s) -> Date | None:
    return Date.fromisoformat(s[:10]) if isinstance(s, str) and s else None


def _is_period_row(start: Date | None, end: Date | None, fp: str | None) -> bool:
    if start is None or end is None:
        return False
    days = (end - start).days
    if _QUARTER_MIN <= days <= _QUARTER_MAX:
        return True
    return fp == "FY" and _ANNUAL_MIN <= days <= _ANNUAL_MAX


class EdgarSource:
    """SEC EDGAR earnings-facts backend (earnings capability only).

    `cik_map` maps TICKER -> CIK int (injected in tests — no network). When omitted, the ticker->CIK map
    is fetched lazily from company_tickers.json via `_get_json`. `earnings_calendar(as_of)` derives a
    (PIT-safe) calendar from filings over `universe` (defaults to the cik_map's tickers) — a broad
    confirmed forward calendar with sessions/estimates is a separate vendor backend on the same seam.
    """

    def __init__(self, *, cik_map: dict[str, int] | None = None,
                 universe: list[str] | None = None, user_agent: str | None = None) -> None:
        self._cik_map = {k.upper(): int(v) for k, v in cik_map.items()} if cik_map else None
        self._universe = [s.upper() for s in universe] if universe is not None else None
        # SEC fair-access requires a descriptive User-Agent (ideally a contact email). Never fails at
        # construction (so make_source("edgar") works keyless); only matters on an actual fetch.
        self._user_agent = (user_agent or os.environ.get("ALPHA_EDGAR_USER_AGENT")
                            or "evolving-alpha research (set ALPHA_EDGAR_USER_AGENT to a contact email)")

    # ── the mockable REST seam (stdlib urllib; fixed SEC host) ──────────────────────────────────────
    def _get_json(self, url: str) -> dict:
        import json
        import urllib.error
        import urllib.request
        req = urllib.request.Request(url, headers={
            "User-Agent": self._user_agent, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:   # nosec - fixed SEC host
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise EdgarNotFound(url) from e
            try:
                body = e.read().decode("utf-8", "replace")[:300]
            except Exception:
                body = ""
            hint = (" — SEC blocks requests without a descriptive User-Agent; set ALPHA_EDGAR_USER_AGENT "
                    "to a contact email" if e.code in (401, 403)
                    else " — rate limited (SEC caps ~10 req/s), back off" if e.code == 429 else "")
            raise RuntimeError(f"EDGAR GET {url} failed: HTTP {e.code} {e.reason}{hint}. "
                               f"Response: {body}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"EDGAR GET {url} failed: network error ({e.reason}).") from e

    def _cik(self, symbol: str) -> int | None:
        sym = symbol.upper()
        if self._cik_map is None:                       # lazy live fetch of the whole ticker->CIK map
            data = self._get_json(_TICKERS_URL)
            rows = data.values() if isinstance(data, dict) else []
            self._cik_map = {str(r["ticker"]).upper(): int(r["cik_str"]) for r in rows
                             if r.get("ticker") and r.get("cik_str") is not None}
        return self._cik_map.get(sym)

    def _concept_points(self, cik: int, concept: str, unit: str) -> list[dict]:
        try:
            payload = self._get_json(_FACTS_URL.format(cik=cik, concept=concept))
        except EdgarNotFound:
            return []                                   # company doesn't report this tag -> try next
        rows = (payload.get("units", {}) or {}).get(unit) or []
        out: list[dict] = []
        for r in rows:
            start, end, filed = _to_date(r.get("start")), _to_date(r.get("end")), _to_date(r.get("filed"))
            fp = r.get("fp")
            if filed is None or not _is_period_row(start, end, fp):
                continue
            out.append({"fy": r.get("fy"), "fp": fp, "filed": filed, "end": end,
                        "form": r.get("form"), "val": r.get("val")})
        return out

    def _first_concept_points(self, cik: int, concepts: tuple[str, ...], unit: str) -> list[dict]:
        for concept in concepts:                        # first concept that yields period rows wins
            pts = self._concept_points(cik, concept, unit)
            if pts:
                return pts
        return []

    def _symbol_facts(self, symbol: str) -> list[EarningsFact]:
        cik = self._cik(symbol)
        if cik is None:
            return []                                   # unknown ticker -> empty, never crash
        eps = self._first_concept_points(cik, _EPS_CONCEPTS, _EPS_UNIT)
        rev = self._first_concept_points(cik, _REV_CONCEPTS, _REV_UNIT)
        # Merge EPS + revenue by (fy, fp, filed) — same 10-Q files both, so they share `filed`. A
        # restatement (a later `filed` for the same period) becomes a SEPARATE fact, PIT-keyed on its
        # own filing_date, which is exactly correct.
        merged: dict[tuple, dict] = {}
        for kind, pts in (("actual_eps", eps), ("actual_revenue", rev)):
            for p in pts:
                key = (p["fy"], p["fp"], p["filed"])
                rec = merged.setdefault(key, {"end": p["end"], "form": p["form"]})
                rec[kind] = None if p["val"] is None else float(p["val"])
        facts = []
        for (fy, fp, filed), rec in merged.items():
            facts.append(EarningsFact(
                symbol=symbol.upper(), fiscal_period=f"{fy}{fp}", period_end=rec["end"],
                filing_date=filed, form=rec.get("form"), actual_eps=rec.get("actual_eps"),
                actual_revenue=rec.get("actual_revenue"), source="edgar"))
        return sorted(facts, key=lambda f: (f.filing_date, f.fiscal_period))

    def _derive_calendar(self, symbol: str, facts: list[EarningsFact],
                         as_of: Date) -> list[EarningsCalendarEntry]:
        if not facts:
            return []
        filed_dates = sorted({f.filing_date for f in facts})
        # Each historical filing = a report knowable as of its own filing date (is_confirmed True).
        entries = [EarningsCalendarEntry(symbol=symbol.upper(), expected_date=d, known_asof=d,
                                         is_confirmed=True, source="edgar") for d in filed_dates]
        # One naive forward estimate off the last filing KNOWN AT as_of (last-known + a quarter's cadence),
        # stamped known_asof = that last-known filing — a PAST date, so no lookahead. Deriving it PER-AS_OF
        # (not off the last-EVER filing) is what makes it visible at a backtest/walk-forward as_of BETWEEN
        # two filings: off the prior quarter's cadence a report is projected forward, so days_to_earnings /
        # the §4.5 T-3 gate can fire in backtest — not only on the historical filing day. Filings dated
        # after as_of are excluded here (their confirmed entries are dropped by known_calendar below), so
        # the estimate can never leak a not-yet-filed report.
        known_filed = [d for d in filed_dates if d <= as_of]
        if known_filed:
            last_known = known_filed[-1]
            entries.append(EarningsCalendarEntry(
                symbol=symbol.upper(), expected_date=last_known + timedelta(days=_NEXT_QUARTER_DAYS),
                known_asof=last_known, is_confirmed=False, source="edgar_estimate"))
        return entries

    # ── earnings capability ─────────────────────────────────────────────────────────────────────────
    def earnings_known(self, symbol: str, as_of: Date) -> list[EarningsFact]:
        return known_earnings(self._symbol_facts(symbol), as_of)

    def earnings_calendar(self, as_of: Date) -> list[EarningsCalendarEntry]:
        symbols = self._universe if self._universe is not None else sorted(self._cik_map or {})
        entries: list[EarningsCalendarEntry] = []
        for sym in symbols:
            entries.extend(self._derive_calendar(sym, self._symbol_facts(sym), as_of))
        return known_calendar(entries, as_of)

    def earnings_available(self) -> bool:
        return True         # live feed always checkable (a fetch returns data or raises), like Alpaca corp

    # ── pure-swap: EdgarSource serves ONLY earnings; everything else raises NotImplementedError ──────
    def _only_earnings(self, *_a, **_k):
        raise NotImplementedError("EdgarSource serves only the `earnings` capability; compose it via "
                                  "CompositeSource(base, {'earnings': EdgarSource(...)})")

    trading_calendar = _only_earnings
    daily_bars = _only_earnings
    daily_snapshot = _only_earnings
    corporate_actions = _only_earnings
    corporate_actions_known = _only_earnings
    corp_actions_available = _only_earnings
