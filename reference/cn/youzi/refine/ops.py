# youzi/refine/ops.py
from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from youzi.llm.extract import extract_json_object

PassKind = Literal["p", "G", "K", "M"]

# pass → 允许的 meta-tool 白名单(ΔG 为空集:G 子 Agent 未建,占位 no-op)
PASS_TOOLS: dict[PassKind, frozenset[str]] = {
    "p": frozenset({"rewrite_doctrine"}),
    "G": frozenset(),
    "K": frozenset({"write_skill", "patch_skill", "retire_skill",
                    "revive_skill", "promote_skill"}),
    "M": frozenset({"process_memory", "update_memory", "demote_memory"}),
}


class RefineOp(BaseModel):
    """一条待应用编辑(frozen)。"""
    model_config = ConfigDict(frozen=True)
    tool: str                                  # meta-tool 名(必填)
    args: dict = Field(default_factory=dict)   # 该 tool 的参数
    rationale: str = ""                        # apply 阶段强制非空


def parse_ops(raw: str) -> list[RefineOp]:
    """LLM 文本 → list[RefineOp]。

    extract_json_object → json.loads → 取 "ops":[...];非对象/无 ops/条目缺 tool 或 args 非 dict
    → 跳过该条(不崩);整体失败 → []。rationale 缺失不在此跳过(默认 ""),留到 apply 阶段
    作为 rejected 上报,使所有 rationale 问题统一可见。
    """
    s = extract_json_object(raw)
    if s is None:
        return []
    try:
        data = json.loads(s)
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    raw_ops = data.get("ops")
    if not isinstance(raw_ops, list):
        return []
    out: list[RefineOp] = []
    for o in raw_ops:
        if not isinstance(o, dict):
            continue
        tool = o.get("tool")
        if not isinstance(tool, str) or not tool:
            continue
        args = o.get("args")
        if args is None:
            args = {}
        if not isinstance(args, dict):
            continue
        rationale = o.get("rationale")
        rationale = rationale if isinstance(rationale, str) else ""
        out.append(RefineOp(tool=tool, args=args, rationale=rationale))
    return out
