# A1 Hygiene + Observability Floor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land DEVELOPMENT-PLAN §2 A1 — secret redaction at the persistence waists, a frozen Settings definition, the assembled-prompt audit record, episode inspector + harness digest, CHECKSUMS for captured PIT windows, `tcb.lock`, and the runbooks/activation-ledger docs.

**Architecture:** Two new low-level stdlib-only modules (`alpha/integrity.py`, `alpha/redact.py`) feed hooks at existing waists (`SqliteProjectStore.put`, `SessionStore.put`, `record_task_episode`, `capture_window`, `build_system_prompt`, `snapshot.py`). No new dependencies, no schema migrations; every change is additive/default-off or a pure single-definition collection.

**Tech Stack:** Python 3 / pydantic (frozen models are house style) / pytest (offline, no keys). Spec: `docs/superpowers/specs/2026-07-10-a1-hygiene-floor-design.md` (READ IT FIRST — it is the authority for every task below).

## Global Constraints

- Work on branch **`feat/a1-hygiene-floor`** (Task 1 creates it). Commit per task. No push.
- Full suite must stay green at every task boundary: `python -m pytest -q` (969 tests at branch point; offline, no keys).
- Zero diffs under `tests/loop/`, `tests/eval/` behavior (eval byte-neutrality; new optional fields must never be read by eval).
- Offline defaults byte-identical: no behavior change when no env is set and no new flag is passed.
- New modules `alpha/integrity.py` / `alpha/redact.py` / `alpha/settings.py` import NOTHING from `alpha.refine.{apply,credit,conflict}` or `alpha.memory.episodes` (lazy-import cycle edges), and nothing from `alpha/harness` except where a task names it.
- **Never scrub rollback-replay payloads**: `StagedEdit.op/preview`, `ProposedEdit` payloads stay verbatim even if they contain secret-looking strings.
- Never write anything under `/Users/pan/Desktop/self-evolve/Sonia-Kairos/`.
- Recon seam map (background reading if a seam surprises you): `/private/tmp/claude-501/-Users-pan-Desktop-self-evolve-evolving-alpha-us/fb17c108-87c3-46fc-af1f-570d7c932de0/tasks/w6qnn27rm.output`.

---

### Task 1: Branch + `alpha/integrity.py` (D5 — the one hashing utility)

**Files:**
- Create: `alpha/integrity.py`
- Modify: `alpha/meta/proposal_store.py` (delegate `canonical_json` digest primitives)
- Test: `tests/harness/test_integrity.py` (new)

**Interfaces:**
- Produces: `sha256_bytes(data: bytes) -> str`, `sha256_file(path) -> str`, `canonical_json(obj) -> str`, `sha256_canonical_json(obj) -> str` — consumed by Tasks 6, 8, 9.
- Constraint: `alpha/meta/proposal_store.py`'s public names (`canonical_json`, `brain_hash`) keep their exact signatures and behavior — existing tests pin them.

- [ ] **Step 1: Create the branch**

```bash
git checkout -b feat/a1-hygiene-floor
```

- [ ] **Step 2: Write the failing test**

```python
# tests/harness/test_integrity.py
"""alpha/integrity — the one hashing utility (kairos-mining §6 order-3)."""
import hashlib
from alpha.integrity import sha256_bytes, sha256_file, canonical_json, sha256_canonical_json


def test_sha256_bytes_matches_hashlib():
    assert sha256_bytes(b"abc") == hashlib.sha256(b"abc").hexdigest()


def test_sha256_file(tmp_path):
    p = tmp_path / "f.bin"
    p.write_bytes(b"hello world")
    assert sha256_file(p) == hashlib.sha256(b"hello world").hexdigest()


def test_canonical_json_is_order_insensitive():
    assert canonical_json({"b": 1, "a": [2, 3]}) == canonical_json({"a": [2, 3], "b": 1})
    assert canonical_json({"a": 1}) == '{"a":1}'


def test_sha256_canonical_json_stable():
    assert sha256_canonical_json({"x": 1}) == sha256_canonical_json({"x": 1})


def test_proposal_store_canonical_json_delegates():
    # the meta-layer canonicalizer and the integrity one must be THE SAME function
    from alpha.meta import proposal_store
    from alpha import integrity
    assert proposal_store.canonical_json is integrity.canonical_json
```

- [ ] **Step 3: Run to verify failure**

Run: `python -m pytest tests/harness/test_integrity.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.integrity'`.

- [ ] **Step 4: Implement `alpha/integrity.py`**

```python
# alpha/integrity.py
"""One hashing utility (kairos-mining §6 order-3): file-bytes + canonical-JSON sha256.

Stdlib-only and imports nothing from alpha — any layer (harness, data, meta, scripts)
may use it without cycle risk. canonical_json is THE one canonicalizer for content
hashing (moved here from alpha/meta/proposal_store.py, which re-exports it).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path | str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_canonical_json(obj) -> str:
    return sha256_bytes(canonical_json(obj).encode("utf-8"))
```

- [ ] **Step 5: Delegate in `alpha/meta/proposal_store.py`**

Read the file first. Replace its local `canonical_json` definition with
`from alpha.integrity import canonical_json` (keeping the name importable from
`proposal_store` — module-level import gives `proposal_store.canonical_json is
integrity.canonical_json`). If its `brain_hash` inlines `hashlib.sha256(...)`, rewrite the digest
line to use `sha256_canonical_json` / `sha256_bytes` from `alpha.integrity` with byte-identical
output. Do not change any signature.

- [ ] **Step 6: Run the new test + the pinned proposal-store tests**

Run: `python -m pytest tests/harness/test_integrity.py tests/meta -q`
Expected: ALL PASS.

- [ ] **Step 7: Commit**

```bash
git add alpha/integrity.py alpha/meta/proposal_store.py tests/harness/test_integrity.py
git commit -m "feat(a1): alpha/integrity — one hashing utility; proposal_store delegates"
```

---

### Task 2: `alpha/redact.py` (D1 core)

**Files:**
- Create: `alpha/redact.py`
- Test: `tests/harness/test_redact.py` (new)

**Interfaces:**
- Produces: `collect_secrets(env=None) -> dict[str, str]`, `redact(obj, secrets)` — consumed by Task 3.

- [ ] **Step 1: Write the failing tests**

