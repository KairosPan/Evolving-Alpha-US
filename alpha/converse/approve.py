"""Make StagedEdit.status load-bearing: a staged brain edit may be applied to the live brain ONLY
after the user approves it. Call assert_approvable(edit) at every live-apply site (T4 human-confirm,
modification-ladder spec §4)."""
from __future__ import annotations
from alpha.converse.project import StagedEdit


class StagedEditNotApproved(Exception):
    pass


def assert_approvable(edit: StagedEdit) -> None:
    if not edit.valid:
        raise StagedEditNotApproved(f"edit {edit.edit_id} did not pass the dry-run gate")
    if edit.status != "approved":
        raise StagedEditNotApproved(f"edit {edit.edit_id} is '{edit.status}', not 'approved'")
