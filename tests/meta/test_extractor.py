from alpha.harness.loader import load_seeds
from alpha.llm.chat import ChatMessage
from alpha.llm.client import MockLLMClient
from alpha.meta.extractor import ExtractionResult, extract_ops
from alpha.meta import prompts


def _convo():
    return [ChatMessage(role="user", text="make gap-fails taboo"),
            ChatMessage(role="assistant", text="noted — want me to record that?")]


def test_extract_ops_returns_ops_from_enforced_json():
    h = load_seeds("seeds")
    reply = '{"ops":[{"tool":"process_memory","args":{"lesson_id":"l1","lesson":"x","outcome":"principle"},"rationale":"the operator asked"}]}'
    res = extract_ops(MockLLMClient(reply), h, _convo())
    assert isinstance(res, ExtractionResult)
    assert res.no_edit is False and [o.tool for o in res.ops] == ["process_memory"]


def test_extract_ops_no_edit_is_explicit_not_silent():
    h = load_seeds("seeds")
    res = extract_ops(MockLLMClient('{"no_edit": true, "reason": "still clarifying the VWAP window"}'), h, _convo())
    assert res.ops == [] and res.no_edit is True and "VWAP" in res.reason


def test_extract_ops_uses_complete_with_brain_and_conversation():
    h = load_seeds("seeds")
    client = MockLLMClient('{"no_edit": true, "reason": "r"}')
    extract_ops(client, h, _convo())
    system, user = client.calls[0]                 # .complete records (system, user)
    assert "RED-LINE" in system                    # brain summary present
    assert "process_memory" in system              # the op vocabulary (_TOOLS_DOC) present
    assert "make gap-fails taboo" in user          # the conversation is in the user prompt


def test_render_conversation_serialises_roles_and_text():
    out = prompts.render_conversation([ChatMessage(role="user", text="hi"),
                                       ChatMessage(role="assistant", text="hello")])
    assert "hi" in out and "hello" in out and "user" in out.lower()


def test_extraction_system_forbids_nearest_neighbor_rewrite():
    # preset 2 (P0.3): a target-not-found edit must return no_edit, never rewrite the nearest entry
    system = prompts.render_extraction_system(load_seeds("seeds"))
    lowered = system.lower()
    assert "does not exist" in lowered or "not found" in lowered
    assert "never rewrite" in lowered and "nearest" in lowered