```python
# tests/harness/test_redact.py
"""Value-based secret redaction (kairos-mining §1.5/§4.3): key/credential-scoped only."""
from alpha.redact import collect_secrets, redact


def test_collect_secrets_matches_name_pattern_and_length_floor():
    env = {
        "DEEPSEEK_API_KEY": "sk-aaaabbbbcccc",
        "MY_TOKEN": "tok-12345678",
        "SOME_PASSWORD": "hunter2hunter2",
        "SHORT_KEY": "abc",              # < 8 chars: never collected
        "PLAIN_VAR": "not-a-secret-var", # name doesn't match: never collected
    }
    s = collect_secrets(env)
    assert set(s) == {"DEEPSEEK_API_KEY", "MY_TOKEN", "SOME_PASSWORD"}


def test_redact_replaces_values_recursively():
    secrets = {"APCA_API_SECRET_KEY": "supersecretvalue"}
    obj = {
        "stdout": "APCA_API_SECRET_KEY=supersecretvalue\nPATH=/usr/bin",
        "nested": [{"text": "prefix supersecretvalue suffix"}, 42, None],
    }
    out = redact(obj, secrets)
    assert "supersecretvalue" not in str(out)
    assert out["stdout"] == "APCA_API_SECRET_KEY=[REDACTED:APCA_API_SECRET_KEY]\nPATH=/usr/bin"
    assert out["nested"][0]["text"] == "prefix [REDACTED:APCA_API_SECRET_KEY] suffix"
    assert out["nested"][1] == 42 and out["nested"][2] is None


def test_redact_no_secrets_is_identity():
    obj = {"a": ["x", {"b": "y"}]}
    assert redact(obj, {}) == obj
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/harness/test_redact.py -v`
Expected: FAIL — no module `alpha.redact`.

- [ ] **Step 3: Implement `alpha/redact.py`**

```python
# alpha/redact.py
"""Value-based secret redaction for the persistence waists (kairos-mining §1.5/§4.3).

Key/credential-scoped ONLY: collect the VALUES of env vars whose NAME matches
KEY|SECRET|TOKEN|PASSWORD (>= 8 chars), replace occurrences inside persisted strings
with [REDACTED:<VAR>]. Never pattern-guesses content, never touches market/PIT data;
callers must not route rollback-replay payloads (StagedEdit.op/preview, ProposedEdit)
through it. Ordering invariant for the future integrity chain (A4): redact BEFORE hash.
Stdlib-only, imports nothing from alpha.
"""
from __future__ import annotations

import os
import re

_NAME_RE = re.compile(r"KEY|SECRET|TOKEN|PASSWORD", re.IGNORECASE)
_MIN_LEN = 8


def collect_secrets(env=None) -> dict[str, str]:
    env = os.environ if env is None else env
    return {n: v for n, v in env.items() if _NAME_RE.search(n) and len(v) >= _MIN_LEN}


def redact(obj, secrets: dict[str, str]):
    if isinstance(obj, str):
        for name, value in secrets.items():
            if value in obj:
                obj = obj.replace(value, f"[REDACTED:{name}]")
        return obj
    if isinstance(obj, dict):
        return {k: redact(v, secrets) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(v, secrets) for v in obj]
    return obj
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/harness/test_redact.py -v` → ALL PASS.

- [ ] **Step 5: Commit**

```bash
git add alpha/redact.py tests/harness/test_redact.py
git commit -m "feat(a1): alpha/redact — value-based secret redaction primitive"
```

---

### Task 3: Redact hooks at the three waists (D1)

**Files:**
- Modify: `alpha/converse/sqlite_store.py` (`put`, ~lines 63–79), `alpha/meta/store.py` (`SessionStore.put`, ~lines 111–114), `alpha/arena/experience.py` (`_task_reflection` error copy, ~lines 93–94)
- Test: `tests/converse/test_redact_store.py`, `tests/sonia/test_redact_sessions.py`, `tests/arena/test_experience.py` (append)

**Interfaces:**
- Consumes: Task 2's `collect_secrets`/`redact`.
- Behavior contract: redaction happens on the DUMPED dicts at write time; in-memory model objects are never mutated; `staged_edits` / `Message.edits` (ProposedEdit) are NEVER routed through redact.

- [ ] **Step 1: Write the failing tests**

```python
# tests/converse/test_redact_store.py
"""D1 leak regression: secrets never reach the converse DB — BOTH channels
(turns JSON tool_calls AND the duplicated [tool:...] message text + FTS)."""
from alpha.converse.project import Project, ProjectTurn, StagedEdit
from alpha.converse.sqlite_store import SqliteProjectStore
from alpha.llm.chat import ChatMessage

SECRET = "sk-planted-secret-value-123"


def _project():
    return Project(
        project_id="p1", created_at="2026-07-10T00:00:00Z", title="t",
        messages=[ChatMessage(role="user", text=f"[tool:shell result]\nDEEPSEEK_API_KEY={SECRET}")],
        turns=[ProjectTurn(turn_id="t1", user_text="run env",
                           tool_calls=[{"tool": "shell", "args": {"cmd": "env"},
                                        "result": {"ok": True, "stdout": f"DEEPSEEK_API_KEY={SECRET}",
                                                   "stderr": "", "exit_code": 0}}],
                           created_at="2026-07-10T00:00:00Z")],
        staged_edits=[StagedEdit(edit_id="e1", op={"tool": "process_memory",
                                                   "args": {"lesson": SECRET}, "rationale": "r"},
                                 summary="s", valid=True, reason=None, preview={})],
    )


def test_secret_never_reaches_db_but_replay_payload_survives(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", SECRET)
    db = tmp_path / "state.db"
    store = SqliteProjectStore.open(db)
    store.put(_project())
    raw = db.read_bytes().decode("utf-8", errors="ignore")
    # both persisted channels are clean, marker present (non-vacuous)
    assert "[REDACTED:DEEPSEEK_API_KEY]" in raw
    # the ONLY allowed occurrences of the secret are the never-scrub replay payload
    got = store.get("p1")
    assert SECRET not in got.messages[0].text
    assert SECRET not in str(got.turns[0].tool_calls)
    assert got.staged_edits[0].op["args"]["lesson"] == SECRET   # replay payload verbatim


def test_search_index_is_clean(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", SECRET)
    store = SqliteProjectStore.open(tmp_path / "state.db")
    store.put(_project())
    assert store.search(SECRET) == []           # FTS never indexed the raw secret
```

