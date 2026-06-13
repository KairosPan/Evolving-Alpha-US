from __future__ import annotations

from youzi.harness.edit_log import EditLog
from youzi.harness.harness import HarnessState
from youzi.harness.metatools import MetaTools
from youzi.harness.snapshot import SnapshotStore


class HarnessManager:
    """持有 live H + EditLog + MetaTools + SnapshotStore;统一 checkpoint / rollback。

    回滚 = 加载整版快照并把 tools 重绑到还原后的 H+log,后续编辑作用在还原态上。
    """

    def __init__(self, harness: HarnessState, store: SnapshotStore,
                 log: EditLog | None = None) -> None:
        self.harness = harness
        self.log = log if log is not None else EditLog()
        self.store = store
        self.tools = MetaTools(self.harness, self.log)

    def checkpoint(self, label: str = "") -> int:
        return self.store.save(self.harness, self.log, label)

    def rollback_to(self, version: int) -> None:
        """加载该版本快照并把 tools 重绑到还原态。
        注意:rollback 后,任何在 rollback 前缓存了 mgr.tools / mgr.harness 的调用方,
        其旧引用会静默操作被丢弃的 pre-rollback 状态——rollback 后务必重新取 mgr.tools。"""
        self.harness, self.log = self.store.load(version)
        self.tools = MetaTools(self.harness, self.log)     # 重绑到还原态

    def latest_version(self) -> int | None:
        """磁盘上最新版本号(非内存当前 rollback 到的版本)。"""
        return self.store.latest()
