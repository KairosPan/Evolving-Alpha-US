# LLM Stack Switch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A console-UI switch between Claude Fable and DeepSeek per charter entity (Sonia / Kairos), backed by a shared `state/llm_stack.json` that `make_client` reads on every call — instant mid-session effect, global scope (web faces + CLI batch), restart-persistent.

**Architecture:** New `alpha/llm/stack.py` owns the named stacks, the role→entity map, and fail-safe read / atomic write of the state file. `make_client` gains a middle resolution layer (env > stack file > defaults, per-field). `alpha_web` gains a "Models" page (two dropdowns) whose POST writes the file directly.

**Tech Stack:** Python 3.11+, FastAPI + Jinja2 (existing `web` extra), pytest (offline, `brain_session_isolation`).

**Spec:** `docs/superpowers/specs/2026-07-14-llm-stack-switch-design.md` (approved).

## Global Constraints

- Stacks: `"claude" → ("claude_code", "claude-fable-5")`, `"deepseek" → ("openai_compat", "deepseek-chat")` — defined once in `alpha/llm/stack.py`, nowhere else.
- Entity map: `sonia, refiner → "sonia"`; `agent, converse → "kairos"`.
- State file: default `./state/llm_stack.json`, env override `ALPHA_LLM_STACK_FILE` (matches the `alpha/settings.py` `./state/...` + `ALPHA_*` convention).
- Precedence in `make_client`: explicit `ALPHA_<ROLE>_PROVIDER`/`_MODEL` env > entity stack from file > `_DEFAULTS` — **per field** (provider and model resolve independently).
- Fail-safe reads: missing/corrupt/non-dict file or unknown stack name → fall through to the next layer, one `logging` warning, never an exception.
- Atomic writes: tmp file + `os.replace` in the same directory.
- All tests offline; face-touching tests rely on `brain_session_isolation` (which gains the stack-file tmp path in Task 2).
- Repo language: English code/comments/docs. Commit messages via `git commit -F <file>` (never `-m` with backticks/parens).

---

### Task 1: `alpha/llm/stack.py` — stacks, entity map, fail-safe read, atomic write

**Files:**
- Create: `alpha/llm/stack.py`
- Test: `tests/llm/test_stack.py`

**Interfaces:**
- Consumes: nothing new (stdlib only).
- Produces (Tasks 2–3 rely on these exact names):
  - `STACKS: dict[str, tuple[str, str]]` — stack name → `(provider, model)`
  - `ROLE_ENTITY: dict[str, str]` — role → entity (`"sonia"` | `"kairos"`)
  - `stack_file_path() -> str`
  - `read_stacks(path: str | None = None) -> dict[str, str]` — entity → stack name; `{}` on any failure
  - `resolve_stack(role: str) -> tuple[str, str] | None` — `(provider, model)` or `None` to fall through
  - `write_stacks(stacks: dict[str, str], path: str | None = None) -> None` — atomic

- [ ] **Step 1: Write the failing tests**

Create `tests/llm/test_stack.py`:

