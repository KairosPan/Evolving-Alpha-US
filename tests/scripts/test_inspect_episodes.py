"""Offline smoke for scripts/inspect_episodes.py: a read-only PIT episode inspector that prints
the SAME summarize()/is_episode_taboo() numbers alpha/guard/screen.py's L4 veto uses — imported
from their production homes, never re-derived, so a doc-drift between the veto and the inspector
can't silently happen."""
import sys
from datetime import date
from pathlib import Path

from alpha.memory.aggregate import is_episode_taboo, summarize
from alpha.memory.episodes import Episode
from alpha.memory.store import EpisodeStore

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import inspect_episodes  # noqa: E402


def _ep(eid, symbol, outcome, adv, exit_d=date(2026, 6, 1), skill="gap_and_go"):
    return Episode(episode_id=eid, symbol=symbol, skill_id=skill, entry_date=date(2026, 5, 1),
                   exit_date=exit_d, outcome=outcome, advantage=adv, learned_asof=exit_d)


def _seed(tmp_path):
    db = tmp_path / "brain.db"
    store = EpisodeStore.open(str(db))
    # RUN: enough nuke history to be taboo (n=3, nuke_rate=1.0 >= 0.5).
    store.add(_ep("RUN:1", "RUN", "nuked", -2.0, exit_d=date(2026, 6, 1)))
    store.add(_ep("RUN:2", "RUN", "nuked", -1.5, exit_d=date(2026, 6, 2)))
    store.add(_ep("RUN:3", "RUN", "nuked", -1.0, exit_d=date(2026, 6, 3)))
    # AAA: healthy history, not taboo.
    store.add(_ep("AAA:1", "AAA", "continued", 2.0, exit_d=date(2026, 6, 1)))
    store.add(_ep("AAA:2", "AAA", "continued", 1.5, exit_d=date(2026, 6, 2)))
    # future episode (learned after asof) must stay PIT-masked out of both the inspector and summarize().
    store.add(_ep("RUN:future", "RUN", "nuked", -3.0, exit_d=date(2026, 7, 1)))
    store.close()
    return str(db)


def test_inspector_prints_the_same_numbers_the_veto_uses(tmp_path, capsys):
    db = _seed(tmp_path)
    asof = "2026-06-05"

    inspect_episodes.main([db, asof])
    out = capsys.readouterr().out

    # Independently recompute via the SAME production functions the L4 guard uses
    # (alpha/guard/screen.py: summarize(store.for_asof(as_of, limit=None), key=symbol)).
    store = EpisodeStore.open(db, create_if_missing=False)
    episodes = store.for_asof(date.fromisoformat(asof), limit=None)
    expected_stats = summarize(episodes, key=lambda e: e.symbol)
    store.close()

    run_stats = expected_stats["RUN"]
    aaa_stats = expected_stats["AAA"]
    assert run_stats.n == 3 and run_stats.nuked == 3
    assert is_episode_taboo(run_stats) is True
    assert is_episode_taboo(aaa_stats) is False

    # The printed output must surface the exact same n / nuke_rate / taboo verdict per symbol —
    # no re-derivation, no vacuous "runs without error".
    assert "RUN" in out and "AAA" in out
    assert f"n={run_stats.n}" in out
    assert f"nuke_rate={run_stats.nuke_rate:.2f}" in out
    assert "taboo=YES" in out          # RUN's verdict
    assert f"n={aaa_stats.n}" in out
    assert f"nuke_rate={aaa_stats.nuke_rate:.2f}" in out
    # AAA must NOT be marked taboo.
    aaa_line = next(line for line in out.splitlines() if line.startswith("AAA"))
    assert "taboo=no" in aaa_line

    # PIT mask: the future-learned RUN episode (exit 2026-07-01) must not appear; 5 rows total
    # (3 RUN + 2 AAA), matching the un-masked-out episode count.
    assert "2026-07-01" not in out
    assert len(episodes) == 5
    assert "(5 rows)" in out


def test_inspector_symbol_filter_restricts_to_one_symbol(tmp_path, capsys):
    db = _seed(tmp_path)
    inspect_episodes.main([db, "2026-06-05", "--symbol", "AAA"])
    out = capsys.readouterr().out
    assert "AAA" in out
    assert "RUN" not in out
