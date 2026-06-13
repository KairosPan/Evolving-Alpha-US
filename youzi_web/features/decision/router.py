# youzi_web/features/decision/router.py
from fastapi import APIRouter, Request

from youzi_web.features.decision.service import cockpit_context

router = APIRouter()


@router.get("/decision/cockpit")
def cockpit_page(request: Request, run: str | None = None, day: str | None = None):
    ctx = cockpit_context(run, day)
    return request.app.state.templates.TemplateResponse(
        request, "cockpit.html",
        {"request": request, "features": request.app.state.features,
         "active_feature_id": "decision", "active_path": "/decision/cockpit", **ctx})
