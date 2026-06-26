# alpha/refine/conflict.py
from __future__ import annotations
from alpha.harness.edit_log import EditLog, EditProvenance
from alpha.refine.ops import RefineOp
from alpha.refine.apply import _target_id

# tool -> the H element kind it targets (mirrors apply._dispatch / _target_id)
_KIND: dict[str, str] = {
    "write_skill": "skill", "patch_skill": "skill", "retire_skill": "skill",
    "revive_skill": "skill", "promote_skill": "skill",
    "process_memory": "memory", "update_memory": "memory", "demote_memory": "memory",
    "rewrite_doctrine": "doctrine",
}
# verbs that MUTATE/RETIRE/DEMOTE an EXISTING element (create verbs are excluded — they can't contest)
_CONTEST_VERBS: frozenset[str] = frozenset({
    "patch_skill", "retire_skill", "revive_skill", "promote_skill",
    "demote_memory", "update_memory", "rewrite_doctrine",
})

def is_conflict(log: EditLog, op: RefineOp, provenance: EditProvenance | None) -> bool:
    """True iff a self-study op contests a teaching-owned existing H element (spec §5.4 asymmetry)."""
    if provenance is None or provenance.path != "self_study":
        return False                                   # only self-study can be held; teaching applies
    if op.tool not in _CONTEST_VERBS:
        return False                                   # create verbs never contest
    tid = _target_id(op.tool, op.args)
    if tid is None:
        return False
    latest = log.latest_for(_KIND.get(op.tool, ""), tid)
    return latest is not None and latest.provenance is not None and latest.provenance.path == "teaching"
