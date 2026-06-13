from __future__ import annotations


class ImmutableDoctrineError(RuntimeError):
    """试图改写/删除标记为 immutable 的纪律红线 doctrine 条目。"""


class InvalidTransitionError(RuntimeError):
    """非法的技能状态转移(如 revive 一个非 dormant 技能)。"""
