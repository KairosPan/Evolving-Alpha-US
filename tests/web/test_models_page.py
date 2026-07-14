import pytest

pytest.importorskip("fastapi", reason="install the web extra: pip install -e '.[web]'")
pytest.importorskip("jinja2", reason="install the web extra: pip install -e '.[web]'")

from fastapi.testclient import TestClient

from alpha.llm import stack
from alpha_web.app import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


def test_models_page_renders_both_entities(client):
    r = client.get("/models")
    assert r.status_code == 200
    assert "Sonia" in r.text and "Kairos" in r.text
    assert "claude" in r.text and "deepseek" in r.text


def test_post_switch_persists_and_redirects(client):
    r = client.post("/settings/llm", data={"entity": "kairos", "stack": "deepseek"},
                    follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/models"
    assert stack.read_stacks().get("kairos") == "deepseek"      # isolated file via conftest
    page = client.get("/models")
    assert 'value="deepseek" selected' in page.text or "selected>deepseek" in page.text.replace('"', "")


def test_post_switch_merges_not_clobbers(client):
    client.post("/settings/llm", data={"entity": "sonia", "stack": "deepseek"})
    client.post("/settings/llm", data={"entity": "kairos", "stack": "claude"})
    assert stack.read_stacks() == {"sonia": "deepseek", "kairos": "claude"}


def test_post_unknown_entity_or_stack_is_422(client):
    assert client.post("/settings/llm", data={"entity": "zeus", "stack": "claude"}).status_code == 422
    assert client.post("/settings/llm", data={"entity": "sonia", "stack": "gpt9"}).status_code == 422
    assert stack.read_stacks().get("sonia") != "gpt9"


def test_env_pinned_badge_shows(client, monkeypatch):
    monkeypatch.setenv("ALPHA_AGENT_PROVIDER", "openai_compat")
    r = client.get("/models")
    assert "env-pinned" in r.text
