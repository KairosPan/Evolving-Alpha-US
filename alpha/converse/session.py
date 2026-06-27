# alpha/converse/session.py
"""Persisted, H-version-stamped conversational turn with optional workspace commit."""
from __future__ import annotations

from alpha.eval.decision import DecisionPackage
from alpha.harness.state import HarnessState
from alpha.llm.chat import ChatMessage

from alpha.converse.agent import build_converse_registry, build_system_prompt
from alpha.converse.loop import run_conversation
from alpha.converse.project import Project, StagedEdit, new_project, new_turn
from alpha.converse.sqlite_store import SqliteProjectStore
from alpha.converse.workspace import Workspace


def converse_project(
    project_id: str,
    user_text: str,
    *,
    harness: HarnessState,
    store: SqliteProjectStore,
    snapshots=None,
    agent_llm,
    chat_llm,
    source,
    workspace: Workspace | None = None,
    max_iters: int = 8,
    write_mode: str = "apply",
) -> Project:
    """Load-or-create *project_id*, run one conversation turn, persist and return the project."""
    # 1. Load or create the project.
    project: Project = store.get(project_id)
    if project is None:
        project = new_project()
        project.project_id = project_id

    # 2. Resolve H-version and read_only flag.
    if project.h_pin is not None and snapshots is not None:
        h, _ = snapshots.load(project.h_pin)
        read_only = True
    else:
        h = harness
        read_only = project.h_pin is not None

    h_version: int | None = (
        project.h_pin
        if project.h_pin is not None
        else (snapshots.latest() if snapshots is not None else None)
    )

    # 3. Build registry + system prompt.
    registry = build_converse_registry(h, agent_llm, source, read_only=read_only, write_mode=write_mode)
    system = build_system_prompt(h, registry)

    # 4. Append the user message.
    project.messages.append(ChatMessage(role="user", text=user_text))

    # 5. Run the conversation loop.
    res = run_conversation(registry, chat_llm, system, project.messages, max_iters=max_iters)
    project.messages = res.messages

    # 6. Build a JSON-safe ProjectTurn.
    turn = new_turn(user_text)
    turn.final_text = res.final_text
    turn.h_version = h_version
    safe_tool_calls: list[dict] = []
    for tc in res.tool_calls:
        result = tc["result"]
        safe_result = result.model_dump() if hasattr(result, "model_dump") else result
        safe_tool_calls.append({"tool": tc["tool"], "args": tc["args"], "result": safe_result})
    turn.tool_calls = safe_tool_calls
    project.turns.append(turn)

    # 6b. Materialize any staged proposals into project.staged_edits.
    for tc in turn.tool_calls:
        r = tc["result"]
        if isinstance(r, dict) and r.get("staged"):
            project.staged_edits.append(StagedEdit(
                edit_id=r["edit_id"], op=r["op"], summary=r.get("summary", ""),
                valid=bool(r.get("valid")), reason=r.get("reason"), preview=r.get("preview", {})))

    # 7. Commit DecisionPackage results to workspace if provided.
    if workspace is not None:
        for tc in res.tool_calls:
            if isinstance(tc["result"], DecisionPackage):
                workspace.put_decision(tc["result"])

    # 8. Persist and return.
    store.put(project)
    return project
