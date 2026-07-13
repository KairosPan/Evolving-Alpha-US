from __future__ import annotations

import json
import os
import sqlite3

from alpha.converse.project import Project, ProjectTurn, StagedEdit
from alpha.llm.chat import ChatMessage
from alpha.redact import collect_secrets, redact

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
  project_id   TEXT PRIMARY KEY,
  created_at   TEXT NOT NULL,
  title        TEXT NOT NULL,
  h_pin        INTEGER,
  turns        TEXT NOT NULL,
  staged_edits TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS messages (
  project_id TEXT NOT NULL, seq INTEGER NOT NULL, role TEXT NOT NULL, text TEXT NOT NULL,
  origin TEXT,
  PRIMARY KEY (project_id, seq));
"""


def _trigram_ok(conn: sqlite3.Connection) -> bool:
    """Probe whether this runtime's sqlite supports the CJK-friendly trigram tokenizer (>=3.34)."""
    try:
        conn.execute("CREATE VIRTUAL TABLE _probe_fts USING fts5(x, tokenize='trigram')")
        conn.execute("DROP TABLE _probe_fts")
        return True
    except sqlite3.OperationalError:
        return False


class SqliteProjectStore:
    """SQLite-backed store of conversational Projects: relational envelope + normalized message
    rows + an FTS5 (trigram, CJK-friendly) index over message text. Replaces the JSON ProjectStore;
    same get/put/delete/list interface. state.db lives outside the JSON H snapshot."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        conn.row_factory = sqlite3.Row
        conn.executescript(_SCHEMA)
        # Guarded migration: a state.db may pre-date the message 'origin' column (A4 principal-origin).
        mcols = {r["name"] for r in conn.execute("PRAGMA table_info(messages)")}
        if "origin" not in mcols:
            conn.execute("ALTER TABLE messages ADD COLUMN origin TEXT")
        tok = "trigram" if _trigram_ok(conn) else "unicode61"
        self.tokenizer = tok
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING "
            f"fts5(project_id UNINDEXED, seq UNINDEXED, text, tokenize='{tok}')")
        conn.commit()

    @classmethod
    def in_memory(cls) -> "SqliteProjectStore":
        return cls(sqlite3.connect(":memory:"))

    @classmethod
    def open(cls, path: str, *, create_if_missing: bool = True) -> "SqliteProjectStore":
        if not create_if_missing and not os.path.exists(path):
            raise FileNotFoundError(path)
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        return cls(sqlite3.connect(path))

    def put(self, project: Project) -> None:
        secrets = collect_secrets()
        turns_dumped = [t.model_dump(mode="json") for t in project.turns]
        turns_dumped = redact(turns_dumped, secrets)
        turns = json.dumps(turns_dumped)
        # NEVER-SCRUB: staged_edits carry the rollback-replay payload verbatim.
        staged = json.dumps([s.model_dump(mode="json") for s in project.staged_edits])
        self._conn.execute(
            "INSERT INTO projects (project_id, created_at, title, h_pin, turns, staged_edits) "
            "VALUES (?,?,?,?,?,?) ON CONFLICT(project_id) DO UPDATE SET "
            "created_at=excluded.created_at, title=excluded.title, h_pin=excluded.h_pin, "
            "turns=excluded.turns, staged_edits=excluded.staged_edits",
            (project.project_id, project.created_at, project.title, project.h_pin, turns, staged))
        self._conn.execute("DELETE FROM messages WHERE project_id=?", (project.project_id,))
        self._conn.execute("DELETE FROM messages_fts WHERE project_id=?", (project.project_id,))
        for seq, m in enumerate(project.messages):
            text = redact(m.text, secrets)
            self._conn.execute(
                "INSERT INTO messages (project_id, seq, role, text, origin) VALUES (?,?,?,?,?)",
                (project.project_id, seq, m.role, text, m.origin))
            self._conn.execute("INSERT INTO messages_fts (project_id, seq, text) VALUES (?,?,?)",
                               (project.project_id, seq, text))
        self._conn.commit()

    def get(self, project_id: str) -> Project | None:
        row = self._conn.execute("SELECT * FROM projects WHERE project_id=?",
                                 (project_id,)).fetchone()
        if row is None:
            return None
        msgs = [ChatMessage(role=r["role"], text=r["text"], origin=r["origin"])
                for r in self._conn.execute(
                    "SELECT role, text, origin FROM messages WHERE project_id=? ORDER BY seq",
                    (project_id,))]
        return Project(
            project_id=row["project_id"], created_at=row["created_at"], title=row["title"],
            h_pin=row["h_pin"], messages=msgs,
            turns=[ProjectTurn.model_validate(t) for t in json.loads(row["turns"])],
            staged_edits=[StagedEdit.model_validate(s) for s in json.loads(row["staged_edits"])])

    def list(self) -> list[Project]:
        ids = [r["project_id"] for r in self._conn.execute(
            "SELECT project_id FROM projects ORDER BY project_id DESC")]
        return [self.get(i) for i in ids]

    def delete(self, project_id: str) -> None:
        """Hard-delete a project. Idempotent: a missing id is a no-op."""
        self._conn.execute("DELETE FROM projects WHERE project_id=?", (project_id,))
        self._conn.execute("DELETE FROM messages WHERE project_id=?", (project_id,))
        self._conn.execute("DELETE FROM messages_fts WHERE project_id=?", (project_id,))
        self._conn.commit()

    def search(self, query: str) -> list[dict]:
        """Full-text search over message text (FTS5). Returns matched messages, best-rank first.
        Queries are matched as literal phrases; FTS5 operator syntax (OR/AND/NOT, prefix *) is
        intentionally disabled by phrase-quoting to prevent crashes on hyphenated and special-char
        queries. Note: the trigram tokenizer requires queries of at least 3 characters."""
        fts_query = '"' + query.replace('"', '""') + '"'
        rows = self._conn.execute(
            "SELECT project_id, seq, text FROM messages_fts WHERE messages_fts MATCH ? "
            "ORDER BY rank", (fts_query,)).fetchall()
        return [{"project_id": r["project_id"], "seq": r["seq"], "text": r["text"]} for r in rows]

    def close(self) -> None:
        self._conn.close()
