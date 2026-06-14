from __future__ import annotations

from collections import deque

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from alpha.harness.edit_log import EditRecord
from alpha.harness.errors import HarnessError
from alpha.harness.memory import Lesson
from alpha.harness.metatools import MetaTools
from alpha.harness.skill import Skill
from alpha.harness.state import HarnessState
from alpha.llm.client import LLMClient
from alpha.refine.ops import PASS_ORDER, PASS_TOOLS, PassKind, RefineOp, parse_ops
from alpha.refine.credit import CreditReport
from alpha.refine.signatures import FailureSignature
from alpha.refine.refiner_prompt import build_refiner_system_prompt, build_refiner_user_prompt
from alpha.eval.trajectory import Trajectory

# Errors a dispatched meta-tool may raise that the Refiner converts into a clean RejectedEdit.
_DISPATCH_ERRORS = (HarnessError, KeyError, ValueError, ValidationError, TypeError, AttributeError)


class RefinerConfig(BaseModel):
    max_edits_per_pass: int = 5
    max_edits_per_refine: int = 12
    window: int = 10
    min_retire_samples: int = Field(default=5, ge=1)
    min_promote_samples: int = Field(default=3, ge=1)
    # (credit `decay` is a parameter of apply_credit / the US-2c LoopConfig, not the Refiner's concern)


class AppliedEdit(BaseModel):
    model_config = ConfigDict(frozen=True)
    pass_kind: PassKind
    tool: str
    target_id: str
    seq: int
    rationale: str


class RejectedEdit(BaseModel):
    model_config = ConfigDict(frozen=True)
    pass_kind: PassKind
    tool: str
    target_id: str | None
    reason: str


class RefineReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    applied: list[AppliedEdit] = Field(default_factory=list)
    rejected: list[RejectedEdit] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def _target_id(tool: str, args: dict) -> str | None:
    """Normalize the target id to str|None (an LLM may emit a numeric id; RejectedEdit.target_id is str|None)."""
    if tool in ("write_skill", "patch_skill", "retire_skill", "revive_skill", "promote_skill"):
        v = args.get("skill_id")
    elif tool in ("process_memory", "update_memory", "demote_memory"):
        v = args.get("lesson_id")
    elif tool == "rewrite_doctrine":
        v = args.get("section")
    else:
        v = None
    return str(v) if v is not None else None


class Refiner:
    """Edits H=(p,K,M) from realized evidence via the 9 meta-tools, behind discipline gates. Edits IN
    PLACE (the agent sees them next decision); does NOT checkpoint or roll back (that is US-2c's InnerLoop)."""

    def __init__(self, harness: HarnessState, llm: LLMClient, meta: MetaTools,
                 config: RefinerConfig | None = None) -> None:
        self._h = harness
        self._llm = llm
        self._meta = meta
        self._cfg = config or RefinerConfig()
        self._recent_reports: "deque[RefineReport]" = deque(maxlen=2)

    def _dispatch(self, op: RefineOp) -> EditRecord:
        """Map an op to its US MetaTools call (rationale is a required positional). Defensive sanitization:
        force write_skill -> incubating + strip stats; strip importance on process_memory."""
        tool, args, r = op.tool, dict(op.args), op.rationale
        m = self._meta
        if tool == "write_skill":
            args.pop("stats", None)
            args["status"] = "incubating"
            return m.write_skill(Skill.from_seed(args), rationale=r)
        if tool == "patch_skill":
            sid = args.pop("skill_id")
            return m.patch_skill(sid, rationale=r, **args)
        if tool == "retire_skill":
            sid = args.pop("skill_id")
            perm = bool(args.pop("permanent", False))
            return m.retire_skill(sid, rationale=r, permanent=perm)
        if tool == "revive_skill":
            return m.revive_skill(args.pop("skill_id"), rationale=r)
        if tool == "promote_skill":
            return m.promote_skill(args.pop("skill_id"), rationale=r)
        if tool == "process_memory":
            args.pop("importance", None)
            return m.process_memory(Lesson.from_seed(args), rationale=r)
        if tool == "update_memory":
            lid = args.pop("lesson_id")
            return m.update_memory(lid, rationale=r, **args)
        if tool == "demote_memory":
            lid = args.pop("lesson_id")
            factor = float(args.pop("factor"))
            return m.demote_memory(lid, factor, rationale=r)
        if tool == "rewrite_doctrine":
            return m.rewrite_doctrine(args.pop("section"), args.pop("new_guidance"), rationale=r)
        raise ValueError(f"unknown tool: {tool}")

    def _apply_op(self, op: RefineOp, pk: PassKind, allowed: frozenset) -> tuple[bool, object]:
        """Gate order: whitelist -> rationale -> empty-patch -> retire/promote evidence -> dispatch (errors -> reject).
        Evidence gates key on the canonical skill_id (h.skills.get(tid)); an op addressing a skill by its
        display NAME (not id) skips the gate and is rejected at dispatch (KeyError) — still a clean reject."""
        tid = _target_id(op.tool, op.args)
        if op.tool not in allowed:
            return False, RejectedEdit(pass_kind=pk, tool=op.tool, target_id=tid,
                                       reason="tool not in this pass or unknown")
        if not op.rationale or not op.rationale.strip():
            return False, RejectedEdit(pass_kind=pk, tool=op.tool, target_id=tid, reason="missing rationale")
        if op.tool in ("patch_skill", "update_memory") and not (set(op.args) - {"skill_id", "lesson_id"}):
            return False, RejectedEdit(pass_kind=pk, tool=op.tool, target_id=tid,
                                       reason="empty patch (no fields to change)")
        if op.tool == "retire_skill" and tid is not None:
            sk = self._h.skills.get(tid)
            if sk is not None and sk.stats.n < self._cfg.min_retire_samples:
                return False, RejectedEdit(pass_kind=pk, tool=op.tool, target_id=tid,
                                           reason=f"retire blocked: n={sk.stats.n} < min_retire_samples={self._cfg.min_retire_samples}")
        if op.tool == "promote_skill" and tid is not None:
            sk = self._h.skills.get(tid)
            if sk is not None:
                if sk.stats.n < self._cfg.min_promote_samples:
                    return False, RejectedEdit(pass_kind=pk, tool=op.tool, target_id=tid,
                                               reason=f"promote blocked: n={sk.stats.n} < min_promote_samples={self._cfg.min_promote_samples}")
                if sk.stats.expectancy is None or sk.stats.expectancy <= 0:
                    return False, RejectedEdit(pass_kind=pk, tool=op.tool, target_id=tid,
                                               reason="promote blocked: expectancy (advantage) not > 0")
        try:
            rec = self._dispatch(op)
        except _DISPATCH_ERRORS as e:
            return False, RejectedEdit(pass_kind=pk, tool=op.tool, target_id=tid, reason=f"{type(e).__name__}: {e}")
        return True, AppliedEdit(pass_kind=pk, tool=op.tool, target_id=str(rec.target_id),
                                 seq=rec.seq, rationale=op.rationale)