```python
import json
import os

from alpha.llm import stack


def test_stacks_and_entity_map_shape():
    assert stack.STACKS["claude"] == ("claude_code", "claude-fable-5")
    assert stack.STACKS["deepseek"] == ("openai_compat", "deepseek-chat")
    assert stack.ROLE_ENTITY == {"sonia": "sonia", "refiner": "sonia",
                                 "agent": "kairos", "converse": "kairos"}


def test_stack_file_path_env_override(monkeypatch, tmp_path):
    p = str(tmp_path / "s.json")
    monkeypatch.setenv("ALPHA_LLM_STACK_FILE", p)
    assert stack.stack_file_path() == p


def test_read_missing_file_returns_empty(tmp_path):
    assert stack.read_stacks(str(tmp_path / "absent.json")) == {}


def test_read_corrupt_file_returns_empty(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    assert stack.read_stacks(str(p)) == {}


def test_read_non_dict_returns_empty(tmp_path):
    p = tmp_path / "list.json"
    p.write_text("[1, 2]", encoding="utf-8")
    assert stack.read_stacks(str(p)) == {}


def test_read_drops_non_string_values(tmp_path):
    p = tmp_path / "mixed.json"
    p.write_text(json.dumps({"sonia": "claude", "kairos": 7}), encoding="utf-8")
    assert stack.read_stacks(str(p)) == {"sonia": "claude"}


def test_write_then_read_round_trip(tmp_path):
    p = str(tmp_path / "state" / "llm_stack.json")   # parent dir does not exist yet
    stack.write_stacks({"sonia": "claude", "kairos": "deepseek"}, p)
    assert stack.read_stacks(p) == {"sonia": "claude", "kairos": "deepseek"}
    assert not [f for f in os.listdir(os.path.dirname(p)) if f.endswith(".tmp")]  # no tmp litter


def test_resolve_stack_maps_role_via_entity(monkeypatch, tmp_path):
    p = str(tmp_path / "s.json")
    stack.write_stacks({"sonia": "deepseek"}, p)
    monkeypatch.setenv("ALPHA_LLM_STACK_FILE", p)
    assert stack.resolve_stack("refiner") == ("openai_compat", "deepseek-chat")  # refiner → sonia entity
    assert stack.resolve_stack("agent") is None                                  # kairos absent → fall through


def test_resolve_stack_unknown_name_falls_through(monkeypatch, tmp_path):
    p = str(tmp_path / "s.json")
    stack.write_stacks({"kairos": "gpt9"}, p)
    monkeypatch.setenv("ALPHA_LLM_STACK_FILE", p)
    assert stack.resolve_stack("converse") is None


def test_resolve_stack_unknown_role_is_none(monkeypatch, tmp_path):
    monkeypatch.setenv("ALPHA_LLM_STACK_FILE", str(tmp_path / "s.json"))
    assert stack.resolve_stack("nonsense") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/llm/test_stack.py -q`
Expected: FAIL/ERROR with `ModuleNotFoundError: No module named 'alpha.llm.stack'`

- [ ] **Step 3: Write the implementation**

Create `alpha/llm/stack.py`:

```python
"""Named LLM stacks + the shared entity-switch state file.

One tiny JSON file (`state/llm_stack.json`, env `ALPHA_LLM_STACK_FILE`) is the single source of
truth for the console's Claude↔DeepSeek switch: `{"sonia": "claude", "kairos": "deepseek"}`.
Every process reads it per `make_client` call (both web faces AND the CLI batch scripts), so a
switch takes effect on the next LLM call — mid-chat-session included — and survives restarts.
Reads are fail-safe (missing/corrupt file or unknown name → fall through to defaults, one warning,
never an exception); writes are atomic (tmp + os.replace). Precedence lives in llm/config.py:
explicit ALPHA_<ROLE>_* env > this file's entity stack > _DEFAULTS.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile

_log = logging.getLogger("alpha.llm.stack")

# Stack name → (provider, model). Defined HERE only. After the Fable-5-on-subscription promo ends
# (2026-07-19), re-point "claude" to claude-opus-4-8 in this one line.
STACKS: dict[str, tuple[str, str]] = {
    "claude": ("claude_code", "claude-fable-5"),
    "deepseek": ("openai_compat", "deepseek-chat"),
}

# Role → charter entity. Sonia the teacher owns teaching chat + evolution; Kairos the worker owns
# the decide path + the workbench face.
ROLE_ENTITY: dict[str, str] = {
    "sonia": "sonia",
    "refiner": "sonia",
    "agent": "kairos",
    "converse": "kairos",
}

_DEFAULT_PATH = "./state/llm_stack.json"


def stack_file_path() -> str:
    return os.environ.get("ALPHA_LLM_STACK_FILE", _DEFAULT_PATH)


def read_stacks(path: "str | None" = None) -> dict[str, str]:
    """Entity → stack name from the state file. Fail-safe: any read/parse/shape problem returns {}
    (one warning) so a corrupt file can never take the LLM seam down."""
    p = path or stack_file_path()
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:  # noqa: BLE001 — corrupt/unreadable file: fall back, loudly once
        _log.warning("llm stack file %s unreadable (%s: %s) — using defaults", p, type(e).__name__, e)
        return {}
    if not isinstance(data, dict):
        _log.warning("llm stack file %s is not a JSON object — using defaults", p)
        return {}
    return {k: v for k, v in data.items() if isinstance(v, str)}


def resolve_stack(role: str) -> "tuple[str, str] | None":
    """(provider, model) for the role's entity per the state file, or None to fall through to
    _DEFAULTS. Unknown stack names fall through too (fail-safe forward-compat)."""
    entity = ROLE_ENTITY.get(role)
    if entity is None:
        return None
    name = read_stacks().get(entity)
    if name is None:
        return None
    pair = STACKS.get(name)
    if pair is None:
        _log.warning("unknown llm stack %r for entity %r — using defaults", name, entity)
        return None
    return pair


def write_stacks(stacks: dict[str, str], path: "str | None" = None) -> None:
    """Atomically replace the state file (tmp + os.replace in the same dir — readers only ever see
    a complete old or new file). Caller validates stack names against STACKS."""
    p = path or stack_file_path()
    d = os.path.dirname(p) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".llm_stack.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(stacks, f, indent=2, sort_keys=True)
        os.replace(tmp, p)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/llm/test_stack.py -q`
