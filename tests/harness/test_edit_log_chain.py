"""A4 (b) — the append-time integrity chain on EditLog (TCB alpha/harness/edit_log.py).

Acceptance: verify_chain() green across a rollback + a legacy unchained-prefix; corruption caught;
the chain is finalized at persist time (the store's save() calls finalize_chain(); to_dict stays
PURE so the evolution packet's per-record model_dump == to_dict). Additive: an unfinalized log
serializes byte-identically to the pre-chain edit log.
"""
from __future__ import annotations

import copy
import tempfile

from alpha.harness.edit_log import EditLog, EditRecord
from alpha.harness.manager import HarnessManager
from alpha.harness.snapshot import SnapshotStore
from alpha.harness.state import HarnessState
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore


def _log(n: int = 3) -> EditLog:
    log = EditLog()
    for i in range(n):
        log.append("write_skill", "skill", f"s{i}", "create", summary=f"c{i}", rationale="r")
    return log


def test_unfinalized_log_serializes_byte_identically():
    # to_dict is PURE: an unfinalized log dumps chain fields at their None defaults — the pre-A4
    # payload plus two null keys (additive), and no per-record model_dump differs from to_dict.
    log = _log()
    assert all(r.chain_hash is None for r in log.records())
    data = log.to_dict()
    assert all(d["chain_hash"] is None and d["prev_chain_hash"] is None for d in data)
    assert data == [r.model_dump(mode="json") for r in log.records()]     # to_dict == per-record dump


def test_finalize_chains_and_verifies():
    log = _log()
    log.finalize_chain()                      # what the store's save() calls at persist time
    assert all(r.chain_hash for r in log.records())
    assert log.verify_chain() is True
    assert log.chain_head() == log.records()[-1].chain_hash
    assert len(log.chain_head()) == 64


def test_chain_links_each_record_to_its_predecessor():
    log = _log()
    log.finalize_chain()
    recs = log.records()
    assert recs[0].prev_chain_hash is None                       # genesis
    for a, b in zip(recs, recs[1:]):
        assert b.prev_chain_hash == a.chain_hash                 # each links to the prior head


def test_finalize_is_idempotent():
    log = _log()
    log.finalize_chain()
    head1, dump1 = log.chain_head(), log.to_dict()
    log.finalize_chain()                      # re-finalize: already chained → no change
    assert (log.chain_head(), log.to_dict()) == (head1, dump1)


def test_verify_green_across_rollback():
    h = HarnessState(doctrine=Doctrine(), skills=SkillRegistry.from_skills([]),
                     memory=MemoryStore.from_lessons([]))
    mgr = HarnessManager(h, SnapshotStore(tempfile.mkdtemp()))
    mgr.log.append("write_skill", "skill", "a", "create", rationale="r")
    v0 = mgr.checkpoint("v0")                 # save() finalizes the chain into the snapshot
    mgr.log.append("patch_skill", "skill", "a", "update", rationale="r2")
    mgr.checkpoint("v1")
    mgr.rollback_to(v0)                        # loads v0's (chained) log
    assert mgr.log.verify_chain() is True
    assert mgr.log.chain_head() is not None


def test_legacy_unchained_prefix_tolerated_on_load_then_chained_on_persist():
    # A legacy snapshot: records with NO chain fields. verify_chain tolerates them on load.
    legacy = [EditRecord(seq=0, tool="t", target_kind="skill", target_id="a", op="create").model_dump(mode="json")]
    for d in legacy:                                # truly pre-feature on disk: no chain fields
        d.pop("prev_chain_hash", None)
        d.pop("chain_hash", None)
    log = EditLog.from_dict(legacy)
    assert log.verify_chain() is True and log.chain_head() is None   # unchained prefix, no head yet
    # A new edit + persist (finalize) chains the whole log from genesis; it still verifies. The
    # honest limit (external anchor) covers the "can't prove pre-feature history" gap, not the chain.
    log.append("patch_skill", "skill", "a", "update", rationale="new")
    log.finalize_chain()
    assert log.verify_chain() is True
    assert log.chain_head() is not None


def test_loaded_chain_is_preserved_not_recomputed():
    # A saved (chained) log, loaded then re-finalized, keeps its hashes byte-for-byte (idempotent).
    log = _log()
    log.finalize_chain()
    data = log.to_dict()
    reloaded = EditLog.from_dict(data)
    reloaded.finalize_chain()                 # already chained → preserved
    assert reloaded.to_dict() == data
    assert reloaded.verify_chain() is True


def test_interior_tamper_is_detected():
    log = _log()
    log.finalize_chain()
    tampered = copy.deepcopy(log.to_dict())
    tampered[1]["rationale"] = "TAMPERED-AFTER-HASH"
    assert EditLog.from_dict(tampered).verify_chain() is False


def test_reorder_is_detected():
    log = _log()
    log.finalize_chain()
    data = log.to_dict()
    reordered = [data[0], data[2], data[1]]        # swap two chained records
    assert EditLog.from_dict(reordered).verify_chain() is False
