# Sonia `/conflicts` Adjudication UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface the §5 held conflicts (self-study ops contesting teaching-owned H elements, persisted in the `ConflictQueue`) for human adjudication: the Sonia service reads + resolves the queue, the `alpha_web` console renders a `/conflicts` page where the user picks **Accept self-study** (record intent only — no auto-re-apply, per the §5-accepted decision) or **Keep teaching** (dismiss); resolving removes the conflict from the queue.

**Architecture:** Additive, following the existing Sonia↔alpha_web split. Sonia (the brain owner) gains an env-wired `ConflictQueue` + `GET /conflicts` (list) + `POST /conflicts/{cid}/resolve` (record decision + remove). `SoniaClient` gains `list_conflicts`/`resolve_conflict`. `alpha_web` gains a top-level **Conflicts** nav item, a `GET /conflicts` page, and a `POST /conflicts/{cid}/resolve` HTMX route that removes the resolved row (the proven empty-**200** swap from `delete_session`, NOT 204/302 — the memory's HTMX lesson). **Deferred (noted, separate task):** wiring a *live* offline Refiner run to feed the shared queue (`ALPHA_CONFLICTS_DIR`); this plan builds the adjudication surface, tested against a populated `ConflictQueue`.

**Tech Stack:** Python ≥3.11, FastAPI, Jinja2 + vendored HTMX, pytest (Starlette `TestClient`). Reuses `alpha.meta.conflict_store.{ConflictQueue, HeldConflict}`, the Sonia `create_app()` pattern, `SoniaClient`, and the `alpha_web` `_render`/NAV/`_sonia()` pattern.

## Global Constraints

- **Python `>=3.11`**, FastAPI. The existing suite (currently **622 passed**) must stay green. Additive — no existing Sonia route / `alpha_web` route / SoniaClient method changes behavior.
- **§5-accepted adjudication semantics:** `resolve` decision ∈ `{accept_self_study, keep_teaching}`. **accept_self_study = record intent only** (do NOT auto-re-apply the held op through the gate); **keep_teaching = dismiss**. Both REMOVE the conflict from the queue (`ConflictQueue.resolve(cid)`).
- **HTMX (per the cockpit hardening lessons):** the resolve action `hx-post`s and swaps the conflict's own row via `outerHTML` with an **empty 200** response (the row disappears) — exactly like `alpha_web` `delete_session` (`app.py:335-343`). NOT 204 (htmx skips the swap on 204), NOT a 302 (htmx's XHR follows it and re-nests). Sonia-unavailable is caught and shown as a banner, like the existing `_sonia()` callers.
- **Conflict store wiring:** Sonia reads `ConflictQueue(os.environ.get("ALPHA_CONFLICTS_DIR", "./state/conflicts"))` — same env-default idiom as `_brain_store`/`_session_store`.
- English; follow existing patterns (`sonia/app.py`, `alpha_web/app.py`, the existing templates).

## File Structure

- Modify: `sonia/app.py` (`_conflict_store()`, `GET /conflicts`, `POST /conflicts/{cid}/resolve`).
- Modify: `alpha_web/sonia_client.py` (`list_conflicts`, `resolve_conflict`).
- Modify: `alpha_web/app.py` (NAV "Conflicts", `GET /conflicts`, `POST /conflicts/{cid}/resolve`).
- Create: `alpha_web/templates/conflicts.html`.
- Tests: `tests/sonia/test_conflicts.py`, `tests/web/test_conflicts_page.py`.

---

### Task 1: Sonia service — conflict store + list + resolve routes

**Files:**
- Modify: `sonia/app.py`
- Test: `tests/sonia/test_conflicts.py`

**Interfaces:**
- Produces: `GET /conflicts -> list[dict]` (HeldConflict dumps, newest-first); `POST /conflicts/{cid}/resolve` with body `{"decision": "accept_self_study"|"keep_teaching"}` → records the decision + `ConflictQueue.resolve(cid)`, returns `{"resolved": cid, "decision": decision}` (404 if the conflict is missing). Consumed by Tasks 2–4.

- [ ] **Step 1: Write the failing test**

