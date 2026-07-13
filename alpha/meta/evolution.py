"""Fork-and-propose evolution (charter conformance 2026-07-09).

The live self-study runners (refine_live, evolve_from_episodes) used to land edits on the live
brain autonomously — the charter's two-hands invariant forbids that. Here the run happens on a
FORK of the live brain (full machine autonomy inside the fork = the charter's trial semantics:
breaker rollbacks, gate rejections, conflict holds all stay fork-internal), and the surviving
delta ships as an EvolutionProposal packet the USER adopts or discards.

Soundness of wholesale adoption: every delta edit passed the full gate against a base that the
content-hash staleness check proves is byte-identical to the live brain at adopt time — landing
the fork ≡ landing the gate-approved results. If the live brain moved (teaching landed, a
rollback happened), the packet is stale and must be re-run, never merged."""
from __future__ import annotations

import re as _re
from typing import Callable

from alpha.harness.edit_log import EditLog
from alpha.harness.state import HarnessState
from alpha.meta.proposal_store import EvolutionProposal, ProposalQueue, brain_hash

# A runner receives a private fork (harness, log) and MUST return the FINAL (harness, log).
# Returning the final handles is load-bearing: an in-fork breaker rollback REBINDS
# HarnessManager.harness/.log to fresh restored objects — packaging from the handles passed in
# would ship the discarded pre-rollback timeline (found by the 2026-07-09 adversarial review).
Runner = Callable[[HarnessState, EditLog], tuple[HarnessState, EditLog]]

# The integrity-chain fields (A4) are DERIVED metadata finalized at persist time — not semantic
# edit content. A fork's in-run checkpoint finalizes its base-prefix records in place, and a legacy
# (pre-A4, unchained) live brain gets chained the moment ANY LiveBrainStore.save runs — so the
# packet's base and the live base can carry different chain metadata over identical edits. BOTH
# adopt-time checks that ask "is this the same base?" — the base_hash staleness pin and the
# prefix-extends check — compare edit CONTENT, so both strip these two fields on each side (at the
# evolution comparison sites only; brain_hash itself and harness_digest/h_digest stay untouched).
# A genuine base CONTENT change is still flagged (different content survives the strip); only a
# chain-metadata-only difference is tolerated. verify_chain integrity detection is unaffected — it
# is a different, whole-record check that reads exactly these fields.
_CHAIN_FIELDS = ("prev_chain_hash", "chain_hash")


def _chain_agnostic(records: list[dict]) -> list[dict]:
    return [{k: v for k, v in r.items() if k not in _CHAIN_FIELDS} for r in records]


# --- Deliberation-packet counsel (A8; charter *Evolution Deliberation Channel* "standard contents").
# All KERNEL-GENERATED from the delta (never the proposer): the Runner returns only handles, so
# there is no channel by which a proposer authors these. behavior_diff is additionally re-derived and
# refused at adopt, catching a hand-forged packet dropped into the queue off the builder.
def _behavior_diff(delta: list[dict]) -> list[dict]:
    """Structural before/after — one row per surviving delta record. NOT a full session-replay
    behavior diff (that needs the deferred trial-run replay infra, A10); the reviewable description
    of WHAT changed in H, a pure function of the records so a proposer cannot forge it."""
    return [{"seq": r.get("seq"), "tool": r.get("tool"), "target_kind": r.get("target_kind"),
             "target_id": r.get("target_id"), "op": r.get("op"), "summary": r.get("summary", "")}
            for r in delta]


def _dedup(delta: list[dict], landed: list[dict], pending: list) -> list[dict]:
    """Kernel-generated reuse/dedup listing: for each delta target, the landed records and pending
    proposals touching the same (target_kind, target_id) — the charter's similarity field over the
    existing library, never the proposer's self-report."""
    out: list[dict] = []
    for r in delta:
        key = (r.get("target_kind"), r.get("target_id"))
        landed_seqs = [lr.get("seq") for lr in landed
                       if (lr.get("target_kind"), lr.get("target_id")) == key]
        pending_ids = sorted({p.proposal_id for p in pending for pr in p.records
                              if (pr.get("target_kind"), pr.get("target_id")) == key})
        if landed_seqs or pending_ids:
            out.append({"target_kind": key[0], "target_id": key[1],
                        "landed_seqs": landed_seqs, "pending_proposal_ids": pending_ids})
    return out


def _coverage(delta: list[dict], window: dict | None) -> dict:
    """Evidence coverage of the window (charter *Trial-run … coverage*): the honest 'no applicable
    recorded coverage' value (has_coverage=False) when the window is empty."""
    return {"window": dict(window or {}), "n_delta": len(delta), "has_coverage": bool(window)}


