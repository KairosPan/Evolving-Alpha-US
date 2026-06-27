from datetime import date
from alpha.memory.episodes import Episode
from alpha.memory.store import EpisodeStore
from alpha.agent.retrieval import select_episodes_for_prompt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ep(eid, phase, exit_d, adv, skill="gap_and_go", sym="RUN"):
    # `phase` holds the RAW prose regime_read exactly as production stores it (e.g. "trend frontside")
    # — NOT a pre-canonicalized token. The phase-match must EXTRACT the canonical phase from this prose
    # (normalize_phase("trend frontside") is None, so a normalize-only match would silently never fire).
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
    s = _store(_ep("e1", "trend frontside", date(2026, 6, 5), 1.0))
    assert select_episodes_for_prompt(s, phase_prior="trend", asof=None) == []


def test_pit_mask_excludes_future_learned_asof():
    # learned_asof defaults to exit_date; "past" exit_date <= asof; "future" > asof
    s = _store(_ep("past", "trend frontside", date(2026, 6, 5), 1.0),
               _ep("future", "trend frontside", date(2026, 6, 25), 9.0))
    out = select_episodes_for_prompt(s, phase_prior="trend", asof=date(2026, 6, 10))
    ids = {e.episode_id for e in out}
    assert "past" in ids and "future" not in ids


def test_prose_phase_match_ranks_first_then_recency_then_advantage():
    # PROSE regime reads (what production stores) — proves the match extracts the canonical phase:
    #   "trend frontside"  -> phase_from_read -> "trend"  (normalize_phase alone returns None)
    #   "distribution backside" -> "distribution"
    #   "flush exhaustion" -> "flush"  (off-phase vs a "trend" prior)
    # phase_prior="trend" (canonical token) — phase_from_read is idempotent so it stays "trend".
    s = _store(_ep("off_phase", "flush exhaustion",       date(2026, 6, 9), 5.0),
               _ep("trend_old", "trend frontside",        date(2026, 6, 5), 1.0),
               _ep("trend_new", "trend backside building", date(2026, 6, 8), 0.5))
    out = select_episodes_for_prompt(s, phase_prior="trend", asof=date(2026, 6, 20))
    # both prose "trend ..." episodes phase-match and outrank the off-phase one despite its bigger advantage
    assert [e.episode_id for e in out[:2]] == ["trend_new", "trend_old"]   # matched, newest first
    assert out[-1].episode_id == "off_phase"


def test_phase_prior_can_itself_be_a_prose_read():
    # The caller may pass a prose regime_read as the prior (not a canonical token) — match must still fire.
    s = _store(_ep("matched", "trend frontside",  date(2026, 6, 8), 1.0),
               _ep("other",   "flush exhaustion", date(2026, 6, 9), 5.0))
    out = select_episodes_for_prompt(s, phase_prior="AI frontside; trend continuation", asof=date(2026, 6, 20))
    assert out[0].episode_id == "matched"   # prose prior -> "trend", phase-matches the prose episode


def test_budget_caps():
    eps = [_ep(f"e{i}", "trend frontside", date(2026, 6, 2 + i), float(i)) for i in range(5)]
    out = select_episodes_for_prompt(_store(*eps), phase_prior="trend", asof=date(2026, 6, 20), budget=3)
    assert len(out) == 3


def test_phase_prior_none_recalls_across_phases_by_recency():
    s = _store(_ep("a", "trend frontside",  date(2026, 6, 5), 1.0),
               _ep("b", "flush exhaustion", date(2026, 6, 9), 1.0))
    out = select_episodes_for_prompt(s, phase_prior=None, asof=date(2026, 6, 20))
    # no phase boost → rank purely by recency; "b" (2026-06-09) is newer
    assert out[0].episode_id == "b"


def test_recall_pool_sees_full_history_past_the_50_cap():
    """An older phase-matching high-|advantage| episode is recalled (ranked first) even behind 50
    more-recent off-phase episodes that would crowd the default-50 window."""
    from datetime import timedelta
    s = EpisodeStore.in_memory()
    s.add(_ep("gold", "trend frontside", date(2026, 1, 2), 9.0, sym="AAA"))   # older, phase-match, big |adv|
    for i in range(50):                                  # off-phase, MORE recent (would fill default-50)
        s.add(_ep(f"n{i}", "flush exhaustion", date(2026, 3, 1) + timedelta(days=i), 0.1, sym="BBB"))
    got = select_episodes_for_prompt(s, phase_prior="trend", asof=date(2026, 6, 1), budget=8)
    assert any(e.episode_id == "gold" for e in got)      # behind the 50-cap, but full pool sees + ranks it
    assert got[0].episode_id == "gold"                   # phase-match boost ranks it first
