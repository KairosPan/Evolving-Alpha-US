# spikes/2026-06-26-hermes-vendor-feasibility/test_coupling.py
from coupling import transitive_internal_imports, eager_internal_imports

def test_registry_reachability_is_measurable():
    r = transitive_internal_imports("tools/registry.py")
    assert isinstance(r["reachable"], set) and r["file_count"] >= 1
    assert isinstance(r["drags_agent_pkg"], bool)

def test_registry_eager_is_leaf():
    """tools/registry.py does dynamic tool loading via importlib at runtime,
    so its module-top-level (eager) import closure is just itself — file_count==1,
    no agent/ drag. This is the 'liftable (eager leaf)' signal for Strategy C."""
    e = eager_internal_imports("tools/registry.py")
    assert e["file_count"] == 1, f"expected 1, got {e['file_count']}"
    assert e["drags_agent_pkg"] is False
