"""A8 part (a): the canonical teach surface is the ONE write-scope authority.
A7 (2026-07-13): the worker (kairos) leg is RETIRED — Sonia is the sole teach face (charter First
Founding Principle: "Kairos does not propose at all")."""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import alpha
import alpha.converse.tools as converse_tools
import alpha.meta.agent as meta_agent
from alpha.meta.teach_surface import TEACH_FACES, teach_provenance, teach_scope
from alpha.refine.apply import ALL_TOOLS

# Read workbench/app.py as TEXT (not import): it needs the `workbench`/fastapi extra, and tests/meta
# stays offline-safe without it. The worker's OLD landing lived here (approve_edit) — now retired.
_REPO_ROOT = Path(alpha.__file__).resolve().parent.parent
_WORKBENCH_APP_SRC = (_REPO_ROOT / "workbench" / "app.py").read_text()


def test_sonia_is_the_sole_teach_face():
    # Sonia the teacher = full scope. The kairos (worker) leg was retired by A7.
    assert teach_scope("sonia") == ALL_TOOLS
    assert set(TEACH_FACES) == {"sonia"}


def test_worker_face_is_retired():
    # A7: the worker is no longer a teach face — deriving its scope/provenance raises.
    with pytest.raises(ValueError):
        teach_scope("kairos")
    with pytest.raises(ValueError):
        teach_provenance("kairos")


def test_unknown_face_rejected():
    with pytest.raises(ValueError):
        teach_scope("stranger")
    with pytest.raises(ValueError):
        teach_provenance("stranger")


def test_provenance_is_the_canonical_teaching_stamp():
    p = teach_provenance("sonia")
    assert p.path == "teaching" and p.proposer == "sonia" and p.human_approver is None
    p2 = teach_provenance("sonia", human_approver="user")
    assert p2.path == "teaching" and p2.proposer == "sonia" and p2.human_approver == "user"


def test_sonia_routes_through_the_authority_no_hardcoded_scope():
    # The consolidation: Sonia does not hard-code `allowed=ALL_TOOLS` — it calls teach_scope().
    # And the worker propose path is gone: converse/tools.py no longer references a teach scope.
    agent_src = inspect.getsource(meta_agent)
    tools_src = inspect.getsource(converse_tools)
    assert "allowed=ALL_TOOLS" not in agent_src
    assert 'teach_scope("sonia")' in agent_src
    assert "teach_scope(" not in tools_src            # A7: the worker no longer derives a teach scope
    assert not hasattr(converse_tools, "make_propose_edit_tool")  # ...its propose tool is retired


def test_worker_real_landing_is_retired():
    # A7: the worker's teaching landing (workbench/app.py::approve_edit) is retired — it no longer
    # references the removed kairos scope/provenance; a kairos edit can never land.
    src = _WORKBENCH_APP_SRC
    assert 'teach_scope("kairos")' not in src
    assert 'teach_provenance("kairos"' not in src
    assert "worker proposals retired" in src          # the endpoint now refuses (charter A7)
