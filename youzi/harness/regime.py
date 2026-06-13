from __future__ import annotations

import re

CANONICAL_PHASES = ["混沌冰点", "修复启动", "情绪回暖", "题材启动", "主升", "震荡补涨", "退潮"]
ECOLOGY_TAGS = ["连板生态", "容量生态", "20cm生态", "次新生态", "超跌生态", "ST生态", "北交生态"]

# 优先级有序:"修复" 必须在 "启动" 之前判定,否则 "修复启动" 会被错归到 题材启动。
_PHASE_RULES: list[tuple[tuple[str, ...], str]] = [
    (("混沌", "冰点"), "混沌冰点"),
    (("修复",), "修复启动"),
    (("回暖",), "情绪回暖"),
    (("题材启动", "启动"), "题材启动"),
    (("主升",), "主升"),
    (("震荡", "补涨"), "震荡补涨"),
    (("退潮",), "退潮"),
]


def classify_regime(raw: str) -> tuple[str, str | None]:
    """归一单个 regime 串。返回 (kind, value),kind ∈ {'phase','ecology','other'}。(入参假定为 playbook 受控词,非通用 NL;子串匹配刻意宽松)"""
    s = raw.strip() if isinstance(raw, str) else ""   # 非字符串(如 LLM 误传 int)视为空,不崩
    if not s:
        return ("other", None)
    for tag in ECOLOGY_TAGS:
        if tag in s:
            return ("ecology", tag)
    for keywords, phase in _PHASE_RULES:
        if any(k in s for k in keywords):
            return ("phase", phase)
    return ("other", None)


def split_regimes(raw: list[str]) -> tuple[list[str], list[str]]:
    """把 raw applicable_regime 列表归一为 (canonical_phases, ecologies),首见序去重,非相位丢弃。"""
    phases: list[str] = []
    ecologies: list[str] = []
    for item in raw or []:
        kind, value = classify_regime(item)
        if kind == "phase" and value not in phases:
            phases.append(value)
        elif kind == "ecology" and value not in ecologies:
            ecologies.append(value)
    return (phases, ecologies)


_REGIME_SPLIT = re.compile(r"[/、,，\s]+")


def parse_regime_field(raw: str) -> tuple[list[str], list[str], bool]:
    """把单值 regime 串(可能复合如 '主升/退潮' 或 'all')解析为 (phases, ecologies, applies_all)。

    用于 Lesson/DoctrineEntry 的 regime 字段(单字符串);Skill 的 applicable_regime 已是列表,仍用 split_regimes。
    未被识别为相位/生态/all 的 token 会从 phases/ecologies 丢弃(仅保留在调用方的 regime_raw 里)。
    """
    s = raw.strip() if isinstance(raw, str) else ""   # 非字符串(如 LLM 误传 list)视为空,不崩
    if not s:
        return ([], [], False)
    tokens = [t for t in _REGIME_SPLIT.split(s) if t]
    applies_all = "all" in tokens
    phases, ecologies = split_regimes([t for t in tokens if t != "all"])
    return (phases, ecologies, applies_all)
