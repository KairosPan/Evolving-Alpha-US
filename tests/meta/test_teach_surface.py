"""A8 part (a): the canonical teach surface is the ONE write-scope authority both faces consume."""
from __future__ import annotations

import inspect
from pathlib import Path

import alpha
import alpha.converse.tools as converse_tools
import alpha.meta.agent as meta_agent
from alpha.meta.teach_surface import TEACH_FACES, teach_provenance, teach_scope
from alpha.refine.apply import ALL_TOOLS
from alpha.refine.ops import PASS_TOOLS

# Read workbench/app.py as TEXT (not import): it needs the `workbench`/fastapi extra, and tests/meta
# stays offline-safe without it. The worker's REAL landing lives here (approve_edit saves to H).
_REPO_ROOT = Path(alpha.__file__).resolve().parent.parent
_WORKBENCH_APP_SRC = (_REPO_ROOT / "workbench" / "app.py").read_text()


def test_scopes_are_the_values_in_force_today():
    # Sonia the teacher = full scope; the Kairos worker = memory-only (least-privilege).
    assert teach_scope("sonia") == ALL_TOOLS
    assert teach_scope("kairos") == PASS_TOOLS["M"]
    assert set(TEACH_FACES) == {"sonia", "kairos"}


def test_unknown_face_rejected():
    import pytest
    with pytest.raises(ValueError):
        teach_scope("stranger")
    with pytest.raises(ValueError):
        teach_provenance("stranger")


def test_provenance_is_the_canonical_teaching_stamp():
    p = teach_provenance("sonia")
    assert p.path == "teaching" and p.proposer == "sonia" and p.human_approver is None
    p2 = teach_provenance("kairos", human_approver="user")
    assert p2.path == "teaching" and p2.proposer == "kairos" and p2.human_approver == "user"


def test_both_faces_route_through_the_authority_no_hardcoded_scope():
    # The consolidation: neither teach face hard-codes `allowed=ALL_TOOLS` / `allowed=PASS_TOOLS[...]`
    # at its call site — both call teach_scope(). (Grep-pin so a regression re-scatters the scope.)
    agent_src = inspect.getsource(meta_agent)
    tools_src = inspect.getsource(converse_tools)
    assert "allowed=ALL_TOOLS" not in agent_src
    assert 'allowed=PASS_TOOLS["M"]' not in tools_src
    assert 'teach_scope("sonia")' in agent_src
    assert 'teach_scope("kairos")' in tools_src


def test_worker_real_landing_routes_through_the_authority():
    # The worker's REAL teaching landing (workbench/app.py::approve_edit — it saves to the LIVE brain),
    # not just its preview, must route through the authority. A8 finding: this write site was missed
    # and hard-coded allowed=PASS_TOOLS["M"] + EditProvenance(path="teaching", ...). Grep-pin so a
    # future A7 narrowing of teach_scope("kairos") can't silently be bypassed at the write site.
    src = _WORKBENCH_APP_SRC
    assert "teach_surface import" in src and 'teach_scope("kairos")' in src
    assert 'teach_provenance("kairos", human_approver="user")' in src
    assert 'allowed=PASS_TOOLS["M"]' not in src           # no hard-coded scope at the write site
    assert 'EditProvenance(path="teaching"' not in src    # no hard-coded provenance at the write site
