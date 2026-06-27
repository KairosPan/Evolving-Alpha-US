# Phase-1 Hermes-Vendoring Completion — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the two named-open §8/Phase-1 Hermes follow-ups (the §8 spec reframe + the deferred narrow-waist vendoring) and the deferred Phase-1 SQLite session-persistence piece.

**Architecture:** Three disjoint deliverables. **D1** reference-vendors the proven-clean `tools/registry.py` leaf (committed, SHA-pinned, audited) with a contract-parity test, leaving the active 28-LOC reimpl untouched. **D2** replaces the JSON `ProjectStore` with a SQLite-backed `SqliteProjectStore` (`state.db`, normalized `messages` table + FTS5 trigram search) behind the identical `get/put/delete/list` interface, plus a one-time JSON→SQLite migration. **D3** reframes the parent spec §8/§9 to the Phase-0 NUANCED-GO reality and moves closed items to `PROJECT_STATE.md`.

**Tech Stack:** Python 3, pydantic v2, stdlib `sqlite3` (FTS5 + trigram tokenizer), pytest. No new dependencies.

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-06-27-phase1-hermes-vendoring-completion-design.md`. Every task's requirements implicitly include it.
- **Pinned Hermes SHA:** `5add283ec8e7a33110a9051179208bd50bda427c` (verbatim, never paraphrased in provenance).
- **Additive-where-possible discipline:** the ONLY existing-code behavior change is D2's persistence backend swap. D1 and D3 add files / edit docs only.
- **TDD:** write the failing test first; run it red; minimal implementation; run green; commit.
- **No new runtime dependencies.** `sqlite3` is stdlib; FTS5 + trigram are confirmed available on this runtime (sqlite 3.50.2). The store still probes trigram and falls back to the default tokenizer (portability).
- **Round-trip contract (D2):** all seven `Project` fields (`project_id`, `created_at`, `title`, `h_pin`, `messages`, `turns`, `staged_edits`) must survive `put`→`get` unchanged.
- **`list()` ordering (D2):** must match the JSON store exactly — `ORDER BY project_id DESC` (the JSON `ProjectStore.list()` sorts `key=project_id, reverse=True`). No wall-clock read in the store.
- **Commit convention:** end commit messages with `Claude-Session: https://claude.ai/code/session_013LUPv6zbu8WxUaDktc6UmE`. Commit to local `main`; do NOT push (push requires explicit user authorization).
- **Trigram queries are ≥3 characters** — FTS5 trigram cannot match shorter terms; all search tests use ≥3-char queries.

---

## File Structure

**D1 — reference-vendor:**
- Create: `third_party/hermes/tools/registry.py` (verbatim copy of the pinned leaf)
- Create: `third_party/hermes/LICENSE` (Hermes MIT, copied)
- Create: `third_party/hermes/PROVENANCE.md` (source, SHA, scope, policy)
- Create: `tests/converse/test_registry_parity.py`

**D2 — SQLite store:**
- Create: `alpha/converse/sqlite_store.py` (`SqliteProjectStore`)
- Create: `tests/converse/test_sqlite_store.py`
- Create: `scripts/migrate_projects_to_sqlite.py`
- Create: `tests/converse/test_migrate_projects.py`
- Modify: `alpha/converse/session.py:12,21` (import + annotation)
- Modify: `workbench/app.py:9,35` (import + `_project_store` + env var)
- Modify: `tests/converse/test_converse_project.py`, `tests/converse/test_converse_project_stage.py`, `tests/converse/test_project_isolation.py` (store constructor)
- Modify: `tests/workbench/test_workbench_service.py`, `tests/workbench/test_workbench_mutation.py`, `tests/web/test_workbench_page.py` (env var rename)
- Delete: `alpha/converse/store.py` (JSON store)
- Delete: `tests/converse/test_project_store.py` (JSON-store-specific; superseded by `test_sqlite_store.py`)

**D3 — docs:**
- Modify: `docs/superpowers/specs/2026-06-25-evolving-alpha-hermes-rebase-architecture-design.md` (§8 table + §8 upstream-tracking line + §9 Phase-1)
- Modify: `docs/PROJECT_STATE.md` (record D1/D2/D3 as built)

---

## D1 — Reference-vendor the clean leaf + parity test

### Task 1: Vendor the leaf + provenance

**Files:**
- Create: `third_party/hermes/tools/registry.py`
- Create: `third_party/hermes/LICENSE`
- Create: `third_party/hermes/PROVENANCE.md`
- Test: `tests/converse/test_registry_parity.py` (provenance half)

