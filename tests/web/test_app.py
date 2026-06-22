"""Route smoke + data-binding contract: every page returns 200 and renders the real brain content.
HTMX filter requests return just the list partial (no chrome)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from alpha_web.app import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["ok"] is True


@pytest.mark.parametrize("path", ["/", "/doctrine", "/memory", "/skills", "/decisions", "/verdict"])
def test_pages_render(client, path):
    r = client.get(path)
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "<!doctype html>" in r.text.lower()


def test_dashboard_shows_brain_counts_and_the_phase_cycle(client):
    body = client.get("/").text
    assert "16" in body and "12" in body          # skills / doctrine counts
    for phase in ("Washout", "Recovery", "Ignition", "Trend", "Distribution", "Flush"):
        assert phase in body                       # the six-phase cycle is on the deck


def test_doctrine_page_shows_a_real_redline(client):
    body = client.get("/doctrine").text
    assert "stop_discipline" in body or "The stop is the plan" in body
    assert "immutable" in body.lower()


def test_skills_filter_returns_partial_for_htmx(client):
    full = client.get("/skills")
    assert "<html" in full.text.lower()
    partial = client.get("/skills?family=meme", headers={"HX-Request": "true"})
    assert partial.status_code == 200
    assert "<html" not in partial.text.lower()      # fragment only
    assert "Short Squeeze" in partial.text          # a meme skill
    assert "Gap and Go" not in partial.text         # a runner skill is filtered out


def test_memory_filter_by_outcome_partial(client):
    partial = client.get("/memory?outcome=loss", headers={"HX-Request": "true"})
    assert partial.status_code == 200
    assert "<html" not in partial.text.lower()


def test_decisions_page_renders_sample_ticket(client):
    body = client.get("/decisions").text
    assert "sample" in body.lower()                  # honest badge
    # a size tier and the portfolio risk surface
    assert any(t in body.lower() for t in ("probe", "core", "heavy"))


def test_verdict_page_renders(client):
    body = client.get("/verdict").text
    assert "HCH" in body and "Hexpert" in body


# ── real-artifact path (ALPHA_WEB_DECISION / ALPHA_WEB_VERDICT) ────────────────
def test_decisions_handles_no_trade_package(client, tmp_path, monkeypatch):
    """A baseline / parse-failure package has regime=None, portfolio=None, no candidates — it must
    render, not 500 (the bug the review caught)."""
    from datetime import date
    from alpha.eval.decision import DecisionPackage
    pkg = DecisionPackage(date=date(2026, 1, 5), no_trade_reason="no gainers — washout tape")
    f = tmp_path / "decision.json"
    f.write_text(pkg.model_dump_json(), encoding="utf-8")
    monkeypatch.setenv("ALPHA_WEB_DECISION", str(f))
    r = client.get("/decisions")
    assert r.status_code == 200
    assert "no gainers — washout tape" in r.text
    assert "no-trade" in r.text.lower()
    assert "Sample package" not in r.text


def test_real_decision_artifact_renders_without_sample_badge(client, tmp_path, monkeypatch):
    from alpha_web import sample
    f = tmp_path / "decision.json"
    f.write_text(sample.sample_decision().model_dump_json(), encoding="utf-8")
    monkeypatch.setenv("ALPHA_WEB_DECISION", str(f))
    r = client.get("/decisions")
    assert r.status_code == 200 and "GPUX" in r.text and "Sample package" not in r.text


def test_malformed_decision_falls_back_gracefully(client, tmp_path, monkeypatch):
    f = tmp_path / "bad.json"
    f.write_text("{ not valid json", encoding="utf-8")
    monkeypatch.setenv("ALPHA_WEB_DECISION", str(f))
    r = client.get("/decisions")
    assert r.status_code == 200 and "wired artifact" in r.text


def test_malformed_verdict_falls_back_gracefully(client, tmp_path, monkeypatch):
    f = tmp_path / "bad.json"
    f.write_text("definitely not json", encoding="utf-8")
    monkeypatch.setenv("ALPHA_WEB_VERDICT", str(f))
    r = client.get("/verdict")
    assert r.status_code == 200 and "wired artifact" in r.text


def test_wrong_shape_verdict_falls_back_gracefully(client, tmp_path, monkeypatch):
    f = tmp_path / "v.json"
    f.write_text('{"arms": {}}', encoding="utf-8")     # valid JSON, missing required keys
    monkeypatch.setenv("ALPHA_WEB_VERDICT", str(f))
    r = client.get("/verdict")
    assert r.status_code == 200 and "wired artifact" in r.text
