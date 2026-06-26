"""Regime Instrument — FastAPI + HTMX console. Read-only window onto the co-pilot's evolving mind
and its outputs. Run: `python -m alpha_web` (or `uvicorn alpha_web.app:app`). Needs the web extra.

Real artifacts override the SAMPLE on the Decisions/Verdict pages:
  ALPHA_WEB_DECISION=/path/to/decision.json   (a DecisionPackage.model_dump_json)
  ALPHA_WEB_VERDICT=/path/to/verdict.json      (a dict shaped like alpha_web.sample.sample_verdict)
"""
from __future__ import annotations

import json
import os
from datetime import date as Date
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from alpha.eval.decision import DecisionPackage
from alpha.eval.decision_store import DecisionStore
from alpha.eval.verdict_store import VerdictStore
from alpha.meta.ingest import ingest_attachments
from alpha_web import data_access as da
from alpha_web import sample
from alpha_web.sonia_client import SoniaClient

_SONIA: SoniaClient | None = None


def set_sonia_client(client) -> None:
    """Test seam: inject an in-process SoniaClient (sync, wrapping a Sonia TestClient). None → use ALPHA_SONIA_URL."""
    global _SONIA
    _SONIA = client


def _sonia() -> SoniaClient:
    return _SONIA if _SONIA is not None else SoniaClient()

NAV = [
    {"path": "/", "key": "teach", "label": "Teach"},
    {"path": "/deck", "key": "deck", "label": "Deck"},
    {"key": "brain", "label": "Brain", "children": [
        {"path": "/doctrine",  "key": "doctrine",  "label": "Doctrine"},
        {"path": "/memory",    "key": "memory",    "label": "Memory"},
        {"path": "/workflow",  "key": "workflow",  "label": "Workflow"},
        {"path": "/skills",    "key": "skills",    "label": "Skill"},
        {"path": "/connector", "key": "connector", "label": "Connector"},
        {"path": "/subagent",  "key": "subagent",  "label": "Subagent"},
    ]},
    {"path": "/decisions", "key": "decisions", "label": "Decisions"},
    {"path": "/verdict", "key": "verdict", "label": "Verdict"},
    {"path": "/evolution", "key": "evolution", "label": "Autonomous"},
    {"path": "/conflicts", "key": "conflicts", "label": "Conflicts"},
]

BRAIN_KEYS = {"doctrine", "memory", "workflow", "skills", "connector", "subagent"}

_BRAIN_STUBS = {
    "workflow":  ("Workflow",  "Named multi-step playbooks Sonia composes from skills."),
    "connector": ("Connector", "External data/tool connections the agent draws on (Alpaca, EDGAR, MCP feeds…)."),
    "subagent":  ("Subagent",  "Specialized dispatch sub-agents the master agent delegates to."),
}

SKILL_STATUSES = ["active", "incubating", "dormant", "retired"]
SKILL_TYPES = ["pattern", "failure_detector", "feature"]
OUTCOMES = ["win", "loss", "principle"]


def _make_templates() -> Jinja2Templates:
    t = Jinja2Templates(directory=str(da.TEMPLATES_DIR))
    t.env.globals.update(
        phases=da.PHASES,
        phase_by_key=da.PHASE_BY_KEY,
        families=da.FAMILIES,
        skill_statuses=SKILL_STATUSES,
        skill_types=SKILL_TYPES,
        outcomes=OUTCOMES,
        nav=NAV,
        brain_keys=BRAIN_KEYS,
        ring=da.ring_segments(),
        tape_regime=sample.sample_regime(),       # the omnipresent regime read (sample state)
        tape_state=sample.sample_market_state(),
        fmt_val=lambda v: ", ".join(map(str, v)) if isinstance(v, list) else str(v),
        brain_badge=da.brain_badge,
    )
    return t