Expected: 10 passed

- [ ] **Step 5: Commit**

Write the message to a scratch file, then:

```bash
git add alpha/llm/stack.py tests/llm/test_stack.py
git commit -F <msgfile>   # "feat(llm): named stacks + shared llm_stack.json state file (fail-safe read, atomic write)"
```

---

### Task 2: `make_client` three-layer resolution + test isolation

**Files:**
- Modify: `alpha/llm/config.py` (the `make_client` body — provider/model resolution lines)
- Modify: `tests/conftest.py` (the `brain_session_isolation` fixture)
- Test: `tests/llm/test_config_stack.py`

**Interfaces:**
- Consumes: `alpha.llm.stack.resolve_stack(role)` from Task 1.
- Produces: `make_client(role)` now honors the state file between env and `_DEFAULTS`. No signature change; no caller changes anywhere.

- [ ] **Step 1: Write the failing tests**

Create `tests/llm/test_config_stack.py`:

```python
from alpha.llm import stack
from alpha.llm.config import make_client
from alpha.llm.claude_code import ClaudeCodeClient
from alpha.llm.openai_compat import OpenAICompatClient


def _write(monkeypatch, tmp_path, stacks):
    p = str(tmp_path / "llm_stack.json")
    stack.write_stacks(stacks, p)
    monkeypatch.setenv("ALPHA_LLM_STACK_FILE", p)


def _clear_role_env(monkeypatch, role):
    monkeypatch.delenv(f"ALPHA_{role.upper()}_PROVIDER", raising=False)
    monkeypatch.delenv(f"ALPHA_{role.upper()}_MODEL", raising=False)


def test_file_layer_switches_entity_roles(monkeypatch, tmp_path):
    _write(monkeypatch, tmp_path, {"kairos": "deepseek"})
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test")
    for role in ("agent", "converse"):                     # kairos roles → deepseek stack
        _clear_role_env(monkeypatch, role)
        c = make_client(role)
        assert isinstance(c, OpenAICompatClient) and c.model == "deepseek-chat"
    _clear_role_env(monkeypatch, "sonia")                  # sonia entity absent → default (claude)
    assert isinstance(make_client("sonia"), ClaudeCodeClient)


def test_env_beats_file_per_field(monkeypatch, tmp_path):
    _write(monkeypatch, tmp_path, {"sonia": "deepseek"})
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test")
    _clear_role_env(monkeypatch, "sonia")
    monkeypatch.setenv("ALPHA_SONIA_MODEL", "deepseek-reasoner")   # model pinned by env…
    c = make_client("sonia")
    assert isinstance(c, OpenAICompatClient)               # …provider still from the file layer
    assert c.model == "deepseek-reasoner"                  # env field wins over the stack's model


def test_missing_file_means_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("ALPHA_LLM_STACK_FILE", str(tmp_path / "absent.json"))
    _clear_role_env(monkeypatch, "refiner")
    c = make_client("refiner")
    assert isinstance(c, ClaudeCodeClient) and c.model == "claude-fable-5"


def test_unknown_stack_name_means_defaults(monkeypatch, tmp_path):
    _write(monkeypatch, tmp_path, {"sonia": "bogus-stack"})
    _clear_role_env(monkeypatch, "sonia")
    assert isinstance(make_client("sonia"), ClaudeCodeClient)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/llm/test_config_stack.py -q`
