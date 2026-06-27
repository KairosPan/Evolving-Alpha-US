# tests/memory/test_aggregate.py
from datetime import date
from alpha.memory.episodes import Episode
from alpha.memory.aggregate import EpisodeStats, summarize, is_episode_taboo

def _ep(sym, outcome, adv, skill="gap_and_go"):
    return Episode(episode_id=f"{sym}:{outcome}:{adv}", symbol=sym, skill_id=skill,
                   entry_date=date(2026, 6, 1), exit_date=date(2026, 6, 3), outcome=outcome, advantage=adv)

def test_summarize_groups_and_tallies_by_key():
    eps = [_ep("RUN", "nuked", -2.0), _ep("RUN", "nuked", -1.0), _ep("RUN", "continued", 3.0),
           _ep("AAA", "faded", 0.0)]
    stats = summarize(eps, key=lambda e: e.symbol)
    run = stats["RUN"]
    assert run.n == 3 and run.nuked == 2 and run.continued == 1 and run.faded == 0
    assert abs(run.mean_advantage - 0.0) < 1e-9             # (-2 -1 +3)/3
    assert abs(run.nuke_rate - 2 / 3) < 1e-9 and abs(run.win_rate - 1 / 3) < 1e-9
    assert stats["AAA"].n == 1 and stats["AAA"].nuke_rate == 0.0

def test_empty_stats_rates_are_zero():
    s = EpisodeStats(n=0, continued=0, faded=0, nuked=0, mean_advantage=0.0)
    assert s.nuke_rate == 0.0 and s.win_rate == 0.0

def test_summarize_by_skill_key():
    eps = [_ep("RUN", "nuked", -1.0, skill="gap_and_go"), _ep("AAA", "continued", 2.0, skill="vwap_reclaim")]
    stats = summarize(eps, key=lambda e: e.skill_id)
    assert set(stats) == {"gap_and_go", "vwap_reclaim"} and stats["gap_and_go"].nuked == 1

def test_is_episode_taboo_thresholds():
    assert is_episode_taboo(None) is False
    two_nuked = summarize([_ep("X", "nuked", -1.0), _ep("X", "nuked", -1.0)], key=lambda e: e.symbol)["X"]
    assert is_episode_taboo(two_nuked) is False             # n=2 < min_samples=3
    half = summarize([_ep("Y", "nuked", -1.0), _ep("Y", "nuked", -1.0),
                      _ep("Y", "continued", 1.0), _ep("Y", "faded", 0.0)], key=lambda e: e.symbol)["Y"]
    assert is_episode_taboo(half) is True                   # n=4, nuke_rate=0.5 >= 0.5
    one_quarter = summarize([_ep("Z", "nuked", -1.0)] + [_ep("Z", "continued", 1.0)] * 3,
                            key=lambda e: e.symbol)["Z"]
    assert is_episode_taboo(one_quarter) is False           # n=4, nuke_rate=0.25 < 0.5
