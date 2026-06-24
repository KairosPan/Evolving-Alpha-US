# Brain Drawer (left-rail accordion) — Design

**Date:** 2026-06-24
**Status:** Approved (brainstorming), pending implementation plan.

## 0. Goal

Group the console's view of the meta-agent brain — *the editable surface Sonia
modifies* — under a single **Brain** item in the left rail that expands
drawer-style (inline accordion) to reveal its six component categories:

```
Doctrine · Memory · Workflow · Skill · Connector · Subagent
```

This round is **UI-first**: the three components that already exist
(doctrine, memory, skills) are re-homed under Brain and wired to their existing
read-only views; the three new ones (workflow, connector, subagent) get
read-only **stub** views. Making Sonia actually edit the three new components —
and giving them real models/stores/meta-tools — is explicitly **out of scope**
for this round (see §7).

## 1. Background (current state)

- The brain is `H = HarnessState(doctrine, skills, memory)` — only these three
  component types exist (`alpha/harness/loader.py`). Each has a model, a store,
  meta-tools (`alpha/harness/metatools.py`), and a read-only console page.
- `workflow`, `connector`, `subagent` **do not exist anywhere** in the code.
- The rail nav is data-driven: `alpha_web/app.py` defines a flat list `NAV` of
  `{path, key, label}` dicts, injected as a Jinja global and looped in
  `base.html` with `loop.index` for the `NN` numbering. Today Doctrine / Memory
  / Skills are top-level nav items.
- Navigation is plain full-page `<a href>` — there is no HTMX in the rail. The
  Brain drawer keeps it that way (deliberately — it sidesteps the HTMX
  fragment-nesting bug class).

## 2. Nav model

`NAV` changes from a flat list to a list that may contain a **group**. Exactly
one group is introduced: **Brain**. Its children are the six components, in the
user's order:

| order | label     | key         | path         | view                      |
|-------|-----------|-------------|--------------|---------------------------|
| 1     | Doctrine  | `doctrine`  | `/doctrine`  | existing real page        |
| 2     | Memory    | `memory`    | `/memory`    | existing real page        |
| 3     | Workflow  | `workflow`  | `/workflow`  | **new** read-only stub    |
| 4     | Skill     | `skills`    | `/skills`    | existing real page        |
| 5     | Connector | `connector` | `/connector` | **new** read-only stub    |
| 6     | Subagent  | `subagent`  | `/subagent`  | **new** read-only stub    |

The Skill child keeps the existing `skills` key and `/skills` route (the page
already exists); only its rail label reads "Skill" to match the requested list.

Top-level nav after the change (Doctrine / Memory / Skills removed from top
level, folded into Brain):

```
01 Teach   02 Deck   03 Brain ▾   04 Decisions   05 Verdict   06 Autonomous
```

