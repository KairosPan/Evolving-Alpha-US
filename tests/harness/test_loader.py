import json
import pytest
from alpha.harness.loader import load_seeds


def _write_seeds(d):
    (d / "skills.json").write_text(json.dumps([
        {"skill_id": "gap_and_go", "name": "Gap and Go", "type": "pattern",
         "family": "runner", "phases": ["ignition", "trend"], "trigger": "t", "entry": "e",
         "exit_stop": "x", "status": "active"},
    ]), encoding="utf-8")
    (d / "memory.json").write_text(json.dumps([
        {"lesson_id": "l1", "phases": ["flush"], "family": "meme", "outcome": "loss",
         "lesson": "don't chase the squeeze top"},
    ]), encoding="utf-8")
    (d / "doctrine.json").write_text(json.dumps([
        {"section": "core", "regime": "all", "immutable": True, "guidance": "stop discipline"},
    ]), encoding="utf-8")


def test_load_seeds_assembles_state(tmp_path):
    _write_seeds(tmp_path)
    st = load_seeds(tmp_path)
    assert len(st.skills) == 1 and len(st.memory) == 1
    assert st.skills.get("gap_and_go").family == "runner"
    assert st.skills.get("gap_and_go").phases == ["ignition", "trend"]
    assert st.doctrine.get("core").immutable is True
    assert [s.skill_id for s in st.active_skills_for("trend")] == ["gap_and_go"]


def test_load_seeds_missing_dir_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_seeds(tmp_path / "nope")


def test_load_seeds_missing_file_raises(tmp_path):
    # skills.json present but empty; memory.json and doctrine.json absent
    # -> loader reads memory.json second and raises FileNotFoundError
    (tmp_path / "skills.json").write_text("[]", encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        load_seeds(tmp_path)


def test_load_seeds_non_list_top_level_raises(tmp_path):
    _write_seeds(tmp_path)
    (tmp_path / "skills.json").write_text('{"not": "a list"}', encoding="utf-8")
    with pytest.raises(ValueError):
        load_seeds(tmp_path)
