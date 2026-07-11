"""D1 leak regression: secrets never reach the converse DB — BOTH channels
(turns JSON tool_calls AND the duplicated [tool:...] message text + FTS)."""
from alpha.converse.project import Project, ProjectTurn, StagedEdit
from alpha.converse.sqlite_store import SqliteProjectStore
from alpha.llm.chat import ChatMessage

SECRET = "sk-planted-secret-value-123"


def _project():
    return Project(
        project_id="p1", created_at="2026-07-10T00:00:00Z", title="t",
        messages=[ChatMessage(role="user", text=f"[tool:shell result]\nDEEPSEEK_API_KEY={SECRET}")],
        turns=[ProjectTurn(turn_id="t1", user_text="run env",
                           tool_calls=[{"tool": "shell", "args": {"cmd": "env"},
                                        "result": {"ok": True, "stdout": f"DEEPSEEK_API_KEY={SECRET}",
                                                   "stderr": "", "exit_code": 0}}],
                           created_at="2026-07-10T00:00:00Z")],
        staged_edits=[StagedEdit(edit_id="e1", op={"tool": "process_memory",
                                                   "args": {"lesson": SECRET}, "rationale": "r"},
                                 summary="s", valid=True, reason=None, preview={})],
    )


def test_secret_never_reaches_db_but_replay_payload_survives(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", SECRET)
    db = tmp_path / "state.db"
    store = SqliteProjectStore.open(db)
    store.put(_project())
    raw = db.read_bytes().decode("utf-8", errors="ignore")
    # both persisted channels are clean, marker present (non-vacuous)
    assert "[REDACTED:DEEPSEEK_API_KEY]" in raw
    # the ONLY allowed occurrences of the secret are the never-scrub replay payload
    got = store.get("p1")
    assert SECRET not in got.messages[0].text
    assert SECRET not in str(got.turns[0].tool_calls)
    assert got.staged_edits[0].op["args"]["lesson"] == SECRET   # replay payload verbatim


def test_search_index_is_clean(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", SECRET)
    store = SqliteProjectStore.open(tmp_path / "state.db")
    store.put(_project())
    assert store.search(SECRET) == []           # FTS never indexed the raw secret
