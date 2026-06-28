from alpha.arena.contract import CapabilityTier, ExecResult, Feedback


def test_capability_tiers_ordered():
    assert CapabilityTier.T0_OBSERVE < CapabilityTier.T3_BRAIN_EDIT < CapabilityTier.T4_CONFIRM
    assert {t.name for t in CapabilityTier} == {
        "T0_OBSERVE", "T1_WORKSPACE_WRITE", "T2_EXECUTE", "T3_BRAIN_EDIT", "T4_CONFIRM"}


def test_exec_result_is_frozen():
    import pytest
    r = ExecResult(ok=True, stdout="hi", stderr="", exit_code=0)
    assert r.ok and r.stdout == "hi"
    with pytest.raises(Exception):     # frozen models reject post-construction mutation
        r.ok = False


def test_feedback_round_trips():
    f = Feedback(kind="gate", detail="applied")
    assert f.kind == "gate" and f.detail == "applied"
