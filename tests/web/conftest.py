"""Web tests need the optional `web` extra (fastapi/jinja2). importorskip skips the whole package when
it is absent (reported as a skip, with the install hint) so the offline core suite stays green without it
— same posture as the `live`/`sonia` extras. CI installs the extra so these run, not silently skip."""
import pytest

pytest.importorskip("fastapi", reason="install the web extra: pip install -e '.[web]'")
pytest.importorskip("jinja2", reason="install the web extra: pip install -e '.[web]'")


@pytest.fixture(autouse=True)
def _isolate_state(brain_session_isolation):
    """Autouse: every web test gets tmp brain/session dirs (the shared fixture in the parent conftest)."""