def run_forked_evolution(bstore, runner: Runner, *, queue: ProposalQueue, kind: str,
                         window: dict | None = None,
                         cost: dict | None = None) -> EvolutionProposal | None:
    """Load the live brain (brief lock), run *runner* on it as a private fork (no lock held —
    load() returns private objects; nothing writes back), package the surviving delta.
    Returns the queued proposal, or None when the run produced no surviving edits (stated by
    the caller, never silent).

    `cost` (A8; A6's per-refinement scalar) rides onto the packet unchanged; None = unmetered. The
    packet's counsel fields (behavior diff / dedup / coverage) are KERNEL-GENERATED here from the
    delta — the Runner contributes only the (harness, log) handles, so a proposer cannot author
    them."""
    with bstore.lock():
        h, log = bstore.load()
    base_len = len(log)
    base_hash = brain_hash(h.to_dict(), _chain_agnostic(log.to_dict()))   # content, not chain metadata
    landed = [r.model_dump(mode="json") for r in log.records()[:base_len]]  # the live base, for dedup

    final_h, final_log = runner(h, log)

    delta = final_log.records()[base_len:]
    if not delta:
        return None
    delta_dicts = [r.model_dump(mode="json") for r in delta]
    return queue.new(kind=kind, base_len=base_len, base_hash=base_hash, window=window or {},
                     summary=f"{len(delta)} surviving edit(s) from a {kind} run",
                     records=delta_dicts,
                     harness_dict=final_h.to_dict(), log_dict=final_log.to_dict(),
                     behavior_diff=_behavior_diff(delta_dicts),
                     dedup=_dedup(delta_dicts, landed, queue.all()),
                     coverage=_coverage(delta_dicts, window), cost=cost)


def adopt_proposal(bstore, proposal: EvolutionProposal, *,
                   human_approver: str = "user") -> tuple[bool, str | None]:
    """Land an adopted packet on the live brain. Takes the brain lock itself — callers must NOT
    wrap this in bstore.lock() (flock on a second fd of the same file self-deadlocks).

    base_hash pins the packet's BASE; the checks below pin its RESULT — a hand-edited or
    producer-buggy packet must not land content the gate never saw (2026-07-09 final review):
    the fork log must EXTEND the live log, the delta the user reviewed must equal the delta that
    lands, and red-line doctrine entries can never change through the gate, so any honest fork
    preserves them byte-for-byte."""
    with bstore.lock():
        h, log = bstore.load()
        live_log_dict = log.to_dict()
        if brain_hash(h.to_dict(), _chain_agnostic(live_log_dict)) != proposal.base_hash:
            return False, "stale: live brain differs from the packet's base; re-run the evolution"
        if proposal.base_len != len(live_log_dict):
            return False, f"invalid packet: base_len={proposal.base_len} != live log {len(live_log_dict)}"
        if _chain_agnostic(proposal.log_dict[:proposal.base_len]) != _chain_agnostic(live_log_dict):
            return False, "invalid packet: fork log does not extend the live log (prefix mismatch)"
        if proposal.records != proposal.log_dict[proposal.base_len:]:
            return False, "invalid packet: reviewed records differ from the landing delta"
        # A8: the behavior-diff counsel is KERNEL-GENERATED from the records — re-derive and refuse a
        # forged one (a hand-built packet dropped into the queue off the builder). Legacy-tolerant:
        # a pre-A8 packet carries behavior_diff=[] and skips the check (byte-identical).
        if proposal.behavior_diff and proposal.behavior_diff != _behavior_diff(proposal.records):
            return False, "invalid packet: behavior_diff does not match the delta (forged counsel)"
        new_h = HarnessState.from_dict(proposal.harness_dict)
        live_core = [e.model_dump(mode="json") for e in h.doctrine.immutable_core()]
        new_core = [e.model_dump(mode="json") for e in new_h.doctrine.immutable_core()]
        if new_core != live_core:
            return False, "invalid packet: red-line doctrine entries differ from the live brain"
        if not bstore.is_live():
            bstore.save(h, log)                       # materialize before snapshot (seeds-only dir)
        # Re-stamp the delta with the human approver — dict-level transform on the serialized log
        # (EditRecord is frozen; no new EditLog mutator, no second write-path around the API).
        log_dict = [dict(r) for r in proposal.log_dict]
        default_proposer = "refiner" if proposal.kind == "refine" else "forge"
        for i in range(proposal.base_len, len(log_dict)):
            prov = dict(log_dict[i].get("provenance") or
                        {"path": "self_study", "proposer": default_proposer})
            prov["human_approver"] = human_approver
            log_dict[i]["provenance"] = prov
        safe_id = _re.sub(r"[^A-Za-z0-9._-]", "_", proposal.proposal_id)   # snapshot() has no
        bstore.snapshot(f"adopt-{safe_id}")                                # traversal guard
        bstore.save(new_h, EditLog.from_dict(log_dict))
    return True, None
