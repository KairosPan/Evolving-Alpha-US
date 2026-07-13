from __future__ import annotations

import logging
import threading
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from alpha.harness.edit_log import EditProvenance
from alpha.harness.metatools import MetaTools
from alpha.llm.chat import ChatMessage
from alpha.llm.client import MockLLMClient
from alpha.llm.config import make_client
from alpha.refine.apply import ALL_TOOLS, try_apply_op
from alpha.refine.ops import RefineOp
from alpha.meta.agent import MetaAgent, preview_op
from alpha.meta.extractor import extract_ops
from alpha.meta.models import Attachment, Message, Session, new_message_id, new_session_id, now_iso
from alpha.meta.sonia_agent import SoniaAgent, turn_text
from alpha.meta.conflict_store import ConflictQueue
from alpha.meta.evolution import adopt_proposal
from alpha.meta.negative_constraint import NegativeConstraintStore
from alpha.meta.proposal_store import ProposalQueue, brain_hash, proposals_dir
from alpha.meta.body_git import make_brain_store
from alpha.meta.reconcile import reconcile_session, reconcile_staged_edits
from alpha.meta.store import LiveBrainStore, SessionStore
from alpha.settings import Settings

_MUTATION_LOCK = threading.Lock()
_log = logging.getLogger("alpha.sonia")

_CHAIN_FIELDS = ("prev_chain_hash", "chain_hash")


def _brain_content_hash(h, log) -> str:
    """A8 staleness pin: content hash of the brain a preview was dry-run against. Chain-agnostic
    (strips the A4 integrity-chain metadata, mirroring evolution.py's staleness pin) so a persist-
    time chain finalize can't spuriously invalidate the pin — only a real content change does."""
    records = [{k: v for k, v in r.items() if k not in _CHAIN_FIELDS} for r in log.to_dict()]
    return brain_hash(h.to_dict(), records)


def _brain_store() -> LiveBrainStore:
    s = Settings.from_env()
    return make_brain_store(s.live_brain_dir, git=s.body_git)   # A5: git-backed iff ALPHA_BODY_GIT


def _session_store() -> SessionStore:
    return SessionStore(Settings.from_env().sessions_dir)


def _conflict_store() -> ConflictQueue:
    return ConflictQueue(Settings.from_env().conflicts_dir)


def _proposal_store() -> ProposalQueue:
    return ProposalQueue(proposals_dir())


def _neg_constraint_store() -> NegativeConstraintStore:
    return NegativeConstraintStore(Settings.from_env().neg_constraints_dir)


def _reconcile_all(live_len: int, sstore: SessionStore, current: "Session | None" = None) -> str:
    """After a brain restore: sweep EVERY derived store that can assert reverted seqs — all
    teaching sessions AND the workbench staged edits (both faces share the one brain, so a
    rollback issued here must also heal workbench state; see alpha/meta/reconcile.py).
    Returns the cross-face sweep status ("ok" | "skipped: …" | "failed: …") — a locked/corrupt
    workbench DB must be VISIBLE in the response, never a silent ok (final review 2026-07-09)."""
    if current is not None:
        reconcile_session(current, live_len)         # caller persists `current` itself
    for other in sstore.list():
        if current is not None and other.session_id == current.session_id:
            continue
        if reconcile_session(other, live_len):
            sstore.put(other)
    from alpha.converse.sqlite_store import SqliteProjectStore
    try:
        pstore = SqliteProjectStore.open(
            Settings.from_env().projects_db,
            create_if_missing=False)
    except FileNotFoundError:                        # no workbench DB → legitimate no-op
        return "skipped: no workbench DB"
    except Exception as e:                           # locked/corrupt — surface, don't swallow
        return f"failed: {type(e).__name__}: {e}"
    try:
        for proj in pstore.list():
            if reconcile_staged_edits(proj.staged_edits, live_len):
                pstore.put(proj)
    except Exception as e:
        return f"failed: {type(e).__name__}: {e}"
    finally:
        pstore.close()
    return "ok"


class ChatIn(BaseModel):
    session_id: str | None = None
    text: str = ""
    attachments: list[Attachment] = []


