import alpha.converse.agent as agent_mod
from alpha.harness.loader import load_seeds


def test_apply_mode_threads_conflict_queue_and_provenance(monkeypatch):
    captured = {}
    def fake_make_gated(harness, **kw):
        captured.update(kw)
        return {"name": "propose_memory_edit"}, (lambda **a: {"status": "applied"})
    monkeypatch.setattr(agent_mod, "make_gated_write_tool", fake_make_gated)
    h = load_seeds("seeds")
    q, p = object(), object()
    agent_mod.build_converse_registry(h, None, None, write_mode="apply", conflict_queue=q, provenance=p)
    assert captured.get("conflict_queue") is q
    assert captured.get("provenance") is p


def test_apply_mode_defaults_are_none(monkeypatch):
    captured = {}
    def fake_make_gated(harness, **kw):
        captured.update(kw)
        return {"name": "propose_memory_edit"}, (lambda **a: {})
    monkeypatch.setattr(agent_mod, "make_gated_write_tool", fake_make_gated)
    agent_mod.build_converse_registry(load_seeds("seeds"), None, None, write_mode="apply")
    assert captured.get("conflict_queue") is None and captured.get("provenance") is None
