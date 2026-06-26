from alpha.converse.project import Project, StagedEdit, new_project


def test_staged_edit_round_trips_on_project():
    p = new_project()
    p.staged_edits.append(StagedEdit(edit_id="e1", op={"tool": "process_memory", "args": {}, "rationale": "r"},
                                     summary="add lesson", valid=True, preview={"op": "create"}))
    assert Project.model_validate_json(p.model_dump_json()) == p
    assert p.staged_edits[0].status == "pending" and p.staged_edits[0].applied_seq is None
