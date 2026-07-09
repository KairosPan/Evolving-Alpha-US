"""Workbench tests need the optional extra (fastapi) and FULL store isolation: the 2026-07-09
cross-face reconcile means workbench /rollback also opens the SONIA sessions store — without the
shared isolation fixture a rollback test would sweep the operator's real ./state/sessions."""
import pytest

pytest.importorskip("fastapi", reason="install: pip install -e '.[web,sonia]'")


@pytest.fixture(autouse=True)
def _isolate_state(brain_session_isolation):
    """Autouse: shared tmp isolation for brain/sessions/projects/conflicts/proposals."""
