# youzi_web/features/research/router.py
from fastapi import APIRouter, Request

from youzi_web.features.research.service import get_seed_harness_view, run_context

router = APIRouter()


@router.get("/research/harness")
def harness_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        request,
        "harness.html",
        {"request": request, "features": request.app.state.features,
         "active_feature_id": "research", "active_path": "/research/harness",
         "h": get_seed_harness_view()})


def _render(request, template, active_path, run):
    ctx = run_context(run)
    return request.app.state.templates.TemplateResponse(
        request, template,
        {"request": request, "features": request.app.state.features,
         "active_feature_id": "research", "active_path": active_path, **ctx})


@router.get("/research/compare")
def compare_page(request: Request, run: str | None = None):
    return _render(request, "compare.html", "/research/compare", run)


@router.get("/research/refine")
def refine_page(request: Request, run: str | None = None):
    return _render(request, "refine.html", "/research/refine", run)


@router.get("/research/trajectory")
def trajectory_page(request: Request, run: str | None = None):
    return _render(request, "trajectory.html", "/research/trajectory", run)
