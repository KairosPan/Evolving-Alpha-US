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
