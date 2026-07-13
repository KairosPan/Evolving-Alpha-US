"""Revert-reconcile pure helpers (alpha/meta/reconcile.py). Duck-typed by design, so lightweight
stand-ins exercise the logic. (Previously covered only through the workbench worker-staged
cross-face flow, retired by A7 — the reconcile mechanism itself is unchanged and still live for
Sonia sessions after a restore.)"""
from __future__ import annotations

from types import SimpleNamespace as NS

from alpha.meta.reconcile import reconcile_session, reconcile_staged_edits


def _msg(applied_seqs, edits=None):
    return NS(applied_seqs=list(applied_seqs), edits=list(edits or []))


def test_reconcile_session_drops_reverted_seqs():
    # seq 2 is >= live_len (2) → dropped; seq 0,1 kept.
    sess = NS(messages=[_msg([0, 1, 2])])
    assert reconcile_session(sess, live_len=2) is True
    assert sess.messages[0].applied_seqs == [0, 1]


def test_reconcile_session_noop_when_all_seqs_kept():
    sess = NS(messages=[_msg([0, 1])])
    assert reconcile_session(sess, live_len=2) is False
    assert sess.messages[0].applied_seqs == [0, 1]


def test_reconcile_session_resets_reverted_edit_record():
    edit = NS(applied_seq=3, status="applied", apply_reason=None)
    sess = NS(messages=[_msg([], edits=[edit])])
    assert reconcile_session(sess, live_len=2) is True
    assert edit.applied_seq is None and edit.status == "accepted" and edit.apply_reason == "rolled back"


def test_reconcile_staged_edits_resets_reverted():
    stale = NS(applied_seq=3, status="approved", snapshot_before="snap", reason=None)
    kept = NS(applied_seq=0, status="approved", snapshot_before="snap0", reason=None)
    assert reconcile_staged_edits([stale, kept], live_len=2) is True
    assert stale.status == "pending" and stale.applied_seq is None
    assert stale.snapshot_before == "" and stale.reason == "rolled back"
    assert kept.status == "approved" and kept.applied_seq == 0     # below live_len → untouched


def test_reconcile_staged_edits_noop_when_none_reverted():
    kept = NS(applied_seq=1, status="approved", snapshot_before="s", reason=None)
    assert reconcile_staged_edits([kept], live_len=2) is False
