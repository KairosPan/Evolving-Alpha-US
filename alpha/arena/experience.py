"""alpha/arena/experience.py — observation-only task episode capture (P-B).

BINDING (observation-channel — §1.3):
  * record_task_episode writes SOLELY via episode_store.add(ep).
  * It is FORBIDDEN from importing or mutating any Skill/SkillStats.
  * No try_apply_op, no harness.to_dict(), no H rollback, zero trade-gate contamination.
  * Skill/tool usage is recorded ONLY inside the kind='task' Episode (skill_id + reflection_text).
  * P-C will add SkillStats accrual behind the domain tag; that is DEFERRED.
"""
from __future__ import annotations

import json
from datetime import date as Date
from typing import TYPE_CHECKING

from alpha.memory.episodes import Episode

if TYPE_CHECKING:
    from alpha.converse.loop import ConversationResult
    from alpha.harness.state import HarnessState
    from alpha.memory.store import EpisodeStore


# ── outcome helpers (§1.4 precedence) ────────────────────────────────────────

def _task_outcome(res: "ConversationResult") -> str:
    """Deterministic, temp=0-safe outcome from ConversationResult.

    Precedence (§1.4):
      1. hit_max_iters → 'incomplete'
      2. any shell ExecResult ok=False → 'failed'
      3. any tool result carrying {'error': ...} → 'failed'
      4. else → 'succeeded'
    """
    if res.hit_max_iters:
        return "incomplete"
    for tc in res.tool_calls:
        result = tc.get("result", {})
        if not isinstance(result, dict):
            continue
        if result.get("ok") is False:          # §1.4 #2: shell ExecResult non-zero exit
            return "failed"
        if "error" in result:                  # §1.4 #3: any tool error key
            return "failed"
    return "succeeded"


# ── skill resolution ──────────────────────────────────────────────────────────

def _resolve_skill_id(res: "ConversationResult", h: "HarnessState") -> str:
    """Return the first K-skill referenced in tool_call args, else '__task__' sentinel."""
    for tc in res.tool_calls:
        args = tc.get("args") or {}
        sid = args.get("skill_id") or args.get("id")
        if sid and h.skills.get(str(sid)) is not None:
            return str(sid)
    return "__task__"


# ── narrative tag ─────────────────────────────────────────────────────────────

def _task_narrative(res: "ConversationResult") -> str:
    """Derive a coarse task-type tag from the dominant tool used."""
    tools = [tc.get("tool", "") for tc in res.tool_calls]
    if not tools:
        return "observe"
    if any("propose" in t or "brain" in t or "edit" in t for t in tools):
        return "brain_edit"
    if any(t == "shell" for t in tools):
        return "shell_exec"
    if any("write" in t for t in tools):
        return "workspace_write"
    if any("read" in t or "decide" in t or "fetch" in t for t in tools):
        return "observe"
    return "generic"


# ── reflection JSON ───────────────────────────────────────────────────────────

def _task_reflection(res: "ConversationResult") -> str:
    """Compact JSON summary: tools used (with gate verdicts + shell ok/exit_code), hit_max_iters."""
    tools_used = []
    for tc in res.tool_calls:
        entry: dict = {"tool": tc.get("tool", "")}
        result = tc.get("result") or {}
        if isinstance(result, dict):
            if "status" in result:                    # gate verdict
                entry["gate_status"] = result["status"]
            if "ok" in result:                        # shell ExecResult
                entry["ok"] = result["ok"]
                if "exit_code" in result:
                    entry["exit_code"] = result["exit_code"]
            if "error" in result:
                entry["error"] = result["error"]
        tools_used.append(entry)
    return json.dumps({"tools": tools_used, "hit_max_iters": res.hit_max_iters},
                      separators=(",", ":"))


# ── public API ────────────────────────────────────────────────────────────────

def record_task_episode(
    res: "ConversationResult",
    h: "HarnessState",
    *,
    asof: Date,
    project_id: str,
    turn_seq: int,
    episode_store: "EpisodeStore | None" = None,
) -> "Episode | None":
    """Build and persist a kind='task' Episode from a completed ConversationResult.

    Returns the Episode when episode_store is provided, None otherwise (no-op).
    The call is idempotent: INSERT OR IGNORE on the deterministic episode_id.

    Fires from converse_project (alpha/converse/session.py) after step 6b, gated behind the
    injected episode_store param so the default (None) is byte-identical to before P-B.

    asof must be the turn's pinned logical date (same PIT key threaded into recall), NOT wall-clock.
    """
    if episode_store is None:
        return None

    ep = Episode(
        episode_id=f"{asof.isoformat()}:{project_id}:{turn_seq}",
        kind="task",
        symbol="",
        family=None,
        skill_id=_resolve_skill_id(res, h),
        narrative=_task_narrative(res),
        phase="",
        entry_date=asof,
        exit_date=asof,
        learned_asof=asof,
        outcome=_task_outcome(res),
        advantage=0.0,
        score=0.0,
        failure_kind="",
        reflection_text=_task_reflection(res),
    )
    episode_store.add(ep)
    return ep
