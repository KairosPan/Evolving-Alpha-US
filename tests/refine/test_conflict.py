# tests/refine/test_conflict.py
from alpha.harness.edit_log import EditLog, EditProvenance
from alpha.refine.ops import RefineOp
from alpha.refine.conflict import is_conflict

def _log_with_teaching_lesson():
    log = EditLog()
    log.append("process_memory", "memory", "m1", "create", rationale="r")
    log.stamp_last(EditProvenance(path="teaching", proposer="sonia"))
    return log

SELF = EditProvenance(path="self_study", proposer="refiner")
TEACH = EditProvenance(path="teaching", proposer="sonia")

def test_self_study_contesting_teaching_owned_is_conflict():
    log = _log_with_teaching_lesson()
    op = RefineOp(tool="demote_memory", args={"lesson_id": "m1", "factor": 0.5}, rationale="data says weak")
    assert is_conflict(log, op, SELF) is True

def test_teaching_op_never_conflicts():
    log = _log_with_teaching_lesson()
    op = RefineOp(tool="demote_memory", args={"lesson_id": "m1", "factor": 0.5}, rationale="r")
    assert is_conflict(log, op, TEACH) is False           # teaching applies directly (asymmetry)

def test_create_verb_never_conflicts():
    log = _log_with_teaching_lesson()
    op = RefineOp(tool="process_memory", args={"lesson_id": "m2", "outcome": "win", "lesson": "z"}, rationale="r")
    assert is_conflict(log, op, SELF) is False            # a brand-new element can't contest existing teaching

def test_self_study_on_self_study_owned_is_not_conflict():
    log = EditLog()
    log.append("process_memory", "memory", "m3", "create", rationale="r")
    log.stamp_last(EditProvenance(path="self_study", proposer="refiner"))
    op = RefineOp(tool="demote_memory", args={"lesson_id": "m3", "factor": 0.5}, rationale="r")
    assert is_conflict(log, op, SELF) is False

def test_untouched_element_is_not_conflict():
    op = RefineOp(tool="demote_memory", args={"lesson_id": "ghost", "factor": 0.5}, rationale="r")
    assert is_conflict(EditLog(), op, SELF) is False


USER = EditProvenance(path="user_direct", proposer="user", human_approver="user")

def _log_with_user_direct_lesson():
    log = EditLog()
    log.append("process_memory", "memory", "u1", "create", rationale="r")
    log.stamp_last(EditProvenance(path="user_direct", proposer="user", human_approver="user"))
    return log

def test_self_study_contesting_user_direct_owned_is_conflict():
    # charter 2026-07-08 second hand: the user's landed edit is a user act — machine contest is held
    log = _log_with_user_direct_lesson()
    op = RefineOp(tool="demote_memory", args={"lesson_id": "u1", "factor": 0.5}, rationale="data says weak")
    assert is_conflict(log, op, SELF) is True

def test_user_direct_op_never_conflicts():
    log = _log_with_teaching_lesson()
    op = RefineOp(tool="demote_memory", args={"lesson_id": "m1", "factor": 0.5}, rationale="r")
    assert is_conflict(log, op, USER) is False            # only self-study can be held