```python
# tests/sonia/test_redact_sessions.py
"""D1: sonia session persistence redacts pasted secrets; ProposedEdit payloads survive."""
from alpha.meta.models import Session, Message, Attachment
from alpha.meta.store import SessionStore

SECRET = "tok-pasted-secret-99999"


def test_session_put_redacts_text_and_attachments(tmp_path, monkeypatch):
    monkeypatch.setenv("PASTED_TOKEN", SECRET)
    store = SessionStore(root=tmp_path)
    s = Session(session_id="s1", created_at="2026-07-10T00:00:00Z", title="t",
                messages=[Message(message_id="m1", role="user", created_at="c",
                                  text=f"my key is {SECRET}",
                                  attachments=[Attachment(kind="file", name="f", mime="text/plain",
                                                          text=f"body {SECRET}")])])
    p = store.put(s)
    raw = p.read_text()
    assert SECRET not in raw and "[REDACTED:PASTED_TOKEN]" in raw
```

Append to `tests/arena/test_experience.py` (match its existing fixtures/helpers when writing the
real test — the shape below states the contract):

```python
def test_task_reflection_error_strings_are_redacted(monkeypatch):
    monkeypatch.setenv("LEAKY_API_KEY", "leaked-value-42xyz")
    # build a res whose tool result carries {"error": "RuntimeError: leaked-value-42xyz"}
    # via the file's existing ConversationResult/record_task_episode helpers, then:
    #   ep = record_task_episode(...)
    #   assert "leaked-value-42xyz" not in ep.reflection_text
    #   assert "[REDACTED:LEAKY_API_KEY]" in ep.reflection_text
```

Adjust constructor kwargs to the real models (Read the model files first: `StagedEdit` requires
whatever fields its pydantic model requires — fill them with minimal valid values; same for
`Message`/`Attachment`/`SessionStore(root=...)` signature).

- [ ] **Step 2: Run to verify failures** (secrets currently persist verbatim)

Run: `python -m pytest tests/converse/test_redact_store.py tests/sonia/test_redact_sessions.py -v`
Expected: FAIL on the `SECRET not in` assertions.

- [ ] **Step 3: Implement the three hooks**

In `alpha/converse/sqlite_store.py::put`: at the top, `from alpha.redact import collect_secrets,
redact` (module-level import is fine — stdlib-only module); compute `secrets =
collect_secrets()` once; dump turns as today, then `turns_dumped = redact(turns_dumped, secrets)`;
redact each message text before the `messages`/`messages_fts` inserts. Do NOT touch the
`staged_edits` dump. In `alpha/meta/store.py::SessionStore.put`: switch from
`session.model_dump_json()` to `d = session.model_dump(mode="json")`; for each message in
`d["messages"]`: redact `m["text"]` and every `att["text"]`; redact `d["notes"]` if present;
leave `m["edits"]` and every other field untouched; then `json.dumps(d)` through the existing
`_atomic_write`. In `alpha/arena/experience.py`: where `entry["error"] = result["error"]` copies
the exception string, wrap it: `entry["error"] = redact(result["error"], collect_secrets())`.

- [ ] **Step 4: Run the new tests + the touched packages**

Run: `python -m pytest tests/converse tests/sonia tests/arena tests/workbench -q`
Expected: ALL PASS (existing store round-trip tests confirm no shape drift).

- [ ] **Step 5: Commit**

```bash
git add alpha/converse/sqlite_store.py alpha/meta/store.py alpha/arena/experience.py \
        tests/converse/test_redact_store.py tests/sonia/test_redact_sessions.py tests/arena/test_experience.py
git commit -m "feat(a1): redact() at the three persistence waists — verified leak closed"
```

---

### Task 4: `alpha/settings.py` + script freeze-once adoption (D2a)

**Files:**
- Create: `alpha/settings.py`
- Modify: `scripts/refine_live.py`, `scripts/evolve_from_episodes.py`, `scripts/save_decisions.py`, `scripts/migrate_projects_to_sqlite.py` (env reads → `Settings.from_env()` once in `main()`)
- Test: `tests/harness/test_settings.py` (new)

**Interfaces:**
- Produces: `Settings` (frozen pydantic, `extra="forbid"`), `Settings.from_env(env=None)`, module constant `EVOLUTION_EPISODES_DB_DEFAULT = "./state/brain.db"`. Consumed by Task 5.
- MUST NOT centralize: `ALPHA_UNSAFE_AUTONOMOUS` (deliberate duplicated friction), secrets (APCA/DEEPSEEK/ANTHROPIC), `alpha/llm/config.py` role reads, `__main__` host/port.

- [ ] **Step 1: Write the failing tests**

```python
# tests/harness/test_settings.py
"""D2: alpha/settings — THE single definition of app-layer env names + defaults."""
import pytest
from alpha.settings import Settings, EVOLUTION_EPISODES_DB_DEFAULT


def test_defaults_match_todays_literals():
    s = Settings()
    assert s.live_brain_dir == "./state/brain"
    assert s.sessions_dir == "./state/sessions"
    assert s.projects_db == "./state/projects/state.db"
    assert s.conflicts_dir == "./state/conflicts"
    assert s.proposals_dir == "./state/proposals"
    assert s.workspace_dir == "./state/workspaces"
    assert s.data_source == "alpaca" and s.data_feed == "iex"
    assert s.sonia_url == "http://127.0.0.1:8810"
    assert s.workbench_url == "http://127.0.0.1:8820"
    # asymmetric no-defaults are load-bearing (unset -> seeds / SAMPLE / no episode store)
    assert s.web_live_brain_dir is None and s.episodes_db is None
    assert s.web_decision is None and s.web_decisions_dir is None
    assert s.web_verdict is None and s.web_verdicts_dir is None and s.web_evolution is None
    assert s.pit_root is None
    assert EVOLUTION_EPISODES_DB_DEFAULT == "./state/brain.db"


def test_from_env_overrides_and_ignores_unrelated(monkeypatch):
    monkeypatch.setenv("ALPHA_LIVE_BRAIN_DIR", "/tmp/b")
    monkeypatch.setenv("TOTALLY_UNRELATED", "x")
    s = Settings.from_env()
    assert s.live_brain_dir == "/tmp/b"


def test_frozen_and_forbid():
    s = Settings()
    with pytest.raises(Exception):
        s.live_brain_dir = "/x"          # frozen
    with pytest.raises(Exception):
        Settings(unknown_field="x")      # extra="forbid"
```

