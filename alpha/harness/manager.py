from __future__ import annotations

from alpha.harness.edit_log import EditLog
from alpha.harness.metatools import MetaTools
from alpha.harness.snapshot import SnapshotStore
from alpha.harness.state import HarnessState


class HarnessManager:
    """Holds the live H + EditLog + MetaTools + SnapshotStore; unifies checkpoint / rollback.

    Rollback = load a whole version snapshot and rebind the tools to the restored (H, log);
    subsequent edits act on the restored state.

    HAZARD: a reference to mgr.tools / mgr.harness cached BEFORE a rollback keeps operating on the
    discarded pre-rollback state. Always re-fetch mgr.tools after a rollback.
    """

    def __init__(self, harness: HarnessState, store: SnapshotStore, log: EditLog | None = None) -> None:
        self.harness = harness
        self.log = log if log is not None else EditLog()
        self.store = store
        self.tools = MetaTools(self.harness, self.log)

    def checkpoint(self, label: str = "") -> int:
        return self.store.save(self.harness, self.log, label)

    def rollback_to(self, version: int) -> None:
        self.harness, self.log = self.store.load(version)
        self.tools = MetaTools(self.harness, self.log)     # rebind to restored state

    def latest_version(self) -> int | None:
        """Latest version on disk (not the in-memory version currently rolled back to)."""
        return self.store.latest()
