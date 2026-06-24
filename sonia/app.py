from __future__ import annotations

import os
import threading

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from alpha.harness.metatools import MetaTools
from alpha.llm.config import make_client
from alpha.meta.models import Attachment, Message, Session, new_message_id, new_session_id, now_iso
from alpha.meta.sonia_agent import SoniaAgent
from alpha.meta.store import LiveBrainStore, SessionStore

_MUTATION_LOCK = threading.Lock()


def _brain_store() -> LiveBrainStore:
    return LiveBrainStore(os.environ.get("ALPHA_LIVE_BRAIN_DIR", "./state/brain"))


def _session_store() -> SessionStore:
    return SessionStore(os.environ.get("ALPHA_SESSIONS_DIR", "./state/sessions"))


class ChatIn(BaseModel):
    session_id: str | None = None
    text: str = ""
    attachments: list[Attachment] = []


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

    @app.post("/chat")
    def chat(body: ChatIn):
        sstore = _session_store()
        sess = sstore.get(body.session_id) if body.session_id else None
        if sess is None:
            sess = Session(session_id=new_session_id(), created_at=now_iso())
        if not sess.title:
            sess.title = (body.text or "untitled").strip()[:60] or "untitled"
        user_msg = Message(message_id=new_message_id(), role="user", created_at=now_iso(),
                           text=body.text, attachments=body.attachments)
        h, log = _brain_store().load()
        try:
            agent = SoniaAgent(MetaTools(h, log), make_client("sonia"))
            asst = agent.respond(sess, user_msg)
        except Exception as e:                                       # never 500: keep the user turn
            asst = Message(message_id=new_message_id(), role="assistant", created_at=now_iso(),
                           text=f"(Sonia couldn't respond: {type(e).__name__}: {e})")
        sess.messages.append(user_msg)
        sess.messages.append(asst)
        sstore.put(sess)
        return {"session_id": sess.session_id, "user_message": user_msg.model_dump(),
                "assistant_message": asst.model_dump()}

    return app


app = create_app()
