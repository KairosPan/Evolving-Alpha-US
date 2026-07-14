import json
import os

from alpha.llm import stack


def test_stacks_and_entity_map_shape():
    assert stack.STACKS["claude"] == ("claude_sdk", "claude-fable-5")
    assert stack.STACKS["deepseek"] == ("openai_compat", "deepseek-chat")
    assert stack.ROLE_ENTITY == {"sonia": "sonia", "refiner": "sonia",
                                 "agent": "kairos", "converse": "kairos"}


def test_stack_file_path_env_override(monkeypatch, tmp_path):
    p = str(tmp_path / "s.json")
    monkeypatch.setenv("ALPHA_LLM_STACK_FILE", p)
    assert stack.stack_file_path() == p


def test_read_missing_file_returns_empty(tmp_path):
    assert stack.read_stacks(str(tmp_path / "absent.json")) == {}


def test_read_corrupt_file_returns_empty(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    assert stack.read_stacks(str(p)) == {}


def test_read_non_dict_returns_empty(tmp_path):
    p = tmp_path / "list.json"
    p.write_text("[1, 2]", encoding="utf-8")
    assert stack.read_stacks(str(p)) == {}


def test_read_drops_non_string_values(tmp_path):
    p = tmp_path / "mixed.json"
    p.write_text(json.dumps({"sonia": "claude", "kairos": 7}), encoding="utf-8")
    assert stack.read_stacks(str(p)) == {"sonia": "claude"}


def test_write_then_read_round_trip(tmp_path):
    p = str(tmp_path / "state" / "llm_stack.json")   # parent dir does not exist yet
    stack.write_stacks({"sonia": "claude", "kairos": "deepseek"}, p)
    assert stack.read_stacks(p) == {"sonia": "claude", "kairos": "deepseek"}
    assert not [f for f in os.listdir(os.path.dirname(p)) if f.endswith(".tmp")]  # no tmp litter


def test_resolve_stack_maps_role_via_entity(monkeypatch, tmp_path):
    p = str(tmp_path / "s.json")
    stack.write_stacks({"sonia": "deepseek"}, p)
    monkeypatch.setenv("ALPHA_LLM_STACK_FILE", p)
    assert stack.resolve_stack("refiner") == ("openai_compat", "deepseek-chat")  # refiner → sonia entity
    assert stack.resolve_stack("agent") is None                                  # kairos absent → fall through


def test_resolve_stack_unknown_name_falls_through(monkeypatch, tmp_path):
    p = str(tmp_path / "s.json")
    stack.write_stacks({"kairos": "gpt9"}, p)
    monkeypatch.setenv("ALPHA_LLM_STACK_FILE", p)
    assert stack.resolve_stack("converse") is None


def test_resolve_stack_unknown_role_is_none(monkeypatch, tmp_path):
    monkeypatch.setenv("ALPHA_LLM_STACK_FILE", str(tmp_path / "s.json"))
    assert stack.resolve_stack("nonsense") is None