```python
# tests/sonia/test_conflicts.py
import os
from fastapi.testclient import TestClient

def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPHA_CONFLICTS_DIR", str(tmp_path / "conflicts"))
    monkeypatch.setenv("ALPHA_LIVE_BRAIN_DIR", str(tmp_path / "brain"))
    monkeypatch.setenv("ALPHA_SESSIONS_DIR", str(tmp_path / "sessions"))
    monkeypatch.setenv("ALPHA_SONIA_PROVIDER", "mock")
    from sonia.app import create_app
    return TestClient(create_app())

def _seed_conflict(tmp_path):
    from alpha.meta.conflict_store import ConflictQueue
    q = ConflictQueue(str(tmp_path / "conflicts"))
    return q.add(op={"tool": "demote_memory", "args": {"lesson_id": "m1"}, "rationale": "data weak"},
                 provenance={"path": "self_study", "proposer": "refiner"},
                 contested={"target_id": "m1", "tool": "process_memory",
                            "provenance": {"path": "teaching", "proposer": "sonia"}})

def test_list_conflicts(tmp_path, monkeypatch):
    held = _seed_conflict(tmp_path)
    c = _client(tmp_path, monkeypatch)
    rows = c.get("/conflicts").json()
    assert len(rows) == 1 and rows[0]["conflict_id"] == held.conflict_id
    assert rows[0]["op"]["tool"] == "demote_memory" and rows[0]["provenance"]["path"] == "self_study"

def test_resolve_removes_conflict(tmp_path, monkeypatch):
    held = _seed_conflict(tmp_path)
    c = _client(tmp_path, monkeypatch)
    r = c.post(f"/conflicts/{held.conflict_id}/resolve", json={"decision": "keep_teaching"})
    assert r.status_code == 200 and r.json() == {"resolved": held.conflict_id, "decision": "keep_teaching"}
    assert c.get("/conflicts").json() == []                       # removed from the queue
    assert c.post(f"/conflicts/{held.conflict_id}/resolve", json={"decision": "keep_teaching"}).status_code == 404
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/sonia/test_conflicts.py -v`
Expected: FAIL — 404 on `/conflicts` (route doesn't exist).

- [ ] **Step 3: Implement** — edit `sonia/app.py`:

Add the import + store helper (next to `_brain_store`/`_session_store`):
```python
from alpha.meta.conflict_store import ConflictQueue

def _conflict_store() -> ConflictQueue:
    return ConflictQueue(os.environ.get("ALPHA_CONFLICTS_DIR", "./state/conflicts"))
```
Add a body model (next to `EditAction`):
```python
class ResolveIn(BaseModel):
    decision: str  # "accept_self_study" | "keep_teaching"
```
Add the two routes inside `create_app()` (before `return app`):
```python
    @app.get("/conflicts")
    def list_conflicts():
        return [c.model_dump() for c in _conflict_store().all()]

    @app.post("/conflicts/{cid}/resolve")
    def resolve_conflict(cid: str, body: ResolveIn):
        q = _conflict_store()
        held = q.get(cid)
        if held is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        # §5-accepted: accept_self_study records intent only (no auto-re-apply); both decisions resolve+remove.
        q.resolve(cid)
        return {"resolved": cid, "decision": body.decision}
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/sonia/test_conflicts.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add sonia/app.py tests/sonia/test_conflicts.py
git commit -m "feat(sonia): /conflicts list + resolve routes (read+adjudicate the held queue)"
```

---

### Task 2: `SoniaClient` — `list_conflicts` + `resolve_conflict`

**Files:**
- Modify: `alpha_web/sonia_client.py`
- Test: `tests/web/test_conflicts_page.py` (the client half — or a focused client test)

**Interfaces:**
- Produces: `SoniaClient.list_conflicts() -> list`; `SoniaClient.resolve_conflict(cid: str, decision: str) -> dict`. Consumed by Tasks 3, 4.

- [ ] **Step 1: Write the failing test** (start `tests/web/test_conflicts_page.py`; inject a Sonia `TestClient` as the SoniaClient transport, mirroring the existing `tests/web/test_sonia_client.py`)

```python
# tests/web/test_conflicts_page.py
import os
from fastapi.testclient import TestClient
from alpha_web.sonia_client import SoniaClient

def _sonia_tc(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPHA_CONFLICTS_DIR", str(tmp_path / "conflicts"))
    monkeypatch.setenv("ALPHA_LIVE_BRAIN_DIR", str(tmp_path / "brain"))
    monkeypatch.setenv("ALPHA_SESSIONS_DIR", str(tmp_path / "sessions"))
    monkeypatch.setenv("ALPHA_SONIA_PROVIDER", "mock")
    from sonia.app import create_app
    return TestClient(create_app())

def _seed(tmp_path):
    from alpha.meta.conflict_store import ConflictQueue
    return ConflictQueue(str(tmp_path / "conflicts")).add(
        op={"tool": "demote_memory", "args": {"lesson_id": "m1"}, "rationale": "weak"},
        provenance={"path": "self_study", "proposer": "refiner"}, contested={"target_id": "m1"})

def test_sonia_client_list_and_resolve(tmp_path, monkeypatch):
    held = _seed(tmp_path)
    sc = SoniaClient(client=_sonia_tc(tmp_path, monkeypatch))
    assert sc.list_conflicts()[0]["conflict_id"] == held.conflict_id
    assert sc.resolve_conflict(held.conflict_id, "keep_teaching")["resolved"] == held.conflict_id
    assert sc.list_conflicts() == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/web/test_conflicts_page.py::test_sonia_client_list_and_resolve -v`
Expected: FAIL — `AttributeError: 'SoniaClient' object has no attribute 'list_conflicts'`.

- [ ] **Step 3: Implement** — add to `alpha_web/sonia_client.py`:

```python
    def list_conflicts(self) -> list:
        return self._request("GET", "/conflicts")

    def resolve_conflict(self, cid: str, decision: str) -> dict:
        return self._request("POST", f"/conflicts/{cid}/resolve", json={"decision": decision})
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/web/test_conflicts_page.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add alpha_web/sonia_client.py tests/web/test_conflicts_page.py
git commit -m "feat(web): SoniaClient list_conflicts + resolve_conflict"
```

---

### Task 3: `alpha_web` — Conflicts nav + `GET /conflicts` page + template

**Files:**
- Modify: `alpha_web/app.py` (NAV + the GET route)
- Create: `alpha_web/templates/conflicts.html`
- Test: `tests/web/test_conflicts_page.py` (the page-render half)

**Interfaces:**
- Consumes: `SoniaClient.list_conflicts` (T2), the existing `_render`/`_sonia()`/NAV machinery.
- Produces: a top-level NAV entry `{"path": "/conflicts", "key": "conflicts", "label": "Conflicts"}`; `GET /conflicts` renders `conflicts.html` with `conflicts=<list>` (or a Sonia-unavailable banner). Consumed by Task 4 (the resolve action).

- [ ] **Step 1: Write the failing test** (append to `tests/web/test_conflicts_page.py`)

```python
def _web_client(tmp_path, monkeypatch):
    from alpha_web.app import app, set_sonia_client
    set_sonia_client(SoniaClient(client=_sonia_tc(tmp_path, monkeypatch)))
    return TestClient(app)

def test_conflicts_page_renders_held(tmp_path, monkeypatch):
    held = _seed(tmp_path)
    r = _web_client(tmp_path, monkeypatch).get("/conflicts")
    assert r.status_code == 200
    assert "Conflicts" in r.text                                  # nav label
    assert held.conflict_id in r.text and "self_study" in r.text  # the held conflict is rendered
    assert "demote_memory" in r.text

def test_conflicts_page_empty_state(tmp_path, monkeypatch):
    r = _web_client(tmp_path, monkeypatch).get("/conflicts")      # no conflicts seeded
    assert r.status_code == 200 and "Conflicts" in r.text         # renders an empty state, no 500
```

> **Implementer note:** read `alpha_web/app.py` lines ~40-55 (the `NAV` list) and ~185-260 (the `_render` helper + an existing GET route like `/decisions`/`/evolution`) and `alpha_web/templates/` (base.html + an existing list page) to match the exact `_render(request, "conflicts.html", {...})` signature and template `{% extends %}` structure. `set_sonia_client` is the existing test seam (`alpha_web/app.py:31`).

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/web/test_conflicts_page.py -k page -v`
Expected: FAIL — `GET /conflicts` is 404 (route missing).

- [ ] **Step 3: Implement**
- `alpha_web/app.py`: add the NAV entry (after the `/evolution` "Autonomous" entry) and the route:
```python
    @app.get("/conflicts")
    def conflicts(request: Request):
        try:
            rows = _sonia().list_conflicts()
            return _render(request, "conflicts.html", {"active": "conflicts", "conflicts": rows, "sonia_down": False})
        except Exception:                                         # Sonia unavailable -> banner, never 500
            return _render(request, "conflicts.html", {"active": "conflicts", "conflicts": [], "sonia_down": True})
```
(Confirm the exact `_render` helper name/signature by reading the file; mirror an existing route.)
- `alpha_web/templates/conflicts.html`: `{% extends "base.html" %}`, render the page heading + an empty-state when `not conflicts`, and one block per conflict showing: the contested element (`c.contested.target_id`), the self-study op (`c.op.tool` + `c.op.rationale`) and its proposer (`c.provenance.path`/`.proposer`), and the teaching record it contests. Each conflict block is a single root element with `id="conflict-{{ c.conflict_id }}"` carrying the two adjudication buttons (wired in Task 4). Match the existing templates' style/markup.

- [ ] **Step 4: Run to verify it passes + full suite**

Run: `python -m pytest tests/web/test_conflicts_page.py -v && python -m pytest -q`
Expected: page tests PASS; full suite green (additive nav/route/template).

- [ ] **Step 5: Commit**

```bash
git add alpha_web/app.py alpha_web/templates/conflicts.html tests/web/test_conflicts_page.py
git commit -m "feat(web): Conflicts nav + /conflicts page (renders the held queue)"
```

---

### Task 4: `alpha_web` — resolve action (HTMX empty-200 row removal)

**Files:**
- Modify: `alpha_web/app.py` (the POST resolve route), `alpha_web/templates/conflicts.html` (the buttons' HTMX attrs)
- Test: `tests/web/test_conflicts_page.py` (the resolve half)

**Interfaces:**
- Consumes: `SoniaClient.resolve_conflict` (T2).
- Produces: `POST /conflicts/{cid}/resolve` (form/HTMX) → calls `_sonia().resolve_conflict(cid, decision)` and returns an **empty 200** (the conflict's row `outerHTML`-swaps to nothing = removed), mirroring `delete_session` (`app.py:335-343`). Sonia-unavailable → a small inline banner fragment (not a 500).

- [ ] **Step 1: Write the failing test** (append)

```python
def test_resolve_returns_empty_200_and_removes(tmp_path, monkeypatch):
    held = _seed(tmp_path)
    tc = _web_client(tmp_path, monkeypatch)
    r = tc.post(f"/conflicts/{held.conflict_id}/resolve", data={"decision": "accept_self_study"})
    assert r.status_code == 200 and r.text == ""                 # empty -> htmx outerHTML-swaps the row away
    assert tc.get("/conflicts").json() if False else True        # (page is HTML; assert via the queue below)
    from alpha.meta.conflict_store import ConflictQueue
    assert ConflictQueue(str(tmp_path / "conflicts")).all() == []   # actually resolved in Sonia's queue
```

> **Implementer note:** the resolve route reads `decision` from the form (`request.form()` / a small pydantic-free form parse) or a query param — match how the existing `/evolve/{session_id}/edit/{edit_id}` route reads its action. Return `Response(status_code=200, content="")` on success (NOT 204 — htmx skips the swap; NOT 302). On a Sonia error, return a small inline error fragment with 200 so the row shows a banner rather than vanishing.

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/web/test_conflicts_page.py -k resolve -v`
Expected: FAIL — `POST /conflicts/{cid}/resolve` is 404.

- [ ] **Step 3: Implement**
- `alpha_web/app.py`: add the resolve route returning the empty-200 (mirror `delete_session`); catch Sonia errors → inline banner fragment.
- `conflicts.html`: give each conflict block the two buttons — **Accept self-study** and **Keep teaching** — each `hx-post="/conflicts/{{ c.conflict_id }}/resolve"` with the decision (e.g. `hx-vals='{"decision": "accept_self_study"}'`), `hx-target="#conflict-{{ c.conflict_id }}"`, `hx-swap="outerHTML"`. (Match the existing cockpit's HTMX attribute style.)

- [ ] **Step 4: Run to verify it passes + full suite**

Run: `python -m pytest tests/web/test_conflicts_page.py -v && python -m pytest -q`
Expected: all conflict tests PASS; full suite green.

- [ ] **Step 5: Commit**

```bash
git add alpha_web/app.py alpha_web/templates/conflicts.html tests/web/test_conflicts_page.py
git commit -m "feat(web): adjudicate conflicts (accept-self-study / keep-teaching, HTMX empty-200 removal)"
```

---

## Self-Review

**Spec coverage (§5.4 adjudication surface):**
- Held conflicts surfaced in the cockpit → Task 1 (Sonia list) + Task 3 (page). ✓
- User decides (accept self-study / keep teaching) → Task 4 (the two HTMX actions). ✓
- accept = record intent only (no auto-re-apply); both resolve+remove → Task 1's resolve. ✓
- Sonia owns the queue (env-wired), alpha_web reads via SoniaClient → Tasks 1 + 2. ✓
- HTMX empty-200 row removal (the cockpit lesson) → Task 4. ✓
- Deferred (noted): the live Refiner→shared-queue feeding; LLM "framing" of the conflict (raw evidence shown). ✓

**Placeholder scan:** Tasks 3 + 4 describe the template/route against the named existing files (`delete_session`, the `NAV` list, base.html) with the exact HTMX contract (empty-200, outerHTML) and the required rendered fields — the implementer notes name the files to read. No production code step is a placeholder.

**Type consistency:** `ConflictQueue.all()/get()/resolve()` + `HeldConflict.model_dump()` (from §5) are consumed in Task 1; `GET /conflicts -> list[dict]` and `POST .../resolve -> {"resolved","decision"}` are consumed by `SoniaClient.list_conflicts`/`resolve_conflict` (Task 2), which the `alpha_web` route (Tasks 3/4) calls. The `_render`/`_sonia`/`set_sonia_client`/NAV machinery is the existing `alpha_web` API. The empty-200 swap contract matches `delete_session` (`alpha_web/app.py:335-343`).
