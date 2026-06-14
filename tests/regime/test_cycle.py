import pytest
from alpha.regime.cycle import StateMachine, EmotionPhase, default_us_cycle
from alpha.harness.regime import CANONICAL_PHASES


def test_default_cycle_has_six_canonical_phases():
    sm = default_us_cycle()
    assert sm.phase_names() == CANONICAL_PHASES        # washout..flush, in order


def test_transitions_point_to_known_phases():
    sm = default_us_cycle()
    known = set(sm.phase_names())
    for name in sm.phase_names():
        for to, _signal in sm.next_signals(name):
            assert to in known                          # no dangling transitions


def test_from_seed_list_rejects_duplicate_phase():
    with pytest.raises(ValueError):
        StateMachine.from_seed_list([{"phase": "trend"}, {"phase": "trend"}])


def test_get_and_signals():
    sm = default_us_cycle()
    assert sm.get("trend") is not None
    assert sm.get("nonexistent") is None
    assert isinstance(sm.next_signals("washout"), list)
