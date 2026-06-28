from __future__ import annotations
import os, threading
from pathlib import Path as _Path
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from alpha.llm.config import make_client
from alpha.data.registry import make_source
from alpha.meta.store import LiveBrainStore
from alpha.converse.sqlite_store import SqliteProjectStore
from alpha.converse.workspace import Workspace
from alpha.converse.session import converse_project
from alpha.harness.metatools import MetaTools
from alpha.harness.edit_log import EditProvenance
from alpha.refine.apply import try_apply_op, ALL_TOOLS
from alpha.refine.ops import RefineOp, PASS_TOOLS
from alpha.converse.approve import assert_approvable, StagedEditNotApproved
from alpha.arena.builder import build_arena
from alpha.arena.environment import LocalEnv

DEFAULT_PROJECT_ID = "default"
_MUTATION_LOCK = threading.Lock()
_CHAT_LLM = None
_AGENT_LLM = None
_SOURCE = None


def set_llms(*, chat=None, agent=None, source=None) -> None:   # test seam
    global _CHAT_LLM, _AGENT_LLM, _SOURCE
    _CHAT_LLM, _AGENT_LLM, _SOURCE = chat, agent, source


def _chat_llm():  return _CHAT_LLM if _CHAT_LLM is not None else make_client("converse")
def _agent_llm(): return _AGENT_LLM if _AGENT_LLM is not None else make_client("agent")
def _source():    return _SOURCE if _SOURCE is not None else make_source()


def _brain_store():   return LiveBrainStore(os.environ.get("ALPHA_LIVE_BRAIN_DIR", "./state/brain"))
def _project_store(): return SqliteProjectStore.open(os.environ.get("ALPHA_PROJECTS_DB", "./state/projects/state.db"))


def _workspace():
    ws = Workspace(os.path.join(os.environ.get("ALPHA_WORKSPACE_DIR", "./state/workspaces"), DEFAULT_PROJECT_ID))
    ws.init()
    return ws


def _brain_dir() -> str:
    return os.environ.get("ALPHA_LIVE_BRAIN_DIR", "./state/brain")


def _assert_brain_outside_workspace() -> None:
    """Fail fast if the brain dir is inside the workspace — a live shell could then reach it."""
    ws_root = _Path(os.environ.get("ALPHA_WORKSPACE_DIR", "./state/workspaces")).resolve()
    brain = _Path(_brain_dir()).resolve()
    if brain == ws_root or brain.is_relative_to(ws_root):
        raise RuntimeError(
            f"brain dir {brain} is inside workspace {ws_root}; move them apart "
            "(LocalEnv is not a kernel boundary — the brain must sit outside the shell's workspace)")


def _arena_factory(workspace_root):
    """Return a converse_project registry_factory that builds the arena with a LocalEnv pointed
    at *workspace_root* (full computer-use: decide/read/write/shell + the policy choke point)."""
    env = LocalEnv(workspace=workspace_root)
    def factory(h, agent_llm, source, *, read_only, write_mode):
        reg, pol = build_arena(h, agent_llm, source, workspace=workspace_root, env=env,
                               write_mode=write_mode, read_only=read_only)
        return reg, pol.dispatch
    return factory


class ConverseIn(BaseModel):
    text: str = ""


def _project_view(proj) -> dict:
    return {"project_id": proj.project_id,
            "messages": [m.model_dump() for m in proj.messages],
            "turns": [t.model_dump() for t in proj.turns],
            "staged_edits": [e.model_dump() for e in proj.staged_edits],
            "artifacts": _workspace().artifacts()}


