"""A4 (c) — scope label on every learned-context write (lessons / skills / episodes), plus the
redact-before-hash ordering invariant pinned at the session-message store.

A4 lands the LABELS; the wider-than-evidence gate that consumes them is A8. Default = agent-global
(today's corpus is Kairos's craft; see the A4 spec), and legacy/unlabeled reads fall back to it.
"""
from __future__ import annotations

import sqlite3
from datetime import date

from alpha.harness.memory import Lesson
from alpha.harness.skill import Skill
from alpha.harness.state import HarnessState
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import MemoryStore, SkillRegistry
from alpha.integrity import sha256_bytes
from alpha.memory.episodes import Episode
from alpha.memory.store import EpisodeStore
from alpha.trace import DEFAULT_SCOPE


# ── the label rides every learned-context write ──────────────────────────────

def test_new_lesson_carries_scope_label():
    assert Lesson(lesson_id="l", outcome="loss", lesson="x").scope == DEFAULT_SCOPE
    assert Lesson(lesson_id="l", outcome="loss", lesson="x", scope="per-session").scope == "per-session"


def test_new_skill_carries_scope_label():
    assert Skill(skill_id="s", name="S", type="pattern").scope == DEFAULT_SCOPE


def test_new_episode_carries_scope_label():
    ep = Episode(episode_id="e", symbol="A", skill_id="s",
                 entry_date=date(2026, 1, 1), exit_date=date(2026, 1, 2), outcome="faded")
    assert ep.scope == DEFAULT_SCOPE


# ── legacy / unlabeled reads default to a sane value ─────────────────────────

def test_legacy_lesson_dict_without_scope_defaults():
    lesson = Lesson.model_validate({"lesson_id": "l", "outcome": "loss", "lesson": "x"})
    assert lesson.scope == DEFAULT_SCOPE


def test_harness_roundtrip_preserves_scope():
    h = HarnessState(
        doctrine=Doctrine(),
        skills=SkillRegistry.from_skills([Skill(skill_id="s", name="S", type="pattern",
                                                scope="per-party")]),
        memory=MemoryStore.from_lessons([Lesson(lesson_id="l", outcome="loss", lesson="x",
                                                scope="per-session")]))
    h2 = HarnessState.from_dict(h.to_dict())
    assert h2.skills.all()[0].scope == "per-party"
    assert h2.memory.all()[0].scope == "per-session"


def test_legacy_harness_dict_without_scope_defaults():
    # A brain.json persisted before A4 has lessons/skills with no scope key.
    legacy = {
        "doctrine": Doctrine().model_dump(mode="json"),
        "skills": [{"skill_id": "s", "name": "S", "type": "pattern"}],
        "memory": [{"lesson_id": "l", "outcome": "loss", "lesson": "x"}],
    }
    h = HarnessState.from_dict(legacy)
    assert h.skills.all()[0].scope == DEFAULT_SCOPE
    assert h.memory.all()[0].scope == DEFAULT_SCOPE


# ── episode scope persists through the (TCB) EpisodeStore ─────────────────────

def test_episode_scope_roundtrips_through_store():
    st = EpisodeStore.in_memory()
    st.add(Episode(episode_id="e1", symbol="A", skill_id="s", entry_date=date(2026, 1, 1),
                   exit_date=date(2026, 1, 2), outcome="faded", scope="per-session"))
    assert st.all()[0].scope == "per-session"


def test_episode_store_migration_adds_scope_column_with_default():
    # A brain.db predating A4 has no `scope` column; the guarded migration adds it, legacy rows default.
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE episodes (episode_id TEXT PRIMARY KEY, symbol TEXT, skill_id TEXT, "
        "kind TEXT NOT NULL DEFAULT 'trade', family TEXT, phase TEXT, narrative TEXT, "
        "entry_date TEXT, exit_date TEXT, outcome TEXT, advantage REAL, score REAL, "
        "failure_kind TEXT, reflection_text TEXT, learned_asof TEXT NOT NULL, superseded INTEGER DEFAULT 0)")
    conn.execute("INSERT INTO episodes (episode_id,symbol,skill_id,entry_date,exit_date,outcome,"
                 "advantage,score,learned_asof) VALUES ('old','A','s','2026-01-01','2026-01-02',"
                 "'faded',0.0,0.0,'2026-01-02')")
    conn.commit()
    st = EpisodeStore(conn)                     # triggers the guarded ALTER TABLE
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(episodes)")}
    assert "scope" in cols
    assert st.all()[0].scope == "agent-global"


# ── redact (A1) before hash (A4) ordering invariant ──────────────────────────

def test_redact_runs_before_hash_at_message_store(tmp_path, monkeypatch):
    """The persist waist redacts message text; a hash over the STORED text covers the redacted
    bytes, never the secret — so redact (A1) precedes any hash (A4). (The EditLog audit chain is a
    separate, deliberately-unredacted stream; this pins the ordering where the two would compose.)"""
    from alpha.converse.project import Project
    from alpha.converse.sqlite_store import SqliteProjectStore
    from alpha.llm.chat import ChatMessage

    secret = "sk-supersecretvalue-1234567890"
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    store = SqliteProjectStore.open(str(tmp_path / "state.db"))
    store.put(Project(project_id="p", messages=[ChatMessage(role="user", text=f"key is {secret}")]))

    stored = store.get("p").messages[0].text
    assert secret not in stored and "[REDACTED:OPENAI_API_KEY]" in stored     # redacted at persist
    raw = f"key is {secret}"
    assert sha256_bytes(stored.encode()) != sha256_bytes(raw.encode())        # hash sees redacted, not raw