- [ ] **Step 2: Run to verify failure** → `ModuleNotFoundError: alpha.settings`.

- [ ] **Step 3: Implement `alpha/settings.py`**

```python
# alpha/settings.py
"""Frozen app-layer settings: THE single definition of env names + defaults (mining §2.7).

Consumption tiers: producer scripts construct Settings.from_env() ONCE in main() and
thread values down; services construct per call inside their store/client helpers —
that per-call timing is load-bearing (tests/web's module-scoped client and the autouse
brain_session_isolation fixture set env AFTER app creation); a boot-time freeze is
deferred until the fixture strategy changes.

Exemptions (deliberate): secrets (APCA_*/DEEPSEEK_*/ANTHROPIC_*) stay at client/source
construction with their lazy RuntimeError-naming-the-var behavior — the offline suite
needs no keys; alpha/llm/config.py's per-role reads stay put (already a central point);
ALPHA_UNSAFE_AUTONOMOUS stays duplicated in the two evolution scripts (the friction is
the point); __main__ host/port uvicorn args stay inline.

Co-flip couplings: the five brain-state dirs (live_brain_dir/sessions_dir/projects_db/
conflicts_dir/proposals_dir) move together — the cross-face reconcile sweep opens the
OTHER face's stores (see tests/conftest.py::brain_session_isolation); workspace_dir ×
live_brain_dir feed the workbench boot assert and must resolve the same way its stores do.
"""
from __future__ import annotations

import os
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

# the evolution scripts' default episodes DB (save_decisions deliberately has NO default)
EVOLUTION_EPISODES_DB_DEFAULT = "./state/brain.db"


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    live_brain_dir: str = "./state/brain"
    sessions_dir: str = "./state/sessions"
    projects_db: str = "./state/projects/state.db"
    conflicts_dir: str = "./state/conflicts"
    proposals_dir: str = "./state/proposals"
    workspace_dir: str = "./state/workspaces"
    episodes_db: str | None = None
    sonia_url: str = "http://127.0.0.1:8810"
    workbench_url: str = "http://127.0.0.1:8820"
    data_source: str = "alpaca"
    pit_root: str | None = None
    data_feed: str = "iex"
    # alpha_web: absence is load-bearing (None -> frozen seeds / badged SAMPLE)
    web_live_brain_dir: str | None = None
    web_decision: str | None = None
    web_decisions_dir: str | None = None
    web_verdict: str | None = None
    web_verdicts_dir: str | None = None
    web_evolution: str | None = None

    _ENV: ClassVar[dict[str, str]] = {
        "live_brain_dir": "ALPHA_LIVE_BRAIN_DIR",
        "sessions_dir": "ALPHA_SESSIONS_DIR",
        "projects_db": "ALPHA_PROJECTS_DB",
        "conflicts_dir": "ALPHA_CONFLICTS_DIR",
        "proposals_dir": "ALPHA_PROPOSALS_DIR",
        "workspace_dir": "ALPHA_WORKSPACE_DIR",
        "episodes_db": "ALPHA_EPISODES_DB",
        "sonia_url": "ALPHA_SONIA_URL",
        "workbench_url": "ALPHA_WORKBENCH_URL",
        "data_source": "ALPHA_DATA_SOURCE",
        "pit_root": "ALPHA_PIT_ROOT",
        "data_feed": "ALPHA_DATA_FEED",
        "web_live_brain_dir": "ALPHA_LIVE_BRAIN_DIR",
        "web_decision": "ALPHA_WEB_DECISION",
        "web_decisions_dir": "ALPHA_WEB_DECISIONS_DIR",
        "web_verdict": "ALPHA_WEB_VERDICT",
        "web_verdicts_dir": "ALPHA_WEB_VERDICTS_DIR",
        "web_evolution": "ALPHA_WEB_EVOLUTION",
    }

    @classmethod
    def from_env(cls, env=None) -> "Settings":
        env = os.environ if env is None else env
        return cls(**{f: env[v] for f, v in cls._ENV.items() if v in env})
```

- [ ] **Step 4: Adopt in the four scripts** (freeze-once; behavior identical)

In each `main()`: `s = Settings.from_env()` once, then replace the inline env reads:
`refine_live.py` — brain/conflicts dirs via `s.live_brain_dir`/`s.conflicts_dir`, episodes via
`s.episodes_db or EVOLUTION_EPISODES_DB_DEFAULT`; same in `evolve_from_episodes.py`
(`ALPHA_UNSAFE_AUTONOMOUS` reads stay EXACTLY as they are); `save_decisions.py` — the `--brain`
fallback becomes `s.episodes_db` (no default — unchanged semantics);
`migrate_projects_to_sqlite.py` — `s.projects_db` (keep its `ALPHA_PROJECTS_DIR` read inline —
it is a one-off migration knob, not app config).

- [ ] **Step 5: Run** `python -m pytest tests/harness/test_settings.py tests/scripts -q` → ALL PASS.

- [ ] **Step 6: Commit**

```bash
git add alpha/settings.py scripts/refine_live.py scripts/evolve_from_episodes.py \
        scripts/save_decisions.py scripts/migrate_projects_to_sqlite.py tests/harness/test_settings.py
git commit -m "feat(a1): frozen Settings — single definition; scripts freeze-once"
```

---

### Task 5: Services adopt Settings (D2b — single definition, per-call resolution)

**Files:**
- Modify: `sonia/app.py` (helpers at ~:32/:36/:40/:63/:289), `workbench/app.py` (~:41/:45/:51/:56/:201), `alpha_web/data_access.py` (~:54), `alpha_web/app.py` (~:120/:128/:162/:170/:190), `alpha_web/sonia_client.py` (~:18), `alpha_web/workbench_client.py` (~:18)
- Test: none new — the ENTIRE existing suite is the regression (zero test edits allowed)

**Interfaces:**
- Consumes: `Settings.from_env()` from Task 4.
- Contract: every helper keeps its per-call construction timing; only the env-name/default
  literals move into Settings. The workbench boot assert keeps firing in `create_app()` and keeps
  reading the SAME values the stores resolve.

- [ ] **Step 1: Mechanical replacement, one service at a time**