def create_app() -> FastAPI:
    app = FastAPI(title="Workbench · evolving-alpha conversational face")

    @app.get("/healthz")
    def healthz():
        s = _brain_store()
        return {"ok": True, "brain_live": s.is_live(), "edit_count": s.edit_count()}

    @app.post("/converse")
    def converse_ep(body: ConverseIn):
        with _MUTATION_LOCK:
            _assert_brain_outside_workspace()
            h, _log = _brain_store().load()                 # read live brain for context/decide
            ws = _workspace()
            try:
                proj = converse_project(DEFAULT_PROJECT_ID, body.text, harness=h, store=_project_store(),
                                        agent_llm=_agent_llm(), chat_llm=_chat_llm(), source=_source(),
                                        workspace=ws, write_mode="stage",
                                        registry_factory=_arena_factory(ws.root))
            except Exception as e:                           # never 500 — keep the user turn
                store = _project_store(); proj = store.get(DEFAULT_PROJECT_ID)
                from alpha.converse.project import new_project, new_turn
                if proj is None:
                    proj = new_project(); proj.project_id = DEFAULT_PROJECT_ID
                t = new_turn(body.text); t.final_text = f"(workbench couldn't respond: {type(e).__name__})"
                proj.turns.append(t); store.put(proj)
            last = proj.turns[-1].final_text if proj.turns else ""
            return {"project_id": proj.project_id, "assistant_text": last,
                    "staged_edits": [e.model_dump() for e in proj.staged_edits if e.status == "pending"],
                    "artifacts": _workspace().artifacts()}

    @app.get("/project")
    def get_project():
        proj = _project_store().get(DEFAULT_PROJECT_ID)
        if proj is None:
            return {"project_id": DEFAULT_PROJECT_ID, "messages": [], "turns": [],
                    "staged_edits": [], "artifacts": []}
        return _project_view(proj)

    def _find(proj, eid):
        return next((e for e in proj.staged_edits if e.edit_id == eid and e.status == "pending"), None)

    @app.post("/edits/{eid}/approve")
    def approve_edit(eid: str):
        with _MUTATION_LOCK:
            pstore = _project_store(); proj = pstore.get(DEFAULT_PROJECT_ID)
            se = _find(proj, eid) if proj else None
            if se is None:
                return JSONResponse({"error": "not found"}, status_code=404)
            bstore = _brain_store()
            with bstore.lock():
                h, log = bstore.load()
                if not bstore.is_live():
                    bstore.save(h, log)
                se.status = "approved"
                try:
                    assert_approvable(se)
                except StagedEditNotApproved as exc:
                    se.status, se.reason = "rejected", str(exc)
                    pstore.put(proj)
                    return JSONResponse({"error": str(exc), "edit_id": eid, "status": "rejected"}, status_code=422)
                snap = bstore.snapshot(f"approve-{eid}")
                op = RefineOp(tool=se.op["tool"], args=dict(se.op["args"]), rationale=se.op.get("rationale", ""))
                rec, reason = try_apply_op(MetaTools(h, log), h, op, allowed=PASS_TOOLS["M"],
                                           min_retire_samples=5, min_promote_samples=3,
                                           provenance=EditProvenance(path="teaching", proposer="hermes"))
                if rec is not None:
                    bstore.save(h, log)
                    se.applied_seq, se.snapshot_before, se.reason = rec.seq, snap, None
                else:
                    se.status, se.reason = "rejected", reason
            pstore.put(proj)
            return {"edit_id": eid, "status": se.status, "reason": se.reason}

    @app.post("/edits/{eid}/reject")
    def reject_edit(eid: str):
        with _MUTATION_LOCK:
            pstore = _project_store(); proj = pstore.get(DEFAULT_PROJECT_ID)
            se = _find(proj, eid) if proj else None
            if se is None:
                return JSONResponse({"error": "not found"}, status_code=404)
            se.status = "rejected"; pstore.put(proj)
            return {"edit_id": eid, "status": "rejected"}

    @app.post("/rollback")
    def rollback():
        with _MUTATION_LOCK:
            pstore = _project_store(); proj = pstore.get(DEFAULT_PROJECT_ID)
            snaps = [e.snapshot_before for e in (proj.staged_edits if proj else []) if e.snapshot_before]
            if not snaps:
                return JSONResponse({"error": "nothing to roll back"}, status_code=404)
            bstore = _brain_store()
            with bstore.lock():
                bstore.restore(snaps[-1])
            return {"ok": True}

    return app


app = create_app()