class EditAction(BaseModel):
    action: str  # "accept" | "reject"


class ResolveIn(BaseModel):
    decision: str  # "accept_self_study" | "keep_teaching"


class DirectEditIn(BaseModel):
    tool: str
    args: dict = {}
    rationale: str = ""


class ProposalResolveIn(BaseModel):
    decision: str  # "adopt" | "discard"


def create_app() -> FastAPI:
    app = FastAPI(title="Sonia · meta-agent")

    @app.get("/healthz")
    def healthz():
        store = _brain_store()
        return {"ok": True, "brain_live": store.is_live(), "edit_count": store.edit_count()}

    @app.post("/sessions/new")
    def new_session():
        sess = Session(session_id=new_session_id(), created_at=now_iso())
        _session_store().put(sess)
        return sess.model_dump()

    @app.get("/sessions")
    def list_sessions():
        return [s.model_dump() for s in _session_store().list()]

    @app.get("/sessions/{sid}")
    def get_session(sid: str):
        s = _session_store().get(sid)
        if s is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        return s.model_dump()

    @app.post("/sessions/{sid}/delete")
    def delete_session(sid: str):
        _session_store().delete(sid)        # idempotent; touches only the session record, not the brain
        return {"deleted": sid}

    @app.post("/chat")
    def chat(body: ChatIn):
        sstore = _session_store()
        sess = sstore.get(body.session_id) if body.session_id else None
        if sess is None:
            sess = Session(session_id=new_session_id(), created_at=now_iso())
        if not sess.title:
            sess.title = (body.text or "untitled").strip()[:60] or "untitled"
        user_msg = Message(message_id=new_message_id(), role="user", created_at=now_iso(),
                           text=body.text, attachments=body.attachments, origin="user")
        try:
            h, log = _brain_store().load()                           # inside the boundary: a locked/
            agent = SoniaAgent(MetaTools(h, log), make_client("sonia"))  # corrupt brain load must not
            asst = agent.respond(sess, user_msg)                     # 500 either — keep the user turn
        except Exception as e:                                       # never 500: keep the user turn
            asst = Message(message_id=new_message_id(), role="assistant", created_at=now_iso(),
                           text=f"(Sonia couldn't respond: {type(e).__name__}: {e})", origin="model")
        sess.messages.append(user_msg)
        sess.messages.append(asst)
        sstore.put(sess)
        return {"session_id": sess.session_id, "user_message": user_msg.model_dump(),
                "assistant_message": asst.model_dump()}

    def _find(sess: Session, mid: str) -> Message | None:
        return next((m for m in sess.messages if m.message_id == mid), None)

    @app.post("/sessions/{sid}/edit/{eid}")
    def edit_action(sid: str, eid: str, body: EditAction):
        with _MUTATION_LOCK:                                  # read-modify-write on the session record —
            sstore = _session_store()                        # serialize with apply/rollback (same lock)
            sess = sstore.get(sid)                            # so a concurrent apply can't lose this flip
            if sess is None:
                return JSONResponse({"error": "not found"}, status_code=404)
            for m in sess.messages:
                for e in m.edits:
                    if e.edit_id == eid:
                        e.status = "accepted" if body.action == "accept" else "rejected"
                        sstore.put(sess)
                        return e.model_dump()
            return JSONResponse({"error": "edit not found"}, status_code=404)

    @app.post("/sessions/{sid}/messages/{mid}/propose")
    def propose(sid: str, mid: str):
        sstore = _session_store()
        sess = sstore.get(sid)
        msg = _find(sess, mid) if sess else None
        if msg is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        if msg.applied_seqs:
            return JSONResponse({"error": "already applied"}, status_code=409)
        idx = sess.messages.index(msg)
        convo = [ChatMessage(role=m.role, text=turn_text(m)) for m in sess.messages[: idx + 1]]
        h, log = _brain_store().load()                                 # read-only
        try:
            res = extract_ops(make_client("sonia"), h, convo)
        except Exception as e:                                         # extractor unavailable — visible, never silent
            return JSONResponse({"error": f"{type(e).__name__}: {e}"}, status_code=502)
        if res.ops:
            msg.edits = [preview_op(h, op) for op in res.ops]
            msg.proposal_note = ""
            msg.previewed_hash = _brain_content_hash(h, log)           # A8: pin the previewed brain
        else:
            msg.edits = []
            msg.proposal_note = res.reason
            msg.previewed_hash = ""
        sstore.put(sess)
        return {"session_id": sid, "message": msg.model_dump()}

    @app.post("/sessions/{sid}/messages/{mid}/apply")
    def apply_message(sid: str, mid: str):
        with _MUTATION_LOCK:
            sstore = _session_store()
            sess = sstore.get(sid)
            msg = _find(sess, mid) if sess else None
            if msg is None:
                return JSONResponse({"error": "not found"}, status_code=404)
            accepted = [e for e in msg.edits if e.status == "accepted"]
            bstore = _brain_store()
            with bstore.lock():
                h, log = bstore.load()
                # A8 staleness pin: what was previewed must be what lands. If the live brain moved
                # since the preview (another teach landed, a rollback, a fork adopt), refuse and
                # ask for a re-preview instead of silently applying against a different base.
                if msg.previewed_hash and _brain_content_hash(h, log) != msg.previewed_hash:
                    return JSONResponse(
                        {"error": "stale: brain changed since preview; re-preview"}, status_code=409)
                if not bstore.is_live():
                    bstore.save(h, log)                               # materialize before snapshot
                msg.snapshot_before = bstore.snapshot(f"{sid}-{mid}")
                applied, _rows = MetaAgent(MetaTools(h, log), MockLLMClient("{}")).apply(
                    accepted, human_approver="user")
                bstore.save(h, log)
                # persist the derived record INSIDE the flock so it can never lag the brain
                # across processes (a concurrent restore's sweep reads both under the same lock)
                msg.applied_seqs = [r.seq for r in applied]
                sstore.put(sess)
            return {"applied": len(applied), "edits": [e.model_dump() for e in msg.edits]}

    @app.post("/edit")
    def direct_edit(body: DirectEditIn):
        """The charter's second hand (2026-07-08 amendment): the USER's own edit, landed through
        the same gate — stamped user/user_direct, audited, snapshotted, no deliberation. Sample
        floors are lifted for the user's hand (min_*=0); the structural checks (tool whitelist,
        rationale required, red-line immutability, set-once domain, positive-expectancy promote)
        still bind — the Applier validates mechanically even for the user."""
        with _MUTATION_LOCK:
            bstore = _brain_store()
            with bstore.lock():
                h, log = bstore.load()
                if not bstore.is_live():
                    bstore.save(h, log)                       # materialize before snapshot
                op = RefineOp(tool=body.tool, args=dict(body.args), rationale=body.rationale)
                rec, reason = try_apply_op(MetaTools(h, log), h, op, allowed=ALL_TOOLS,
                                           min_retire_samples=0, min_promote_samples=0,
                                           provenance=EditProvenance(path="user_direct", proposer="user",
                                                                     human_approver="user"))
                if rec is None:
                    return JSONResponse({"applied": False, "reason": reason}, status_code=422)
                snap = bstore.snapshot(f"user-edit-{new_session_id()}")   # disk still pre-edit here
                bstore.save(h, log)
            return {"applied": True, "seq": rec.seq, "summary": rec.summary, "snapshot_before": snap}

    @app.get("/conflicts")
    def list_conflicts():
        return [c.model_dump() for c in _conflict_store().all()]

    @app.post("/conflicts/{cid}/resolve")
    def resolve_conflict(cid: str, body: ResolveIn):
        q = _conflict_store()
        held = q.get(cid)
        if held is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        # §5-accepted: accept_self_study records intent only (no auto-re-apply); both decisions resolve+remove.
        q.resolve(cid)
        return {"resolved": cid, "decision": body.decision}

    @app.get("/proposals")
    def list_proposals():
        # list view drops the heavy brain payloads; the delta records ARE the review surface
        return [p.model_dump(exclude={"harness_dict", "log_dict"}) for p in _proposal_store().all()]

    @app.post("/proposals/{pid}/resolve")
    def resolve_proposal(pid: str, body: ProposalResolveIn):
        """Adopt or discard an evolution packet. Adopt lands the fork wholesale IFF the live
        brain still content-hashes to the packet's base (else 409 stale — re-run, never merge);
        discard deletes the packet (the fork's evidence dies with its session, per charter)."""
        with _MUTATION_LOCK:
            q = _proposal_store()
            prop = q.get(pid)
            if prop is None:
                return JSONResponse({"error": "not found"}, status_code=404)
            if body.decision not in ("adopt", "discard"):           # discard is DESTRUCTIVE —
                return JSONResponse({"error": f"unknown decision {body.decision!r}; "
                                              "expected 'adopt' or 'discard'"}, status_code=422)
            if body.decision == "adopt":
                ok, reason = adopt_proposal(_brain_store(), prop)   # takes the brain lock itself
                if not ok:
                    return JSONResponse({"adopted": False, "reason": reason}, status_code=409)
                q.resolve(pid)
                return {"resolved": pid, "decision": "adopt", "landed_records": len(prop.records)}
            # A3 human-rejection mining: a DISCARDED self-learning (kind="reflect") proposal turns
            # each direction it carried into a negative constraint, so the detector never re-proposes
            # it. Scoped to reflect packets (a discarded refine/forge packet creates no constraint);
            # never breaks the discard on a store error (best-effort, like the reconcile sweeps).
            mined = 0
            if prop.kind == "reflect":
                try:
                    from alpha.refine.reflect import record_directions_from_proposal
                    mined = record_directions_from_proposal(_neg_constraint_store(), prop)
                except Exception:                       # a store failure must not block the discard
                    _log.exception("negative-constraint mining failed for discarded proposal %s", pid)
                    mined = 0
            q.resolve(pid)
            return {"resolved": pid, "decision": "discard", "constraints_recorded": mined}

    def _history_dir() -> Path:
        return Path(Settings.from_env().live_brain_dir) / "history"

    @app.get("/snapshots")
    def list_snapshots():
        hist = _history_dir()
        if not hist.is_dir():
            return []
        return sorted((p.stem for p in hist.glob("*.json")), reverse=True)

    @app.post("/snapshots/{name}/restore")
    def restore_snapshot(name: str):
        """The user's revert lever for ANY landing (incl. /edit user-direct edits, which have no
        session message to roll back through). Restores a named history snapshot, then runs the
        full derived-state reconcile sweep."""
        with _MUTATION_LOCK:
            hist = _history_dir()
            p = (hist / f"{name}.json").resolve()
            if not hist.is_dir() or not p.is_relative_to(hist.resolve()):
                return JSONResponse({"error": "invalid snapshot name"}, status_code=400)
            if not p.exists():
                return JSONResponse({"error": "not found"}, status_code=404)
            bstore = _brain_store()
            with bstore.lock():                      # sweep INSIDE the flock: the other face
                bstore.restore(str(p))               # must not land/read between restore and
                _, log = bstore.load()               # reconcile (final review 2026-07-09)
                sweep = _reconcile_all(len(log), _session_store())
            return {"ok": True, "restored": name, "workbench_sweep": sweep}

    @app.post("/sessions/{sid}/messages/{mid}/rollback")
    def rollback_message(sid: str, mid: str):
        with _MUTATION_LOCK:
            sstore = _session_store()
            sess = sstore.get(sid)
            msg = _find(sess, mid) if sess else None
            if msg is None or not msg.snapshot_before:
                return JSONResponse({"error": "nothing to roll back"}, status_code=404)
            bstore = _brain_store()
            with bstore.lock():                      # sweep INSIDE the flock (final review)
                bstore.restore(msg.snapshot_before)
                _, log = bstore.load()
                # Revert reconciles derived state (charter conformance 2026-07-09): any record
                # asserting a now-reverted seq must stop asserting it — else /propose 409s forever
                # on a rolled-back turn and workbench keeps dead 'approved+applied' rows.
                sweep = _reconcile_all(len(log), sstore, current=sess)
                sess.notes.append(f"rolled back {mid}")
                sstore.put(sess)
            return {"ok": True, "workbench_sweep": sweep}

    return app


app = create_app()
