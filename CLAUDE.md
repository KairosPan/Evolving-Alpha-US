# CLAUDE.md

Early-stage project; the code will keep changing, so **this file describes — it doesn't
prescribe.** When a description here disagrees with the tree, the code is current and the
description gets updated. This is the only CLAUDE.md — deeper detail lives in the code itself
and in `docs/`.

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

## Standing properties (current facts, pinned by tests)

- **A co-pilot by design.** There is no order-submission path; every `DecisionPackage` goes to
  a human for explicit confirmation. Not financial advice.
- **Point-in-time discipline.** Data access is PIT-guarded: corp actions key on
  `announce_date` (not `ex_date`), prices are stored raw/unadjusted, windowed features use
  trailing bars only, learned artifacts carry `learned_asof`. Four firewall regression tests
  pin this.
- **One write-waist.** Brain mutations flow through `refine/apply.py::try_apply_op`; red-line
  doctrine entries are immutable objects.
- **Honest eval.** Returns are gross (stated, not assumed); a delisting/halt-to-zero scores
  −1.0 rather than being dropped.
- `reference/cn/` and `spikes/` are read-only reference material (edits denied via
  `.claude/settings.json`); they contain look-alike twins of core files that searches will hit.
- Code, comments and docs are in English; the test suite runs fully offline
  (`FakeSource`/`MockLLMClient`, temp=0), with tests living next to what they cover.

## Commands

```bash
pip install -e ".[dev]"       # extras as needed: [live] [web] [sonia]
python -m pytest -q           # full suite, offline, no keys
python -m alpha_web           # :8100 ─┐
python -m sonia               # :8810  ├─ run/env details: README quickstart sections
python -m workbench           # :8820 ─┘
```

## Orientation

`alpha/` layers, roughly: perception (`data→universe→state→regime`) · the playbook (`harness/`)
· act (`agent/`) · score (`eval/sizing/guard`) · self-evolution (`refine/loop`) · faces
(`meta/converse/arena`). Apps talk over HTTP, never imports. **Bare names collide across
packages** (`agent.py` ×3, `registry.py` ×3, `store.py` ×2; "harness" here = the evolvable
playbook `H`, which the `../Sonia-Kairos/` charter calls the Body; lowercase `kairos` = the
sibling CN legal-agent repo) — qualify by package before editing. Backlog: `ROADMAP.md` ·
built log: `docs/PROJECT_STATE.md` · memory: `MEMORY.md`.