Concrete shape (illustrative — exact field names finalized in the plan):

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
```

A small helper exposes the set of brain child keys
(`BRAIN_KEYS = {"doctrine","memory","workflow","skills","connector","subagent"}`)
so the template can decide whether the drawer is open for the current `active`.

## 3. Rail rendering & the drawer mechanic

Rendered in `base.html`. Two complementary parts — no HTMX, no server round-trip
to toggle:

1. **Server-side auto-expand.** The Brain group renders with class `is-open`
   whenever `active in BRAIN_KEYS`, and the matching child gets `is-active`. So
   navigating to `/doctrine` lands on a full page with the drawer already open
   and Doctrine highlighted. When `active` is not a brain key, the group renders
   collapsed.

2. **Client-side manual toggle.** The "Brain ▾" header is a `<button>` that a
   tiny JS handler (in the existing `app.js`/`cockpit.js`) toggles: it flips
   `is-open` on the group and updates `aria-expanded`. CSS shows/hides the
   `.nav-sub` child list off `.is-open`. This lets the user peek/collapse
   without navigating. No persistence across page loads is required — auto-expand
   (part 1) restores the correct state after any navigation.

Numbering: the top-level loop numbers only top-level entries (`NN`). The Brain
group renders its own `NN` like any top-level item; its children are indented
and **unnumbered** (matches the approved mockup).

Accessibility: the toggle button carries `aria-expanded`; the sub-list is a
labelled region. Children are ordinary links.

## 4. Component views

- **Doctrine / Memory / Skill** — unchanged routes and templates
  (`/doctrine`, `/memory`, `/skills`). They keep their existing `active` keys
  (`doctrine` / `memory` / `skills`), which are all in `BRAIN_KEYS`, so they
  render under the open drawer.

- **Workflow / Connector / Subagent** — three **new** GET routes
  (`/workflow`, `/connector`, `/subagent`), each rendering one shared template
  `brain_stub.html` with a per-component context `{title, blurb}`. The stub
  shows: the component name, a one-line description, and an empty-state line
  noting that Sonia will manage it and that editing arrives in a later round.
  Read-only; cannot 500.

Stub copy (the one-line glosses, approved):

- **Workflow** — "Named multi-step playbooks Sonia composes from skills."
- **Connector** — "External data/tool connections the agent draws on (Alpaca,
  EDGAR, MCP feeds…)."
- **Subagent** — "Specialized dispatch sub-agents the master agent delegates to."

Each stub also carries a short, explicit "Not yet built — read-only preview"
empty state so it never reads as a finished feature.

## 5. Data flow & error handling

- The rail is rendered from the static `NAV` global plus `active`; no new data
  source, no Sonia call, no brain read beyond the existing `brain_badge()`
  already in the rail. The drawer cannot fail.
- The three stub routes are pure template renders with constant context —
  no I/O, structurally 500-proof. (The existing never-500 posture for the
  Sonia-dependent routes is untouched.)

## 6. Testing

- **Nav structure:** `NAV` contains a Brain group whose children are the six
  components in the specified order with the specified keys/paths.
- **Auto-expand:** `GET /doctrine` (and the other five) renders the Brain group
  with `is-open` and the active child marked; a non-brain page (`GET /deck`)
  renders the group collapsed (no `is-open`).
- **Toggle markup:** the Brain header is a button with `aria-expanded`.
- **Stub routes:** `GET /workflow`, `/connector`, `/subagent` each return 200,
  contain their title + blurb + the "not yet built" empty state, and are full
  pages (extend base — they are top-level navigations, not fragments).
- **Existing pages:** `/doctrine`, `/memory`, `/skills` still return 200 and
  render their real content (regression).
- JS toggle behavior itself is not unit-tested (consistent with the codebase's
  treatment of `app.js`); the server-rendered auto-expand carries the tested
  state.

## 7. Out of scope (deferred to a later round)

- Real models / stores / seed data for workflow, connector, subagent.
- Meta-tools + gated-apply path so Sonia can **edit** the three new components
  (today Sonia edits only doctrine/skills/memory via the Teach chat).
- Any write/edit UI inside the drawer. The drawer is navigation + read-only
  views only; brain edits continue to flow exclusively through the Teach chat
  with Sonia.

These become their own brainstorm → spec → plan rounds, one per component type
(each needs its own model and meaning before Sonia can touch it).

## 8. Files touched (anticipated)

- `alpha_web/app.py` — restructure `NAV`; add `BRAIN_KEYS`; add three stub routes.
- `alpha_web/templates/base.html` — render the Brain group / accordion.
- `alpha_web/templates/brain_stub.html` — **new** shared stub view.
- `alpha_web/static/app.css` (or `cockpit.css`) — `.nav-group` / `.nav-sub` /
  `.is-open` styles + indentation.
- `alpha_web/static/app.js` (or `cockpit.js`) — the toggle handler.
- `tests/web/test_app.py` — nav structure, auto-expand, stub routes, regressions.
