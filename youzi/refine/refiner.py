# youzi/refine/refiner.py
from __future__ import annotations

from collections import deque

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from youzi.eval.trajectory import Trajectory
from youzi.harness.errors import ImmutableDoctrineError, InvalidTransitionError
from youzi.harness.harness import HarnessState
from youzi.harness.memory_item import Lesson
from youzi.harness.metatools import MetaTools
from youzi.harness.skill import Skill
from youzi.llm.client import LLMClient
from youzi.refine.credit import UNATTRIBUTED, CreditReport
from youzi.refine.ops import PASS_TOOLS, PassKind, RefineOp, parse_ops
from youzi.refine.refiner_prompt import build_refiner_system_prompt, build_refiner_user_prompt
from youzi.refine.signatures import FailureSignature

_PASS_ORDER: tuple[PassKind, ...] = ("p", "G", "K", "M")


class RefinerConfig(BaseModel):
    max_edits_per_pass: int = 5
    max_edits_per_refine: int = 12
    window: int = 10
    min_retire_samples: int = Field(default=5, ge=1)   # retire_skill 需 skill.stats.n>=此值,防小样本过度退役
    min_promote_samples: int = Field(default=3, ge=1)  # promote_skill 需 skill.stats.n>=此值 且 expectancy>0(A1 晋升证据门,镜像退役门)


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

    def __bool__(self) -> bool:
        return True


def _target_id(tool: str, args: dict) -> str | None:
    # 归一为 str|None:LLM 可能把 id 发成数字(如 {"skill_id": 7}),若不归一,
    # 拒绝路径构造 RejectedEdit(target_id=非str) 会 pydantic ValidationError 崩掉 refine()。
    if tool in ("write_skill", "patch_skill", "retire_skill", "revive_skill", "promote_skill"):
        v = args.get("skill_id")
    elif tool in ("process_memory", "update_memory", "demote_memory"):
        v = args.get("lesson_id")
    elif tool == "rewrite_doctrine":
        v = args.get("section")
    else:
        v = None
    return None if v is None else str(v)


