"""Sonia tests need the optional extra (fastapi). importorskip skips the whole package when it is absent
(reported as a skip, with the install hint) so the offline core suite stays green without it. CI installs
the extra so these run, not silently skip."""
import pytest

pytest.importorskip("fastapi", reason="install: pip install -e '.[sonia]'")


@pytest.fixture(autouse=True)
def _isolate_state(brain_session_isolation, monkeypatch):
    """Autouse: shared tmp brain/session isolation (parent conftest) + the Sonia mock provider."""
    monkeypatch.setenv("ALPHA_SONIA_PROVIDER", "mock")
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE", "let's discuss your thesis")