Pattern (example, `sonia/app.py`):
```python
from alpha.settings import Settings

def _brain_store() -> LiveBrainStore:
    return LiveBrainStore(Path(Settings.from_env().live_brain_dir))
```
Apply to every helper the recon names: sonia `_brain_store`/`_session_store`/`_conflict_store`/
`_reconcile_all`(projects_db)/`_history_dir`; workbench `_project_store`/`_workspace`/
`_brain_dir`/`_assert_brain_outside_workspace`/reconcile-route sessions dir; alpha_web
`_live_store` (uses `web_live_brain_dir` — the no-default field), the five `ALPHA_WEB_*` context
readers, and the two HTTP clients' base-url fallbacks (`sonia_url`/`workbench_url`).

- [ ] **Step 2: Run the full suite** — this is the task's whole verification

Run: `python -m pytest -q`
Expected: ALL PASS, zero test edits. Then: `grep -rn "\./state/brain\b" sonia/ workbench/ alpha_web/ scripts/ alpha/ --include="*.py" | grep -v settings.py` → no production hits (the literal lives once, in `alpha/settings.py`).

- [ ] **Step 3: Commit**

```bash
git add sonia/app.py workbench/app.py alpha_web/data_access.py alpha_web/app.py \
        alpha_web/sonia_client.py alpha_web/workbench_client.py
git commit -m "feat(a1): services read env through Settings — one definition, per-call timing preserved"
```

---

### Task 6: Prompt audit collect hook + sidecar + `render_prompt.py` (D3)

**Files:**
- Modify: `alpha/agent/prompt.py` (`build_system_prompt`, ~:69), `scripts/save_decisions.py`
- Create: `scripts/render_prompt.py`
- Test: `tests/agent/test_prompt_collect.py` (new), `tests/scripts/test_render_prompt.py` (new)

**Interfaces:**
- Produces: `build_system_prompt(..., collect: "Callable[[dict], None] | None" = None)`; sidecar
  file `<decisions_dir>/<date>.prompt.json` = `{"date": ..., "records": [...], "assembled": ...}`;
  record shape `{"kind": "skill|lesson|episode", "id": ..., "status": "offered|dropped", "reason": ...}`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/agent/test_prompt_collect.py
"""D3: the collect hook observes offered/dropped; default None is byte-identical."""
from alpha.agent.prompt import build_system_prompt


def _h_with_content():
    # build a HarnessState via the seeds or the tests' existing helpers (mirror
    # tests/agent's existing prompt tests' setup — Read them first) containing at
    # least one skill that passes and one element that gets dropped (e.g. a skill
    # whose depends_on names an unavailable signal).
    ...


def test_collect_none_is_byte_identical():
    h = _h_with_content()
    assert build_system_prompt(h) == build_system_prompt(h, collect=None)


def test_collector_sees_offered_and_dropped_with_reasons():
    h = _h_with_content()
    records = []
    out = build_system_prompt(h, collect=records.append)
    assert out == build_system_prompt(h)                      # hook never changes output
    statuses = {r["status"] for r in records if "status" in r}
    assert {"offered", "dropped"} <= statuses
    dropped = [r for r in records if r.get("status") == "dropped"]
    assert all(r.get("reason") for r in dropped)              # every drop names its reason
    assert any(r.get("kind") == "assembled" for r in records) # final text captured
```

(Fill `_h_with_content()` by mirroring the existing `tests/agent` prompt-test fixtures — Read
those files first; the drop case uses `available_signals` exclusion, which the recon confirms is
a real silent-drop point.)

```python
# tests/scripts/test_render_prompt.py
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import render_prompt


def test_render_prompt_prints_sidecar(tmp_path, capsys):
    side = {"date": "2026-01-05", "assembled": "SYSTEM PROMPT TEXT",
            "records": [{"kind": "skill", "id": "s1", "status": "offered"},
                        {"kind": "lesson", "id": "m1", "status": "dropped", "reason": "budget-cut"}]}
    (tmp_path / "2026-01-05.prompt.json").write_text(json.dumps(side))
    render_prompt.main([str(tmp_path), "2026-01-05"])
    out = capsys.readouterr().out
    assert "SYSTEM PROMPT TEXT" in out and "budget-cut" in out and "s1" in out
```

- [ ] **Step 2: RED** — `collect` kwarg unknown / no module `render_prompt`.

- [ ] **Step 3: Implement**

`build_system_prompt` gains `collect=None`; at each existing drop/offer decision point emit one
record via `if collect is not None: collect({...})` (reasons: `depends_on-unmet`, `budget-cut`,
`weight-cut`, plus any other existing silent-drop branch the file shows); after assembly emit
`{"kind": "assembled", "text": <prompt>}`. NO other logic change — the hook only observes.
`save_decisions.py`: build `records: list` + pass `collect=records.append` down to its prompt
call (thread through whatever seam its decide path exposes — Read the call chain first; if the
prompt is built inside a policy/agent layer, add the same optional pass-through kwarg there,
default None), then write the sidecar JSON next to the day's decision file.
`scripts/render_prompt.py`: `main(argv=None)` with `(decisions_dir, date)` args; loads
`<dir>/<date>.prompt.json`; prints assembled text then an offered/dropped table.
Also EXTEND the existing `save_decisions` script test (find it under `tests/scripts/` — it runs
the producer with MockLLMClient factories): after the run, assert `<date>.prompt.json` exists in
the store dir and contains a non-empty `records` list (pins the sidecar write end-to-end).

- [ ] **Step 4: Run** `python -m pytest tests/agent tests/scripts tests/eval tests/loop -q` → ALL PASS (eval byte-neutral).

- [ ] **Step 5: Commit**

```bash
git add alpha/agent/prompt.py scripts/save_decisions.py scripts/render_prompt.py \
        tests/agent/test_prompt_collect.py tests/scripts/test_render_prompt.py
git commit -m "feat(a1): assembled-prompt audit — collect hook, sidecar, render_prompt"
```

---

### Task 7: `harness_digest` + episode inspector (D4)

**Files:**
- Modify: `alpha/harness/snapshot.py` (add `harness_digest`), the `DecisionPackage` model file (locate via `grep -rn "class DecisionPackage" alpha/`), `scripts/save_decisions.py` (populate)
- Create: `scripts/inspect_episodes.py`
- Test: `tests/harness/test_harness_digest.py`, `tests/scripts/test_inspect_episodes.py` (new)

- [ ] **Step 1: Write the failing tests**

```python
# tests/harness/test_harness_digest.py
"""D4: canonical sha256 of HarnessState; optional h_digest on DecisionPackage; eval never reads it."""
from alpha.harness.snapshot import harness_digest


