# Landing-doc adoption — charter moves in-repo + the two remaining conformance gaps

**Date:** 2026-07-10 · **Status:** APPROVED (user, 2026-07-10) — scope option B of three offered
**Mandate:** user: "按照此文档对这个项目做修改，甚至是修改CLAUDE.md" — land
`../Sonia-Kairos/docs/reviews/2026-07-08-kairos-fold-and-charter-amendments-landing.md` into this
repo. The user has moved the charter (`Evolving-Agent-Design-SoniaKairos.md`) into this repo's
root; `../Sonia-Kairos/` is henceforth **read-only**.

## 0. Gap assessment (why this round is small)

The landing doc describes the design repo's 2026-07-08 working tree. Mapped item-by-item onto
this repo (4-agent recon workflow + direct verification):

- **Already built here** — the only code-behavioral amendment, §2.C *User direct-write Body*,
  shipped in the 2026-07-09 charter-conformance arc
  (`docs/superpowers/specs/2026-07-09-charter-conformance-live-governance.md` D3/D5): sonia
  `POST /edit` (`sonia/app.py:223`) lands a user-authored op through the same `try_apply_op`
  waist, stamped `EditProvenance(path="user_direct", proposer="user", human_approver="user")`,
  sample floors lifted (`min_*=0`), structural gates (red-lines, rationale, set-once,
  positive-expectancy promote) still binding — pinned by `tests/sonia/test_direct_edit.py`.
  Rollback coverage (D7 reconcile sweep + `POST /snapshots/{name}/restore` as the revert lever
  for `/edit`, §5.9) also shipped.
- **Not applicable here** — §3 B1–B6 (Backend-Design folds), §4 face docs, §5 prototypes, §6
  NOTES belong to the design repo's future system; the design repo has since committed the whole
  landing (`f956a6f`) plus two later moves (Mem0 substrate `1231d31`; **frontend-design layer
  removed** `56b56e2`, 2026-07-09 — Backend-Design is now the sole design doc). §7/§8 (design
  repo ROADMAP/CLAUDE.md) are done there. §10.1 never_relax deferral is charter text (already in
  the moved copy); this repo's gate is not a monotonic-posture gate.
- **Verified** — the moved charter copy is byte-identical to the design repo's committed HEAD
  version: 574 lines, all 19 `2026-07-08` amendment markers, plus the 2026-07-09 Mem0 decisions.

What remains is adoption (D1–D3), two real conformance gaps (D4–D5), and records (D6).

## D1 — Charter adoption

Commit the root `Evolving-Agent-Design-SoniaKairos.md` (currently untracked) as its own commit.
Semantics: this copy is now the charter's **live home** — future amendments are edited here,
with the same dated-marker discipline the design repo used; `../Sonia-Kairos/` (charter twin,
Backend-Design, ROADMAP, docs/reviews, docs/research) is a frozen, read-only design reference.

## D2 — Read-only enforcement for `../Sonia-Kairos/`

`.claude/settings.json` `permissions.deny` gains three rules (mirroring the `reference/cn` /
`spikes` mechanism):

```
"Edit(//Users/pan/Desktop/self-evolve/Sonia-Kairos/**)",
"Write(//Users/pan/Desktop/self-evolve/Sonia-Kairos/**)",
"NotebookEdit(//Users/pan/Desktop/self-evolve/Sonia-Kairos/**)"
```

Absolute (`//`) form is required: bare patterns resolve against the cwd and leading-`/` patterns
anchor to this project root — neither reaches a sibling directory. `Read` is deliberately not
denied (the folder stays grep-able reference, same posture as `reference/cn`). Accepted cost: a
machine-specific path in a committed file — single-operator repo; noted in the commit message.

## D3 — CLAUDE.md (three spots, minimal-file discipline: net growth ≤ ~3 lines)

1. **Header** — the charter-entities sentence points at the in-repo charter:
   > Two charter entities (charter: `Evolving-Agent-Design-SoniaKairos.md`, moved in-repo
   > 2026-07-10; `../Sonia-Kairos/` is its frozen read-only design home — edits denied via
   > committed settings): **Sonia** the teacher, **Kairos** the worker.