Expected: `test_file_layer_switches_entity_roles`, `test_env_beats_file_per_field`,
`test_unknown_stack_name_means_defaults` FAIL (file layer not consulted → claude_code defaults /
AssertionError); `test_missing_file_means_defaults` may already pass.

- [ ] **Step 3: Implement the resolution layer**

In `alpha/llm/config.py`, replace the two resolution lines inside `make_client`:

```python
    provider = os.environ.get(f"ALPHA_{role.upper()}_PROVIDER", def_provider)
    model = os.environ.get(f"ALPHA_{role.upper()}_MODEL", def_model)
```

with:

```python
    # Three layers, resolved PER FIELD: explicit role env (expert escape hatch) > the entity's
    # named stack from the shared state file (the console switch) > _DEFAULTS.
    from alpha.llm.stack import resolve_stack
    stacked = resolve_stack(role)
    if stacked is not None:
        def_provider, def_model = stacked
    provider = os.environ.get(f"ALPHA_{role.upper()}_PROVIDER", def_provider)
    model = os.environ.get(f"ALPHA_{role.upper()}_MODEL", def_model)
```

Also extend the `make_client` docstring line about env with: `The console's entity switch
(state/llm_stack.json, see alpha/llm/stack.py) sits between env and the defaults.`

In `tests/conftest.py`, add one line at the end of `brain_session_isolation` (after the
`ALPHA_NEG_CONSTRAINTS_DIR` line):

```python
    # LLM entity-switch state file (console Models page) — isolate so face tests never read or
    # write the operator's real ./state/llm_stack.json.
    monkeypatch.setenv("ALPHA_LLM_STACK_FILE", str(tmp_path / "llm_stack.json"))
```

- [ ] **Step 4: Run tests to verify they pass, then the full suite**

Run: `python -m pytest tests/llm/test_config_stack.py -q`
Expected: 4 passed

Run: `python -m pytest -q`
Expected: all pass (1927 + 14 new = 1941). If any face test now fails on provider resolution,
that test is missing `brain_session_isolation` — fix the test, not the resolution.

- [ ] **Step 5: Commit**

```bash
git add alpha/llm/config.py tests/conftest.py tests/llm/test_config_stack.py
git commit -F <msgfile>   # "feat(llm): make_client honors the entity stack file (env > file > defaults, per-field)"
```

---

### Task 3: alpha_web "Models" page + write endpoint

**Files:**
- Modify: `alpha_web/app.py` (NAV list; imports; two routes inside `create_app`)
- Create: `alpha_web/templates/models.html`
- Test: `tests/web/test_models_page.py`

**Interfaces:**
- Consumes: `alpha.llm.stack` — `STACKS`, `read_stacks()`, `write_stacks()`, `stack_file_path()` (Task 1).
- Produces: `GET /models` (page), `POST /settings/llm` (form: `entity`, `stack` → 303 redirect to `/models`; 422 on unknown values).

- [ ] **Step 1: Write the failing tests**

Create `tests/web/test_models_page.py`:

