"""US-1a acceptance: a harness H=(p,K,M) loads from seeds, queries by phase/family, and
the immutable-core guard survives a to_dict/from_dict round-trip."""
import json
import pytest
from alpha.harness.loader import load_seeds
from alpha.harness.state import HarnessState
from alpha.harness.errors import ImmutableDoctrineError


def _seed_dir(d):
    (d / "skills.json").write_text(json.dumps([
        {"skill_id": "gap_and_go", "name": "Gap and Go", "type": "pattern", "family": "runner",
         "phases": ["trend"], "trigger": "t", "entry": "e", "exit_stop": "x", "status": "active"},
        {"skill_id": "squeeze", "name": "Squeeze", "type": "pattern", "family": "meme",
         "phases": ["ignition"], "status": "incubating"},
    ]), encoding="utf-8")
    (d / "memory.json").write_text(json.dumps([
        {"lesson_id": "l1", "phases": ["flush"], "family": "meme", "outcome": "loss", "lesson": "z"},
    ]), encoding="utf-8")
    (d / "doctrine.json").write_text(json.dumps([
        {"section": "core", "regime": "all", "immutable": True, "guidance": "stop discipline"},
    ]), encoding="utf-8")
    return d


def test_end_to_end_harness_core(tmp_path):
    st = load_seeds(_seed_dir(tmp_path))
    # query by phase and family
    assert [s.skill_id for s in st.active_skills_for("trend")] == ["gap_and_go"]
    assert [s.skill_id for s in st.skills.by_family("meme")] == ["squeeze"]
    assert [l.lesson_id for l in st.memory.by_family("meme")] == ["l1"]
    # immutable core survives round-trip
    st2 = HarnessState.from_dict(st.to_dict())
    with pytest.raises(ImmutableDoctrineError):
        st2.doctrine.get("core").guidance = "tampered"