2. **Governance gotcha** — gains the second hand + the held-ownership rule (content normative,
   wording compressible):
   > **Governance (charter, amended 2026-07-08).** Two hands, one waist: agent proposals need
   > user approval (worker edits stage-only — `write_mode="apply"` raises), or the user edits
   > directly via sonia `POST /edit` (`user_direct` provenance, sample floors lifted, red-lines
   > still bind; revert lever `POST /snapshots/{name}/restore`). Self-study contesting a
   > teaching- **or user_direct-**owned element is held for user adjudication. Live self-study
   > forks-and-proposes (`EvolutionProposal`, user adopts in Sonia); in-place autonomy needs
   > `--autonomous` **and** `ALPHA_UNSAFE_AUTONOMOUS=1`. Deviations ledger:
   > `docs/superpowers/specs/2026-07-09-charter-conformance-live-governance.md` §5.
3. **Test count** in the owner line: refresh to the post-round count.

## D4 — Gap A: `is_conflict` protects `user_direct`-owned elements

**Today** (`alpha/refine/conflict.py::is_conflict`, last line): only `teaching`-owned elements
are protected — the Refiner's self-study can silently overwrite an element the user landed via
`/edit`. Charter rule (machine-authority boundary + 2026-07-08 second hand): both hands' landings
are user acts; a machine contest goes to user adjudication.

**Change:** `latest.provenance.path == "teaching"` → `latest.provenance.path in ("teaching",
"user_direct")`; docstring names the charter amendment.

**Tests** (`tests/refine/test_conflict.py` + one integration mirror of
`tests/refine/test_apply_provenance_held.py:44-58`):
- self_study op contesting a `user_direct`-owned element → `is_conflict` True; via
  `try_apply_op` with a `conflict_queue`: record is None, reason startswith `held_for_review`,
  enqueued, live H unchanged.
- a `user_direct`-path op itself never conflicts (only self_study can be held) — regression.
- teaching-owned behavior unchanged — regression.

## D5 — Gap B: waist-side stamp coherence (charter drill L491 analog)

Charter drill roster, extended 2026-07-08: *"a seeded direct edit whose edit event lacks the
user-channel/authored stamp must be refused."* This repo's gate trusts caller-supplied
provenance; `path="user_direct"` with `proposer="refiner"` or no `human_approver` currently
passes.

**Change:** first check in `try_apply_op` (before the whitelist; docstring gate-order updated to
"stamp coherence -> whitelist -> ..."):

```python
if provenance is not None and provenance.path == "user_direct" and (
        provenance.proposer != "user" or not provenance.human_approver):
    return None, "user_direct requires proposer='user' with human_approver (unstamped direct edit refused)"
```

Scope is deliberately `user_direct`-only (the charter drill names exactly the direct-edit case;
other paths' stamps stay caller-trusted — YAGNI).

**Tests** (drill-style, new `tests/refine/test_user_direct_stamp.py` — the waist's home
package): wrong proposer → refused, `len(log) == 0`; missing
`human_approver` → refused, unlogged; correct stamp → lands (and the sonia `/edit` route still
passes end-to-end — existing `tests/sonia/test_direct_edit.py` is the pin).

## D6 — Records & commits

- **PROJECT_STATE.md**: one dated 2026-07-10 entry (charter moved in-repo + this round),
  following the file's existing section format.
- **ROADMAP.md** §6 (Sonia cockpit follow-ups): new backlog bullet — *Cockpit UI for the
  user-direct hand* (form → `POST /edit`; honest-limits line — a direct edit forgoes packet
  counsel; revert lever surfaced). API-only today; own brainstorm→spec→plan round. (Deferred
  from this round by user decision 2026-07-10.)
- **Commits: two, no push** (user-approved, mirroring the landing doc's §10.4 split):
  1. charter copy adoption (frozen input, alone);
  2. this round — settings deny + CLAUDE.md + D4 + D5 + tests + this spec + records.

## Acceptance

- Full suite green (963 + new tests); zero diffs under `tests/loop/`, `tests/eval/`.
- `is_conflict` holds self_study-vs-`user_direct` contests; gate refuses incoherent
  `user_direct` stamps; both pinned by tests.
- `../Sonia-Kairos/**` write-denied by committed settings; charter tracked at repo root;
  CLAUDE.md pointers current.