def test_digest_stable_and_content_sensitive(...):
    # build two HarnessStates via existing test helpers (mirror tests/harness fixtures):
    # equal content -> equal digest; mutate one lesson -> digest changes; 64 hex chars.
    ...


def test_decision_package_h_digest_optional_and_eval_neutral():
    # DecisionPackage() without h_digest still validates (default None) — additive field;
    # grep-level neutrality is pinned in Step 3.
    ...
```

```python
# tests/scripts/test_inspect_episodes.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import inspect_episodes


def test_inspector_prints_the_same_numbers_the_veto_uses(tmp_path, capsys):
    # seed an EpisodeStore (mirror tests/memory's store fixtures) with a few episodes,
    # run inspect_episodes.main([db, asof]), and assert the printed summary numbers
    # EQUAL alpha.memory.aggregate.summarize(...)'s output for the same inputs
    # (import and call it in the test — same source, no re-derivation).
    ...
```

Complete the `...` bodies by mirroring the named existing fixtures (Read them first); each test
must assert real values, never just "runs without error" (no vacuous pass).

- [ ] **Step 2: RED.**

- [ ] **Step 3: Implement**

`alpha/harness/snapshot.py`:
```python
from alpha.integrity import sha256_canonical_json

def harness_digest(h) -> str:
    """Canonical content digest of a HarnessState (feeds A10's joint rollback; eval never reads it)."""
    return sha256_canonical_json(h.to_dict())
```
`DecisionPackage`: add `h_digest: str | None = None`. `save_decisions.py`: populate it at
package-build time. Then verify eval neutrality mechanically:
`grep -rn "h_digest" alpha/eval alpha/loop` → zero hits.
`scripts/inspect_episodes.py`: argparse `(db, asof, --symbol)`; `EpisodeStore.open(db)`,
`for_asof(...)`, print rows + `summarize()` + `is_episode_taboo()` outputs imported from their
production homes.

- [ ] **Step 4: Run** `python -m pytest tests/harness tests/scripts tests/eval tests/loop tests/memory -q` → ALL PASS.

- [ ] **Step 5: Commit**

```bash
git add alpha/harness/snapshot.py scripts/inspect_episodes.py scripts/save_decisions.py \
        tests/harness/test_harness_digest.py tests/scripts/test_inspect_episodes.py $(grep -rln "class DecisionPackage" alpha/)
git commit -m "feat(a1): harness_digest + read-only episode inspector"
```

---

### Task 8: CHECKSUMS write + verify (D6)

**Files:**
- Modify: `alpha/data/capture.py` (`capture_window` writes the manifest), `scripts/run_verdict.py`, `scripts/save_decisions.py`, `scripts/refine_live.py` (fail-closed), `scripts/save_evolution.py`, `scripts/scan_tradeable.py` (warn)
- Create: `alpha/data/integrity_check.py`
- Test: `tests/data/test_checksums.py` (new)

**Interfaces:**
- Produces: `write_checksums(root: Path) -> Path` (in capture.py or integrity_check.py),
  `verify_checksums(root: Path, *, fail_closed: bool) -> list[str]` (returns human-readable
  problem strings; raises `RuntimeError("\n".join(problems))` when `fail_closed` and problems
  exist; a MISSING manifest prints a warning and returns `[]` in both postures).
- Manifest format: `CHECKSUMS` at pit root, lines `"{sha256}  {posix-relpath}"` sorted by
  relpath, covering every regular file under root EXCEPT `CHECKSUMS` itself.

- [ ] **Step 1: Write the failing tests**

```python
# tests/data/test_checksums.py
"""D6: capture writes CHECKSUMS; verify is typed; fail-closed vs warn; missing manifest warns."""
import pytest
from pathlib import Path
from alpha.data.capture import capture_window
from alpha.data.pit import PITStore          # adjust import to the real PITStore home
from alpha.data.integrity_check import verify_checksums


def _captured_root(tmp_path, fake_source):
    root = tmp_path / "win"
    capture_window(fake_source, PITStore(root), "2026-06-01", "2026-06-03", ["AAPL", "MSFT"])
    return root


def test_capture_writes_manifest_covering_every_file(tmp_path, fake_source):
    root = _captured_root(tmp_path, fake_source)
    manifest = root / "CHECKSUMS"
    assert manifest.exists()
    listed = {line.split(maxsplit=1)[1] for line in manifest.read_text().splitlines() if line}
    on_disk = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()} - {"CHECKSUMS"}
    assert listed == on_disk and len(listed) > 0        # non-vacuous


def test_clean_window_verifies_in_both_postures(tmp_path, fake_source):
    root = _captured_root(tmp_path, fake_source)
    assert verify_checksums(root, fail_closed=True) == []
    assert verify_checksums(root, fail_closed=False) == []


def test_tampered_file_fails_closed_with_typed_message(tmp_path, fake_source):
    root = _captured_root(tmp_path, fake_source)
    victim = next(p for p in root.rglob("*.parquet"))
    victim.write_bytes(victim.read_bytes() + b"x")
    with pytest.raises(RuntimeError, match="mismatch"):
        verify_checksums(root, fail_closed=True)
    problems = verify_checksums(root, fail_closed=False)     # warn posture: returned, not raised
    assert any("mismatch" in p and victim.name in p for p in problems)


def test_missing_and_extra_files_are_typed(tmp_path, fake_source):
    root = _captured_root(tmp_path, fake_source)
    (root / "stray.txt").write_text("x")
    next(iter(root.rglob("*.parquet"))).unlink()
    problems = verify_checksums(root, fail_closed=False)
    assert any(p.startswith("missing:") for p in problems)
    assert any(p.startswith("extra:") for p in problems)


def test_manifestless_window_warns_never_raises(tmp_path, fake_source, capsys):
    root = _captured_root(tmp_path, fake_source)
    (root / "CHECKSUMS").unlink()
    assert verify_checksums(root, fail_closed=True) == []
    assert "no CHECKSUMS" in capsys.readouterr().out
