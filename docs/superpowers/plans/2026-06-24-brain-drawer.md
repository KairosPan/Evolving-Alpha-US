# Brain Drawer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Group the console's six brain-component views under one inline-accordion **Brain** item in the left rail.

**Architecture:** The rail nav (`NAV` in `alpha_web/app.py`, looped in `base.html`) gains one group entry, **Brain**, whose children are the six components in order. The drawer opens via two complementary mechanisms with **no HTMX**: the server renders the group with class `is-open` whenever the active page is a brain component (so navigation restores state), and a tiny `app.js` handler toggles it manually. The three existing components (doctrine/memory/skills) reuse their real pages; workflow/connector/subagent are new read-only stub routes sharing one template.

**Tech Stack:** FastAPI + Jinja2 (autoescape on), vanilla CSS/JS, pytest + Starlette `TestClient`. No new dependencies.

## Global Constraints

- **No HTMX in the rail.** Sub-items are plain `<a href>` full-page navigations; the accordion toggle is CSS + a vanilla-JS class flip. (Deliberately avoids the HTMX fragment-nesting bug class.)
- **Never a 500.** The three stub routes are pure template renders with constant context — structurally 500-proof.
- **Jinja autoescape stays ON.** No `| safe` anywhere; all stub copy is static literals.
- **Component order is exactly:** Doctrine · Memory · Workflow · Skill · Connector · Subagent.
- **The Skill child keeps the existing key `skills` and path `/skills`** (the page already exists); only its rail label reads "Skill".
- **`BRAIN_KEYS = {"doctrine", "memory", "workflow", "skills", "connector", "subagent"}`** — the set the template checks to auto-expand the drawer.
- Out of scope (do NOT build): real models/stores/meta-tools for workflow/connector/subagent, and any Sonia editing of them.

---

### Task 1: Grouped NAV + Brain accordion markup with server auto-expand

**Files:**
- Modify: `alpha_web/app.py` (the `NAV` list ~lines 40-49; add `BRAIN_KEYS`; add `brain_keys=BRAIN_KEYS` to the Jinja globals in `_make_templates`)
- Modify: `alpha_web/templates/base.html` (the rail nav loop, ~lines with `{% for item in nav %}`)
- Test: `tests/web/test_app.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `NAV` now contains a group dict `{"key": "brain", "label": "Brain", "children": [...]}`; the global `brain_keys` (a set of strings); the rendered rail emits `<div class="nav-group [is-open]">` with a `<button class="nav-item nav-group-toggle" aria-expanded=...>` and a `<div class="nav-sub">` of `<a class="nav-subitem [is-active]">` children. Task 2 relies on the child paths `/workflow`, `/connector`, `/subagent` existing as nav entries.

- [ ] **Step 1: Write the failing tests**

Add to `tests/web/test_app.py`:

```python
def test_brain_group_lists_six_children_in_order(client):
    body = client.get("/").text
    # The six brain components appear, in the spec order, as sub-item links.
    order = ["/doctrine", "/memory", "/workflow", "/skills", "/connector", "/subagent"]
    positions = [body.index(f'href="{p}"') for p in order]
    assert positions == sorted(positions)                 # strictly increasing == in order
    assert 'class="nav-group' in body                     # the drawer group is rendered
    assert "Brain" in body


def test_brain_drawer_auto_expands_only_on_brain_pages(client):
    open_body = client.get("/doctrine").text              # doctrine is a brain component
    assert "nav-group is-open" in open_body
    assert 'aria-expanded="true"' in open_body
    collapsed = client.get("/deck").text                  # deck is NOT a brain component
    assert "nav-group is-open" not in collapsed
    assert 'aria-expanded="false"' in collapsed


def test_active_brain_child_is_marked(client):
    body = client.get("/memory").text
    assert 'class="nav-subitem is-active"' in body        # the open drawer highlights Memory
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/web/test_app.py::test_brain_group_lists_six_children_in_order tests/web/test_app.py::test_brain_drawer_auto_expands_only_on_brain_pages tests/web/test_app.py::test_active_brain_child_is_marked -v`
Expected: FAIL (no `nav-group` markup yet; `/workflow` etc. not in nav).

- [ ] **Step 3: Restructure `NAV` and add `BRAIN_KEYS`**

In `alpha_web/app.py`, replace the existing `NAV = [...]` block with:

```python
NAV = [
    {"path": "/", "key": "teach", "label": "Teach"},
    {"path": "/deck", "key": "deck", "label": "Deck"},
    {"key": "brain", "label": "Brain", "children": [
        {"path": "/doctrine",  "key": "doctrine",  "label": "Doctrine"},
        {"path": "/memory",    "key": "memory",    "label": "Memory"},
        {"path": "/workflow",  "key": "workflow",  "label": "Workflow"},
        {"path": "/skills",    "key": "skills",    "label": "Skill"},
        {"path": "/connector", "key": "connector", "label": "Connector"},
        {"path": "/subagent",  "key": "subagent",  "label": "Subagent"},
    ]},
    {"path": "/decisions", "key": "decisions", "label": "Decisions"},
    {"path": "/verdict", "key": "verdict", "label": "Verdict"},
    {"path": "/evolution", "key": "evolution", "label": "Autonomous"},
]

