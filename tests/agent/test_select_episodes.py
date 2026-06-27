from datetime import date
from alpha.memory.episodes import Episode
from alpha.memory.store import EpisodeStore
from alpha.agent.retrieval import select_episodes_for_prompt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ep(eid, phase, exit_d, adv, skill="gap_and_go", sym="RUN"):
    # Use only canonical or alias-mapped phase strings so normalize_phase() works:
    # "trend" -> "trend", "momentum" -> "trend" (alias), "washout" -> "washout"
    return Episode(episode_id=eid, symbol=sym, skill_id=skill, phase=phase,
                   entry_date=date(2026, 6, 1), exit_date=exit_d, outcome="continued", advantage=adv)


def _store(*eps):
    s = EpisodeStore.in_memory()
    for e in eps:
        s.add(e)
    return s


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_none_store_returns_empty():
    assert select_episodes_for_prompt(None, phase_prior="trend", asof=date(2026, 6, 20)) == []


def test_none_asof_returns_empty():
    s = _store(_ep("e1", "trend", date(2026, 6, 5), 1.0))
    assert select_episodes_for_prompt(s, phase_prior="trend", asof=None) == []


def test_pit_mask_excludes_future_learned_asof():
    # learned_asof defaults to exit_date; "past" exit_date <= asof; "future" > asof
    s = _store(_ep("past", "trend", date(2026, 6, 5), 1.0),
               _ep("future", "trend", date(2026, 6, 25), 9.0))
    out = select_episodes_for_prompt(s, phase_prior="trend", asof=date(2026, 6, 10))
    ids = {e.episode_id for e in out}
    assert "past" in ids and "future" not in ids


def test_phase_match_ranks_first_then_recency_then_advantage():
    # "washout" is a recognized canonical phase; "trend" is canonical; "momentum" aliases to "trend"
    # phase_prior="trend" → canon="trend"
    # off_phase uses "washout" → normalize_phase("washout")="washout" != "trend" → match=0
    # trend_old uses "trend" → match=1, exit_date=2026-06-05
    # trend_new uses "momentum" → normalize_phase("momentum")="trend" == "trend" → match=1, exit_date=2026-06-08
    s = _store(_ep("off_phase", "washout", date(2026, 6, 9), 5.0),
               _ep("trend_old", "trend",   date(2026, 6, 5), 1.0),
               _ep("trend_new", "momentum", date(2026, 6, 8), 0.5))
    out = select_episodes_for_prompt(s, phase_prior="trend", asof=date(2026, 6, 20))
    # both phase-matched episodes outrank off_phase despite its bigger advantage
    # within matched, trend_new (2026-06-08) ranks before trend_old (2026-06-05)
    assert [e.episode_id for e in out[:2]] == ["trend_new", "trend_old"]
    assert out[-1].episode_id == "off_phase"


def test_budget_caps():
    eps = [_ep(f"e{i}", "trend", date(2026, 6, 2 + i), float(i)) for i in range(5)]
    out = select_episodes_for_prompt(_store(*eps), phase_prior="trend", asof=date(2026, 6, 20), budget=3)
    assert len(out) == 3


def test_phase_prior_none_recalls_across_phases_by_recency():
    s = _store(_ep("a", "trend",   date(2026, 6, 5), 1.0),
               _ep("b", "washout", date(2026, 6, 9), 1.0))
    out = select_episodes_for_prompt(s, phase_prior=None, asof=date(2026, 6, 20))
    # no phase boost → rank purely by recency; "b" (2026-06-09) is newer
    assert out[0].episode_id == "b"
