# Agent-Modification Drawer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a resizable, collapsible right drawer to the Teach cockpit (`/`) that surfaces the teaching→brain-edit flow: a PENDING change-set (proposed/accepted edits, moved out of the chat bubbles) stacked over a CURRENT brain mirror (the live six-component read that refreshes on apply).

**Architecture:** Server-rendered Jinja partials updated via HTMX out-of-band (`hx-swap-oob`) swaps — the house style (already used for the composer's `session_id`). No new Sonia endpoint: the CURRENT-brain half reuses `alpha_web.data_access.load_brain()`, which reads the same `ALPHA_LIVE_BRAIN_DIR/brain.json` Sonia writes on apply. Apply/rollback keep Sonia's existing per-message snapshot model. Only new JS is vanilla drag-resize + collapse.

**Tech Stack:** FastAPI, Jinja2, vendored HTMX, plain CSS/JS. Tests: pytest + FastAPI `TestClient` driving the real Sonia app in-process (mock LLM), fully offline.

## Global Constraints

- All code, comments, docs in **English**.
- **No new Sonia endpoint / no new write path.** The drawer is surfacing-only; brain edits still flow through Sonia's gated apply (`refine/apply.py::try_apply_op`). Do not mutate the brain from `alpha_web`.
- `alpha_web/drawer.py` must stay **pure** (no I/O): the route hands it the session dict and a `HarnessState`.
- Reuse existing tokens/patterns: the `.acc`/`.is-open` accordion mechanic mirrors the left brain drawer; CSS uses existing custom properties (`--line`, `--panel`, `--gold`, `--gold-soft`, `--hover`, `--track`, `--fg-dim`, `--fg-faint`, `--serif`, `--mono`).
- Tests run offline via `pytest.importorskip("fastapi")` + the in-process Sonia `TestClient` + `ALPHA_SONIA_PROVIDER=mock`; the autouse `brain_session_isolation` fixture (parent `tests/conftest.py`) points both services at a tmp `ALPHA_LIVE_BRAIN_DIR`.
- Full suite green after every task: `python -m pytest -q`.

## File Structure

**New files**
- `alpha_web/drawer.py` — pure view-models: `pending_view(session)` → `PendingView`, `brain_view(state)` → `BrainView`.
- `alpha_web/templates/partials/_drawer.html` — drawer shell (resizer + collapse header + body).
- `alpha_web/templates/partials/_pending.html` — the PENDING section (`id="pending"`, OOB-swappable).
- `alpha_web/templates/partials/_brain_panel.html` — the CURRENT-brain section (`id="brain-panel"`, OOB-swappable).
- `alpha_web/templates/partials/_drawer_update.html` — apply/rollback response: `_pending` (main) + `_brain_panel` (OOB).
- `tests/web/test_drawer.py` — view-model units + route/OOB/reflection tests.

**Modified files**
- `alpha_web/app.py` — import `drawer`; extend `_cockpit_ctx`; OOB-wire `message`/`edit`/`apply`/`rollback`.
- `alpha_web/templates/cockpit.html` — include the drawer inside `.cockpit`.
- `alpha_web/templates/partials/message_assistant.html` — drop inline edit cards + apply form; add the change chip.
- `alpha_web/templates/partials/edit_card.html` — retarget accept/reject to `#pending`.
- `alpha_web/templates/partials/_two_turns.html` — append OOB `#pending` + `#brain-panel`.
- `alpha_web/static/cockpit.css` — drawer + accordion + chip styles.
- `alpha_web/static/cockpit.js` — drag-resize, collapse, delegated accordions, chip flash.
- `alpha_web/templates/base.html` — bump `cockpit.css?v=` to bust cache.

Note: `alpha_web/templates/partials/apply_result.html` becomes unused after Task 3 (the inline apply form is removed). Leave it in place — it is harmless and touched by no test.

---

## Task 1: `drawer.py` view-models + unit tests

**Files:**
- Create: `alpha_web/drawer.py`
- Test: `tests/web/test_drawer.py`

**Interfaces:**
- Produces:
  - `pending_view(session: dict | None) -> PendingView` where `PendingView(session_id: str, groups: list[MessageGroup], pending_count: int)` and `MessageGroup(message_id: str, edits: list[dict], accepted: int, applied: bool)`.
  - `brain_view(state: HarnessState) -> BrainView` where `BrainView(components: list[Component])` and `Component(key: str, label: str, path: str, count: int | None, items: list, is_stub: bool, blurb: str = "")`.

- [ ] **Step 1: Write the failing unit tests**

Create `tests/web/test_drawer.py`:

```python
import pytest

pytest.importorskip("fastapi")

from alpha.harness.loader import load_seeds
from alpha_web import drawer


# ── view-model units ─────────────────────────────────────────────────────────

def test_pending_view_none_session_is_empty():
    v = drawer.pending_view(None)
    assert v.session_id == "" and v.groups == [] and v.pending_count == 0


def test_pending_view_groups_by_message_and_counts_actionable():
    session = {"session_id": "s1", "messages": [
        {"message_id": "m1", "edits": [
            {"edit_id": "e1", "status": "accepted"},
            {"edit_id": "e2", "status": "proposed"}]},
        {"message_id": "m2", "edits": []},                     # no edits → skipped
        {"message_id": "m3", "edits": [{"edit_id": "e3", "status": "applied"}]},
    ]}
    v = drawer.pending_view(session)
    assert [g.message_id for g in v.groups] == ["m1", "m3"]
    assert v.groups[0].accepted == 1 and v.groups[0].applied is False
    assert v.groups[1].applied is True and v.groups[1].accepted == 0
    assert v.pending_count == 2                                 # e1 accepted + e2 proposed; e3 applied excluded


def test_brain_view_mirrors_six_components_in_rail_order():
    v = drawer.brain_view(load_seeds("seeds"))
    assert [c.key for c in v.components] == \
        ["doctrine", "memory", "workflow", "skills", "connector", "subagent"]


def test_brain_view_live_have_counts_stubs_do_not():
    state = load_seeds("seeds")
    v = drawer.brain_view(state)
    by_key = {c.key: c for c in v.components}
    assert by_key["skills"].count == len(state.skills.all())
    assert by_key["skills"].items == state.skills.all()
    assert by_key["skills"].is_stub is False and by_key["skills"].path == "/skills"
    for k in ("workflow", "connector", "subagent"):
        assert by_key[k].is_stub is True
        assert by_key[k].count is None and by_key[k].items == [] and by_key[k].blurb
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/web/test_drawer.py -q`
Expected: FAIL / collection error — `ModuleNotFoundError: No module named 'alpha_web.drawer'`.

- [ ] **Step 3: Write `alpha_web/drawer.py`**

```python
"""Right-drawer view-models for the Teach cockpit: the PENDING change-set (the session's
proposed/accepted edits) and the CURRENT brain summary (the live six-component mirror).

Pure functions — no I/O. The route hands in the Sonia session dict and a HarnessState (read via
data_access.load_brain), so these stay trivially unit-testable. The drawer is a surfacing layer:
it never mutates the brain; edits still flow through Sonia's gated apply."""
from __future__ import annotations

from dataclasses import dataclass

from alpha.harness.state import HarnessState

# ── PENDING (the change-set) ─────────────────────────────────────────────────
_ACTIONABLE = ("proposed", "accepted")


@dataclass(frozen=True)
class MessageGroup:
    """One assistant turn's edits, grouped so apply/rollback stay per-message (matching Sonia's
    per-message snapshot). `accepted` drives the Apply button; `applied` flips the group to the
    rollback line."""
    message_id: str
    edits: list[dict]
    accepted: int
    applied: bool


@dataclass(frozen=True)
class PendingView:
    session_id: str
    groups: list[MessageGroup]
    pending_count: int          # edits still actionable (proposed + accepted) across all groups


def pending_view(session: dict | None) -> PendingView:
    """Flatten a Sonia session dict into per-message edit groups. Messages without edits are
    skipped; a None/empty session yields an empty view."""
    session = session or {}
    groups: list[MessageGroup] = []
    pending = 0
    for m in session.get("messages", []):
        edits = m.get("edits") or []
        if not edits:
            continue
        pending += sum(1 for e in edits if e.get("status") in _ACTIONABLE)
        groups.append(MessageGroup(
            message_id=m.get("message_id", ""),
            edits=edits,
            accepted=sum(1 for e in edits if e.get("status") == "accepted"),
            applied=any(e.get("status") == "applied" for e in edits),
        ))
    return PendingView(session_id=session.get("session_id", ""), groups=groups, pending_count=pending)


# ── CURRENT brain (the live six-component mirror) ────────────────────────────
_STUBS = (
    ("workflow",  "Workflow",  "Named multi-step playbooks Sonia composes from skills."),
    ("connector", "Connector", "External data/tool connections the agent draws on (Alpaca, EDGAR, MCP feeds…)."),
    ("subagent",  "Subagent",  "Specialized dispatch sub-agents the master agent delegates to."),
)


@dataclass(frozen=True)
class Component:
    """One brain component row. Live components carry a count + item objects (Skill/Lesson/
    DoctrineEntry) the template renders; stubs carry a blurb and no count."""
    key: str
    label: str
    path: str            # full-page link ("" for stubs)
    count: int | None    # None → stub
    items: list          # [] for stubs
    is_stub: bool
    blurb: str = ""


@dataclass(frozen=True)
class BrainView:
    components: list[Component]


def brain_view(state: HarnessState) -> BrainView:
    """Mirror the six brain components in the left-rail order: three live (doctrine/memory/skills,
    with item lists) and three read-only stubs (workflow/connector/subagent)."""
    doctrine = list(state.doctrine.entries)
    lessons = state.memory.all()
    skills = state.skills.all()
    blurb = {k: b for k, _, b in _STUBS}
    return BrainView(components=[
        Component("doctrine",  "Doctrine",  "/doctrine", len(doctrine), doctrine, False),
        Component("memory",    "Memory",    "/memory",   len(lessons),  lessons,  False),
        Component("workflow",  "Workflow",  "", None, [], True, blurb["workflow"]),
        Component("skills",    "Skill",     "/skills",   len(skills),   skills,   False),
        Component("connector", "Connector", "", None, [], True, blurb["connector"]),
        Component("subagent",  "Subagent",  "", None, [], True, blurb["subagent"]),
    ])
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/web/test_drawer.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add alpha_web/drawer.py tests/web/test_drawer.py
git commit -m "feat(web): drawer view-models (pending change-set + live brain mirror)"
```

---

## Task 2: CURRENT-brain half + drawer shell on `GET /`

Renders the drawer (resizer + collapse header + brain panel) into the Teach page. PENDING is a placeholder here; the real change-set + route wiring land in Task 3. No JS yet — the panel is fixed-width and sections render server-open. `message_assistant.html`/`edit_card.html` are left untouched (inline cards stay), so existing tests stay green.

**Files:**
- Create: `alpha_web/templates/partials/_drawer.html`, `alpha_web/templates/partials/_pending.html`, `alpha_web/templates/partials/_brain_panel.html`
- Modify: `alpha_web/app.py` (import `drawer`; extend `_cockpit_ctx` at `alpha_web/app.py:355-360`), `alpha_web/templates/cockpit.html`, `alpha_web/static/cockpit.css`, `alpha_web/templates/base.html:13`
- Test: `tests/web/test_drawer.py` (append route fixtures + one test)

**Interfaces:**
- Consumes: `drawer.pending_view`, `drawer.brain_view` (Task 1); `da.load_brain()` (existing).
- Produces: cockpit render context now carries `pending: PendingView` and `brain: BrainView`; the page contains `#agent-drawer`, `#pending`, `#brain-panel`, `.drawer-resizer`, `.drawer-collapse`.

- [ ] **Step 1: Write the failing route test**

Append to `tests/web/test_drawer.py`:

```python
from fastapi.testclient import TestClient

from alpha_web import app as webapp
from alpha_web.sonia_client import SoniaClient
from sonia.app import create_app as create_sonia


@pytest.fixture(autouse=True)
def _wire_sonia(monkeypatch):
    # Drive the real Sonia app in-process via an injected sync TestClient; mock copilot + isolated state.
    monkeypatch.setenv("ALPHA_SONIA_PROVIDER", "mock")
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE", "lets discuss the squeeze setup")
    webapp.set_sonia_client(SoniaClient(client=TestClient(create_sonia())))
    yield
    webapp.set_sonia_client(None)


@pytest.fixture()
def client():
    return TestClient(webapp.create_app())


def test_home_renders_drawer_shell_and_six_brain_components(client):
    body = client.get("/").text
    assert 'id="agent-drawer"' in body
    assert 'id="pending"' in body and 'id="brain-panel"' in body
    assert 'class="drawer-resizer"' in body           # drag-resize hook (JS wired in Task 4)
    assert "drawer-collapse" in body                  # collapse hook
    panel = body.split('id="brain-panel"', 1)[1]      # isolate the brain panel from the left-rail nav
    for label in ("Doctrine", "Memory", "Workflow", "Skill", "Connector", "Subagent"):
        assert label in panel
    assert "read-only" in panel                       # stub marker
    assert "→ open full page" in panel                # live-component full-page link
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/web/test_drawer.py::test_home_renders_drawer_shell_and_six_brain_components -q`
Expected: FAIL — `assert 'id="agent-drawer"' in body` (the drawer is not rendered yet).

- [ ] **Step 3: Create `alpha_web/templates/partials/_brain_panel.html`**

```html
<section id="brain-panel" class="acc dsec is-open"{% if brain_oob %} hx-swap-oob="true"{% endif %}>
  <button type="button" class="acc-toggle dsec-toggle" aria-expanded="true">
    Current brain <span class="caret" aria-hidden="true">&#9656;</span>
  </button>
  <div class="acc-body">
    {% for c in brain.components %}
    {% if c.is_stub %}
    <div class="bcomp is-stub" title="{{ c.blurb }}">
      <span class="bcomp-label">{{ c.label }}</span>
      <span class="bcomp-count">&ndash;</span>
      <span class="stub-tag">read-only</span>
    </div>
    {% else %}
    <div class="acc bcomp">
      <button type="button" class="acc-toggle bcomp-toggle" aria-expanded="false">
        <span class="bcomp-label">{{ c.label }}</span>
        <span class="bcomp-count">{{ c.count }}</span>
        <span class="caret" aria-hidden="true">&#9656;</span>
      </button>
      <div class="acc-body">
        <a class="open-full" href="{{ c.path }}">&rarr; open full page</a>
        {% if c.key == "doctrine" %}
          {% for e in c.items %}<div class="brow"><span class="bname">{{ e.section }}</span>{% if e.immutable %}<span class="tag">red-line</span>{% endif %}</div>{% endfor %}
        {% elif c.key == "memory" %}
          {% for l in c.items %}<div class="brow"><span class="bname">{{ l.lesson[:64] }}</span><span class="tag">{{ l.outcome }}</span></div>{% endfor %}
        {% elif c.key == "skills" %}
          {% for s in c.items %}<div class="brow"><span class="bname">{{ s.name }}</span><span class="tag">{{ s.status }}</span></div>{% endfor %}
        {% endif %}
      </div>
    </div>
    {% endif %}
    {% endfor %}
  </div>
</section>
```

Note: `&rarr;` renders as `→`, satisfying the test's `"→ open full page"` assertion (Jinja emits the entity, the browser/response text decodes it — `TestClient` returns decoded text).

- [ ] **Step 4: Create `alpha_web/templates/partials/_pending.html` (placeholder for now)**

```html
<section id="pending" class="acc dsec is-open"{% if pending_oob %} hx-swap-oob="true"{% endif %}>
  <button type="button" class="acc-toggle dsec-toggle" aria-expanded="true">
    Pending changes <span class="count">{{ pending.pending_count if pending else 0 }}</span>
    <span class="caret" aria-hidden="true">&#9656;</span>
  </button>
  <div class="acc-body">
    <p class="empty">Proposed changes will appear here as you teach.</p>
  </div>
</section>
```

- [ ] **Step 5: Create `alpha_web/templates/partials/_drawer.html`**

```html
<div class="drawer-resizer" aria-hidden="true"></div>
<aside class="agent-drawer" id="agent-drawer">
  <div class="drawer-head">
    <span class="drawer-title">Agent</span>
    <button type="button" class="drawer-collapse" aria-expanded="true" aria-label="Collapse panel">&rsaquo;</button>
  </div>
  <div class="drawer-body">
    {% include "partials/_pending.html" %}
    {% include "partials/_brain_panel.html" %}
  </div>
</aside>
```

- [ ] **Step 6: Include the drawer in `cockpit.html`**

Replace the closing of the `.cockpit` section in `alpha_web/templates/cockpit.html` — add the include after `</main>` (before `</section>`):

```html
    <form id="composer" class="composer" hx-post="/evolve/message"
          hx-target="#thread" hx-swap="beforeend" hx-encoding="multipart/form-data"
          hx-on::after-request="this.reset()">
      <input type="hidden" id="composer-session" name="session_id" value="{{ session_id or '' }}">
      <textarea name="text" placeholder="Teach Sonia… (paste text, links; attach .txt/.md/.csv/.pdf)"></textarea>
      <input type="file" name="files" multiple>
      <button type="submit">Send</button>
      <span class="thinking htmx-indicator">thinking…</span>
    </form>
  </main>
  {% include "partials/_drawer.html" %}
</section>
```

- [ ] **Step 7: Wire context in `app.py`**

Add the import near the other `alpha_web` imports (after `alpha_web/app.py:25` `from alpha_web import data_access as da`):

```python
from alpha_web import drawer
```

Replace `_cockpit_ctx` (`alpha_web/app.py:355-360`) with:

```python
    def _cockpit_ctx(request, session: dict | None, banner: str = ""):
        return {"active": "teach",
                "session_id": (session or {}).get("session_id", ""),
                "messages": (session or {}).get("messages", []),
                "sessions": _safe_sessions(),
                "banner": banner,
                "pending": drawer.pending_view(session),
                "brain": drawer.brain_view(da.load_brain())}
```

- [ ] **Step 8: Add drawer CSS**

Append to `alpha_web/static/cockpit.css`:

```css
/* ── right agent drawer ─────────────────────────────────────────────────── */
.cockpit{align-items:stretch}
.drawer-resizer{flex:none;width:6px;cursor:col-resize;border-left:1px solid var(--line)}
.drawer-resizer:hover{background:var(--hover)}
.agent-drawer{flex:none;width:var(--drawer-w,22rem);min-width:0;display:flex;flex-direction:column;border-left:1px solid var(--line);overflow:hidden}
.agent-drawer.is-collapsed{width:2rem}
.agent-drawer.is-collapsed .drawer-body,.agent-drawer.is-collapsed .drawer-title{display:none}
.agent-drawer.flash{animation:drawerflash .8s ease}
@keyframes drawerflash{from{background:var(--gold-soft)}to{background:transparent}}
.drawer-head{display:flex;align-items:center;gap:.4rem;padding:.4rem .6rem;border-bottom:1px solid var(--line)}
.drawer-title{font-family:var(--serif);font-weight:600}
.drawer-collapse{margin-left:auto;border:none;background:none;cursor:pointer;font-size:1.05rem;color:var(--fg-dim)}
.drawer-body{flex:1;overflow-y:auto;padding:.3rem}
/* accordions inside the drawer */
.dsec{border-bottom:1px solid var(--line)}
.acc-toggle{width:100%;display:flex;align-items:center;gap:.4rem;background:none;border:none;cursor:pointer;font:inherit;text-align:left;padding:.4rem .3rem}
.acc-toggle .caret{margin-left:auto;font-size:.7rem;color:var(--fg-faint);transition:transform .15s}
.acc.is-open>.acc-toggle .caret{transform:rotate(90deg)}
.acc>.acc-body{display:none;padding:0 .3rem .4rem}
.acc.is-open>.acc-body{display:block}
.count{font-family:var(--mono);font-size:.72rem;background:var(--track);color:var(--fg-dim);border-radius:.3rem;padding:0 .35rem}
/* pending groups */
.pgroup{border:1px solid var(--line);border-radius:.4rem;padding:.3rem;margin:.3rem 0}
.applied-line{font-size:.8rem;color:var(--fg-dim);margin-top:.3rem}
.empty{color:var(--fg-faint);font-size:.85rem;padding:.3rem}
/* brain components */
.bcomp{border-top:1px solid var(--line)}
.bcomp.is-stub{display:flex;align-items:center;gap:.4rem;padding:.4rem .3rem;color:var(--fg-faint)}
.bcomp-count{font-family:var(--mono);font-size:.72rem}
.stub-tag{margin-left:auto;font-size:.68rem;color:var(--fg-faint);border:1px solid var(--line);border-radius:.3rem;padding:0 .3rem}
.brow{display:flex;align-items:center;gap:.4rem;font-size:.82rem;padding:.15rem .2rem}
.bname{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.brow .tag{margin-left:auto;flex:none;font-size:.7rem;color:var(--fg-dim)}
.open-full{display:inline-block;font-size:.74rem;color:var(--gold);margin:.15rem 0}
/* chat → drawer chip */
.change-chip{display:inline-block;margin-top:.35rem;font-size:.78rem;color:var(--gold);text-decoration:none}
.change-chip:hover{text-decoration:underline}
```

- [ ] **Step 9: Bust the CSS cache**

In `alpha_web/templates/base.html:13`, bump the version query:

```html
  <link rel="stylesheet" href="/static/cockpit.css?v=porcelain4">
```

- [ ] **Step 10: Run the new test + the cockpit regression suite**

Run: `python -m pytest tests/web/test_drawer.py tests/web/test_cockpit.py -q`
Expected: PASS (all Task-1 units + the new drawer-shell test + every existing cockpit test still green).

- [ ] **Step 11: Commit**

```bash
git add alpha_web/drawer.py alpha_web/app.py alpha_web/templates/cockpit.html \
        alpha_web/templates/partials/_drawer.html alpha_web/templates/partials/_pending.html \
        alpha_web/templates/partials/_brain_panel.html alpha_web/static/cockpit.css \
        alpha_web/templates/base.html tests/web/test_drawer.py
git commit -m "feat(web): render the agent drawer shell + live brain mirror on the Teach page"
```

---

## Task 3: PENDING half + OOB wiring (teach lands in the drawer)

Move the edit change-set into the drawer, add the chat chip, and OOB-update the drawer from all four mutation routes. After this task the assistant bubble is prose + chip only; accept/reject/apply/rollback live in the drawer; the CURRENT brain refreshes on apply.

**Files:**
- Create: `alpha_web/templates/partials/_drawer_update.html`
- Modify: `alpha_web/templates/partials/_pending.html` (rewrite `.acc-body`), `alpha_web/templates/partials/edit_card.html`, `alpha_web/templates/partials/message_assistant.html`, `alpha_web/templates/partials/_two_turns.html`, `alpha_web/app.py` (routes `message` `alpha_web/app.py:379-394`, `edit` `:400-406`, `apply` `:408-415`, `rollback` `:417-424`)
- Test: `tests/web/test_drawer.py` (append 3 tests)

**Interfaces:**
- Consumes: `drawer.pending_view`, `drawer.brain_view`, `da.load_brain()`; Sonia client `chat/edit/apply/rollback/get_session` (existing).
- Produces: `POST /evolve/message` returns `_two_turns.html` with OOB `#pending` + `#brain-panel` and a `.change-chip`; `POST /evolve/{sid}/edit/{eid}` returns `_pending.html`; `POST /evolve/{sid}/message/{mid}/apply` and `POST /evolve/rollback/{sid}/{mid}` return `_drawer_update.html` (`#pending` main + `#brain-panel` OOB).

- [ ] **Step 1: Write the failing tests**

Append to `tests/web/test_drawer.py`:

```python
def test_message_lands_edits_in_the_drawer_with_a_chip_not_inline(client, monkeypatch):
    sid_skill = load_seeds("seeds").skills.all()[0].skill_id
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE",
        '{"ops":[{"tool":"patch_skill","args":{"skill_id":"%s","notes":"n"},"rationale":"r"}]}' % sid_skill)
    r = client.post("/evolve/message", data={"text": "patch it"})
    assert r.status_code == 200
    assert 'id="pending"' in r.text and 'hx-swap-oob="true"' in r.text     # drawer refreshes OOB
    assert 'id="brain-panel"' in r.text
    head = r.text.split('id="pending"', 1)[0]                              # chat turns + composer, before the OOB drawer
    assert "change-chip" in head                                          # bubble points at the drawer
    assert "edit-card" not in head                                        # …and no inline cards in the bubble
    assert "edit-card" in r.text and "patch_skill" in r.text              # the edit lives in the drawer's pending section


def test_apply_reflects_in_brain_panel_and_rollback_reverts(client, monkeypatch):
    import re
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE",
        '{"ops":[{"tool":"process_memory",'
        '"args":{"lesson_id":"les-test-1","lesson":"NEW-TEST-LESSON","outcome":"principle"},'
        '"rationale":"teach test"}]}')
    m = client.post("/evolve/message", data={"text": "remember this"})
    sid = re.search(r'id="composer-session"[^>]*value="([^"]+)"', m.text).group(1)
    eid = re.search(r"/edit/([\w-]+)", m.text).group(1)
    # before apply: only proposed — not in the live brain mirror yet (the proposed edit card, which
    # DOES echo the lesson text, lives in #pending; check only the brain-panel portion)
    assert "NEW-TEST-LESSON" not in m.text.split('id="brain-panel"', 1)[1]
    # accept: the Apply form only appears once an edit is accepted, so scrape mid from THIS response
    acc = client.post(f"/evolve/{sid}/edit/{eid}", data={"action": "accept"})
    mid = re.search(r"/message/([\w-]+)/apply", acc.text).group(1)
    ap = client.post(f"/evolve/{sid}/message/{mid}/apply")
    assert 'id="brain-panel"' in ap.text and 'hx-swap-oob="true"' in ap.text
    assert "NEW-TEST-LESSON" in ap.text.split('id="brain-panel"', 1)[1]    # brain mirror reflects the applied lesson
    # rollback reverts the brain. The edit card stays status=applied (Sonia rollback restores the
    # brain snapshot, not edit status), so it still echoes the text in #pending — assert on the mirror.
    rb = client.post(f"/evolve/rollback/{sid}/{mid}")
    assert "NEW-TEST-LESSON" not in rb.text.split('id="brain-panel"', 1)[1]  # gone from the live brain


def test_drawer_mutations_stay_unavailable_when_sonia_down(client):
    webapp.set_sonia_client(SoniaClient(base_url="http://127.0.0.1:9", timeout=0.2))
    for r in (
        client.post("/evolve/s1/edit/e1", data={"action": "accept"}),
        client.post("/evolve/s1/message/m1/apply"),
        client.post("/evolve/rollback/s1/m1"),
    ):
        assert r.status_code == 200 and "unavailable" in r.text.lower()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m pytest tests/web/test_drawer.py -k "lands or reflects or unavailable" -q`
Expected: FAIL — the message response has no OOB `#pending`/`#brain-panel` and the bubble still contains an inline `edit-card`.

- [ ] **Step 3: Rewrite `_pending.html` to render the change-set**

Replace `alpha_web/templates/partials/_pending.html` entirely:

```html
<section id="pending" class="acc dsec is-open"{% if pending_oob %} hx-swap-oob="true"{% endif %}>
  <button type="button" class="acc-toggle dsec-toggle" aria-expanded="true">
    Pending changes <span class="count">{{ pending.pending_count }}</span>
    <span class="caret" aria-hidden="true">&#9656;</span>
  </button>
  <div class="acc-body">
    {% for g in pending.groups %}
    <div class="pgroup">
      {% for e in g.edits %}{% include "partials/edit_card.html" %}{% endfor %}
      {% if g.applied %}
      <div class="applied-line">applied &#10003;
        <form hx-post="/evolve/rollback/{{ session_id }}/{{ g.message_id }}"
              hx-target="#pending" hx-swap="outerHTML" style="display:inline">
          <button type="submit">&#8630; rollback</button>
        </form>
      </div>
      {% elif g.accepted %}
      <form hx-post="/evolve/{{ session_id }}/message/{{ g.message_id }}/apply"
            hx-target="#pending" hx-swap="outerHTML">
        <button type="submit">Apply accepted ({{ g.accepted }})</button>
      </form>
      {% endif %}
    </div>
    {% else %}
    <p class="empty">Proposed changes will appear here as you teach.</p>
    {% endfor %}
  </div>
</section>
```

- [ ] **Step 4: Retarget the accept/reject buttons in `edit_card.html`**

In `alpha_web/templates/partials/edit_card.html`, change both buttons' `hx-target`/`hx-swap` from the per-card id to the whole pending section (so the Apply-count and statuses re-render together):

```html
<div class="edit-card status-{{ e.status }}" id="edit-{{ e.edit_id }}">
  <code>{{ e.tool }}</code> <span>{{ e.summary or e.target_id or "" }}</span>{% if e.target_id %} <code class="target">{{ e.target_id }}</code>{% endif %}
  {% if e.status == "failed" %}<em class="reason">{{ e.apply_reason }}</em>{% endif %}
  {% if e.status in ("proposed", "accepted", "rejected") %}
  <span class="actions">
    <button hx-post="/evolve/{{ session_id }}/edit/{{ e.edit_id }}" hx-vals='{"action":"accept"}'
            hx-target="#pending" hx-swap="outerHTML">accept</button>
    <button hx-post="/evolve/{{ session_id }}/edit/{{ e.edit_id }}" hx-vals='{"action":"reject"}'
            hx-target="#pending" hx-swap="outerHTML">reject</button>
  </span>
  <span class="state">{{ e.status }}</span>
  {% endif %}
</div>
```

- [ ] **Step 5: Replace inline cards with the chip in `message_assistant.html`**

Replace `alpha_web/templates/partials/message_assistant.html` entirely:

```html
<div class="bubble assistant" id="msg-{{ m.message_id }}">
  <div class="prose">{{ m.text | md }}</div>
  {% for d in m.directions %}<div class="direction">▸ {{ d.title }}{% if d.summary %} — {{ d.summary }}{% endif %}</div>{% endfor %}
  {% if m.edits %}<a class="change-chip" href="#agent-drawer" data-flash="agent-drawer">&#8629; {{ m.edits|length }} proposed change{{ "" if m.edits|length == 1 else "s" }} &rarr;</a>{% endif %}
</div>
```

- [ ] **Step 6: Append the OOB drawer refresh to `_two_turns.html`**

Replace `alpha_web/templates/partials/_two_turns.html` entirely:

```html
{% with m = user %}{% include "partials/message_user.html" %}{% endwith %}
{% with m = assistant %}{% include "partials/message_assistant.html" %}{% endwith %}
{# Thread the (possibly newly created) session id back into the composer so the NEXT message stays in
   this session instead of spawning a new one. Out-of-band: replaces the hidden input by id. #}
<input type="hidden" id="composer-session" name="session_id" value="{{ session_id }}" hx-swap-oob="true">
{# Land the turn in the drawer: refresh the PENDING change-set and the CURRENT brain out-of-band. #}
{% with pending_oob = true %}{% include "partials/_pending.html" %}{% endwith %}
{% with brain_oob = true %}{% include "partials/_brain_panel.html" %}{% endwith %}
```

- [ ] **Step 7: Create `_drawer_update.html` (apply/rollback response)**

Create `alpha_web/templates/partials/_drawer_update.html`:

```html
{# apply/rollback response: #pending is the main swap target, #brain-panel updates out-of-band. #}
{% include "partials/_pending.html" %}
{% with brain_oob = true %}{% include "partials/_brain_panel.html" %}{% endwith %}
```

- [ ] **Step 8: OOB-wire the four routes in `app.py`**

Replace the `message` route (`alpha_web/app.py:379-394`):

```python
    @app.post("/evolve/message")
    def message(request: Request, session_id: str = Form(""), text: str = Form(""),
                files: list[UploadFile] = File(default=[])):
        uploads = [(f.filename, f.file.read()) for f in files if f.filename]
        clean, attachments = ingest_attachments(text, uploads)
        try:
            out = _sonia().chat(session_id or None, clean, attachments)
            session = _sonia().get_session(out["session_id"])
        except httpx.HTTPError:
            return render(request, "partials/message_assistant.html",
                          {"session_id": session_id, "m": {"message_id": "err", "role": "assistant",
                           "text": "Sonia service unavailable — start it with `python -m sonia`.",
                           "directions": [], "edits": []},
                           "banner": "unavailable"})
        return render(request, "partials/_two_turns.html",
                      {"session_id": out["session_id"], "user": out["user_message"],
                       "assistant": out["assistant_message"],
                       "pending": drawer.pending_view(session),
                       "brain": drawer.brain_view(da.load_brain())})
```

Replace the `edit` route (`alpha_web/app.py:400-406`):

```python
    @app.post("/evolve/{session_id}/edit/{edit_id}")
    def edit(request: Request, session_id: str, edit_id: str, action: str = Form(...)):
        try:
            _sonia().edit(session_id, edit_id, action)
            session = _sonia().get_session(session_id)
        except httpx.HTTPError:
            return _unavailable(request)
        return render(request, "partials/_pending.html",
                      {"session_id": session_id, "pending": drawer.pending_view(session)})
```

Replace the `apply` route (`alpha_web/app.py:408-415`):

```python
    @app.post("/evolve/{session_id}/message/{message_id}/apply")
    def apply(request: Request, session_id: str, message_id: str):
        try:
            _sonia().apply(session_id, message_id)
            session = _sonia().get_session(session_id)
        except httpx.HTTPError:
            return _unavailable(request)
        return render(request, "partials/_drawer_update.html",
                      {"session_id": session_id, "pending": drawer.pending_view(session),
                       "brain": drawer.brain_view(da.load_brain())})
```

Replace the `rollback` route (`alpha_web/app.py:417-424`):

```python
    @app.post("/evolve/rollback/{session_id}/{message_id}")
    def rollback(request: Request, session_id: str, message_id: str):
        try:
            _sonia().rollback(session_id, message_id)
            session = _sonia().get_session(session_id)
        except httpx.HTTPError:
            return _unavailable(request)
        return render(request, "partials/_drawer_update.html",
                      {"session_id": session_id, "pending": drawer.pending_view(session),
                       "brain": drawer.brain_view(da.load_brain())})
```

- [ ] **Step 9: Run the drawer + cockpit suites**

Run: `python -m pytest tests/web/test_drawer.py tests/web/test_cockpit.py -q`
Expected: PASS — the three new tests pass; existing cockpit tests (including `test_accept_then_apply_then_rollback`, which now finds `patch_skill` in the OOB `#pending`) stay green.

- [ ] **Step 10: Commit**

```bash
git add alpha_web/app.py alpha_web/templates/partials/_pending.html \
        alpha_web/templates/partials/edit_card.html alpha_web/templates/partials/message_assistant.html \
        alpha_web/templates/partials/_two_turns.html alpha_web/templates/partials/_drawer_update.html \
        tests/web/test_drawer.py
git commit -m "feat(web): teaching lands in the drawer — pending change-set + OOB brain refresh"
```

---

## Task 4: Drawer interactions (drag-resize, collapse, accordions, chip flash)

Adds the vanilla JS that animates the Task-2 hooks. Per the codebase's posture (`app.js`/`cockpit.js` are not unit-tested), behavior is verified by asserting the server-rendered hooks exist and the script wires them; the accordion handler uses event delegation so it survives OOB swaps.

**Files:**
- Modify: `alpha_web/static/cockpit.js`
- Test: `tests/web/test_drawer.py` (append one hooks test)

**Interfaces:**
- Consumes: DOM ids/classes from Tasks 2–3 (`#cockpit`, `#agent-drawer`, `.drawer-resizer`, `.drawer-collapse`, `.acc`/`.acc-toggle`, `.change-chip[data-flash]`).
- Produces: no server contract change; `--drawer-w` on `#cockpit`, `.is-collapsed` on `#agent-drawer`, `.is-open` toggling on `.acc`, `.flash` pulse on the drawer.

- [ ] **Step 1: Write the failing hooks test**

Append to `tests/web/test_drawer.py`:

```python
import pathlib


def test_cockpit_js_wires_the_drawer_controls():
    js = pathlib.Path("alpha_web/static/cockpit.js").read_text("utf-8")
    assert "drawer-resizer" in js            # drag-to-resize handler
    assert "--drawer-w" in js                # sets the width custom property
    assert "drawer-collapse" in js           # collapse toggle
    assert "acc-toggle" in js                # delegated accordion handler
    assert "data-flash" in js or "change-chip" in js   # chip → drawer flash
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/web/test_drawer.py::test_cockpit_js_wires_the_drawer_controls -q`
Expected: FAIL — `cockpit.js` has only the autoscroll handler.

- [ ] **Step 3: Extend `alpha_web/static/cockpit.js`**

Append to `alpha_web/static/cockpit.js` (keep the existing autoscroll block):

```javascript
// ── Agent drawer: drag-to-resize + collapse (persisted), accordions, chip flash ──
(() => {
  const cockpit = document.getElementById("cockpit");
  const drawer = document.getElementById("agent-drawer");
  const resizer = document.querySelector(".drawer-resizer");
  const WKEY = "agentDrawerW", CKEY = "agentDrawerCollapsed";

  // restore persisted width + collapsed state
  if (cockpit) {
    const w = localStorage.getItem(WKEY);
    if (w) cockpit.style.setProperty("--drawer-w", w);
  }
  if (drawer && localStorage.getItem(CKEY) === "1") drawer.classList.add("is-collapsed");

  // drag-to-resize: width = distance from the pointer to the cockpit's right edge (clamped)
  if (cockpit && resizer) {
    let dragging = false;
    resizer.addEventListener("pointerdown", (e) => {
      dragging = true; resizer.setPointerCapture(e.pointerId); e.preventDefault();
    });
    resizer.addEventListener("pointermove", (e) => {
      if (!dragging) return;
      const r = cockpit.getBoundingClientRect();
      const w = Math.max(220, Math.min(r.right - e.clientX, r.width - 320));
      const val = w + "px";
      cockpit.style.setProperty("--drawer-w", val);
      localStorage.setItem(WKEY, val);
    });
    resizer.addEventListener("pointerup", () => { dragging = false; });
  }

  // collapse toggle
  const cbtn = document.querySelector(".drawer-collapse");
  if (drawer && cbtn) {
    cbtn.addEventListener("click", () => {
      const c = drawer.classList.toggle("is-collapsed");
      localStorage.setItem(CKEY, c ? "1" : "0");
      cbtn.setAttribute("aria-expanded", c ? "false" : "true");
    });
  }

  // accordions — delegated so OOB-swapped #pending / #brain-panel keep working
  document.body.addEventListener("click", (e) => {
    const btn = e.target.closest(".acc-toggle");
    if (!btn) return;
    const acc = btn.closest(".acc");
    if (!acc) return;
    const open = acc.classList.toggle("is-open");
    btn.setAttribute("aria-expanded", open ? "true" : "false");
  });

  // chat chip → reveal + flash the drawer
  document.body.addEventListener("click", (e) => {
    const chip = e.target.closest(".change-chip[data-flash]");
    if (!chip) return;
    const d = document.getElementById(chip.getAttribute("data-flash"));
    if (!d) return;
    d.classList.remove("is-collapsed");
    localStorage.setItem(CKEY, "0");
    d.classList.remove("flash"); void d.offsetWidth; d.classList.add("flash");
  });
})();
```

- [ ] **Step 4: Run the hooks test + full web suite**

Run: `python -m pytest tests/web/test_drawer.py -q`
Expected: PASS (all drawer tests, including the JS hooks test).

- [ ] **Step 5: Commit**

```bash
git add alpha_web/static/cockpit.js tests/web/test_drawer.py
git commit -m "feat(web): drawer interactions — drag-resize, collapse, accordions, chip flash"
```

---

## Final verification

- [ ] **Run the whole suite offline:**

Run: `python -m pytest -q`
Expected: PASS — the pre-existing count (704) **plus the new `tests/web/test_drawer.py` tests**, zero regressions.

- [ ] **Manual smoke (optional, needs the services):**

```bash
ALPHA_SONIA_PROVIDER=mock python -m sonia &      # :8810
python -m alpha_web                              # :8100 → open /
```
Teach a message that yields an op; confirm the chip appears in the bubble, the edit shows in the drawer's PENDING, accept → Apply reflects in CURRENT brain, rollback reverts, and the drawer drags/collapses.

## Self-review notes (traceability to the spec)

- Spec §PENDING → Task 3 (`_pending.html`, per-message groups, accept/reject/apply/rollback, chip).
- Spec §CURRENT brain (all six, 3 live expandable + 3 stubs, live via `load_brain`) → Task 2 (`_brain_panel.html`, `brain_view`).
- Spec §Approach A (HTMX OOB, one template re-emitted) → Task 3 (`_two_turns.html`, `_drawer_update.html`, `pending_oob`/`brain_oob` flags).
- Spec §resize + collapse → Task 4 (drag `--drawer-w`, `.is-collapsed`, persisted).
- Spec §edge cases: Sonia-down → `test_drawer_mutations_stay_unavailable_when_sonia_down` + `_cockpit_ctx` brain from disk; no-live-brain → `load_brain()` seeds fallback (unchanged); gate-failed edit → `edit_card` `status-failed` reason (unchanged).
- Spec §per-message apply/rollback → `MessageGroup` + reused per-message endpoints; multi-message case renders one group (with its own Apply/rollback) per message, honestly.
- Spec §testing → `test_drawer.py` covers view-model units, `GET /` render, message OOB, accept→apply-reflects-in-brain, rollback-reverts, Sonia-down, and the JS hooks.
```