def _is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def _decision_context(selected_iso: str = "") -> dict:
    """Resolve which DecisionPackage `/decisions` renders, with date browsing. Precedence:
      1. ALPHA_WEB_DECISION  — a single package file (back-compat override).
      2. ALPHA_WEB_DECISIONS_DIR — a DecisionStore; browse by `?date=` (defaults to the latest).
      3. the badged SAMPLE.
    A mis-shaped/stale artifact falls back to the SAMPLE with a human-readable error, never a 500 —
    the path is operator-supplied, not adversarial. Returns the decisions.html context fragment."""
    base = {"pkg": None, "is_sample": True, "load_error": "", "dates": [], "selected": None}

    f = os.environ.get("ALPHA_WEB_DECISION")
    if f and Path(f).exists():
        try:
            return {**base, "pkg": DecisionPackage.model_validate_json(Path(f).read_text("utf-8")),
                    "is_sample": False}
        except Exception as e:
            return {**base, "pkg": sample.sample_decision(), "load_error": f"{Path(f).name}: {type(e).__name__}."}

    d = os.environ.get("ALPHA_WEB_DECISIONS_DIR")
    if d:
        store = DecisionStore(d)
        dates = [x.isoformat() for x in store.dates()]
        if dates:
            sel = selected_iso if selected_iso in dates else dates[-1]
            try:
                return {**base, "pkg": store.get(Date.fromisoformat(sel)), "is_sample": False,
                        "dates": dates, "selected": sel}
            except Exception as e:
                return {**base, "pkg": sample.sample_decision(), "dates": dates, "selected": sel,
                        "load_error": f"{sel}: {type(e).__name__}."}

    return {**base, "pkg": sample.sample_decision()}


_VERDICT_KEYS = {"window", "arms", "headline", "stat_verdict"}


def _validated_verdict(data: dict) -> dict:
    missing = _VERDICT_KEYS - set(data)
    if missing:
        raise ValueError(f"missing keys {sorted(missing)}")
    return data


def _verdict_context(selected_label: str = "") -> dict:
    """Resolve which verdict `/verdict` renders, with run browsing. Precedence mirrors decisions:
      1. ALPHA_WEB_VERDICT       — a single view-dict file (back-compat override).
      2. ALPHA_WEB_VERDICTS_DIR  — a VerdictStore; browse by `?run=` (defaults to the latest label).
      3. the badged SAMPLE.
    Mis-shaped/stale JSON falls back to the SAMPLE with a human-readable error, never a 500."""
    base = {"report": None, "is_sample": True, "load_error": "", "runs": [], "selected": None}

    f = os.environ.get("ALPHA_WEB_VERDICT")
    if f and Path(f).exists():
        try:
            return {**base, "report": _validated_verdict(json.loads(Path(f).read_text("utf-8"))),
                    "is_sample": False}
        except Exception as e:
            return {**base, "report": sample.sample_verdict(), "load_error": f"{Path(f).name}: {type(e).__name__}."}

    d = os.environ.get("ALPHA_WEB_VERDICTS_DIR")
    if d:
        store = VerdictStore(d)
        runs = store.names()
        if runs:
            sel = selected_label if selected_label in runs else runs[-1]
            try:
                return {**base, "report": _validated_verdict(store.get(sel)), "is_sample": False,
                        "runs": runs, "selected": sel}
            except Exception as e:
                return {**base, "report": sample.sample_verdict(), "runs": runs, "selected": sel,
                        "load_error": f"{sel}: {type(e).__name__}."}

    return {**base, "report": sample.sample_verdict()}


def _evolution_context() -> dict:
    """Resolve the Evolution page artifact: a single run's edit trajectory via ALPHA_WEB_EVOLUTION
    (the JSON `scripts/save_evolution.py` writes), else the badged SAMPLE. Mis-shaped JSON falls back."""
    base = {"evo": None, "is_sample": True, "load_error": ""}
    f = os.environ.get("ALPHA_WEB_EVOLUTION")
    if f and Path(f).exists():
        try:
            data = json.loads(Path(f).read_text("utf-8"))
            if "edits" not in data:
                raise ValueError("missing 'edits'")
            return {**base, "evo": data, "is_sample": False}
        except Exception as e:
            return {**base, "evo": sample.sample_evolution(), "load_error": f"{Path(f).name}: {type(e).__name__}."}
    return {**base, "evo": sample.sample_evolution()}


