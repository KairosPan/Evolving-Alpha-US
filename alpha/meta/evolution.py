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

from typing import Callable

from alpha.harness.edit_log import EditLog
from alpha.harness.state import HarnessState
from alpha.meta.proposal_store import EvolutionProposal, ProposalQueue, brain_hash

# A runner receives a private fork (harness, log) and MUST return the FINAL (harness, log).
# Returning the final handles is load-bearing: an in-fork breaker rollback REBINDS
# HarnessManager.harness/.log to fresh restored objects — packaging from the handles passed in
# would ship the discarded pre-rollback timeline (found by the 2026-07-09 adversarial review).
Runner = Callable[[HarnessState, EditLog], tuple[HarnessState, EditLog]]


def run_forked_evolution(bstore, runner: Runner, *, queue: ProposalQueue, kind: str,
                         window: dict | None = None) -> EvolutionProposal | None:
    """Load the live brain (brief lock), run *runner* on it as a private fork (no lock held —
    load() returns private objects; nothing writes back), package the surviving delta.
    Returns the queued proposal, or None when the run produced no surviving edits (stated by
    the caller, never silent)."""
    with bstore.lock():
        h, log = bstore.load()
    base_len = len(log)
    base_hash = brain_hash(h.to_dict(), log.to_dict())

    final_h, final_log = runner(h, log)

    delta = final_log.records()[base_len:]
    if not delta:
        return None
    return queue.new(kind=kind, base_len=base_len, base_hash=base_hash, window=window or {},
                     summary=f"{len(delta)} surviving edit(s) from a {kind} run",
                     records=[r.model_dump(mode="json") for r in delta],
                     harness_dict=final_h.to_dict(), log_dict=final_log.to_dict())


def adopt_proposal(bstore, proposal: EvolutionProposal, *,
                   human_approver: str = "user") -> tuple[bool, str | None]:
    """Land an adopted packet on the live brain. Takes the brain lock itself — callers must NOT
    wrap this in bstore.lock() (flock on a second fd of the same file self-deadlocks).
    Staleness is checked by content hash (length alone is spoofable by land+rollback)."""
    with bstore.lock():
        h, log = bstore.load()
        if brain_hash(h.to_dict(), log.to_dict()) != proposal.base_hash:
            return False, "stale: live brain differs from the packet's base; re-run the evolution"
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
        bstore.snapshot(f"adopt-{proposal.proposal_id}")
        bstore.save(HarnessState.from_dict(proposal.harness_dict), EditLog.from_dict(log_dict))
    return True, None
