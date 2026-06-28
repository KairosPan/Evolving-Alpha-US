import pytest
from alpha.converse.approve import assert_approvable, StagedEditNotApproved
from alpha.converse.project import StagedEdit


def _edit(**kw):
    base = dict(edit_id="e1", op={"tool": "process_memory", "args": {}, "rationale": "r"}, valid=True)
    base.update(kw)
    return StagedEdit(**base)


def test_pending_edit_is_not_approvable():
    with pytest.raises(StagedEditNotApproved):
        assert_approvable(_edit(status="pending"))


def test_rejected_edit_is_not_approvable():
    with pytest.raises(StagedEditNotApproved):
        assert_approvable(_edit(status="rejected"))


def test_invalid_edit_is_not_approvable_even_if_approved():
    with pytest.raises(StagedEditNotApproved):
        assert_approvable(_edit(status="approved", valid=False))


def test_approved_and_valid_passes():
    assert_approvable(_edit(status="approved", valid=True))   # no raise