```

(Use the existing `fake_source` fixture from `tests/conftest.py`; fix the PITStore import to its
real home — `grep -rn "class PITStore" alpha/data/`.)

- [ ] **Step 2: RED.**

- [ ] **Step 3: Implement**

`alpha/data/integrity_check.py` (uses `alpha.integrity.sha256_file`): `write_checksums(root)`
walks `root.rglob("*")`, skips `CHECKSUMS`, writes sorted `"{digest}  {relpath}"` lines;
`verify_checksums(root, *, fail_closed)`: missing manifest → print
`f"warning: no CHECKSUMS in {root} — pre-manifest window (re-capture to pin it)"`, return `[]`;
otherwise compare → problems typed `mismatch: <rel>`, `missing: <rel>`, `extra: <rel>`;
`fail_closed and problems` → raise `RuntimeError("\n".join(problems))`; else print each as
`warning: ...` and return them. `capture.py::capture_window` calls `write_checksums(root)` last
and the capture CLI prints `f"CHECKSUMS written — commit it: git add -f {root}/CHECKSUMS"`.
Wire the five script mains right after each constructs `PITStore(root)`: fail-closed →
`run_verdict.py`, `save_decisions.py`, `refine_live.py`; warn → `save_evolution.py`,
`scan_tradeable.py`. (The registry path `make_source("snapshot")` is deliberately NOT wired —
recorded limit, spec D6.)

- [ ] **Step 4: Run** `python -m pytest tests/data tests/scripts -q` → ALL PASS (the existing
manifest-less tmp-store tests keep passing because verification lives in script mains, and a
missing manifest only warns).

- [ ] **Step 5: Commit**

```bash
git add alpha/data/integrity_check.py alpha/data/capture.py scripts/run_verdict.py \
        scripts/save_decisions.py scripts/refine_live.py scripts/save_evolution.py \
        scripts/scan_tradeable.py tests/data/test_checksums.py
git commit -m "feat(a1): CHECKSUMS manifest — capture writes, consumers verify (fail-closed/warn)"
```

---

### Task 9: `tcb.lock` (D7a)

**Files:**
- Create: `scripts/gen_tcb_lock.py`, `tcb.lock` (generated + committed), `tests/test_tcb_lock.py`

**Interfaces:**
- Manifest set (spec D7 — corrected §3 rows + the two human-approved additions):

```python
TCB_FILES = [
    "alpha/refine/apply.py",        # the gate (try_apply_op) — one-write-waist
    "alpha/refine/ops.py",          # PASS_TOOLS whitelist / RefineOp vocabulary
    "alpha/refine/conflict.py",     # two-loop conflict -> held_for_review
    "alpha/harness/metatools.py",   # the only edit facade; rationale floor
    "alpha/harness/edit_log.py",    # append-only audit + provenance stamping
    "alpha/harness/snapshot.py",    # atomic checkpoint (the version authority)
    "alpha/harness/manager.py",     # rollback + handle rebinding
    "alpha/harness/doctrine.py",    # red-line immutability
    "alpha/loop/floor_breaker.py",  # capability-floor breaker
    "alpha/data/firewall.py",       # PIT firewall (AsOfGuard/GuardedSource)
    "alpha/memory/store.py",        # recall PIT-mask: for_asof (spec §3 row 11, corrected)
    "alpha/agent/retrieval.py",     # recall PIT-mask: select_for_prompt (row 11, corrected)
    "alpha/arena/policy.py",        # single dispatch choke point + tiers
    "alpha/meta/evolution.py",      # adopt-time red-line/prefix validation (added 2026-07-10, user-approved)
    "alpha/meta/proposal_store.py", # brain_hash staleness pin (added 2026-07-10, user-approved)
]
# Deliberately excluded: alpha/guard/ (spec §3's own choice), alpha/refine/credit.py +
# alpha/arena/experience.py (observation channel), alpha/meta/store.py (locks are ops).
# Row 13 (red-line lint / try_promote_body / verifier harness): declared-but-absent, body phase.
```

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tcb_lock.py
"""tcb.lock drift gate (modification-ladder §3: 'defining the manifest is a NOW deliverable').

REGEN RITUAL: a legitimate TCB edit re-runs `python scripts/gen_tcb_lock.py` and commits
the updated tcb.lock IN THE SAME CHANGE — this test staying red is the reminder.
Additions to TCB_FILES are highest-approval, human-only (spec §3 red-line rule).
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import gen_tcb_lock


def test_manifest_is_non_empty_and_complete():
    entries = gen_tcb_lock.read_lock(REPO / "tcb.lock")
    assert len(entries) >= 15                              # non-vacuous
    assert set(entries) == set(gen_tcb_lock.TCB_FILES)     # lockfile matches the declared set


def test_every_tcb_file_exists_and_matches():
    problems = gen_tcb_lock.check(REPO)
    assert problems == [], "TCB drift — re-run scripts/gen_tcb_lock.py in the same change:\n" + "\n".join(problems)
```

- [ ] **Step 2: RED** (no script, no lockfile).

- [ ] **Step 3: Implement `scripts/gen_tcb_lock.py`**