BRAIN_KEYS = {"doctrine", "memory", "workflow", "skills", "connector", "subagent"}
```

- [ ] **Step 4: Expose `brain_keys` to templates**

In `alpha_web/app.py`, inside `_make_templates()`'s `t.env.globals.update(...)` call, add one line alongside `nav=NAV,`:

```python
        nav=NAV,
        brain_keys=BRAIN_KEYS,
```

- [ ] **Step 5: Render the group in `base.html`**

In `alpha_web/templates/base.html`, replace the existing nav loop:

```html
    {% for item in nav %}
    <a class="nav-item {% if item.key == active %}is-active{% endif %}" href="{{ item.path }}"
       {% if item.key == active %}aria-current="page"{% endif %}>
      <span class="idx">{{ "%02d"|format(loop.index) }}</span>{{ item.label }}
    </a>
    {% endfor %}
```

with:

```html
    {% for item in nav %}
    {% if item.children %}
    {% set group_open = active in brain_keys %}
    <div class="nav-group {% if group_open %}is-open{% endif %}">
      <button type="button" class="nav-item nav-group-toggle"
              aria-expanded="{{ 'true' if group_open else 'false' }}" aria-controls="nav-{{ item.key }}">
        <span class="idx">{{ "%02d"|format(loop.index) }}</span>{{ item.label }}
        <span class="caret" aria-hidden="true">&#9662;</span>
      </button>
      <div class="nav-sub" id="nav-{{ item.key }}">
        {% for c in item.children %}
        <a class="nav-subitem {% if c.key == active %}is-active{% endif %}" href="{{ c.path }}"
           {% if c.key == active %}aria-current="page"{% endif %}>{{ c.label }}</a>
        {% endfor %}
      </div>
    </div>
    {% else %}
    <a class="nav-item {% if item.key == active %}is-active{% endif %}" href="{{ item.path }}"
       {% if item.key == active %}aria-current="page"{% endif %}>
      <span class="idx">{{ "%02d"|format(loop.index) }}</span>{{ item.label }}
    </a>
    {% endif %}
    {% endfor %}
```

- [ ] **Step 6: Run the new tests to verify they pass**

Run: `python -m pytest tests/web/test_app.py::test_brain_group_lists_six_children_in_order tests/web/test_app.py::test_brain_drawer_auto_expands_only_on_brain_pages tests/web/test_app.py::test_active_brain_child_is_marked -v`
Expected: PASS. (`/workflow`/`/connector`/`/subagent` links render in the nav even though their routes arrive in Task 2 — these tests only read the homepage markup.)

- [ ] **Step 7: Run the whole web suite to verify no regressions**

Run: `python -m pytest tests/web/ -q`
Expected: PASS (existing `/doctrine`, `/memory`, `/skills` pages still render; they now sit under the open drawer).

- [ ] **Step 8: Commit**

```bash
git add alpha_web/app.py alpha_web/templates/base.html tests/web/test_app.py
git commit -m "feat(web): group brain components under a Brain rail accordion (markup + auto-expand)"
```

---

### Task 2: Stub routes + shared `brain_stub.html` for workflow/connector/subagent

**Files:**
- Create: `alpha_web/templates/brain_stub.html`
- Modify: `alpha_web/app.py` (add `_BRAIN_STUBS` dict + three GET routes, near the other `@app.get` page routes inside `create_app`)
- Test: `tests/web/test_app.py`

**Interfaces:**
- Consumes: the `render(request, name, ctx)` helper defined in `create_app` (it pops `active` from `ctx` and renders the template); `base.html`; the `brain_keys` auto-expand from Task 1.
- Produces: GET `/workflow`, `/connector`, `/subagent`, each a full HTML page (extends `base.html`) with `active` set to its key.

- [ ] **Step 1: Write the failing tests**

Add to `tests/web/test_app.py`:

```python
@pytest.mark.parametrize("path,title,needle", [
    ("/workflow", "Workflow", "playbooks"),
    ("/connector", "Connector", "connections"),
    ("/subagent", "Subagent", "sub-agents"),
])
def test_brain_stub_pages_render_readonly(client, path, title, needle):
    r = client.get(path)
    assert r.status_code == 200
    assert "<!doctype html>" in r.text.lower()             # full page, not a fragment
    assert title in r.text                                 # component name
    assert needle in r.text                                # the one-line blurb
    assert "not yet built" in r.text.lower()               # honest read-only empty state
    assert "nav-group is-open" in r.text                   # opens under the Brain drawer
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/web/test_app.py::test_brain_stub_pages_render_readonly -v`
Expected: FAIL with 404 (routes not defined yet).

- [ ] **Step 3: Create the shared stub template**

Create `alpha_web/templates/brain_stub.html`:

```html
{% extends "base.html" %}
{% block title %}{{ title }}{% endblock %}
{% block content %}
<section class="brain-stub">
  <h1>{{ title }}</h1>
  <p class="blurb">{{ blurb }}</p>
  <div class="empty-state">Not yet built &mdash; read-only preview. Sonia will manage {{ title|lower }} in a later round.</div>