**Interfaces:**
- Consumes: the gitignored pinned clone at `spikes/2026-06-26-hermes-vendor-feasibility/_hermes/`.
- Produces: a committed `third_party/hermes/` tree the parity test (Task 2) imports.

- [ ] **Step 1: Write the failing provenance test**

Create `tests/converse/test_registry_parity.py` with (the provenance half only for now):

```python
import pathlib

ROOT = pathlib.Path(__file__).parents[2]
VENDOR = ROOT / "third_party" / "hermes"
PINNED_SHA = "5add283ec8e7a33110a9051179208bd50bda427c"


def test_vendored_tree_present_and_provenanced():
    assert (VENDOR / "tools" / "registry.py").is_file()
    license_text = (VENDOR / "LICENSE").read_text()
    assert "MIT" in license_text
    prov = (VENDOR / "PROVENANCE.md").read_text()
    assert PINNED_SHA in prov                      # exact pinned commit recorded
    assert "do not track upstream" in prov.lower() # §8 policy recorded
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/converse/test_registry_parity.py::test_vendored_tree_present_and_provenanced -v`
Expected: FAIL (files do not exist yet).

- [ ] **Step 3: Copy the vendored files**

Run:
```bash
mkdir -p third_party/hermes/tools
cp spikes/2026-06-26-hermes-vendor-feasibility/_hermes/tools/registry.py third_party/hermes/tools/registry.py
cp spikes/2026-06-26-hermes-vendor-feasibility/_hermes/LICENSE third_party/hermes/LICENSE
```
Verify the license is MIT: `head -5 third_party/hermes/LICENSE` (expect "MIT License"). If it is not literally "MIT", adjust the test's assertion to match the real license name found in the file (do not fabricate).

- [ ] **Step 4: Write `third_party/hermes/PROVENANCE.md`**

```markdown
# Vendored Hermes — provenance

- **Upstream:** NousResearch/hermes-agent (MIT).
- **Pinned commit:** `5add283ec8e7a33110a9051179208bd50bda427c`
- **What is vendored:** ONLY `tools/registry.py` (the central tool registry — an eager
  leaf: 1 file / 589 LOC, no `agent/` package drag, measured by the Phase-0 spike
  `spikes/2026-06-26-hermes-vendor-feasibility/COUPLING.md`).
- **Why reference-only:** the active tool-registry code path is
  `alpha/converse/registry.py` (a 28-LOC reimplementation). This committed copy is the
  audit / provenance anchor and the schema source-of-truth that the parity test
  (`tests/converse/test_registry_parity.py`) checks the reimpl against. We do NOT import
  this file in production.
- **Upstream-tracking policy (parent spec §8):** **hard-pin this SHA; do not track
  upstream.** Hermes is a ~2 579-file daily-moving monolith; the narrow waist we depend on
  is the tool-calling *schema contract*, not the code. Only bump deliberately, and when you
  do, re-run the Phase-0 coupling measurement
  (`spikes/2026-06-26-hermes-vendor-feasibility/coupling.py`) as a gating check.
```

- [ ] **Step 5: Run the provenance test green**

Run: `pytest tests/converse/test_registry_parity.py::test_vendored_tree_present_and_provenanced -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add third_party/hermes tests/converse/test_registry_parity.py
git commit -m "feat(vendor): reference-vendor hermes tools/registry.py (pinned 5add283e)

Claude-Session: https://claude.ai/code/session_013LUPv6zbu8WxUaDktc6UmE"
```

---

### Task 2: Contract-parity test (reimpl ↔ vendored schema)

**Files:**
- Modify: `tests/converse/test_registry_parity.py` (add the parity assertions)

**Interfaces:**
- Consumes: `third_party/hermes/tools/registry.py` (Task 1); `alpha.converse.registry.ToolRegistry`.
- Produces: the guard that the reimpl honors the vendored tool-calling contract.

**Importability note (resolved, not assumed):** the vendored leaf's top-level imports are all stdlib (`ast, importlib, json, logging, threading, time, pathlib, typing`) — verified by reading the file — so it imports standalone. The golden-snapshot fallback in the spec is therefore NOT needed; load the file directly via `importlib.util`.

- [ ] **Step 1: Add the two failing parity tests**

Append to `tests/converse/test_registry_parity.py`:

