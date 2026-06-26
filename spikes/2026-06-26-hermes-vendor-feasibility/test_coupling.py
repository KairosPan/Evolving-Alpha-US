# spikes/2026-06-26-hermes-vendor-feasibility/test_coupling.py
from coupling import transitive_internal_imports

def test_registry_reachability_is_measurable():
    r = transitive_internal_imports("tools/registry.py")
    assert isinstance(r["reachable"], set) and r["file_count"] >= 1
    assert isinstance(r["drags_agent_pkg"], bool)