def create_app() -> FastAPI:
    app = FastAPI(title="Evolving-Alpha-US · Regime Instrument")
    app.mount("/static", StaticFiles(directory=str(da.STATIC_DIR)), name="static")
    templates = _make_templates()

    def render(request: Request, name: str, ctx: dict):
        return templates.TemplateResponse(request, name, {"active": ctx.pop("active", None), **ctx})

    @app.get("/health")
    def health() -> JSONResponse:
        return JSONResponse({"ok": True})

    @app.get("/deck")
    def deck(request: Request):
        state = da.load_brain()
        return render(request, "dashboard.html", {
            "active": "deck", "stats": da.brain_stats(state),
            "regime": sample.sample_regime(), "market": sample.sample_market_state(),
        })

    @app.get("/doctrine")
    def doctrine(request: Request):
        immutable, mutable = da.split_doctrine(da.load_brain())
        return render(request, "doctrine.html",
                      {"active": "doctrine", "immutable": immutable, "mutable": mutable})

    @app.get("/memory")
    def memory(request: Request, family: str = "", outcome: str = "", phase: str = ""):
        lessons = da.filter_lessons(da.load_brain(), family=family or None,
                                    outcome=outcome or None, phase=phase or None)
        ctx = {"active": "memory", "lessons": lessons,
               "sel": {"family": family, "outcome": outcome, "phase": phase}}
        if _is_htmx(request):
            return render(request, "partials/memory_list.html", ctx)
        return render(request, "memory.html", ctx)

    @app.get("/skills")
    def skills(request: Request, family: str = "", status: str = "", type: str = "", phase: str = ""):
        items = da.filter_skills(da.load_brain(), family=family or None, status=status or None,
                                 type=type or None, phase=phase or None)
        ctx = {"active": "skills", "skills": items,
               "sel": {"family": family, "status": status, "type": type, "phase": phase}}
        if _is_htmx(request):
            return render(request, "partials/skill_list.html", ctx)
        return render(request, "skills.html", ctx)

    @app.get("/decisions")
    def decisions(request: Request, date: str = ""):
        return render(request, "decisions.html", {"active": "decisions", **_decision_context(date)})

    @app.get("/verdict")
    def verdict(request: Request, run: str = ""):
        return render(request, "verdict.html", {"active": "verdict", **_verdict_context(run)})

    @app.get("/evolution")
    def evolution(request: Request):
        return render(request, "evolution.html", {"active": "evolution", **_evolution_context()})

    @app.get("/conflicts")
    def conflicts(request: Request):
        try:
            rows = _sonia().list_conflicts()
            return render(request, "conflicts.html", {"active": "conflicts", "conflicts": rows, "sonia_down": False})
        except Exception:
            return render(request, "conflicts.html", {"active": "conflicts", "conflicts": [], "sonia_down": True})

    @app.post("/conflicts/{cid}/resolve")
    def resolve_conflict(request: Request, cid: str, decision: str = Form(...)):
        # Mirror delete_session: return EMPTY 200 (not 204 — htmx skips swap on 204) so the
        # conflict row outerHTML-swaps to nothing and vanishes from the page.
        try:
            _sonia().resolve_conflict(cid, decision)
        except Exception:
            return Response(
                status_code=200,
                content=f'<div id="conflict-{cid}" class="banner err">⚠ Sonia unavailable — could not resolve conflict.</div>',
                media_type="text/html",
            )
        return Response(status_code=200, content="")

    def _brain_stub(request: Request, key: str):
        title, blurb = _BRAIN_STUBS[key]
        return render(request, "brain_stub.html", {"active": key, "title": title, "blurb": blurb})

    @app.get("/workflow")
    def workflow(request: Request):
        return _brain_stub(request, "workflow")

    @app.get("/connector")
    def connector(request: Request):
        return _brain_stub(request, "connector")

    @app.get("/subagent")
    def subagent(request: Request):
        return _brain_stub(request, "subagent")

    import httpx

    def _cockpit_ctx(request, session: dict | None, banner: str = ""):
        return {"active": "teach",
                "session_id": (session or {}).get("session_id", ""),
                "messages": (session or {}).get("messages", []),
                "sessions": _safe_sessions(),
                "banner": banner}

    def _safe_sessions():
        try:
            return _sonia().list_sessions()
        except httpx.HTTPError:
            return []

    @app.get("/")
    def home(request: Request):
        try:
            sessions = _sonia().list_sessions()
            latest = next((s for s in sessions if s.get("status") == "open"), None)
            session = _sonia().get_session(latest["session_id"]) if latest else None
            return render(request, "cockpit.html", _cockpit_ctx(request, session))
        except httpx.HTTPError:
            return render(request, "cockpit.html", _cockpit_ctx(request, None,
                          banner="Sonia service unavailable — start it with `python -m sonia`"))

    @app.post("/evolve/message")
    def message(request: Request, session_id: str = Form(""), text: str = Form(""),
                files: list[UploadFile] = File(default=[])):
        uploads = [(f.filename, f.file.read()) for f in files if f.filename]
        clean, attachments = ingest_attachments(text, uploads)
        try:
            out = _sonia().chat(session_id or None, clean, attachments)
        except httpx.HTTPError:
            return render(request, "partials/message_assistant.html",
                          {"session_id": session_id, "m": {"message_id": "err", "role": "assistant",
                           "text": "Sonia service unavailable — start it with `python -m sonia`.",
                           "directions": [], "edits": []},
                           "banner": "unavailable"})
        return render(request, "partials/_two_turns.html",
                      {"session_id": out["session_id"], "user": out["user_message"],
                       "assistant": out["assistant_message"]})

    def _unavailable(request):
        return render(request, "partials/unavailable.html",
                      {"banner": "Sonia service unavailable — start it with `python -m sonia`"})

    @app.post("/evolve/{session_id}/edit/{edit_id}")
    def edit(request: Request, session_id: str, edit_id: str, action: str = Form(...)):
        try:
            e = _sonia().edit(session_id, edit_id, action)
            return render(request, "partials/edit_card.html", {"session_id": session_id, "e": e})
        except httpx.HTTPError:
            return _unavailable(request)

    @app.post("/evolve/{session_id}/message/{message_id}/apply")
    def apply(request: Request, session_id: str, message_id: str):
        try:
            r = _sonia().apply(session_id, message_id)
            return render(request, "partials/apply_result.html",
                          {"session_id": session_id, "message_id": message_id, "applied": r["applied"]})
        except httpx.HTTPError:
            return _unavailable(request)

    @app.post("/evolve/rollback/{session_id}/{message_id}")
    def rollback(request: Request, session_id: str, message_id: str):
        try:
            _sonia().rollback(session_id, message_id)
            return render(request, "partials/apply_result.html",
                          {"session_id": session_id, "message_id": message_id, "applied": 0})
        except httpx.HTTPError:
            return _unavailable(request)

    @app.get("/evolve/sessions")
    def sessions_index(request: Request):
        return render(request, "cockpit.html", _cockpit_ctx(request, None))

    @app.post("/evolve/{session_id}/delete")
    def delete_session(request: Request, session_id: str):
        # The delete button hx-swaps this into its own <li> (outerHTML); return EMPTY (200, not 204 —
        # HTMX skips the swap on 204) so the row vanishes. No full document → no nesting.
        try:
            _sonia().delete_session(session_id)
        except httpx.HTTPError:
            return _unavailable(request)
        return Response(status_code=200, content="")

    @app.get("/evolve/sessions/{session_id}")
    def session_detail(request: Request, session_id: str):
        try:
            session = _sonia().get_session(session_id)
        except httpx.HTTPError:
            session = None
        return render(request, "cockpit.html", _cockpit_ctx(request, session))

    @app.post("/evolve/new")
    def new_chat(request: Request):
        # The New-chat button is HTMX-posted into #thread; returning a full cockpit document would
        # nest the whole page inside itself. Instead, create the session and tell HTMX to navigate
        # to a fresh full-page render of it (consistent with GET /evolve/sessions/{id}).
        try:
            s = _sonia().new_session()
            sid = s.get("session_id", "") if isinstance(s, dict) else ""
        except httpx.HTTPError:
            sid = ""
        target = f"/evolve/sessions/{sid}" if sid else "/"
        return Response(status_code=204, headers={"HX-Redirect": target})

    return app


app = create_app()   # uvicorn alpha_web.app:app