```python
import ast
import sys
import importlib.util
from alpha.converse.registry import ToolRegistry as OurRegistry

VENDORED_FILE = VENDOR / "tools" / "registry.py"


def _load_vendored():
    spec = importlib.util.spec_from_file_location("hermes_vendored_registry", VENDORED_FILE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_vendored_leaf_imports_clean_no_monolith():
    """§8 narrow-waist claim: the leaf's top-level imports are all stdlib — importing it
    drags in NO hermes/agent module. (This is the property that makes it liftable.)"""
    tree = ast.parse(VENDORED_FILE.read_text())
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    nonstd = {r for r in roots if r not in sys.stdlib_module_names}
    assert nonstd == set(), f"vendored leaf has non-stdlib top-level imports: {nonstd}"
    # And it genuinely imports standalone:
    assert _load_vendored() is not None


def test_reimpl_matches_vendored_schema_contract():
    """Our 28-LOC reimpl honors the same tool-calling contract the vendored registry exposes:
    a tool is (name, schema, callable); registration is name-keyed; the provider-facing schema
    is retrievable by name; dispatch is by name."""
    vend = _load_vendored()
    schema = {"name": "ping", "description": "demo",
              "parameters": {"type": "object", "properties": {}}}

    # Vendored: register -> name is known -> schema retrievable by name.
    vr = vend.ToolRegistry()
    vr.register(name="ping", toolset="demo", schema=schema,
                handler=lambda args, **k: "pong", check_fn=None)
    assert "ping" in vr.get_all_tool_names()
    assert vr.get_schema("ping") == schema

    # Our reimpl: same essential contract, narrower surface.
    our = OurRegistry()
    our.register("ping", schema, lambda: "pong")
    assert our.specs() == [schema]      # provider-facing schema list == the registered schema
    assert our.call("ping") == "pong"   # dispatch by name invokes the callable
```

- [ ] **Step 2: Run to verify behavior**

Run: `pytest tests/converse/test_registry_parity.py -v`
Expected: PASS (all three tests). If `test_reimpl_matches_vendored_schema_contract` fails on a vendored method name (`get_all_tool_names`/`get_schema`), open `third_party/hermes/tools/registry.py`, confirm the public method names, and correct the test to the real names (do not change the reimpl).

- [ ] **Step 3: Commit**

```bash
git add tests/converse/test_registry_parity.py
git commit -m "test(vendor): parity — reimpl honors vendored registry schema contract

Claude-Session: https://claude.ai/code/session_013LUPv6zbu8WxUaDktc6UmE"
```

---

## D2 — Replace JSON `ProjectStore` with SQLite + FTS5

