import pytest
from fastapi.testclient import TestClient
from sonia.app import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())

# NOTE: test_accept_then_apply_mutates_brain_and_snapshots,
# test_rollback_restores_pre_apply_brain, and test_apply_with_no_accepted_edits_is_a_noop
# were removed in Task 3 (chat is now prose-only and no longer seeds edit cards).
# They will be replaced in Task 4 when the /propose endpoint exists and can seed edits.
