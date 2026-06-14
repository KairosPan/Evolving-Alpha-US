from alpha.sizing.correlation import Pick, group_by_narrative, correlated_groups


def _picks():
    return [
        Pick(symbol="AI1", narrative="ai", confidence=0.9),
        Pick(symbol="AI2", narrative="ai", confidence=0.6),
        Pick(symbol="NUKE1", narrative="nuclear", confidence=0.7),
        Pick(symbol="SOLO", narrative="", confidence=0.5),   # untagged -> its own bet
    ]


def test_group_by_narrative():
    groups = group_by_narrative(_picks())
    assert {s.symbol for s in groups["ai"]} == {"AI1", "AI2"}
    assert {s.symbol for s in groups["nuclear"]} == {"NUKE1"}
    # untagged narratives are keyed by symbol so they don't merge into one bucket
    assert "SOLO" in groups and len(groups["SOLO"]) == 1


def test_correlated_groups_returns_multi_member_only():
    cg = correlated_groups(_picks())
    assert cg == [["AI1", "AI2"]]            # only the multi-ticker narrative is a correlated group