> **DDL note (refines spec §4.2):** the `messages_fts` virtual table is a self-contained FTS5 table with `project_id`/`seq` as `UNINDEXED` columns plus the indexed `text` column (NOT the spec's illustrative `content=''`). This lets `search()` read matched rows back directly and lets `delete`/`put` scope FTS rows by `project_id`, without external-content rowid bookkeeping. The interface contract is unchanged.

### Task 3: `SqliteProjectStore` — schema, constructors, `get`/`put` round-trip

**Files:**
- Create: `alpha/converse/sqlite_store.py`
- Test: `tests/converse/test_sqlite_store.py`

**Interfaces:**
- Consumes: `alpha.converse.project.{Project, ProjectTurn, StagedEdit}`, `alpha.llm.chat.ChatMessage`.
- Produces: `SqliteProjectStore` with `in_memory()`, `open(path, *, create_if_missing=True)`, `get(project_id) -> Project | None`, `put(project) -> None`, and a `.tokenizer` attribute (`"trigram"` or `"unicode61"`).

- [ ] **Step 1: Write the failing round-trip test**

Create `tests/converse/test_sqlite_store.py`:

```python
from alpha.converse.sqlite_store import SqliteProjectStore
from alpha.converse.project import Project, ProjectTurn, StagedEdit
from alpha.llm.chat import ChatMessage


def _rich_project() -> Project:
    return Project(
        project_id="p1", created_at="2026-06-27T00:00:00", title="demo", h_pin=7,
        messages=[ChatMessage(role="user", text="hello there"),
                  ChatMessage(role="assistant", text="general kenobi")],
        turns=[ProjectTurn(turn_id="t1", user_text="hello there", final_text="hi",
                           tool_calls=[{"tool": "decide", "args": {}, "result": {"ok": 1}}],
                           h_version=7, created_at="2026-06-27T00:00:01")],
        staged_edits=[StagedEdit(edit_id="e1", op={"tool": "process_memory", "args": {"x": 1}},
                                 summary="s", valid=True, preview={"k": "v"})])


def test_put_get_round_trips_all_seven_fields():
    s = SqliteProjectStore.in_memory()
    p = _rich_project()
    s.put(p)
    got = s.get("p1")
    assert got is not None
    assert got.model_dump() == p.model_dump()     # all seven fields identical


def test_get_missing_returns_none():
    s = SqliteProjectStore.in_memory()
    assert s.get("nope") is None


def test_put_is_idempotent_upsert():
    s = SqliteProjectStore.in_memory()
    p = _rich_project()
    s.put(p)
    p.title = "renamed"
    p.messages.append(ChatMessage(role="user", text="another message"))
    s.put(p)                                       # second put overwrites, no duplicate rows
    got = s.get("p1")
    assert got.title == "renamed"
    assert len(got.messages) == 3
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/converse/test_sqlite_store.py -v`
Expected: FAIL with `ModuleNotFoundError: alpha.converse.sqlite_store`.

- [ ] **Step 3: Implement `SqliteProjectStore` (schema + constructors + get/put)**

Create `alpha/converse/sqlite_store.py`:

```python
from __future__ import annotations

import json
import os
import sqlite3

from alpha.converse.project import Project, ProjectTurn, StagedEdit
from alpha.llm.chat import ChatMessage

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
        turns = json.dumps([t.model_dump() for t in project.turns])
        staged = json.dumps([s.model_dump() for s in project.staged_edits])
        self._conn.execute(
            "INSERT INTO projects (project_id, created_at, title, h_pin, turns, staged_edits) "
            "VALUES (?,?,?,?,?,?) ON CONFLICT(project_id) DO UPDATE SET "
            "created_at=excluded.created_at, title=excluded.title, h_pin=excluded.h_pin, "
            "turns=excluded.turns, staged_edits=excluded.staged_edits",
            (project.project_id, project.created_at, project.title, project.h_pin, turns, staged))
        self._conn.execute("DELETE FROM messages WHERE project_id=?", (project.project_id,))
        self._conn.execute("DELETE FROM messages_fts WHERE project_id=?", (project.project_id,))
        for seq, m in enumerate(project.messages):
            self._conn.execute("INSERT INTO messages (project_id, seq, role, text) VALUES (?,?,?,?)",
                               (project.project_id, seq, m.role, m.text))
            self._conn.execute("INSERT INTO messages_fts (project_id, seq, text) VALUES (?,?,?)",
                               (project.project_id, seq, m.text))
        self._conn.commit()

    def get(self, project_id: str) -> Project | None:
        row = self._conn.execute("SELECT * FROM projects WHERE project_id=?",
                                 (project_id,)).fetchone()
        if row is None:
            return None
        msgs = [ChatMessage(role=r["role"], text=r["text"]) for r in self._conn.execute(
            "SELECT role, text FROM messages WHERE project_id=? ORDER BY seq", (project_id,))]
        return Project(
            project_id=row["project_id"], created_at=row["created_at"], title=row["title"],
            h_pin=row["h_pin"], messages=msgs,
            turns=[ProjectTurn.model_validate(t) for t in json.loads(row["turns"])],
            staged_edits=[StagedEdit.model_validate(s) for s in json.loads(row["staged_edits"])])

    def close(self) -> None:
        self._conn.close()
```

- [ ] **Step 4: Run the round-trip tests green**

Run: `pytest tests/converse/test_sqlite_store.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add alpha/converse/sqlite_store.py tests/converse/test_sqlite_store.py
git commit -m "feat(converse): SqliteProjectStore — schema + get/put round-trip

Claude-Session: https://claude.ai/code/session_013LUPv6zbu8WxUaDktc6UmE"
```

---

### Task 4: `list()` (project_id DESC) + `delete()` (idempotent)

**Files:**
- Modify: `alpha/converse/sqlite_store.py` (add `list`, `delete`)
- Test: `tests/converse/test_sqlite_store.py` (add cases)

**Interfaces:**
- Produces: `list() -> list[Project]` (project_id DESC), `delete(project_id) -> None` (idempotent).

- [ ] **Step 1: Write the failing tests**

Append to `tests/converse/test_sqlite_store.py`:

```python
def test_list_is_project_id_desc():
    s = SqliteProjectStore.in_memory()
    for pid in ("p1", "p3", "p2"):
        s.put(Project(project_id=pid, created_at="2026-06-27T00:00:00", title=pid))
    assert [p.project_id for p in s.list()] == ["p3", "p2", "p1"]


def test_delete_is_idempotent():
    s = SqliteProjectStore.in_memory()
    s.put(Project(project_id="p1", created_at="2026-06-27T00:00:00", title="x"))
    s.delete("p1")
    s.delete("p1")                  # second delete is a no-op, not an error
    assert s.get("p1") is None
    assert s.list() == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/converse/test_sqlite_store.py -k "list or delete" -v`
Expected: FAIL (`AttributeError: 'SqliteProjectStore' object has no attribute 'list'`).

- [ ] **Step 3: Implement `list` and `delete`**

Add to `SqliteProjectStore` (before `close`):

```python
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
```

- [ ] **Step 4: Run green**

Run: `pytest tests/converse/test_sqlite_store.py -v`
Expected: PASS (all cases).

- [ ] **Step 5: Commit**

```bash
git add alpha/converse/sqlite_store.py tests/converse/test_sqlite_store.py
git commit -m "feat(converse): SqliteProjectStore list (id DESC) + idempotent delete

Claude-Session: https://claude.ai/code/session_013LUPv6zbu8WxUaDktc6UmE"
```

---

### Task 5: `search()` — FTS5 message search

**Files:**
- Modify: `alpha/converse/sqlite_store.py` (add `search`)
- Test: `tests/converse/test_sqlite_store.py` (add cases)

**Interfaces:**
- Produces: `search(query: str) -> list[dict]` — matched messages as `{"project_id","seq","text"}`, best-rank first.

- [ ] **Step 1: Write the failing tests**

Append to `tests/converse/test_sqlite_store.py`:

```python
def test_search_finds_messages_by_text():
    s = SqliteProjectStore.in_memory()
    s.put(Project(project_id="p1", created_at="2026-06-27T00:00:00", title="x",
                  messages=[ChatMessage(role="user", text="the gamma squeeze setup")]))
    s.put(Project(project_id="p2", created_at="2026-06-27T00:00:00", title="y",
                  messages=[ChatMessage(role="user", text="a quiet range day")]))
    hits = s.search("gamma")                       # >=3 chars (trigram floor)
    assert [(h["project_id"], h["seq"]) for h in hits] == [("p1", 0)]
    assert "gamma" in hits[0]["text"]


def test_search_reflects_deletes_and_updates():
    s = SqliteProjectStore.in_memory()
    s.put(Project(project_id="p1", created_at="2026-06-27T00:00:00", title="x",
                  messages=[ChatMessage(role="user", text="halt then dump pattern")]))
    s.delete("p1")
    assert s.search("halt") == []                  # FTS rows removed on delete


def test_tokenizer_is_recorded():
    s = SqliteProjectStore.in_memory()
    assert s.tokenizer in ("trigram", "unicode61")
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/converse/test_sqlite_store.py -k search -v`
Expected: FAIL (`AttributeError: ... 'search'`).

- [ ] **Step 3: Implement `search`**

Add to `SqliteProjectStore` (before `close`):

```python
    def search(self, query: str) -> list[dict]:
        """Full-text search over message text (FTS5). Returns matched messages, best-rank first.
        Note: the trigram tokenizer requires queries of at least 3 characters."""
        rows = self._conn.execute(
            "SELECT project_id, seq, text FROM messages_fts WHERE messages_fts MATCH ? "
            "ORDER BY rank", (query,)).fetchall()
        return [{"project_id": r["project_id"], "seq": r["seq"], "text": r["text"]} for r in rows]
```

- [ ] **Step 4: Run green**

Run: `pytest tests/converse/test_sqlite_store.py -v`
Expected: PASS (all cases).

- [ ] **Step 5: Commit**

```bash
git add alpha/converse/sqlite_store.py tests/converse/test_sqlite_store.py
git commit -m "feat(converse): SqliteProjectStore FTS5 message search

Claude-Session: https://claude.ai/code/session_013LUPv6zbu8WxUaDktc6UmE"
```

---

### Task 6: One-time JSON→SQLite migration script

**Files:**
- Create: `scripts/migrate_projects_to_sqlite.py`
- Test: `tests/converse/test_migrate_projects.py`

**Interfaces:**
- Consumes: an `ALPHA_PROJECTS_DIR` of `*.json` files (the JSON store's on-disk format) + `SqliteProjectStore`.
- Produces: `migrate_projects(json_dir: str, db_path: str) -> int` (count migrated) + a `__main__` CLI.

- [ ] **Step 1: Write the failing test**

Create `tests/converse/test_migrate_projects.py`:

```python
import json
from alpha.converse.project import Project
from alpha.converse.sqlite_store import SqliteProjectStore
from alpha.llm.chat import ChatMessage
from scripts.migrate_projects_to_sqlite import migrate_projects


def test_migrate_imports_json_projects(tmp_path):
    jdir = tmp_path / "projects"
    jdir.mkdir()
    p = Project(project_id="p1", created_at="2026-06-27T00:00:00", title="t",
                messages=[ChatMessage(role="user", text="hello world")])
    (jdir / "p1.json").write_text(p.model_dump_json())
    db = tmp_path / "state.db"

    n = migrate_projects(str(jdir), str(db))
    assert n == 1
    got = SqliteProjectStore.open(str(db)).get("p1")
    assert got.model_dump() == p.model_dump()


def test_migrate_is_idempotent(tmp_path):
    jdir = tmp_path / "projects"
    jdir.mkdir()
    p = Project(project_id="p1", created_at="2026-06-27T00:00:00", title="t")
    (jdir / "p1.json").write_text(p.model_dump_json())
    db = tmp_path / "state.db"
    migrate_projects(str(jdir), str(db))
    migrate_projects(str(jdir), str(db))            # re-run: upsert, no duplicate / no error
    assert len(SqliteProjectStore.open(str(db)).list()) == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/converse/test_migrate_projects.py -v`
Expected: FAIL (`ModuleNotFoundError: scripts.migrate_projects_to_sqlite`).

- [ ] **Step 3: Implement the migration script**

Create `scripts/migrate_projects_to_sqlite.py`:

```python
"""One-time migration: import JSON ProjectStore files into a SqliteProjectStore (state.db).

Usage:
    ALPHA_PROJECTS_DIR=./state/projects \\
    ALPHA_PROJECTS_DB=./state/projects/state.db \\
    python scripts/migrate_projects_to_sqlite.py

Idempotent (upsert by project_id). Safe to re-run.
"""
from __future__ import annotations

import os
from pathlib import Path

from alpha.converse.project import Project
from alpha.converse.sqlite_store import SqliteProjectStore


def migrate_projects(json_dir: str, db_path: str) -> int:
    """Import every *.json Project under *json_dir* into the SQLite store at *db_path*.
    Returns the number of projects migrated."""
    store = SqliteProjectStore.open(db_path)
    n = 0
    for jf in sorted(Path(json_dir).glob("*.json")):
        try:
            project = Project.model_validate_json(jf.read_text(encoding="utf-8"))
        except Exception:
            continue
        store.put(project)
        n += 1
    return n


if __name__ == "__main__":
    src = os.environ.get("ALPHA_PROJECTS_DIR", "./state/projects")
    dst = os.environ.get("ALPHA_PROJECTS_DB", "./state/projects/state.db")
    count = migrate_projects(src, dst)
    print(f"migrated {count} project(s) from {src} -> {dst}")
```

- [ ] **Step 4: Run green**

Run: `pytest tests/converse/test_migrate_projects.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/migrate_projects_to_sqlite.py tests/converse/test_migrate_projects.py
git commit -m "feat(scripts): one-time JSON->SQLite project migration

Claude-Session: https://claude.ai/code/session_013LUPv6zbu8WxUaDktc6UmE"
```

---

### Task 7: Rewire consumers; delete the JSON store

**Files:**
- Modify: `alpha/converse/session.py:12,21`
- Modify: `workbench/app.py:9,35`
- Modify: `tests/converse/test_converse_project.py`, `tests/converse/test_converse_project_stage.py`, `tests/converse/test_project_isolation.py`
- Modify: `tests/workbench/test_workbench_service.py`, `tests/workbench/test_workbench_mutation.py`, `tests/web/test_workbench_page.py`
- Delete: `alpha/converse/store.py`, `tests/converse/test_project_store.py`

**Interfaces:**
- Consumes: `SqliteProjectStore` (Tasks 3–5).
- Produces: a tree with no remaining importer of `alpha.converse.store`.

- [ ] **Step 1: Re-grep for every `ProjectStore` / `ALPHA_PROJECTS_DIR` consumer (guard against orphans)**

Run: `grep -rn "converse.store\|ProjectStore\|ALPHA_PROJECTS_DIR" --include="*.py" . | grep -v __pycache__ | grep -v sqlite_store`
Expected importers: `alpha/converse/session.py`, `workbench/app.py`, the three converse test files, the three workbench/web test files, and `tests/converse/test_project_store.py`. If anything else appears, add it to this task's edit list before proceeding.

- [ ] **Step 2: Rewire `alpha/converse/session.py`**

Change line 12 `from alpha.converse.store import ProjectStore` → `from alpha.converse.sqlite_store import SqliteProjectStore`.
Change line 21 `store: ProjectStore,` → `store: SqliteProjectStore,`.
(The body uses only `store.get`/`store.put`, both unchanged. `store.put` now returns `None`; line 89 discards the return, so no change there.)

- [ ] **Step 3: Rewire `workbench/app.py`**

Change line 9 `from alpha.converse.store import ProjectStore` → `from alpha.converse.sqlite_store import SqliteProjectStore`.
Change line 35:
```python
def _project_store(): return SqliteProjectStore.open(os.environ.get("ALPHA_PROJECTS_DB", "./state/projects/state.db"))
```
(Routes use only `.get`/`.put` — verified — both unchanged.)

- [ ] **Step 4: Rewire the converse tests (store constructor)**

In each of `tests/converse/test_converse_project.py`, `tests/converse/test_converse_project_stage.py`, `tests/converse/test_project_isolation.py`:
- replace the import `from alpha.converse.store import ProjectStore` → `from alpha.converse.sqlite_store import SqliteProjectStore`
- replace every `ProjectStore(tmp_path / "projects")` → `SqliteProjectStore.open(str(tmp_path / "state.db"))`

- [ ] **Step 5: Rewire the workbench/web tests (env var rename)**

In `tests/workbench/test_workbench_service.py`, `tests/workbench/test_workbench_mutation.py`, `tests/web/test_workbench_page.py`:
- replace `monkeypatch.setenv("ALPHA_PROJECTS_DIR", str(tmp_path / "projects"))`
  → `monkeypatch.setenv("ALPHA_PROJECTS_DB", str(tmp_path / "state.db"))`

- [ ] **Step 6: Delete the JSON store and its dedicated test**

Run:
```bash
git rm alpha/converse/store.py tests/converse/test_project_store.py
```
(The JSON store's behaviors — round-trip, list, delete — are now covered by `tests/converse/test_sqlite_store.py`; its `_path` traversal test is obsolete because `project_id` is now a bound SQL parameter, not a filename.)

- [ ] **Step 7: Run the affected suites green**

Run: `pytest tests/converse tests/workbench tests/web -v`
Expected: PASS (no remaining import of `alpha.converse.store`; converse + workbench + web behavior identical against SQLite).

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor(converse): replace JSON ProjectStore with SqliteProjectStore everywhere

Rewire converse_project + workbench + tests onto the SQLite store (state.db,
ALPHA_PROJECTS_DB); delete the JSON store and its traversal test (project_id is
now a bound SQL param). Interface-identical (get/put/delete/list); behavior of
the converse/workbench/web suites unchanged.

Claude-Session: https://claude.ai/code/session_013LUPv6zbu8WxUaDktc6UmE"
```

---

## D3 — Reframe parent spec §8/§9 + update PROJECT_STATE

### Task 8: Reframe parent spec §8 + §9 to the Phase-0 reality

**Files:**
- Modify: `docs/superpowers/specs/2026-06-25-evolving-alpha-hermes-rebase-architecture-design.md`

**Interfaces:** docs-only; no tests. Validation = the self-review consistency pass below.

- [ ] **Step 1: Rewrite the §8 disposition table rows to match the spike**

In §8's "Narrow-waist vendor boundary" table, change the dispositions of the conversational-loop / state / registry rows to the NUANCED-GO reality (cite `spikes/2026-06-26-hermes-vendor-feasibility/FINDINGS.md`):
- `Tool registry (tools/registry.py ...)` → **REFERENCE-VENDOR (pinned `5add283e`)** — committed at `third_party/hermes/` as the audited schema source-of-truth; the active path is the `alpha/converse/registry.py` reimpl (parity-tested). Eager leaf (1 file / 589 LOC, no `agent/` drag).
- `Tool-calling conversation loop (agent/conversation_loop.py)` → **REIMPLEMENTED (done)** — eager 28 files / drags `agent/`; reimplemented as `alpha/converse/loop.py`.
- `SQLite state.db + FTS5 ... resumable sessions` → **REIMPLEMENTED SCHEMA (done)** — eager 7 files / drags `agent/`; reimplemented as `alpha/converse/sqlite_store.py` (state.db + FTS5 trigram), NOT a code-level vendor of `hermes_state.py`.

- [ ] **Step 2: Resolve the §8 "upstream-tracking policy — Open" line**

Replace the "**Open:** pin to a single reviewed commit … vs. a periodic rebase cadence" paragraph with the resolved decision: **hard-pin SHA `5add283e`; do not track upstream** (the Phase-0 spike measured the coupling; the narrow waist we depend on is the tool-calling schema contract, not the code; re-run the coupling suite as a gate before any deliberate bump). Cross-reference `third_party/hermes/PROVENANCE.md`.

- [ ] **Step 3: Update §9 Phase-1 "Done" criteria**

In §9 "Phase 1 — Conversational face (B-WIDE)", update the "Done" line so the deferred SQLite piece is now satisfied: "messages persist to SQLite (`state.db`) + FTS5 search; artifacts to the git workspace; provenance ref per turn." Add a one-line note that the registry was reimplemented (active) with the vendored leaf reference-pinned.

- [ ] **Step 4: Update the status header's "Confirmed decisions" §8 bullet**

In the header block, change the §8 bullet from "hard-pin … revisit pin-vs-rebase after the Phase-0 spike" to "**§8 — RESOLVED: hard-pin `5add283e`, do not track upstream** (Phase-0 spike measured coupling; reference-vendor the registry leaf, reimplement the rest)."

- [ ] **Step 5: Self-review consistency pass + commit**

Re-read the edited §8/§9 with fresh eyes: no contradictions with §2.1's layer diagram (which still lists the modules as "VENDORED HERMES CORE" — add a parenthetical "(registry reference-vendored; loop + session reimplemented — see §8)" to §2.1 so the diagram and §8 agree). No "Open" left where a decision was made. Then:
```bash
git add docs/superpowers/specs/2026-06-25-evolving-alpha-hermes-rebase-architecture-design.md
git commit -m "docs(spec): reframe §8/§9 to Phase-0 reality (reference-vendor + reimplement-thin; hard-pin)

Claude-Session: https://claude.ai/code/session_013LUPv6zbu8WxUaDktc6UmE"
```

---

### Task 9: Record the work in PROJECT_STATE.md

**Files:**
- Modify: `docs/PROJECT_STATE.md`

**Interfaces:** docs-only.

- [ ] **Step 1: Append a "Phase-1 Hermes-vendoring completion" entry**

Add a dated (2026-06-27) entry to `docs/PROJECT_STATE.md` recording: D1 (reference-vendored `third_party/hermes/tools/registry.py` pinned `5add283e` + parity test), D2 (replaced JSON `ProjectStore` with `SqliteProjectStore` — state.db + FTS5 trigram message search + migration script; converse/workbench rewired; JSON store deleted), D3 (parent spec §8/§9 reframed to the NUANCED-GO reality, pin-vs-rebase resolved to hard-pin). Note the new test count and that the only existing-code behavior change was the persistence backend swap.

- [ ] **Step 2: Commit**

```bash
git add docs/PROJECT_STATE.md
git commit -m "docs: record Phase-1 Hermes-vendoring completion (D1/D2/D3)

Claude-Session: https://claude.ai/code/session_013LUPv6zbu8WxUaDktc6UmE"
```

---

## Final verification (after all tasks)

- [ ] **Full suite green**

Run: `pytest -q`
Expected: all tests pass; the count is the prior total (676) + the new tests (parity 3 + sqlite_store ~8 + migrate 2) − the deleted JSON-store test file's cases. Record the final number.

- [ ] **Verification gates recorded**
  - Trigram tokenizer: `python -c "from alpha.converse.sqlite_store import SqliteProjectStore as S; print(S.in_memory().tokenizer)"` → expect `trigram` on this runtime (sqlite 3.50.2); `unicode61` is the accepted fallback elsewhere.
  - No orphaned JSON-store import: `grep -rn "converse.store" --include="*.py" . | grep -v __pycache__ | grep -v sqlite_store` → expect no hits.

- [ ] **Adversarial review** (orchestration layer — see spec §6): an independent agent attempts to refute (a) the round-trip fidelity claim, (b) the `list()`-ordering / interface-identity claim, (c) FTS delete/update consistency, (d) the parity test's non-vacuity, (e) any leftover `ProjectStore` importer.

---

## Self-Review (plan vs spec)

- **Spec coverage:** D1 §3 → Tasks 1–2; D2 §4 (interface, schema, put/get/search, construction sites, replace+delete, migration, gates) → Tasks 3–7; D3 §2/§8-done-criteria → Tasks 8–9; testing §5 → per-task TDD + final suite; orchestration §6 → final adversarial-review hook. No spec section is unaddressed.
- **Placeholder scan:** every code/test step shows complete code; commands have expected output. The two "judgment" spots (license-name string in Task 1 Step 3; vendored method-name confirmation in Task 2 Step 2) include explicit verify-and-correct instructions rather than TODOs.
- **Type consistency:** `SqliteProjectStore.{in_memory, open, get, put, delete, list, search, close, tokenizer}` are used consistently across Tasks 3–7 and the migration test; `Project`/`ProjectTurn`/`StagedEdit`/`ChatMessage` field names match `alpha/converse/project.py` and `alpha/llm/chat.py` as read. `migrate_projects(json_dir, db_path) -> int` matches its test.
