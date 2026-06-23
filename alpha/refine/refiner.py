from __future__ import annotations

from collections import deque

from pydantic import BaseModel, ConfigDict, Field

from alpha.harness.metatools import MetaTools
from alpha.harness.state import HarnessState
from alpha.llm.client import LLMClient
from alpha.refine.apply import try_apply_op, _target_id
from alpha.refine.ops import PASS_ORDER, PASS_TOOLS, PassKind, RefineOp, parse_ops
from alpha.refine.credit import CreditReport
from alpha.refine.signatures import FailureSignature
from alpha.refine.refiner_prompt import build_refiner_system_prompt, build_refiner_user_prompt
from alpha.eval.trajectory import Trajectory


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

    def _apply_op(self, op: RefineOp, pk: PassKind, allowed: frozenset) -> tuple[bool, object]:
        """Delegate to shared try_apply_op then wrap result into Refiner's AppliedEdit/RejectedEdit."""
        rec, reason = try_apply_op(self._meta, self._h, op, allowed=allowed,
                                   min_retire_samples=self._cfg.min_retire_samples,
                                   min_promote_samples=self._cfg.min_promote_samples)
        if reason is not None:
            return False, RejectedEdit(pass_kind=pk, tool=op.tool,
                                       target_id=_target_id(op.tool, op.args), reason=reason)
        return True, AppliedEdit(pass_kind=pk, tool=op.tool, target_id=str(rec.target_id),
                                 seq=rec.seq, rationale=op.rationale)

    def refine(self, traj: Trajectory, credit: CreditReport,
               signatures: list[FailureSignature]) -> RefineReport:
        """Run the 4 passes (p, G, K, M) over the live H. G is a reserved no-op (no LLM call). Each
        non-empty pass = one scoped LLM call -> parse_ops -> apply under per-pass / per-refine caps."""
        history = list(self._recent_reports)            # snapshot BEFORE the loop (never see our own report)
        applied: list[AppliedEdit] = []
        rejected: list[RejectedEdit] = []
        notes: list[str] = []
        involved = set(credit.per_skill) | {s.skill_id for s in signatures if s.skill_id}
        user = build_refiner_user_prompt(traj, credit, signatures, window=self._cfg.window,
                                         recent_reports=history)
        for pk in PASS_ORDER:
            allowed = PASS_TOOLS[pk]
            if not allowed:                              # G-pass: reserved no-op (sub-agents unbuilt)
                notes.append(f"{pk}-pass reserved (no sub-agents yet); skipped")
                continue
            system = build_refiner_system_prompt(self._h, pk, min_retire_samples=self._cfg.min_retire_samples,
                                                 min_promote_samples=self._cfg.min_promote_samples,
                                                 involved_skill_ids=involved)
            ops = parse_ops(self._llm.complete(system, user))
            pass_count = 0
            for op in ops:
                tid = _target_id(op.tool, op.args)
                if len(applied) >= self._cfg.max_edits_per_refine:
                    rejected.append(RejectedEdit(pass_kind=pk, tool=op.tool, target_id=tid,
                                                 reason="exceeds per-refine limit"))
                    continue
                if pass_count >= self._cfg.max_edits_per_pass:
                    rejected.append(RejectedEdit(pass_kind=pk, tool=op.tool, target_id=tid,
                                                 reason="exceeds per-pass limit"))
                    continue
                ok, edit = self._apply_op(op, pk, allowed)
                if ok:
                    applied.append(edit)
                    pass_count += 1
                else:
                    rejected.append(edit)
        report = RefineReport(applied=applied, rejected=rejected, notes=notes)
        self._recent_reports.append(report)
        return report
