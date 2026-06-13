from __future__ import annotations

from datetime import date as Date


class LookaheadError(RuntimeError):
    """请求了游标之后的数据 —— 未来函数/前视偏差被拦截。"""


class AsOfGuard:
    """单调时间边界守卫:只允许访问 <= as_of 的数据。"""

    def __init__(self, as_of: Date) -> None:
        self._as_of = as_of

    @property
    def as_of(self) -> Date:
        return self._as_of

    def check(self, requested: Date) -> None:
        if requested > self._as_of:
            raise LookaheadError(
                f"未来函数拦截:请求 {requested} > 游标 {self._as_of}"
            )

    def advance(self, new_as_of: Date) -> None:
        if new_as_of < self._as_of:
            raise ValueError(f"游标不可回退:{new_as_of} < {self._as_of}")
        self._as_of = new_as_of
