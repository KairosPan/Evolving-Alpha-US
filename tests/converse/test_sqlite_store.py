from alpha.converse.sqlite_store import SqliteProjectStore
from alpha.converse.project import Project, ProjectTurn, StagedEdit
from alpha.llm.chat import ChatMessage


def _rich_project() -> Project:
    return Project(
        project_id="p1", created_at="2026-06-27T00:00:00", title="demo", h_pin=7,
        messages=[ChatMessage(role="user", text="hello there"),
                  ChatMessage(role="assistant", text="general kenobi")],
        turns=[ProjectTurn(turn_id="t1", user_text="hello there", final_text="hi",
                           tool_calls=[{"tool": "decide", "args": {}, "result": {"ok": 1}}],
                           h_version=7, created_at="2026-06-27T00:00:01")],
        staged_edits=[StagedEdit(edit_id="e1", op={"tool": "process_memory", "args": {"x": 1}},
                                 summary="s", valid=True, preview={"k": "v"})])


def test_put_get_round_trips_all_seven_fields():
    s = SqliteProjectStore.in_memory()
    p = _rich_project()
    s.put(p)
    got = s.get("p1")
    assert got is not None
    assert got.model_dump() == p.model_dump()     # all seven fields identical


def test_get_missing_returns_none():
    s = SqliteProjectStore.in_memory()
    assert s.get("nope") is None


def test_put_is_idempotent_upsert():
    s = SqliteProjectStore.in_memory()
    p = _rich_project()
    s.put(p)
    p.title = "renamed"
    p.messages.append(ChatMessage(role="user", text="another message"))
    s.put(p)                                       # second put overwrites, no duplicate rows
    got = s.get("p1")
    assert got.title == "renamed"
    assert len(got.messages) == 3
