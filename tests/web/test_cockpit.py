import pytest
from fastapi.testclient import TestClient
from alpha_web.app import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


def test_cockpit_is_home_and_shows_input_panel(client):
    body = client.get("/").text
    assert "Teach" in body and ("paste" in body.lower() or "url" in body.lower())


def test_seed_baseline_badge_shows_when_store_empty(client):
    body = client.get("/deck").text
    assert "seed baseline" in body.lower()


def test_ingest_text_returns_direction_cards(client, monkeypatch):
    monkeypatch.setenv("ALPHA_REFINER_PROVIDER", "mock")
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE", '{"directions": [{"title": "lean into squeezes"}]}')
    r = client.post("/evolve/ingest", data={"text": "High short interest writeup"})
    assert r.status_code == 200 and "lean into squeezes" in r.text
    assert "<html" not in r.text.lower()        # partial only


def test_ingest_missing_key_shows_graceful_panel(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("ALPHA_REFINER_PROVIDER", "anthropic")
    r = client.post("/evolve/ingest", data={"text": "x"})
    assert r.status_code == 200 and ("set your key" in r.text.lower() or "mock mode" in r.text.lower())
