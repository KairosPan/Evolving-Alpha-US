"""Charter-conformance vocabulary (2026-07-09): the two-hands principals exist in the Literal,
and retired 'hermes' records in persisted brains still validate (read-compat)."""
from alpha.harness.edit_log import EditLog, EditProvenance, EditRecord


def _rec(prov: EditProvenance) -> dict:
    return EditRecord(seq=0, tool="process_memory", target_kind="memory", target_id="m-1",
                      op="create", provenance=prov).model_dump()


def test_kairos_and_user_principals_validate():
    for path, proposer in [("teaching", "kairos"), ("user_direct", "user")]:
        prov = EditProvenance(path=path, proposer=proposer, human_approver="user")
        rec = EditRecord.model_validate(_rec(prov))
        assert rec.provenance.proposer == proposer


def test_persisted_hermes_records_still_load():
    dumped = _rec(EditProvenance(path="teaching", proposer="hermes"))
    log = EditLog.from_dict([dumped])
    assert log.records()[0].provenance.proposer == "hermes"
