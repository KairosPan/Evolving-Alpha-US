# CLAUDE.md

Early-stage project — **expect large architectural changes; trust the code over any doc,
including this one.** This file stays deliberately small: identity, durable red lines, commands.
Current-architecture detail lives in per-directory CLAUDE.mds that auto-load where relevant
(`alpha/` map+collisions+current-architecture guards · `alpha/arena/` · `alpha_web/` · `sonia/` ·
`workbench/`) — after a big refactor, rewrite those freely; this root should barely change.

> Owner: KairosPan · reviewed 2026-07-10 · 963 offline tests.

## What this is

**Sonia-Kairos-US-Stock** — a self-evolving US-stock decision-support co-pilot, built on the
轮回 doctrine (`../evolving-alpha/轮回.docx`) + the Continual Harness two-loop architecture
(paper 2605.09998). Daily: screen → regime read → LLM agent → ranked `DecisionPackage`; a
Refiner evolves the playbook `H` overnight. Two entities (named after the `../Sonia-Kairos/`
design charter): **Sonia** = teacher (`alpha/meta/` + `sonia/` :8810), **Kairos** = worker
(`alpha/converse/` + `alpha/arena/` + `workbench/` :8820). Governance converged to the charter
2026-07-09; the deviations ledger is
`docs/superpowers/specs/2026-07-09-charter-conformance-live-governance.md` §5.

## Red lines — these survive any refactor

- **Co-pilot only.** Never submits live orders; every `DecisionPackage` requires explicit human
  confirmation. Not financial advice.
- **PIT firewall.** No future leakage, ever: corp actions key on `announce_date` (never
  `ex_date`), prices stored raw/unadjusted, windowed features trailing-only, learned artifacts
  carry `learned_asof`. Four firewall regression tests pin this — keep them green.
- **One write-waist.** Every brain mutation flows through `refine/apply.py::try_apply_op`;
  red-line doctrine entries are immutable. No side channels, whatever shape the code takes.
- **Honest eval.** Gross returns, stated not assumed; a delisting/halt-to-zero scores −1.0,
  never silently dropped.
- `reference/cn/` + `spikes/` are **read-only reference** (edits denied via
  `.claude/settings.json`); they contain look-alike twins of core files that searches will hit.
- **All English** — code, comments, docs. Tests run fully offline
  (`FakeSource`/`MockLLMClient`, temp=0); add a test next to what you change.

## Commands

```bash
pip install -e ".[dev]"       # extras as needed: [live] [web] [sonia]
python -m pytest -q           # full suite, offline, no keys
python -m alpha_web           # :8100 ─┐
python -m sonia               # :8810  ├─ run/env details: each service's CLAUDE.md
python -m workbench           # :8820 ─┘
```

## Orientation

`alpha/` layers, roughly: perception (`data→universe→state→regime`) · the playbook (`harness/`)
· act (`agent/`) · score (`eval/sizing/guard`) · self-evolution (`refine/loop`) · faces
(`meta/converse/arena`). Apps talk over HTTP, never imports. **Bare names collide across
packages** (`agent.py` ×3, `registry.py` ×3, "harness"/"kairos" mean different things across
repos) — read `alpha/CLAUDE.md` before editing there. Backlog: `ROADMAP.md` · built log:
`docs/PROJECT_STATE.md` · memory: `MEMORY.md`.
