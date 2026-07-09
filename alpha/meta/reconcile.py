"""Revert reconciles derived state (charter conformance 2026-07-09): after any brain restore,
every derived record asserting a now-reverted seq must stop asserting it — session applied_seqs
(else /propose 409s forever) and workbench staged edits (else dead 'approved+applied' rows).
Pure functions over the record objects: both faces share ONE brain, so BOTH apps sweep BOTH
derived stores through these helpers (a sonia rollback must also heal workbench state and
vice versa). Duck-typed on purpose — no converse imports here (layer spine)."""
from __future__ import annotations


def reconcile_session(session, live_len: int) -> bool:
    """Drop assertions of seqs >= live_len from one teaching Session. Returns True if changed."""
    changed = False
    for m in session.messages:
        kept = [q for q in m.applied_seqs if q < live_len]
        if len(kept) != len(m.applied_seqs):
            m.applied_seqs = kept
            changed = True
        for e in m.edits:
            if e.applied_seq is not None and e.applied_seq >= live_len:
                if e.status == "applied":
                    e.status = "accepted"
                e.applied_seq, e.apply_reason = None, "rolled back"
                changed = True
    return changed


def reconcile_staged_edits(staged_edits, live_len: int) -> bool:
    """Reset workbench StagedEdits whose applied record no longer exists. Returns True if changed."""
    changed = False
    for e in staged_edits:
        if e.applied_seq is not None and e.applied_seq >= live_len:
            e.status, e.applied_seq = "pending", None
            e.snapshot_before, e.reason = "", "rolled back"
            changed = True
    return changed
