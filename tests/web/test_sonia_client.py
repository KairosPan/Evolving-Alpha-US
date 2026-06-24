# tests/web/test_sonia_client.py
import httpx
import pytest

pytest.importorskip("fastapi", reason="install: pip install -e '.[web,sonia]'")

from fastapi.testclient import TestClient

from sonia.app import create_app as create_sonia
from alpha_web.sonia_client import SoniaClient


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPHA_LIVE_BRAIN_DIR", str(tmp_path / "brain"))
    monkeypatch.setenv("ALPHA_SESSIONS_DIR", str(tmp_path / "sessions"))
    monkeypatch.setenv("ALPHA_SONIA_PROVIDER", "mock")
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE", "discussing it")


@pytest.fixture()
def sonia():
    return SoniaClient(client=TestClient(create_sonia()))


def test_healthz_roundtrips_in_process(sonia):
    assert sonia.healthz()["ok"] is True


def test_chat_returns_two_turns(sonia):
    out = sonia.chat(session_id=None, text="teach me", attachments=[])
    assert out["user_message"]["text"] == "teach me"
    assert out["assistant_message"]["role"] == "assistant"
    assert sonia.list_sessions()[0]["session_id"] == out["session_id"]


def test_unreachable_sonia_raises_httpx_error():
    client = SoniaClient(base_url="http://127.0.0.1:9", timeout=0.2)   # nothing listening
    with pytest.raises(httpx.HTTPError):
        client.healthz()
