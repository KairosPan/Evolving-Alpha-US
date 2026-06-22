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

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from alpha.eval.decision import DecisionPackage
from alpha.eval.decision_store import DecisionStore
from alpha_web import data_access as da
from alpha_web import sample

NAV = [
    {"path": "/", "key": "deck", "label": "Deck"},
    {"path": "/doctrine", "key": "doctrine", "label": "Doctrine"},
    {"path": "/memory", "key": "memory", "label": "Memory"},
    {"path": "/skills", "key": "skills", "label": "Skills"},
    {"path": "/decisions", "key": "decisions", "label": "Decisions"},
    {"path": "/verdict", "key": "verdict", "label": "Verdict"},
]

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


def _load_verdict() -> tuple[dict, bool, str]:
    p = os.environ.get("ALPHA_WEB_VERDICT")
    if p and Path(p).exists():
        try:
            data = json.loads(Path(p).read_text("utf-8"))
            missing = _VERDICT_KEYS - set(data)
            if missing:
                raise ValueError(f"missing keys {sorted(missing)}")
            return data, False, ""
        except Exception as e:
            return sample.sample_verdict(), True, f"{Path(p).name}: {type(e).__name__}."
    return sample.sample_verdict(), True, ""


def create_app() -> FastAPI:
    app = FastAPI(title="Evolving-Alpha-US · Regime Instrument")
    app.mount("/static", StaticFiles(directory=str(da.STATIC_DIR)), name="static")
    templates = _make_templates()

    def render(request: Request, name: str, ctx: dict):
        return templates.TemplateResponse(request, name, {"active": ctx.pop("active", None), **ctx})

    @app.get("/health")
    def health() -> JSONResponse:
        return JSONResponse({"ok": True})

    @app.get("/")
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
    def verdict(request: Request):
        report, is_sample, load_error = _load_verdict()
        return render(request, "verdict.html",
                      {"active": "verdict", "report": report, "is_sample": is_sample, "load_error": load_error})

    return app


app = create_app()   # uvicorn alpha_web.app:app
