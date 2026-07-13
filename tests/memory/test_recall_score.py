# tests/memory/test_recall_score.py
from datetime import date, timedelta

from alpha.memory.episodes import Episode
from alpha.memory.recall_score import (
    DEFAULT_RECALL_WEIGHTS as W,
    RecallWeights,
    blended_recall,
    recall_score,
)

ASOF = date(2026, 6, 20)


def _ep(*, phase="trend", narrative="", adv=0.0, learned=ASOF, sym="RUN", skill="s1"):
    d = learned
    return Episode(episode_id=f"{sym}:{skill}:{phase}:{narrative}:{adv}:{d}", symbol=sym, skill_id=skill,
                   phase=phase, narrative=narrative, entry_date=d - timedelta(days=2), exit_date=d,
                   outcome="continued", advantage=adv, learned_asof=d)


def test_phase_match_adds_w_rel():
    # same phase, age 0, adv 0, no narrative -> relevance only
    s = recall_score(_ep(phase="trend", adv=0.0, learned=ASOF), asof=ASOF, phase="trend")
    # recency=1.0 (age 0) contributes w_rec too; relevance=1, distance=0
    assert abs(s - (W.w_rel * 1.0 + W.w_rec * 1.0)) < 1e-9


def test_phase_mismatch_applies_regime_penalty():
    match = recall_score(_ep(phase="trend", learned=ASOF), asof=ASOF, phase="trend")
    miss = recall_score(_ep(phase="flush", learned=ASOF), asof=ASOF, phase="trend")
    # match gets +w_rel, no penalty; miss gets no relevance and −w_reg (binary distance=1)
    assert abs((match - miss) - (W.w_rel + W.w_reg)) < 1e-9


def test_recency_decays_by_half_life():
    hl = 30.0
    now = recall_score(_ep(phase="", learned=ASOF), asof=ASOF, phase=None, half_life_days=hl)
    one = recall_score(_ep(phase="", learned=ASOF - timedelta(days=30)), asof=ASOF, phase=None,
                       half_life_days=hl)
    two = recall_score(_ep(phase="", learned=ASOF - timedelta(days=60)), asof=ASOF, phase=None,
                       half_life_days=hl)
    # phase=None -> relevance & distance both 0; only recency contributes
    assert abs(now - W.w_rec * 1.0) < 1e-9
    assert abs(one - W.w_rec * 0.5) < 1e-9
    assert abs(two - W.w_rec * 0.25) < 1e-9


def test_importance_saturates_at_cap():
    cap = 3.0
    below = recall_score(_ep(phase="", adv=1.5, learned=ASOF), asof=ASOF, phase=None, imp_cap=cap)
    at = recall_score(_ep(phase="", adv=3.0, learned=ASOF), asof=ASOF, phase=None, imp_cap=cap)
    over = recall_score(_ep(phase="", adv=9.0, learned=ASOF), asof=ASOF, phase=None, imp_cap=cap)
    base = W.w_rec * 1.0                                  # age 0 recency
    assert abs(below - (base + W.w_imp * 0.5)) < 1e-9
    assert abs(at - (base + W.w_imp * 1.0)) < 1e-9
    assert abs(over - at) < 1e-9                          # saturated
    # importance keys off |advantage| (magnitude), so a big loss is as "impactful" as a big win
    neg = recall_score(_ep(phase="", adv=-9.0, learned=ASOF), asof=ASOF, phase=None, imp_cap=cap)
    assert abs(neg - over) < 1e-9


def test_narrative_match_inert_by_default_active_when_supplied():
    ep = _ep(phase="", narrative="AI", learned=ASOF)
    inert = recall_score(ep, asof=ASOF, phase=None)                     # narrative=None -> 0 contribution
    active = recall_score(ep, asof=ASOF, phase=None, narrative="AI")    # match -> +w_narr
    assert abs((active - inert) - W.w_narr) < 1e-9
    mismatch = recall_score(ep, asof=ASOF, phase=None, narrative="EV")
    assert abs(mismatch - inert) < 1e-9


def test_full_weighted_sum_hand_computed():
    # trend match, 30d old (half-life 30 -> recency 0.5), adv 1.5 (cap 3 -> 0.5), narrative AI match
    ep = _ep(phase="trend", narrative="AI", adv=1.5, learned=ASOF - timedelta(days=30))
    s = recall_score(ep, asof=ASOF, phase="trend", narrative="AI", half_life_days=30.0, imp_cap=3.0)
    expect = W.w_rel * 1.0 + W.w_rec * 0.5 + W.w_imp * 0.5 - W.w_reg * 0.0 + W.w_narr * 1.0
    assert abs(s - expect) < 1e-9


def test_custom_weights_and_graded_phase_distance():
    weights = RecallWeights(w_rel=0.0, w_rec=0.0, w_imp=0.0, w_reg=2.0, w_narr=0.0)
    # a graded distance: 0.25 between these phases
    graded = lambda a, b: 0.25
    s = recall_score(_ep(phase="flush", learned=ASOF), asof=ASOF, phase="trend",
                     weights=weights, phase_distance=graded)
    assert abs(s - (-2.0 * 0.25)) < 1e-9


def test_blended_recall_ranks_and_budgets():
    eps = [
        _ep(phase="flush", adv=0.1, learned=ASOF - timedelta(days=200), sym="OLD"),      # off-regime, stale
        _ep(phase="trend", adv=3.0, learned=ASOF, sym="BEST"),                            # in-regime, recent, big
        _ep(phase="trend", adv=0.1, learned=ASOF - timedelta(days=120), sym="MID"),       # in-regime, stale
    ]
    ranked = blended_recall(eps, asof=ASOF, phase="trend", budget=2)
    assert [e.symbol for e in ranked] == ["BEST", "MID"]                                  # budget cap drops OLD


def test_blended_recall_drops_future_learned_pit():
    past = _ep(phase="trend", learned=ASOF, sym="PAST")
    future = _ep(phase="trend", learned=ASOF + timedelta(days=5), sym="FUT")
    ranked = blended_recall([past, future], asof=ASOF, phase="trend")
    assert [e.symbol for e in ranked] == ["PAST"]                                         # future masked out
