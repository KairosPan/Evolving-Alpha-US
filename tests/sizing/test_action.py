"""P0.6 trim-derisk action vocabulary: RecommendationAction + derisk_tier + candidate_action.
The executable meaning of the growth doctrine's `derisk_on_breakdown.rule` ('reduce to core');
holdings are not modeled (spec 2026-07-13-p06), so the vocabulary defaults to `enter` = today's
behaviour byte-for-byte."""
from types import SimpleNamespace

from alpha.eval.decision import Candidate
from alpha.sizing.action import DEFAULT_ACTION, candidate_action, derisk_tier


def test_default_action_is_enter():
    assert DEFAULT_ACTION == "enter"


def test_derisk_tier_enter_is_identity():
    for t in ("flat", "probe", "core", "heavy"):
        assert derisk_tier("enter", t) == t


def test_derisk_tier_trim_caps_at_core():
    assert derisk_tier("trim", "heavy") == "core"      # reduce to core position (原仓位的 1/2)
    assert derisk_tier("trim", "core") == "core"       # already at/under core -> unchanged
    assert derisk_tier("trim", "probe") == "probe"     # never RAISES a smaller tier
    assert derisk_tier("trim", "flat") == "flat"


def test_derisk_tier_exit_is_flat():
    for t in ("flat", "probe", "core", "heavy"):
        assert derisk_tier("exit", t) == "flat"


def test_candidate_action_defaults_enter_on_real_candidate():
    # a real Candidate now carries `action`, defaulting to "enter" -> candidate_action reads the field
    assert candidate_action(Candidate(symbol="X", confidence=0.9)) == "enter"


def test_candidate_action_defaults_enter_when_attribute_absent():
    # the getattr fallback branch: an object WITHOUT an `action` attribute -> "enter" (so the L4/L3
    # seams stay byte-identical for any non-Candidate caller, e.g. a bare Pick/namespace)
    assert candidate_action(SimpleNamespace()) == "enter"
    assert candidate_action(object()) == "enter"


def test_candidate_action_reads_action_when_present():
    assert candidate_action(SimpleNamespace(action="trim")) == "trim"
    assert candidate_action(SimpleNamespace(action="exit")) == "exit"
