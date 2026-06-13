from __future__ import annotations

from datetime import date as Date
from typing import Literal

from pydantic import BaseModel, ConfigDict

from youzi.eval.trajectory import Trajectory
from youzi.harness.harness import HarnessState
from youzi.refine.credit import resolve_skill

FailureKind = Literal["chased_into_nuke", "weed_over_dragon", "generic_nuke", "faded_miss"]


class FailureSignature(BaseModel):
    """一条确定性入场失败签名(board-rank × oracle outcome,无 OHLCV/相位)。"""
    model_config = ConfigDict(frozen=True)
    date: Date
    code: str
    pattern: str
    skill_id: str | None
    kind: FailureKind
    score: float
    evidence: str


def extract_signatures(traj: Trajectory, harness: HarnessState) -> list[FailureSignature]:
    """对已打分轨迹抽取入场类失败签名(continued 不产签名)。"""
    out: list[FailureSignature] = []
    for step in traj.scored_steps():
        mx = step.market.max_board_height
        for code, sc in step.outcomes.items():
            if sc.outcome == "continued":
                continue
            snap = step.entries.get(code)
            boards = snap.boards if snap is not None else None
            if sc.outcome == "faded":
                kind: FailureKind = "faded_miss"
                ev = f"boards={boards}/max={mx} → 入场后次日 faded(空耗,SCORE 0)"
            elif boards is not None and boards == mx:
                kind = "chased_into_nuke"
                ev = f"boards={boards}/max={mx} → 追最高板被闷(次日跌停/炸板)"
            elif boards is not None and boards < mx:
                kind = "weed_over_dragon"
                ev = f"boards={boards}/max={mx} → 接非最高板被砸(把杂毛当龙头)"
            else:
                kind = "generic_nuke"
                ev = f"boards={boards}/max={mx} → 被砸(板数未知或异常)"
            sk = resolve_skill(sc.pattern, harness)
            out.append(FailureSignature(
                date=step.date, code=code, pattern=sc.pattern,
                skill_id=sk.skill_id if sk is not None else None,
                kind=kind, score=sc.score, evidence=ev))
    return out
