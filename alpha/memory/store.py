from __future__ import annotations
import sqlite3
from datetime import date as Date
from alpha.memory.episodes import Episode

_COLS = ("episode_id", "symbol", "skill_id", "family", "phase", "narrative",
         "entry_date", "exit_date", "outcome", "advantage", "score",
         "failure_kind", "reflection_text", "learned_asof", "superseded")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes (
  episode_id TEXT PRIMARY KEY, symbol TEXT, skill_id TEXT, family TEXT, phase TEXT, narrative TEXT,
  entry_date TEXT, exit_date TEXT, outcome TEXT, advantage REAL, score REAL,
  failure_kind TEXT, reflection_text TEXT, learned_asof TEXT NOT NULL, superseded INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS ix_episodes_learned_asof ON episodes(learned_asof);
CREATE VIRTUAL TABLE IF NOT EXISTS episodes_fts USING fts5(reflection_text, narrative, content='');
"""


def _row_to_episode(r: sqlite3.Row) -> Episode:
    return Episode(episode_id=r["episode_id"], symbol=r["symbol"], skill_id=r["skill_id"],
                   family=r["family"], phase=r["phase"] or "", narrative=r["narrative"] or "",
                   entry_date=Date.fromisoformat(r["entry_date"]), exit_date=Date.fromisoformat(r["exit_date"]),
                   outcome=r["outcome"], advantage=r["advantage"], score=r["score"],
                   failure_kind=r["failure_kind"] or "", reflection_text=r["reflection_text"] or "",
                   learned_asof=Date.fromisoformat(r["learned_asof"]))


class EpisodeStore:
    """SQLite (+FTS5) store of observation-channel episodes. Brain.db lives outside the JSON H snapshot."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    @classmethod
    def in_memory(cls) -> "EpisodeStore":
        return cls(sqlite3.connect(":memory:"))

    @classmethod
    def open(cls, path: str, *, create_if_missing: bool = True) -> "EpisodeStore":
        import os
        if not create_if_missing and not os.path.exists(path):
            raise FileNotFoundError(path)
        return cls(sqlite3.connect(path))

    def add(self, ep: Episode) -> None:
        d = ep.model_dump()
        d["superseded"] = 0
        for k in ("entry_date", "exit_date", "learned_asof"):
            d[k] = d[k].isoformat()
        cur = self._conn.execute(
            f"INSERT OR IGNORE INTO episodes ({','.join(_COLS)}) VALUES ({','.join('?' for _ in _COLS)})",
            tuple(d[c] for c in _COLS))
        if cur.rowcount:                                  # only index FTS for genuinely-new rows
            self._conn.execute("INSERT INTO episodes_fts (rowid, reflection_text, narrative) "
                               "SELECT rowid, reflection_text, narrative FROM episodes WHERE episode_id=?",
                               (ep.episode_id,))
        self._conn.commit()

    def all(self) -> list[Episode]:
        return [_row_to_episode(r) for r in self._conn.execute("SELECT * FROM episodes")]

    def for_asof(self, asof: Date, *, phase: str | None = None, narrative: str | None = None,
                 limit: int | None = 50) -> list[Episode]:
        """PIT-safe recall: non-superseded episodes knowable by `asof` (learned_asof <= asof), newest first.
        `limit=None` -> the FULL PIT-masked history (no cap). CONVENTION: aggregation callers that key off
        full per-key history (recall, taboo, forge) ALL pass `limit=None`; the default 50 is the safety cap
        for ad-hoc / display callers only (there are no default-50 production callers today — audited)."""
        clauses = ["superseded = 0", "learned_asof <= ?"]
        params: list = [asof.isoformat()]
        if phase is not None:
            clauses.append("phase = ?"); params.append(phase)
        if narrative is not None:
            clauses.append("narrative = ?"); params.append(narrative)
        where = " AND ".join(clauses)
        if limit is None:                                 # uncapped: full PIT-masked, non-superseded history
            sql = f"SELECT * FROM episodes WHERE {where} ORDER BY exit_date DESC"
        else:
            params.append(limit)
            sql = f"SELECT * FROM episodes WHERE {where} ORDER BY exit_date DESC LIMIT ?"
        return [_row_to_episode(r) for r in self._conn.execute(sql, params)]

    def mark_superseded(self, *, after: Date) -> int:
        """Mechanism for a breaker rollback (call-site deferred to §6.6): mark episodes learned after a
        checkpoint date as superseded so recall skips them. Returns the number marked."""
        cur = self._conn.execute("UPDATE episodes SET superseded = 1 WHERE learned_asof > ?",
                                 (after.isoformat(),))
        self._conn.commit()
        return cur.rowcount

    def close(self) -> None:
        self._conn.close()
