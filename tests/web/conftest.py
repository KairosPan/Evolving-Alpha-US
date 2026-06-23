"""Web tests need the optional `web` extra (fastapi/jinja2). Skip the whole package when it
is absent so the offline core suite stays green without it — same posture as the `live` extra."""
import pytest

pytest.importorskip("fastapi", reason="install the web extra: pip install -e '.[web]'")
pytest.importorskip("jinja2", reason="install the web extra: pip install -e '.[web]'")


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPHA_LIVE_BRAIN_DIR", str(tmp_path / "brain"))
    monkeypatch.setenv("ALPHA_SESSIONS_DIR", str(tmp_path / "sessions"))
