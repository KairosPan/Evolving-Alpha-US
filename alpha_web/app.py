"""Regime Instrument — FastAPI + HTMX console. Read-only window onto the co-pilot's evolving mind
and its outputs. Run: `python -m alpha_web` (or `uvicorn alpha_web.app:app`). Needs the web extra.

Real artifacts override the SAMPLE on the Decisions/Verdict pages:
  ALPHA_WEB_DECISION=/path/to/decision.json   (a DecisionPackage.model_dump_json)
  ALPHA_WEB_VERDICT=/path/to/verdict.json      (a dict shaped like alpha_web.sample.sample_verdict)
"""
from __future__ import annotations

import json
import os
import threading
from datetime import date as Date
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from alpha.eval.decision import DecisionPackage
from alpha.eval.decision_store import DecisionStore
from alpha.eval.verdict_store import VerdictStore
from alpha.harness.metatools import MetaTools
from alpha.llm.config import make_client
from alpha.meta import ingest as meta_ingest
from alpha.meta.agent import MetaAgent
from alpha.meta.models import Session, new_session_id
from alpha.meta.store import LiveBrainStore, SessionStore
from alpha_web import data_access as da
from alpha_web import sample

NAV = [
    {"path": "/", "key": "teach", "label": "Teach"},
    {"path": "/deck", "key": "deck", "label": "Deck"},
    {"path": "/doctrine", "key": "doctrine", "label": "Doctrine"},
    {"path": "/memory", "key": "memory", "label": "Memory"},
    {"path": "/skills", "key": "skills", "label": "Skills"},
    {"path": "/decisions", "key": "decisions", "label": "Decisions"},
    {"path": "/verdict", "key": "verdict", "label": "Verdict"},
    {"path": "/evolution", "key": "evolution", "label": "Autonomous"},
]

_MUTATION_LOCK = threading.Lock()


def _meta_agent():
    """Fresh per request: load the live brain, bind MetaTools, attach the refiner LLM."""
    h, log = _brain_store().load()
    return MetaAgent(MetaTools(h, log), make_client("refiner")), (h, log)


def _llm_unavailable(exc: Exception) -> bool:
    return "missing" in str(exc).lower() and "API_KEY" in str(exc)


def _brain_store() -> LiveBrainStore:
    return LiveBrainStore(os.environ.get("ALPHA_LIVE_BRAIN_DIR", "./state/brain"))


def _session_store() -> SessionStore:
    return SessionStore(os.environ.get("ALPHA_SESSIONS_DIR", "./state/sessions"))

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

    @app.get("/")
    def cockpit(request: Request):
        return render(request, "cockpit.html", {"active": "teach", "sessions": _session_store().list()[:20]})

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

    @app.post("/evolve/{session_id}/direction")
    def choose_direction(request: Request, session_id: str, direction_id: str = Form(...), comment: str = Form("")):
        store = _session_store()
        sess = store.get(session_id)
        if sess is None:
            return render(request, "partials/edit_queue.html", {"error": "session not found", "session": None, "edits": []})
        sess.chosen_direction_id = direction_id
        sess.direction_comment = comment
        direction = next((d for d in sess.directions if d.direction_id == direction_id), None)
        agent, _ = _meta_agent()
        sess.edits = agent.expand_to_edits(sess.sources[0], direction, comment=comment or None)
        store.put(sess)
        return render(request, "partials/edit_queue.html", {"error": "", "session": sess, "edits": sess.edits})

    @app.post("/evolve/ingest")
    def ingest(request: Request, text: str = Form(""), url: str = Form("")):
        if url.strip():
            try:
                source = meta_ingest.fetch_url(url.strip())
            except meta_ingest.IngestError as e:
                return render(request, "partials/directions.html",
                              {"error": f"{e} — paste the text instead.", "directions": [], "session": None})
        else:
            source = meta_ingest.from_text(text, title="pasted text")
        try:
            agent, _ = _meta_agent()
        except RuntimeError as e:
            if _llm_unavailable(e):
                return render(request, "partials/directions.html",
                              {"error": "No API key — set your key or use mock mode.", "directions": [], "session": None})
            raise
        dirs = agent.propose_directions(source)
        sess = Session(session_id=new_session_id(),
                       created_at=datetime.now(timezone.utc).isoformat(),
                       sources=[source], directions=dirs)
        _session_store().put(sess)
        return render(request, "partials/directions.html",
                      {"error": "", "directions": dirs, "session": sess})

    return app


app = create_app()   # uvicorn alpha_web.app:app
