# spikes/2026-06-26-hermes-vendor-feasibility/test_gated_write_tool.py
from alpha.harness.skill import Skill
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from gated_write_tool import make_gated_write_tool

def _h():
    return HarnessState(doctrine=Doctrine(),
                        skills=SkillRegistry.from_skills([]),
                        memory=MemoryStore.from_lessons([]))

def test_gated_write_applies_a_valid_memory_op():
    h = _h()
    _schema, propose = make_gated_write_tool(h)
    out = propose(tool="process_memory",
                  args={"lesson_id": "spike-mem-1", "phases": ["trend"],
                        "outcome": "win", "lesson": "spike: gate routing works"},
                  rationale="prove the gated write path")
    assert out["status"] == "applied"
    assert any(l.lesson_id == "spike-mem-1" for l in h.memory.all())   # H actually mutated, via the gate

def test_gated_write_rejects_a_non_whitelisted_op():
    h = _h()
    _schema, propose = make_gated_write_tool(h)
    out = propose(tool="rewrite_doctrine",
                  args={"section": "x", "new_guidance": "y"},
                  rationale="should be blocked — not in the M whitelist")
    assert out["status"] == "rejected"
    assert out["reason"]                                  # a non-empty gate reason
    assert h.memory.all() == [] or all(l.lesson_id != "x" for l in h.memory.all())
