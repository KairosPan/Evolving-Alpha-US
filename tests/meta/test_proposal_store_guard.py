"""Direct pins for the store-level traversal guards (the HTTP layer can't reach them: Starlette
percent-decodes before routing, so an encoded ../ 404s at the router — these guards are
defense-in-depth and need function-level tests to be non-vacuous)."""
import pytest

from alpha.meta.proposal_store import ProposalQueue


def test_proposal_path_rejects_traversal(tmp_path):
    q = ProposalQueue(tmp_path / "proposals")
    with pytest.raises(ValueError, match="invalid proposal_id"):
        q._path("../escape")
    with pytest.raises(ValueError, match="invalid proposal_id"):
        q._path("../../brain")


def test_proposal_get_missing_is_none(tmp_path):
    assert ProposalQueue(tmp_path / "proposals").get("nope") is None
