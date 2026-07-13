from alpha.data.sector_map import (
    BOOTSTRAP_SECTORS, UNMAPPED, SectorMap, StaticSectorMap, make_sector_map,
)


def test_static_map_sector_of_and_case_insensitive():
    m = StaticSectorMap({"NVDA": "semiconductors", "MSFT": "software"})
    assert m.sector_of("NVDA") == "semiconductors"
    assert m.sector_of("msft") == "software"          # case-insensitive lookup


def test_unknown_symbol_falls_into_unmapped_bucket():
    m = StaticSectorMap({"NVDA": "semiconductors"})
    assert m.sector_of("ZZZZ") == UNMAPPED
    assert UNMAPPED not in m.sectors()                # UNMAPPED is not a declared group


def test_sectors_are_the_declared_group_keys():
    m = StaticSectorMap({"A": "energy", "B": "energy", "C": "biotech"})
    assert m.sectors() == frozenset({"energy", "biotech"})


def test_bootstrap_map_covers_the_common_growth_sectors():
    m = make_sector_map()                             # default = bootstrap
    # a representative name in each of the sectors the growth doctrine cares about resolves (not unmapped)
    for sym in ("NVDA", "MSFT", "GOOGL", "MRNA", "LLY", "XOM", "JPM", "TSLA", "CAT"):
        assert m.sector_of(sym) != UNMAPPED, sym
    assert m.sectors() >= {"semiconductors", "software", "biotech", "energy", "financials"}


def test_bootstrap_table_has_no_symbol_mapped_to_unmapped():
    # the bootstrap table must never itself assign the reserved UNMAPPED key to a symbol
    assert UNMAPPED not in set(BOOTSTRAP_SECTORS.values())


def test_make_sector_map_env_and_explicit(monkeypatch):
    monkeypatch.setenv("ALPHA_SECTOR_MAP", "bootstrap")
    assert isinstance(make_sector_map(), StaticSectorMap)
    assert isinstance(make_sector_map("bootstrap"), StaticSectorMap)   # explicit arg wins


def test_make_sector_map_unknown_name_raises():
    try:
        make_sector_map("gics_real_feed")
    except ValueError as e:
        assert "gics_real_feed" in str(e)
    else:
        raise AssertionError("expected ValueError for an unregistered sector map")


def test_swap_seam_custom_map_satisfies_protocol():
    # a hand-rolled SectorMap (the shape a real GICS/IBD feed will take) is a drop-in.
    class OneGroupMap:
        def sector_of(self, symbol: str) -> str:
            return "ai" if symbol.upper().startswith("A") else UNMAPPED

        def sectors(self) -> frozenset[str]:
            return frozenset({"ai"})

    m: SectorMap = OneGroupMap()
    assert m.sector_of("AMD") == "ai" and m.sector_of("NVDA") == UNMAPPED