</section>
{% endblock %}
```

- [ ] **Step 4: Add the stub routes**

In `alpha_web/app.py`, add this module-level dict near `SKILL_STATUSES` (top of file):

```python
_BRAIN_STUBS = {
    "workflow":  ("Workflow",  "Named multi-step playbooks Sonia composes from skills."),
    "connector": ("Connector", "External data/tool connections the agent draws on (Alpaca, EDGAR, MCP feeds…)."),
    "subagent":  ("Subagent",  "Specialized dispatch sub-agents the master agent delegates to."),
}
```

Inside `create_app`, alongside the other page routes (e.g. just after the `/evolution` route), add:

```python
    def _brain_stub(request: Request, key: str):
        title, blurb = _BRAIN_STUBS[key]
        return render(request, "brain_stub.html", {"active": key, "title": title, "blurb": blurb})

    @app.get("/workflow")
    def workflow(request: Request):
        return _brain_stub(request, "workflow")

    @app.get("/connector")
    def connector(request: Request):
        return _brain_stub(request, "connector")

    @app.get("/subagent")
    def subagent(request: Request):
        return _brain_stub(request, "subagent")
```

- [ ] **Step 5: Run the new tests to verify they pass**

Run: `python -m pytest tests/web/test_app.py::test_brain_stub_pages_render_readonly -v`
Expected: PASS (all three params).

- [ ] **Step 6: Extend the existing page-render smoke to cover the new routes**

In `tests/web/test_app.py`, update the `test_pages_render` parametrize list to include the three new paths:

```python
@pytest.mark.parametrize("path", ["/", "/deck", "/doctrine", "/memory", "/skills", "/workflow", "/connector", "/subagent", "/decisions", "/verdict", "/evolution"])
def test_pages_render(client, path):
```

- [ ] **Step 7: Run the whole web suite**

Run: `python -m pytest tests/web/ -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add alpha_web/app.py alpha_web/templates/brain_stub.html tests/web/test_app.py
git commit -m "feat(web): read-only stub views for workflow/connector/subagent"
```

---

### Task 3: Accordion CSS + manual toggle JS

**Files:**
- Modify: `alpha_web/static/app.css` (add nav-group / nav-sub / nav-subitem / caret rules + a `.brain-stub` block; place after the `.rail-foot` rules ~line 111)
- Modify: `alpha_web/static/app.js` (append the toggle handler)
- Test: manual (CSS/JS is not unit-tested in this codebase; the markup it targets is already asserted in Tasks 1-2).

**Interfaces:**
- Consumes: the markup from Task 1 (`.nav-group`, `.nav-group-toggle`, `.nav-sub`, `.nav-subitem`, `.caret`, `.is-open`) and the `brain-stub` markup from Task 2.
- Produces: visual collapse/expand (sub-list hidden unless `.is-open`) and a click handler that toggles `.is-open` + `aria-expanded`.

- [ ] **Step 1: Add the CSS**

Append to `alpha_web/static/app.css` (after the `.rail-foot` rules):

```css
/* Brain drawer (inline rail accordion) */
.nav-group { display: flex; flex-direction: column; }
.nav-group-toggle { width: 100%; background: none; border: none; cursor: pointer; font: inherit; text-align: left; }
.nav-group-toggle .caret { margin-left: auto; font-size: 10px; color: var(--fg-faint); transition: transform .15s; }
.nav-group.is-open .nav-group-toggle .caret { transform: rotate(180deg); }
.nav-sub { display: none; flex-direction: column; gap: 2px; padding: 2px 0 4px 27px; }
.nav-group.is-open .nav-sub { display: flex; }
.nav-subitem {
  padding: 6px 11px; border-radius: var(--r-sm); color: var(--fg-dim);
  font-size: 13px; font-weight: 500; transition: background .15s, color .15s;
}
.nav-subitem:hover { background: rgba(255,255,255,.04); color: var(--fg); }
.nav-subitem.is-active { background: var(--gold-soft); color: var(--fg); box-shadow: inset 2px 0 0 var(--gold); }