```python
import pytest

pytest.importorskip("fastapi", reason="install the web extra: pip install -e '.[web]'")
pytest.importorskip("jinja2", reason="install the web extra: pip install -e '.[web]'")

from fastapi.testclient import TestClient

from alpha.llm import stack
from alpha_web.app import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


def test_models_page_renders_both_entities(client):
    r = client.get("/models")
    assert r.status_code == 200
    assert "Sonia" in r.text and "Kairos" in r.text
    assert "claude" in r.text and "deepseek" in r.text


def test_post_switch_persists_and_redirects(client):
    r = client.post("/settings/llm", data={"entity": "kairos", "stack": "deepseek"},
                    follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/models"
    assert stack.read_stacks().get("kairos") == "deepseek"      # isolated file via conftest
    page = client.get("/models")
    assert 'value="deepseek" selected' in page.text or "selected>deepseek" in page.text.replace('"', "")


def test_post_switch_merges_not_clobbers(client):
    client.post("/settings/llm", data={"entity": "sonia", "stack": "deepseek"})
    client.post("/settings/llm", data={"entity": "kairos", "stack": "claude"})
    assert stack.read_stacks() == {"sonia": "deepseek", "kairos": "claude"}


def test_post_unknown_entity_or_stack_is_422(client):
    assert client.post("/settings/llm", data={"entity": "zeus", "stack": "claude"}).status_code == 422
    assert client.post("/settings/llm", data={"entity": "sonia", "stack": "gpt9"}).status_code == 422
    assert stack.read_stacks().get("sonia") != "gpt9"


def test_env_pinned_badge_shows(client, monkeypatch):
    monkeypatch.setenv("ALPHA_AGENT_PROVIDER", "openai_compat")
    r = client.get("/models")
    assert "env-pinned" in r.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/web/test_models_page.py -q`
Expected: FAIL — `GET /models` returns 404.

- [ ] **Step 3: Implement routes, nav, template**

In `alpha_web/app.py`:

(a) Extend the responses import:

```python
from fastapi.responses import JSONResponse, RedirectResponse, Response
```

(b) Add near the other alpha imports:

```python
import os
import shutil

from alpha.llm import stack as llm_stack
```

(`import os` may already exist via other edits — keep a single import.)

(c) Append a nav entry at the END of the `NAV` list (after "Workbench"):

```python
    {"path": "/models", "key": "models", "label": "Models"},
```

(d) Add two module-level helpers directly below `_BRAIN_STUBS`:

```python
_ENTITY_ROWS = (
    ("sonia", "Sonia — teaching + evolution", ("sonia", "refiner")),
    ("kairos", "Kairos — decisions + workbench", ("agent", "converse")),
)


def _stack_rows() -> list[dict]:
    current = llm_stack.read_stacks()
    rows = []
    for entity, label, roles in _ENTITY_ROWS:
        pinned = [r for r in roles
                  if os.environ.get(f"ALPHA_{r.upper()}_PROVIDER") or os.environ.get(f"ALPHA_{r.upper()}_MODEL")]
        rows.append({"entity": entity, "label": label, "roles": ", ".join(roles),
                     "selected": current.get(entity), "pinned_roles": pinned})
    return rows


def _stack_warnings() -> list[str]:
    """Best-effort forewarnings from the CONSOLE's env — each face resolves its own env, so these
    are hints, not gates; the faces' request-time error boundaries stay authoritative."""
    warns = []
    if shutil.which("claude") is None:
        warns.append("claude CLI not found in this console's PATH — the claude stack needs Claude Code installed.")
    if not os.environ.get("DEEPSEEK_API_KEY"):
        warns.append("DEEPSEEK_API_KEY is not set in this console's env — the deepseek stack fails in any face missing it.")
    if os.environ.get("ANTHROPIC_API_KEY"):
        warns.append("ANTHROPIC_API_KEY is set — the claude stack would bill the metered API instead of the subscription.")
    return warns
```

(e) Add two routes inside `create_app()` (next to the other simple pages, e.g. after the
`/conflicts` block):

