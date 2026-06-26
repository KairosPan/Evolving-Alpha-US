from __future__ import annotations
import os, threading
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from alpha.llm.config import make_client
from alpha.data.registry import make_source
from alpha.meta.store import LiveBrainStore
from alpha.converse.store import ProjectStore
from alpha.converse.workspace import Workspace
from alpha.converse.session import converse_project

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
def _project_store(): return ProjectStore(os.environ.get("ALPHA_PROJECTS_DIR", "./state/projects"))


def _workspace():
    ws = Workspace(os.path.join(os.environ.get("ALPHA_WORKSPACE_DIR", "./state/workspaces"), DEFAULT_PROJECT_ID))
    ws.init()
    return ws


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
            h, _log = _brain_store().load()                 # read live brain for context/decide
            try:
                proj = converse_project(DEFAULT_PROJECT_ID, body.text, harness=h, store=_project_store(),
                                        agent_llm=_agent_llm(), chat_llm=_chat_llm(), source=_source(),
                                        workspace=_workspace(), write_mode="stage")
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

    return app


app = create_app()
