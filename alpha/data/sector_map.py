"""Theme/sector membership: `symbol -> group` + the swap seam (P5b).

The data prerequisite for the growth doctrine's §1.2 赛道时钟 (theme-lifecycle clock): a coarse
partition of the tape into sector/theme groups over which `alpha.features.theme_breadth` measures
per-group breadth. No GICS/IBD-group feed exists offline, so we ship a small STATIC BOOTSTRAP table
(`BOOTSTRAP_SECTORS`) as a deliberate placeholder.

Swap seam (the data-layer twin of `alpha.data.registry.make_source` / `alpha.llm.config.make_client`):
a real feed later (GICS via a vendor, or the IBD-197 industry groups) implements the `SectorMap`
Protocol and registers one line in `_SECTOR_MAPS` — a whole-map swap. Callers depend on the Protocol,
never on the concrete table (dependency injection, like `build_market_state(breadth=…)`).

Spec: docs/superpowers/specs/2026-07-13-p5b-theme-breadth-design.md.
"""
from __future__ import annotations

import os
from typing import Protocol, runtime_checkable

UNMAPPED = "unmapped"    # reserved bucket for a symbol not in the map (explicit, never a silent drop)


@runtime_checkable
class SectorMap(Protocol):
    """Membership contract: which sector/theme group a symbol belongs to."""
    def sector_of(self, symbol: str) -> str: ...   # a group key; UNMAPPED for an unknown symbol
    def sectors(self) -> frozenset[str]: ...        # the declared group keys (excludes UNMAPPED)


class StaticSectorMap:
    """A `SectorMap` backed by an in-memory `{symbol: group}` dict. Symbol lookup is case-insensitive
    (uppercased); an unknown symbol maps to `UNMAPPED`. This is the bootstrap implementation — a real
    GICS/IBD feed is a drop-in replacement satisfying the same Protocol."""

    def __init__(self, table: dict[str, str]) -> None:
        self._table = {sym.upper(): group for sym, group in table.items()}

    def sector_of(self, symbol: str) -> str:
        return self._table.get(symbol.upper(), UNMAPPED)

    def sectors(self) -> frozenset[str]:
        return frozenset(self._table.values())


# ── bootstrap table ─────────────────────────────────────────────────────────────────────────────────
# A small, deliberately coarse `symbol -> group` map covering the sectors the growth doctrine cares
# about, with enough liquid representatives per group that a typical growth universe clears the
# theme_breadth min-members floor. THIS IS A PLACEHOLDER for a real GICS/IBD industry-group feed — the
# groups are broad sectors, not the fine industry lines a real classifier gives; swap via make_sector_map.
BOOTSTRAP_SECTORS: dict[str, str] = {
    # semiconductors + semi-cap equipment
    **{s: "semiconductors" for s in (
        "NVDA", "AMD", "AVGO", "TSM", "MU", "INTC", "QCOM", "ASML", "AMAT", "LRCX", "KLAC",
        "ARM", "SMCI", "MRVL", "ON", "MCHP", "TXN", "ADI", "NXPI")},
    # application + infrastructure software
    **{s: "software" for s in (
        "MSFT", "CRM", "ORCL", "ADBE", "NOW", "SNOW", "PLTR", "DDOG", "NET", "CRWD", "PANW",
        "ZS", "MDB", "TEAM", "WDAY", "HUBS", "SHOP", "INTU", "FTNT")},
    # internet, media, communications
    **{s: "internet" for s in (
        "GOOGL", "GOOG", "META", "NFLX", "SPOT", "PINS", "SNAP", "RBLX", "U", "DASH", "ABNB",
        "UBER", "LYFT", "ROKU")},
    # hardware, devices, networking
    **{s: "hardware" for s in (
        "AAPL", "DELL", "HPQ", "ANET", "CSCO", "JNPR", "STX", "WDC", "GLW")},
    # biotech
    **{s: "biotech" for s in (
        "MRNA", "BNTX", "VRTX", "REGN", "GILD", "BIIB", "AMGN", "CRSP", "NTLA", "BEAM",
        "ALNY", "EXAS", "SRPT")},
    # large-cap pharma
    **{s: "pharma" for s in (
        "PFE", "JNJ", "LLY", "MRK", "ABBV", "BMY", "NVO", "AZN", "GSK")},
    # energy (oil & gas, services)
    **{s: "energy" for s in (
        "XOM", "CVX", "OXY", "SLB", "COP", "FANG", "DVN", "MRO", "HAL", "EOG", "PSX", "VLO")},
    # financials (banks, brokers, payments, fintech)
    **{s: "financials" for s in (
        "JPM", "BAC", "GS", "MS", "WFC", "C", "SCHW", "COIN", "SOFI", "HOOD", "AXP",
        "V", "MA", "PYPL", "BLK", "KKR")},
    # consumer (discretionary + staples + retail)
    **{s: "consumer" for s in (
        "AMZN", "TSLA", "HD", "NKE", "SBUX", "MCD", "LULU", "CMG", "TGT", "WMT", "COST",
        "PEP", "KO", "PG", "DIS")},
    # industrials, transports, defense
    **{s: "industrials" for s in (
        "CAT", "DE", "BA", "GE", "HON", "LMT", "RTX", "UPS", "UNP", "ETN", "PH", "EMR")},
    # healthcare devices, services, tools
    **{s: "healthcare" for s in (
        "ISRG", "MDT", "ABT", "TMO", "DHR", "SYK", "BSX", "UNH", "CI", "HUM")},
    # clean energy / EV (a live growth theme; broad by design)
    **{s: "clean_energy" for s in (
        "ENPH", "FSLR", "PLUG", "RUN", "SEDG", "RIVN", "LCID", "CHPT")},
}


def _build_bootstrap() -> SectorMap:
    return StaticSectorMap(BOOTSTRAP_SECTORS)


_SECTOR_MAPS = {"bootstrap": _build_bootstrap}


def make_sector_map(name: str | None = None) -> SectorMap:
    """Build the active sector map. Name precedence: explicit arg > ALPHA_SECTOR_MAP env > 'bootstrap'.

    The seam a real GICS/IBD feed swaps into: implement `SectorMap` in a new module, add a builder, and
    register one line in `_SECTOR_MAPS`; select it with ALPHA_SECTOR_MAP=<name>."""
    name = (name or os.environ.get("ALPHA_SECTOR_MAP", "bootstrap")).strip().lower()
    if name not in _SECTOR_MAPS:
        raise ValueError(f"unknown sector map: {name!r} (expected one of {sorted(_SECTOR_MAPS)})")
    return _SECTOR_MAPS[name]()