```python
    @app.get("/models")
    def models_page(request: Request):
        return render(request, "models.html", {
            "active": "models", "rows": _stack_rows(), "stack_names": sorted(llm_stack.STACKS),
            "stack_defs": llm_stack.STACKS, "warnings": _stack_warnings(),
            "stack_file": llm_stack.stack_file_path(),
        })

    @app.post("/settings/llm")
    def set_llm_stack(entity: str = Form(...), stack: str = Form(...)):
        if entity not in llm_stack.ROLE_ENTITY.values() or stack not in llm_stack.STACKS:
            return JSONResponse({"error": f"unknown entity or stack: {entity!r}/{stack!r}"},
                                status_code=422)
        stacks = llm_stack.read_stacks()
        stacks[entity] = stack
        llm_stack.write_stacks(stacks)
        return RedirectResponse("/models", status_code=303)
```

(f) Create `alpha_web/templates/models.html` (plain form POSTs — full-page reload is fine for a
settings page and sidesteps the HTMX-nesting bug class entirely):

```html
{% extends "base.html" %}
{% block title %}Models{% endblock %}
{% block content %}
<section class="panel">
  <header class="panel-head">
    <h1>Models</h1>
    <p class="lede">Which LLM stack each charter entity runs on. Takes effect on the next LLM
    call — mid-conversation included — across the web faces and CLI batch runs. Stored in
    <code>{{ stack_file }}</code>.</p>
  </header>

  {% for w in warnings %}
  <p class="banner warn">{{ w }}</p>
  {% endfor %}

  {% for row in rows %}
  <form method="post" action="/settings/llm" class="model-row">
    <input type="hidden" name="entity" value="{{ row.entity }}">
    <div>
      <strong>{{ row.label }}</strong>
      <span class="sub">roles: {{ row.roles }}</span>
      {% if row.pinned_roles %}
      <span class="badge">env-pinned (custom): {{ row.pinned_roles|join(", ") }} — the env pin
      keeps winning until removed</span>
      {% endif %}
    </div>
    <select name="stack">
      {% for name in stack_names %}
      <option value="{{ name }}" {% if name == row.selected %}selected{% endif %}>
        {{ name }} · {{ stack_defs[name][1] }}
      </option>
      {% endfor %}
      {% if not row.selected %}
      <option value="" disabled {% if not row.selected %}selected{% endif %}>default (unset)</option>
      {% endif %}
    </select>
    <button type="submit">Save</button>
  </form>
  {% endfor %}
</section>
{% endblock %}
```

- [ ] **Step 4: Run tests to verify they pass, then the web slice**

Run: `python -m pytest tests/web/test_models_page.py -q`
Expected: 5 passed

Run: `python -m pytest tests/web -q`
Expected: all pass (nav change must not break existing page tests; if a test asserts the exact
NAV length, update that assertion).

- [ ] **Step 5: Commit**

```bash
git add alpha_web/app.py alpha_web/templates/models.html tests/web/test_models_page.py
git commit -F <msgfile>   # "feat(web): Models page — per-entity Claude/DeepSeek stack switch"
```

---

### Task 4: docs — CLAUDE.md gotcha + ROADMAP built-log entry

**Files:**
- Modify: `CLAUDE.md` (the "LLM defaults." gotcha bullet)
- Modify: `ROADMAP.md` (Part II append-only built log — one new entry at its end)

**Interfaces:** none (docs only; descriptive, matching what Tasks 1–3 shipped).

- [ ] **Step 1: Update the CLAUDE.md LLM bullet**

Append to the existing "LLM defaults." bullet (keep the current text) the sentences:

```
Between env and the defaults sits the console's entity switch: `state/llm_stack.json`
(`ALPHA_LLM_STACK_FILE`) maps entity→stack (`sonia|kairos` → `claude|deepseek`, defined in
`alpha/llm/stack.py`); the :8100 "Models" page writes it; `make_client` reads it per call, so a
switch lands mid-session and also steers CLI batch runs.
```

- [ ] **Step 2: Append the ROADMAP Part II built-log entry**