class Refiner:
    """LLM 复盘官:读证据 → 经 MetaTools 结构性编辑 H → RefineReport。

    就地编辑传入的 HarnessState(reset-free,agent 立即可见);不 checkpoint/不回滚(1b-3)。
    """

    def __init__(self, harness: HarnessState, llm: LLMClient,
                 meta: MetaTools, config: RefinerConfig | None = None) -> None:
        self._h = harness
        self._llm = llm
        self._meta = meta
        self._cfg = config or RefinerConfig()
        # A3 编辑史:记住最近 2 次 RefineReport,渲染进 user prompt(applied 别重复提 /
        # rejected 带拒因别原样重发)。注意:InnerLoop._rebind(rollback 后)重建 Refiner
        # 时历史丢失——可接受:回滚已把 H 还原,旧编辑史描述的编辑均已撤销,作废是正确语义。
        self._recent_reports: deque[RefineReport] = deque(maxlen=2)

    def _apply_op(self, op: RefineOp, pk: PassKind,
                  allowed: frozenset[str]) -> tuple[bool, object]:
        tid = _target_id(op.tool, op.args)
        if op.tool not in allowed:
            return False, RejectedEdit(pass_kind=pk, tool=op.tool, target_id=tid,
                                       reason=f"tool 不属于本 {pk}-pass 或未知")
        if not op.rationale.strip():
            return False, RejectedEdit(pass_kind=pk, tool=op.tool, target_id=tid,
                                       reason="缺 rationale")
        # 退役证据门(治真实数据退化根因:小样本过度退役)。只读 stats.n,不改 stats。
        if op.tool == "retire_skill":
            sk = self._h.skills.get(str(tid)) if tid else None
            if sk is not None and sk.stats.n < self._cfg.min_retire_samples:
                return False, RejectedEdit(
                    pass_kind=pk, tool=op.tool, target_id=tid,
                    reason=(f"证据不足:n={sk.stats.n}<min_retire_samples="
                            f"{self._cfg.min_retire_samples},不退役(faded 是空耗非亏损,样本不足别退役)"))
        # 晋升证据门(A1,镜像退役门):孵化技能须先经试验位积累战绩——n≥K 且
        # 超额(expectancy=advantage)>0 才许 incubating→active,否则零证据上岗。
        # 同退役门:只读 stats、不改 stats;目标不存在 → 落到 dispatch 的 KeyError 干净拒绝。
        if op.tool == "promote_skill":
            sk = self._h.skills.get(str(tid)) if tid else None
            if sk is not None:
                if sk.stats.n < self._cfg.min_promote_samples:
                    return False, RejectedEdit(
                        pass_kind=pk, tool=op.tool, target_id=tid,
                        reason=(f"证据不足:n={sk.stats.n}<min_promote_samples="
                                f"{self._cfg.min_promote_samples},不晋升(让它留在试验位积累战绩)"))
                exp = sk.stats.expectancy
                if exp is None or exp <= 0:
                    return False, RejectedEdit(
                        pass_kind=pk, tool=op.tool, target_id=tid,
                        reason=(f"证据不足:超额={'无' if exp is None else f'{exp:+.2f}'}≤0,"
                                "不晋升(无正优势不上岗,等证据或 retire 腾位)"))
        try:
            rec = self._dispatch(op)
        except (ImmutableDoctrineError, InvalidTransitionError, KeyError,
                ValueError, ValidationError, TypeError, AttributeError) as e:
            return False, RejectedEdit(pass_kind=pk, tool=op.tool, target_id=tid,
                                       reason=f"{type(e).__name__}: {e}")
        return True, AppliedEdit(pass_kind=pk, tool=op.tool,
                                 target_id=str(rec.target_id), seq=rec.seq,
                                 rationale=op.rationale)

    def _dispatch(self, op: RefineOp):
        a = dict(op.args)
        r = op.rationale
        m = self._meta
        if op.tool == "write_skill":
            # LLM 不可注入伪造 stats(观测,由 apply_credit 维护),也不可直接铸造 active(孵化→晋升闸)
            a = {k: v for k, v in a.items() if k != "stats"}
            a["status"] = "incubating"
            return m.write_skill(Skill.from_seed(a), rationale=r)
        if op.tool == "patch_skill":
            sid = a.pop("skill_id")
            return m.patch_skill(sid, rationale=r, **a)
        if op.tool == "retire_skill":
            sid = a.pop("skill_id")
            perm = bool(a.pop("permanent", False))
            return m.retire_skill(sid, permanent=perm, rationale=r)
        if op.tool == "revive_skill":
            return m.revive_skill(a["skill_id"], rationale=r)
        if op.tool == "promote_skill":
            return m.promote_skill(a["skill_id"], rationale=r)
        if op.tool == "process_memory":
            # LLM 不可注入伪造 importance(观测,由 demote_memory/时间衰减管理)
            a = {k: v for k, v in a.items() if k != "importance"}
            return m.process_memory(Lesson.from_seed(a), rationale=r)
        if op.tool == "update_memory":
            lid = a.pop("lesson_id")
            return m.update_memory(lid, rationale=r, **a)
        if op.tool == "demote_memory":
            return m.demote_memory(a["lesson_id"], a["factor"], rationale=r)
        if op.tool == "rewrite_doctrine":
            return m.rewrite_doctrine(a["section"], a["new_guidance"], rationale=r)
        raise ValueError(f"未知 tool: {op.tool}")

    def refine(self, traj: Trajectory, credit: CreditReport,
               signatures: list[FailureSignature]) -> RefineReport:
        applied: list[AppliedEdit] = []
        rejected: list[RejectedEdit] = []
        notes: list[str] = []
        history = list(self._recent_reports)   # A3:快照既往编辑史(本次 refine 不看自己)
        # A3 涉案技能 = 本窗信用 keys ∪ 签名 skill_id(去 None / unattributed 桶)→ K-pass 渲染全文
        involved = set(credit.per_skill) | {s.skill_id for s in signatures if s.skill_id}
        involved.discard(UNATTRIBUTED)
        for pk in _PASS_ORDER:
            allowed = PASS_TOOLS[pk]
            if not allowed:                                   # ΔG 占位 no-op(不发 LLM 调用)
                notes.append(f"{pk}-pass reserved(G 子 Agent 未建,跳过)")
                continue
            system = build_refiner_system_prompt(self._h, pk, self._cfg.min_retire_samples,
                                                 involved_skill_ids=involved,
                                                 min_promote_samples=self._cfg.min_promote_samples)
            user = build_refiner_user_prompt(traj, credit, signatures, self._cfg.window,
                                             recent_reports=history)
            ops = parse_ops(self._llm.complete(system, user))
            pass_count = 0
            for op in ops:
                if len(applied) >= self._cfg.max_edits_per_refine:
                    rejected.append(RejectedEdit(pass_kind=pk, tool=op.tool,
                        target_id=_target_id(op.tool, op.args), reason="超出 per-refine 编辑上限"))
                    continue
                if pass_count >= self._cfg.max_edits_per_pass:
                    rejected.append(RejectedEdit(pass_kind=pk, tool=op.tool,
                        target_id=_target_id(op.tool, op.args), reason="超出 per-pass 编辑上限"))
                    continue
                ok, res = self._apply_op(op, pk, allowed)
                if ok:
                    applied.append(res)
                    pass_count += 1
                else:
                    rejected.append(res)
        report = RefineReport(applied=applied, rejected=rejected, notes=notes)
        self._recent_reports.append(report)    # A3:滚入编辑史(deque maxlen=2 自动滚动)
        return report