```python
#!/usr/bin/env python3
"""Generate/check tcb.lock — content hashes of the TCB file set (modification-ladder §3).

Usage: python scripts/gen_tcb_lock.py [--check]
The manifest set is TCB_FILES below; ADDITIONS ARE HUMAN-ONLY (the list is a red-line).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from alpha.integrity import sha256_file

TCB_FILES = [ ... ]  # exactly the 15-entry list from Interfaces above, comments included

def generate(repo: Path) -> str:
    lines = [f"{sha256_file(repo / f)}  {f}" for f in sorted(TCB_FILES)]
    header = ("# tcb.lock — TCB content hashes (modification-ladder spec §3; additions human-only)\n"
              "# Row 13 (red-line lint / try_promote_body / verifier harness): declared, not yet built.\n"
              "# alpha/meta/{evolution,proposal_store}.py added 2026-07-10 (user-approved, backend-design round).\n")
    return header + "\n".join(lines) + "\n"

def read_lock(path: Path) -> dict[str, str]:
    out = {}
    for line in path.read_text().splitlines():
        if line and not line.startswith("#"):
            digest, name = line.split(maxsplit=1)
            out[name] = digest
    return out

def check(repo: Path) -> list[str]:
    lock = read_lock(repo / "tcb.lock")
    problems = [f"listed-but-absent: {f}" for f in lock if not (repo / f).exists()]
    problems += [f"unlisted: {f}" for f in TCB_FILES if f not in lock]
    problems += [f"drift: {f}" for f, d in lock.items()
                 if (repo / f).exists() and sha256_file(repo / f) != d]
    return problems

def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    repo = Path(__file__).resolve().parents[1]
    if "--check" in argv:
        problems = check(repo)
        for p in problems: print(p)
        return 1 if problems else 0
    (repo / "tcb.lock").write_text(generate(repo))
    print("tcb.lock written")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

Run `python scripts/gen_tcb_lock.py` to produce `tcb.lock`.

- [ ] **Step 4: GREEN** `python -m pytest tests/test_tcb_lock.py -v` → ALL PASS.

- [ ] **Step 5: Commit** (lockfile included — it is a tracked artifact)

```bash
git add scripts/gen_tcb_lock.py tcb.lock tests/test_tcb_lock.py
git commit -m "feat(a1): tcb.lock — TCB manifest + drift gate (regen ritual documented)"
```

---

### Task 10: Runbooks + activation ledger + doc ripples (D7b)

**Files:**
- Create: `docs/superpowers/runbooks/p-b-p-c-activation.md`
- Modify: `DEVELOPMENT-PLAN.md` (ledger table under the header; A1 bullet text update)
- Delete: `docs/ROADMAP.md` (stale 5-line tombstone)
- Test: none (docs); verification = content checklist below

- [ ] **Step 1: Write the runbook** — structure (mining §1.2), content from `docs/PROJECT_STATE.md`'s P-B/P-C entry + DEVELOPMENT-PLAN A2:
  - §0 What flipping ON does + the named verifying tests:
    `tests/loop/test_verdict_neutrality_task.py::test_verdict_neutral_to_task_episodes_single_window`,
    `::test_verdict_neutral_to_task_episodes_multi_window`,
    `tests/refine/test_separation_integration.py::test_verdict_neutral_with_operational_skill_and_task_episodes`.
  - §1 Wire | Role | Without-it table (`experience_writer` injection · `task_forge` producer ·
    `confirmed_ids` resolution · pinned logical-date asof · conflict_queue routing for
    operational ops · gate-side re-derivation) + the verbatim warning: **"the headline wires are
    NOT sufficient"** + two-tier kill switch (un-wire `experience_writer`; the
    `for_asof(kind=)` fence is the hard floor).
  - §2 Pre-flip checklist: A2's 4 steps + verdict read/write symmetry re-assert +
    default-off-when-dark re-assert; each row: step → named proving test → blocker type
    (code/design/human). Steps A2 will BUILD are marked `blocker: code (A2)`.
  - §3 Staged rollout: dark → shadow (writer on, forge off) → full; each stage's watch signals.
- [ ] **Step 2: Ledger into `DEVELOPMENT-PLAN.md`** — insert directly under the header block:

```markdown
## Activation ledger (capability = done only when live)
| Capability | Built | Live in prod | Path to ON |
|---|---|---|---|
| P-B/P-C operational-K coupling | ✓ (882-test arc, dark) | ✗ | `docs/superpowers/runbooks/p-b-p-c-activation.md` (A2 builds the missing steps) |
| Daily production loop | producers only (`save_decisions` / `run_verdict --json` / `save_evolution`) | ✗ | P9 |
```

  And update the A1 bullet's ledger sentence to point here (one-place discipline).
- [ ] **Step 3: Delete the tombstone** — `git rm docs/ROADMAP.md`.
- [ ] **Step 4: Verify** — runbook names 3 real test functions (`python -m pytest --collect-only -q <each>` finds them); DEVELOPMENT-PLAN renders (markdown lint by eye); `docs/ROADMAP.md` gone.
- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/runbooks/p-b-p-c-activation.md DEVELOPMENT-PLAN.md
git commit -m "docs(a1): P-B/P-C activation runbook + activation ledger; drop stale ROADMAP tombstone"
```

---

### Task 11: Arc close — full suite, sync rule, merge prep

**Files:**
- Modify: `Backend-Design.md` (§2.12 landing note + G12 row → closed-by-A1 status; the registry-path recorded limit from spec D6), `DEVELOPMENT-PLAN.md` (A1 arc: delete/move per one-place discipline), `docs/PROJECT_STATE.md` (dated entry), `CLAUDE.md` (test count), `docs/superpowers/specs+plans` (this spec + plan committed)

- [ ] **Step 1: Full suite** — `python -m pytest -q` → note count N (969 + new; all green).
- [ ] **Step 2: T2-shell acceptance replay** — `python -m pytest tests/converse/test_redact_store.py tests/sonia/test_redact_sessions.py tests/data/test_checksums.py tests/test_tcb_lock.py -v` → ALL PASS (the arc's acceptance gates).
- [ ] **Step 3: Sync rule (DEVELOPMENT-PLAN §5)** —
  - `Backend-Design.md`: G12 ledger row gains `— closed 2026-07-10 (A1)`; §2.12's landing text
    gains the D6 recorded limit (registry snapshot path unverified — live-face concern) and the
    §2.7 A1-list items get `(landed 2026-07-10)` markers where shipped.
  - `DEVELOPMENT-PLAN.md`: A1 arc section replaced by a one-line pointer (`A1 SHIPPED 2026-07-10
    → docs/PROJECT_STATE.md`), G3's redact leg noted closed; ledger stays (it is A1's product).
  - `docs/PROJECT_STATE.md`: dated blockquote — what shipped (7 deliverables, key files, test
    count), spec/plan pointers.
  - `CLAUDE.md`: owner line test count → N.
- [ ] **Step 4: Commit the close + spec/plan docs**

```bash
git add Backend-Design.md DEVELOPMENT-PLAN.md docs/PROJECT_STATE.md CLAUDE.md \
        docs/superpowers/specs/2026-07-10-a1-hygiene-floor-design.md \
        docs/superpowers/plans/2026-07-10-a1-hygiene-floor.md
git commit -m "docs(a1): arc close — sync Backend-Design/PLAN/PROJECT_STATE, test count"
```

- [ ] **Step 5: Merge prep** — leave the branch for the final whole-branch review; after review
  approval: `git checkout main && git merge --ff-only feat/a1-hygiene-floor`. NO push.