/* Brain component stub pages */
.brain-stub { padding: 8px 4px; max-width: 44rem; }
.brain-stub h1 { font-family: var(--serif); font-size: 28px; margin: 0 0 6px; }
.brain-stub .blurb { color: var(--fg-dim); margin: 0 0 18px; }
.brain-stub .empty-state {
  border: 1px dashed var(--line); border-radius: var(--r-sm);
  padding: 14px 16px; color: var(--fg-faint); font-size: 13px;
}
```

- [ ] **Step 2: Add the toggle handler**

Append to `alpha_web/static/app.js`:

```javascript
// Brain drawer: toggle the rail accordion open/closed without navigating.
document.querySelectorAll(".nav-group-toggle").forEach((btn) => {
  btn.addEventListener("click", () => {
    const group = btn.closest(".nav-group");
    const open = group.classList.toggle("is-open");
    btn.setAttribute("aria-expanded", open ? "true" : "false");
  });
});
```

(`app.js` is loaded with `defer`, so the DOM is ready when this runs.)

- [ ] **Step 3: Manual verification (two-process app)**

Start both processes (Sonia + console) per `README.md`, then in a browser at the console:
- Navigate to a non-brain page (e.g. Deck): the **Brain** item shows collapsed (caret down, no sub-items visible).
- Click **Brain**: the six sub-items reveal (caret flips); click again: they hide.
- Click **Doctrine** (or any of the six): full-page navigation; on arrival the drawer is open and that child is highlighted gold.
- Visit **Workflow / Connector / Subagent**: each shows its title, blurb, and the "Not yet built — read-only preview" box, with the drawer open.

Confirm via curl that the markup is intact (no JS needed for this check):

Run: `curl -s http://127.0.0.1:8101/subagent | grep -o 'nav-group is-open\|brain-stub\|Not yet built'`
Expected: prints `nav-group is-open`, `brain-stub`, and `Not yet built`.

- [ ] **Step 4: Run the full suite (guard against accidental breakage)**

Run: `python -m pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add alpha_web/static/app.css alpha_web/static/app.js
git commit -m "style(web): accordion CSS + manual toggle for the Brain drawer"
```

---

## Self-Review

**1. Spec coverage:**
- §2 grouped NAV + Brain group + order + Skill keeps `skills`/`/skills` → Task 1 (NAV block) + Global Constraints. ✓
- §3 server auto-expand + manual JS toggle + numbering → Task 1 (auto-expand, `loop.index` numbering) + Task 3 (toggle). ✓
- §4 existing three reuse routes; three new stub routes + shared template + glosses → Task 2. ✓
- §5 never-500 (pure renders) → Task 2 routes have constant context. ✓
- §6 testing (nav structure, auto-expand, stub routes 200/full-page, existing pages regression) → Tasks 1 & 2 tests + extended `test_pages_render`. ✓
- §7 out of scope (no models, no Sonia editing) → stated in Global Constraints; nothing in the tasks builds them. ✓

**2. Placeholder scan:** No TBD/TODO; every code step shows complete code; commands have expected output. ✓

**3. Type consistency:** `BRAIN_KEYS` (set of str) defined in Task 1 and read in `base.html` as `brain_keys`; child `key` values (`doctrine/memory/workflow/skills/connector/subagent`) match the keys passed as `active` by the stub routes (Task 2) and the existing pages; class names (`nav-group`, `is-open`, `nav-group-toggle`, `nav-sub`, `nav-subitem`, `caret`, `brain-stub`, `empty-state`) are identical across base.html (Task 1), brain_stub.html (Task 2), and the CSS/JS (Task 3). ✓
