from alpha.llm.chat import ChatMessage
from alpha.converse.project import Project, ProjectTurn, new_project, new_turn


def test_project_round_trips_with_turns_and_messages():
    p = new_project(title="TSLA squeeze")
    assert p.project_id and p.created_at and p.title == "TSLA squeeze" and p.h_pin is None
    p.messages.append(ChatMessage(role="user", text="hi"))
    t = new_turn("what's your read?"); t.final_text = "RUN looks strong"; t.h_version = 3
    t.tool_calls = [{"tool": "decide", "args": {"date": "2026-06-12"}, "result": {"candidates": []}}]
    p.turns.append(t)
    assert Project.model_validate_json(p.model_dump_json()) == p


def test_new_turn_has_id_and_timestamp():
    t = new_turn("x")
    assert t.turn_id and t.created_at and t.h_version is None and t.final_text == ""
