from alpha.llm import stack
from alpha.llm.config import make_client
from alpha.llm.claude_code import ClaudeCodeClient
from alpha.llm.openai_compat import OpenAICompatClient


def _write(monkeypatch, tmp_path, stacks):
    p = str(tmp_path / "llm_stack.json")
    stack.write_stacks(stacks, p)
    monkeypatch.setenv("ALPHA_LLM_STACK_FILE", p)


def _clear_role_env(monkeypatch, role):
    monkeypatch.delenv(f"ALPHA_{role.upper()}_PROVIDER", raising=False)
    monkeypatch.delenv(f"ALPHA_{role.upper()}_MODEL", raising=False)


def test_file_layer_switches_entity_roles(monkeypatch, tmp_path):
    _write(monkeypatch, tmp_path, {"kairos": "deepseek"})
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test")
    for role in ("agent", "converse"):                     # kairos roles → deepseek stack
        _clear_role_env(monkeypatch, role)
        c = make_client(role)
        assert isinstance(c, OpenAICompatClient) and c.model == "deepseek-chat"
    _clear_role_env(monkeypatch, "sonia")                  # sonia entity absent → default (claude)
    assert isinstance(make_client("sonia"), ClaudeCodeClient)


def test_env_beats_file_per_field(monkeypatch, tmp_path):
    _write(monkeypatch, tmp_path, {"sonia": "deepseek"})
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test")
    _clear_role_env(monkeypatch, "sonia")
    monkeypatch.setenv("ALPHA_SONIA_MODEL", "deepseek-reasoner")   # model pinned by env…
    c = make_client("sonia")
    assert isinstance(c, OpenAICompatClient)               # …provider still from the file layer
    assert c.model == "deepseek-reasoner"                  # env field wins over the stack's model


def test_missing_file_means_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("ALPHA_LLM_STACK_FILE", str(tmp_path / "absent.json"))
    _clear_role_env(monkeypatch, "refiner")
    c = make_client("refiner")
    assert isinstance(c, ClaudeCodeClient) and c.model == "claude-fable-5"


def test_unknown_stack_name_means_defaults(monkeypatch, tmp_path):
    _write(monkeypatch, tmp_path, {"sonia": "bogus-stack"})
    _clear_role_env(monkeypatch, "sonia")
    assert isinstance(make_client("sonia"), ClaudeCodeClient)