Add at the end of Part II (append-only), dated 2026-07-14:

```
- 2026-07-14 — LLM stack switch: per-entity (Sonia/Kairos) Claude↔DeepSeek switch on the :8100
  Models page, backed by shared `state/llm_stack.json` read by `make_client` per call (env >
  file > defaults); instant mid-session, covers CLI batch, restart-persistent. Spec:
  docs/superpowers/specs/2026-07-14-llm-stack-switch-design.md.
```

- [ ] **Step 3: Full suite still green**

Run: `python -m pytest -q`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md ROADMAP.md
git commit -F <msgfile>   # "docs: LLM stack switch — CLAUDE.md gotcha + ROADMAP built log"
```

---

### Task 5: ops — split `.env.deepseek`, restart services, live smoke (INLINE ONLY — touches the operator's secrets and running services; do not dispatch to a subagent)

**Files:**
- Modify (local, gitignored, contains secrets — shell only, never read values into the transcript):
  `.env.deepseek` → key-only; create `.env.deepseek.roles` (the `ALPHA_*` pins).

**Interfaces:** none in code; produces the runtime environment in which the switch actually works.

- [ ] **Step 1: Split the env file (key-only vs role pins)**

```bash
cd /Users/pan/Desktop/self-evolve/evolving-alpha-us
grep -v "DEEPSEEK_API_KEY" .env.deepseek > .env.deepseek.roles
grep "DEEPSEEK_API_KEY" .env.deepseek > .env.deepseek.tmp && mv .env.deepseek.tmp .env.deepseek
chmod 600 .env.deepseek .env.deepseek.roles
git check-ignore .env.deepseek.roles   # must print the path; if not, add to .gitignore first
```

Expected: `.env.deepseek` = 1 line (the key); `.env.deepseek.roles` = the 7 `ALPHA_*` lines.

- [ ] **Step 2: Restart the three services with the key but WITHOUT role pins**

Stop the running `python -m sonia` / `python -m workbench` / `python -m alpha_web` processes, then:

```bash
# each in its own background shell, from the repo root:
set -a; . ./.env.deepseek; set +a; env -u ANTHROPIC_API_KEY python -m sonia
set -a; . ./.env.deepseek; . ./.env.alpaca; set +a; env -u ANTHROPIC_API_KEY python -m workbench
set -a; . ./.env.deepseek; set +a; env -u ANTHROPIC_API_KEY python -m alpha_web
```

(Key present → the deepseek stack works at runtime; no `ALPHA_*` pins → the file layer steers;
`ANTHROPIC_API_KEY` unset → claude stack stays on subscription.)

- [ ] **Step 3: Live smoke — switch mid-session**

1. `GET http://localhost:8100/models` → page renders, both rows, no env-pinned badge.
2. Start a Sonia chat (`POST :8810/chat`), note the reply style/model self-report.
3. On `/models`, set Sonia → deepseek; send a second message in the SAME session asking which
   model is answering. Expected: the reply comes from deepseek-chat.
4. Switch Sonia back to claude; a third message self-reports Claude again.
5. `cat state/llm_stack.json` → reflects the final choice.

- [ ] **Step 4: Update the run-workbench memory note**

Update `run-workbench-live-face.md` memory (and the session memory) with the new start recipe
(key-only env + stack file switch) — memory is outside the repo; no commit.

---

## Self-Review (run after writing)

1. **Spec coverage:** stacks/entity map (T1), precedence + per-field + fail-safe + atomic (T1/T2),
   conftest isolation (T2), Models page + POST + 422 + env-pinned badge + credential warnings +
   mid-session semantics (T3, live-verified T5), ops split (T5), docs (T4). ✓
2. **Placeholder scan:** no TBD/TODO; every code step shows the code. ✓
3. **Type consistency:** `resolve_stack(role) -> tuple[str, str] | None` consumed as
   `def_provider, def_model = stacked` (T2); `read_stacks()/write_stacks()` dict[str, str] used by
   T3 routes; template keys match the T3 `render` ctx. ✓
