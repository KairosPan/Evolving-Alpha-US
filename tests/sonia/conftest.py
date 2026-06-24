import pytest

pytest.importorskip("fastapi", reason="install: pip install -e '.[sonia]'")


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPHA_LIVE_BRAIN_DIR", str(tmp_path / "brain"))
    monkeypatch.setenv("ALPHA_SESSIONS_DIR", str(tmp_path / "sessions"))
    monkeypatch.setenv("ALPHA_SONIA_PROVIDER", "mock")
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE", "let's discuss your thesis")
