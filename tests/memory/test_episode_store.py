import sqlite3
from datetime import date
from alpha.memory.episodes import Episode
from alpha.memory.store import EpisodeStore


def _ep(eid, exit_d, sym="RUN", text="held the breakout", kind="trade"):
    return Episode(episode_id=eid, symbol=sym, skill_id="gap_and_go", entry_date=date(2026, 6, 1),
                   exit_date=exit_d, outcome="continued", advantage=0.3, score=0.4,
                   reflection_text=text, narrative="ai-compute", kind=kind)


def test_add_and_all_round_trip():
    s = EpisodeStore.in_memory()
    s.add(_ep("a", date(2026, 6, 3)))
    s.add(_ep("b", date(2026, 6, 5)))
    got = s.all()
    assert {e.episode_id for e in got} == {"a", "b"}
    assert got[0] == _ep("a", date(2026, 6, 3)) or got[1] == _ep("a", date(2026, 6, 3))


def test_insert_or_ignore_dedups_by_id():
    s = EpisodeStore.in_memory()
    s.add(_ep("a", date(2026, 6, 3), text="first"))
    s.add(_ep("a", date(2026, 6, 3), text="second"))   # same id -> ignored
    assert len(s.all()) == 1 and s.all()[0].reflection_text == "first"


def test_kind_persists_and_round_trips(tmp_path):
    """A kind='task' episode survives a close/reopen cycle."""
    db_path = str(tmp_path / "brain.db")
    task_ep = _ep("c", date(2026, 6, 10), kind="task")
    s = EpisodeStore.open(db_path)
    s.add(task_ep)
    s.close()
    s2 = EpisodeStore.open(db_path)
    rows = s2.all()
    assert len(rows) == 1
    assert rows[0].kind == "task"
    s2.close()


# Schema that matches the old brain.db layout before 'kind' was added
_OLD_SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes (
  episode_id TEXT PRIMARY KEY, symbol TEXT, skill_id TEXT, family TEXT, phase TEXT, narrative TEXT,
  entry_date TEXT, exit_date TEXT, outcome TEXT, advantage REAL, score REAL,
  failure_kind TEXT, reflection_text TEXT, learned_asof TEXT NOT NULL, superseded INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS ix_episodes_learned_asof ON episodes(learned_asof);
CREATE VIRTUAL TABLE IF NOT EXISTS episodes_fts USING fts5(reflection_text, narrative, content='');
"""


def test_for_asof_kind_filter_defaults_to_trade():
    """Default kind='trade' silently scopes recall to trade rows only (verdict-neutrality fence)."""
    s = EpisodeStore.in_memory()
    asof = date(2026, 6, 10)
    trade_ep = _ep("t1", date(2026, 6, 5), kind="trade")
    task_ep = _ep("k1", date(2026, 6, 5), sym="TSLA", kind="task")
    trade_ep = trade_ep.model_copy(update={"learned_asof": asof})
    task_ep = task_ep.model_copy(update={"learned_asof": asof})
    s.add(trade_ep)
    s.add(task_ep)

    # (a) default kind="trade" → only the trade row
    result_a = s.for_asof(asof, limit=None)
    assert [e.episode_id for e in result_a] == ["t1"]

    # (b) kind="task" → only the task row
    result_b = s.for_asof(asof, kind="task", limit=None)
    assert [e.episode_id for e in result_b] == ["k1"]

    # (c) kind=None → both rows (no filter)
    result_c = s.for_asof(asof, kind=None, limit=None)
    assert {e.episode_id for e in result_c} == {"t1", "k1"}


def test_guarded_migration_old_db(tmp_path):
    """Opening EpisodeStore on an old brain.db (no 'kind' column) migrates silently; rows default to 'trade'."""
    db_path = str(tmp_path / "old_brain.db")
    # Seed old-format db directly without kind column
    conn = sqlite3.connect(db_path)
    conn.executescript(_OLD_SCHEMA)
    conn.execute(
        "INSERT INTO episodes "
        "(episode_id, symbol, skill_id, entry_date, exit_date, outcome, advantage, score, learned_asof) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("old-1", "AAPL", "gap_and_go", "2026-06-01", "2026-06-03", "continued", 0.3, 0.4, "2026-06-03"),
    )
    conn.commit()
    conn.close()
    # EpisodeStore.__init__ must detect missing 'kind' and run ALTER TABLE
    s = EpisodeStore.open(db_path)
    rows = s.all()
    assert len(rows) == 1
    assert rows[0].kind == "trade"   # migration filled in the DEFAULT
    s.close()
