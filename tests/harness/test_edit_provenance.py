from alpha.harness.edit_log import EditLog, EditRecord, EditProvenance


def test_provenance_defaults_none_and_round_trips():
    log = EditLog()
    rec = log.append("patch_skill", "skill", "s1", "update", rationale="r")
    assert rec.provenance is None
    p = EditProvenance(path="self_study", proposer="refiner", parent_checkpoint_version=3)
    stamped = log.stamp_last(p)
    assert stamped.provenance == p and log.records()[-1].provenance == p
    assert EditLog.from_dict(log.to_dict()).records()[-1].provenance == p   # serializes


def test_latest_for_returns_most_recent_for_element():
    log = EditLog()
    log.append("process_memory", "memory", "m1", "create", rationale="r")
    log.stamp_last(EditProvenance(path="teaching", proposer="sonia"))
    log.append("update_memory", "memory", "m1", "update", rationale="r")
    log.stamp_last(EditProvenance(path="self_study", proposer="refiner"))
    log.append("patch_skill", "skill", "s1", "update", rationale="r")
    latest = log.latest_for("memory", "m1")
    assert latest is not None and latest.op == "update" and latest.provenance.proposer == "refiner"
    assert log.latest_for("skill", "nope") is None
