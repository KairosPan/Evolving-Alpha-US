# Landing-Doc Adoption Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adopt the in-repo charter copy, write-deny the frozen `../Sonia-Kairos/` design repo, and close the last two 2026-07-08-amendment conformance gaps (`is_conflict` protection for `user_direct`-owned elements; waist-side stamp coherence).

**Architecture:** No new modules. Two one-line-scale changes at existing seams (`alpha/refine/conflict.py`, `alpha/refine/apply.py`) pinned by TDD tests mirroring the package's existing test shapes, plus docs/config adoption (`.claude/settings.json`, `CLAUDE.md`, `ROADMAP.md`, `docs/PROJECT_STATE.md`).

**Tech Stack:** Python 3 / pydantic / pytest (offline, no keys). Spec: `docs/superpowers/specs/2026-07-10-landing-doc-adoption-design.md`.

## Global Constraints

- **Exactly TWO git commits, no push** (user-approved 2026-07-10): commit ① = the charter file alone (Task 1); commit ② = everything else (Task 5). Tasks 2–4 leave changes uncommitted. This overrides the default frequent-commit discipline.
- Full suite must stay green: `python -m pytest -q` (963 tests before this plan; offline, no keys).
- Zero diffs under `tests/loop/` and `tests/eval/` (eval byte-neutrality).
- `CLAUDE.md` stays minimal (~56 lines): net growth ≤ ~3 lines.
- Code, comments, docs in English.
- Never write anything under `/Users/pan/Desktop/self-evolve/Sonia-Kairos/` (it is read-only by user decision; Task 4 encodes this in settings).

---

### Task 1: Commit ① — adopt the charter copy

**Files:**
- Commit (already on disk, untracked): `Evolving-Agent-Design-SoniaKairos.md` (repo root, 574 lines)

**Interfaces:**
- Produces: the tracked charter file later tasks reference by path.

- [ ] **Step 1: Verify the file is present, untracked, and the only staged content**

Run: `cd /Users/pan/Desktop/self-evolve/evolving-alpha-us && git status --short`
Expected: `?? Evolving-Agent-Design-SoniaKairos.md` among the entries (also expect untracked spec/plan files under `docs/superpowers/` — do NOT stage those here).

- [ ] **Step 2: Stage exactly the charter and commit**

```bash
git add Evolving-Agent-Design-SoniaKairos.md
git commit -m "$(cat <<'EOF'
docs: adopt the SoniaKairos charter at repo root (2026-07-08-amended copy)

Moved in by the user 2026-07-10; byte-identical to the design repo's committed
HEAD version (574 lines, all 19 dated 2026-07-08 amendment markers — the
two-hands/user-direct-write axiom, three deferrals, egress clarification — plus
the 2026-07-09 Mem0 decisions). This copy is now the charter's LIVE HOME: future
amendments are edited here with the same dated-marker discipline;
../Sonia-Kairos/ is henceforth a frozen, read-only design reference (write-deny
lands in .claude/settings.json in the follow-up commit).
EOF
)"
```

- [ ] **Step 3: Verify the commit contains only the charter**

Run: `git show --stat HEAD`
Expected: exactly one file changed, `Evolving-Agent-Design-SoniaKairos.md`, +574 lines.

---

### Task 2: D4 — `is_conflict` protects `user_direct`-owned elements

**Files:**
- Modify: `alpha/refine/conflict.py` (the `is_conflict` docstring + final return, lines 21–31)
- Test: `tests/refine/test_conflict.py` (append), `tests/refine/test_apply_provenance_held.py` (append)

**Interfaces:**
- Consumes: `is_conflict(log, op, provenance) -> bool` (existing signature, unchanged).
- Produces: protected-owner semantics `path in ("teaching", "user_direct")` that Task 4's CLAUDE.md gotcha line describes.

- [ ] **Step 1: Write the failing tests**

Append to `tests/refine/test_conflict.py`:

```python
USER = EditProvenance(path="user_direct", proposer="user", human_approver="user")

def _log_with_user_direct_lesson():
    log = EditLog()
    log.append("process_memory", "memory", "u1", "create", rationale="r")
    log.stamp_last(EditProvenance(path="user_direct", proposer="user", human_approver="user"))
    return log

def test_self_study_contesting_user_direct_owned_is_conflict():
    # charter 2026-07-08 second hand: the user's landed edit is a user act — machine contest is held
    log = _log_with_user_direct_lesson()
    op = RefineOp(tool="demote_memory", args={"lesson_id": "u1", "factor": 0.5}, rationale="data says weak")
    assert is_conflict(log, op, SELF) is True

def test_user_direct_op_never_conflicts():
    log = _log_with_teaching_lesson()
    op = RefineOp(tool="demote_memory", args={"lesson_id": "m1", "factor": 0.5}, rationale="r")
    assert is_conflict(log, op, USER) is False            # only self-study can be held
```

Append to `tests/refine/test_apply_provenance_held.py` (uses that file's existing `_h` and `_FakeQueue`):

```python
def test_self_study_contesting_user_direct_is_held_not_applied():
    h = _h(); log = EditLog(); meta = MetaTools(h, log)
    # the user's direct hand creates m9 (sonia POST /edit posture: floors lifted, full stamp)
    try_apply_op(meta, h, RefineOp(tool="process_memory",
                 args={"lesson_id": "m9", "phases": ["trend"], "outcome": "win", "lesson": "user landed this"},
                 rationale="user edit"), allowed=PASS_TOOLS["M"], min_retire_samples=0, min_promote_samples=0,
                 provenance=EditProvenance(path="user_direct", proposer="user", human_approver="user"))
    q = _FakeQueue()
    # self-study tries to demote the user_direct-owned m9 -> HELD, live H unchanged
    rec, reason = try_apply_op(meta, h, RefineOp(tool="demote_memory", args={"lesson_id": "m9", "factor": 0.5},
                 rationale="data weak"), allowed=PASS_TOOLS["M"], min_retire_samples=5, min_promote_samples=3,
                 provenance=EditProvenance(path="self_study", proposer="refiner"), conflict_queue=q)
    assert rec is None and reason.startswith("held_for_review")
    assert len(q.items) == 1
    assert h.memory.get("m9").importance.time_decay == 1.0
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `python -m pytest tests/refine/test_conflict.py tests/refine/test_apply_provenance_held.py -v`
Expected: `test_self_study_contesting_user_direct_owned_is_conflict` FAILS (`assert False is True`); `test_self_study_contesting_user_direct_is_held_not_applied` FAILS (op applies: `rec is None` assertion fails). The other new test passes already (regression guard); all pre-existing tests pass.

- [ ] **Step 3: Minimal implementation**

In `alpha/refine/conflict.py`, replace the `is_conflict` docstring and final return:

```python
def is_conflict(log: EditLog, op: RefineOp, provenance: EditProvenance | None) -> bool:
    """True iff a self-study op contests a teaching- or user_direct-owned existing H element
    (spec §5.4 asymmetry; user_direct added per the charter's 2026-07-08 second hand — both
    hands' landings are user acts, so a machine contest goes to user adjudication)."""
    if provenance is None or provenance.path != "self_study":
        return False                                   # only self-study can be held; user hands apply
    if op.tool not in _CONTEST_VERBS:
        return False                                   # create verbs never contest
    tid = _target_id(op.tool, op.args)
    if tid is None:
        return False
    latest = log.latest_for(_KIND.get(op.tool, ""), tid)
    return (latest is not None and latest.provenance is not None
            and latest.provenance.path in ("teaching", "user_direct"))
```

- [ ] **Step 4: Run the same tests to verify all pass**

Run: `python -m pytest tests/refine/test_conflict.py tests/refine/test_apply_provenance_held.py -v`
Expected: ALL PASS.

- [ ] **Step 5: Ripple check — the conflict/held machinery's consumers**

Run: `python -m pytest tests/refine tests/meta tests/sonia tests/workbench tests/converse -q`
Expected: all pass (teaching-owned behavior unchanged; no production caller pins the old owner set). Do NOT commit.

---

### Task 3: D5 — waist-side stamp coherence (charter drill L491 analog)

**Files:**
- Modify: `alpha/refine/apply.py` (`try_apply_op` docstring + first gate check, around lines 100–116)
- Create: `tests/refine/test_user_direct_stamp.py`

**Interfaces:**
- Consumes: `try_apply_op(..., provenance=...)` (existing signature, unchanged), `ALL_TOOLS` (exported at `alpha/refine/apply.py:19`).
- Produces: rejection reason string `"user_direct requires proposer='user' with human_approver (unstamped direct edit refused)"`.

- [ ] **Step 1: Write the failing drill tests**

Create `tests/refine/test_user_direct_stamp.py`:

```python
# tests/refine/test_user_direct_stamp.py
"""Charter drill (roster extended 2026-07-08): a seeded direct edit whose provenance lacks the
user-authored stamp must be refused at the waist — path="user_direct" requires proposer="user"
AND a human_approver. Mis-stamped ops are rejected BEFORE dispatch and never logged."""
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.harness.metatools import MetaTools
from alpha.harness.edit_log import EditLog, EditProvenance
from alpha.refine.apply import try_apply_op, ALL_TOOLS
from alpha.refine.ops import RefineOp


def _h():
    return HarnessState(doctrine=Doctrine(), skills=SkillRegistry.from_skills([]),
                        memory=MemoryStore.from_lessons([]))


def _apply(provenance):
    h = _h(); log = EditLog(); meta = MetaTools(h, log)
    op = RefineOp(tool="process_memory", args={"lesson_id": "m1", "phases": ["trend"],
                  "outcome": "win", "lesson": "x"}, rationale="direct edit")
    rec, reason = try_apply_op(meta, h, op, allowed=ALL_TOOLS,
                               min_retire_samples=0, min_promote_samples=0, provenance=provenance)
    return rec, reason, log


def test_user_direct_with_wrong_proposer_is_refused_and_unlogged():
    rec, reason, log = _apply(EditProvenance(path="user_direct", proposer="refiner",
                                             human_approver="user"))
    assert rec is None and "user_direct requires" in reason
    assert len(log.records()) == 0


def test_user_direct_without_human_approver_is_refused_and_unlogged():
    rec, reason, log = _apply(EditProvenance(path="user_direct", proposer="user"))
    assert rec is None and "user_direct requires" in reason
    assert len(log.records()) == 0


def test_properly_stamped_user_direct_lands():
    rec, reason, log = _apply(EditProvenance(path="user_direct", proposer="user",
                                             human_approver="user"))
    assert reason is None and rec is not None
    assert rec.provenance.path == "user_direct"
```

- [ ] **Step 2: Run to verify the two refusal tests fail**

Run: `python -m pytest tests/refine/test_user_direct_stamp.py -v`
Expected: the two `*_is_refused_*` tests FAIL (op currently applies → `rec is None` assertion fails); `test_properly_stamped_user_direct_lands` PASSES.

- [ ] **Step 3: Minimal implementation**

In `alpha/refine/apply.py::try_apply_op`, insert as the FIRST check (immediately after `tid = _target_id(op.tool, op.args)`, before the whitelist check):

```python
    # Stamp coherence (charter drill roster, extended 2026-07-08): a direct edit not carrying
    # the user-authored stamp is refused at the waist, before any content check.
    if provenance is not None and provenance.path == "user_direct" and (
            provenance.proposer != "user" or not provenance.human_approver):
        return None, "user_direct requires proposer='user' with human_approver (unstamped direct edit refused)"
```

And update the docstring's gate-order sentence from
`"""Gate order: whitelist -> rationale -> ...` to
`"""Gate order: stamp coherence -> whitelist -> rationale -> ...` (rest unchanged).

- [ ] **Step 4: Run to verify all pass**

Run: `python -m pytest tests/refine/test_user_direct_stamp.py tests/sonia/test_direct_edit.py -v`
Expected: ALL PASS (the sonia `/edit` route already mints the full stamp, so its end-to-end tests confirm no production regression).

- [ ] **Step 5: Waist-wide ripple check**

Run: `python -m pytest tests/refine tests/meta tests/sonia tests/workbench tests/harness -q`
Expected: all pass. Do NOT commit.

---

### Task 4: D2 + D3 + D6 — settings deny, CLAUDE.md, ROADMAP, PROJECT_STATE

**Files:**
- Modify: `.claude/settings.json` (append 3 deny rules)
- Modify: `CLAUDE.md` (header sentence; Governance gotcha; owner-line test count is refreshed in Task 5)
- Modify: `ROADMAP.md` (§6 "Broader meta-agent follow-ups": one new bullet)
- Modify: `docs/PROJECT_STATE.md` (one new dated blockquote entry after the 2026-07-10 entry)

**Interfaces:**
- Consumes: Task 2/3 semantics (the gotcha line describes them).
- Produces: final doc/config state committed by Task 5.

- [ ] **Step 1: Extend the settings deny-list**

`.claude/settings.json` — full new content (absolute `//` form is required: bare patterns resolve against the cwd and leading-`/` patterns anchor to this project root, so neither reaches the sibling; `Read` deliberately not denied — same grep-able posture as `reference/cn`):

```json
{
  "permissions": {
    "deny": [
      "Edit(/reference/cn/**)",
      "Write(/reference/cn/**)",
      "NotebookEdit(/reference/cn/**)",
      "Edit(/spikes/**)",
      "Write(/spikes/**)",
      "NotebookEdit(/spikes/**)",
      "Edit(//Users/pan/Desktop/self-evolve/Sonia-Kairos/**)",
      "Write(//Users/pan/Desktop/self-evolve/Sonia-Kairos/**)",
      "NotebookEdit(//Users/pan/Desktop/self-evolve/Sonia-Kairos/**)"
    ]
  }
}
```

Validate: `python -c "import json; json.load(open('.claude/settings.json')); print('ok')"` → `ok`.

- [ ] **Step 2: CLAUDE.md header sentence**

Read `CLAUDE.md` first (exact wrapping may differ). Replace the charter-entities sentence

> Two charter entities (`../Sonia-Kairos/`): **Sonia** the teacher, **Kairos** the worker.

with

> Two charter entities (charter: `Evolving-Agent-Design-SoniaKairos.md`, moved in-repo 2026-07-10; `../Sonia-Kairos/` = its frozen read-only design home, write-denied via committed settings): **Sonia** the teacher, **Kairos** the worker.

- [ ] **Step 3: CLAUDE.md Governance gotcha**

Replace the whole bullet starting `- **Governance (charter, 2026-07-09).**` with:

```markdown
- **Governance (charter, amended 2026-07-08).** Two hands, one waist: agent proposals need user
  approval (worker edits stage-only — `write_mode="apply"` raises), or the user edits directly
  via sonia `POST /edit` (`user_direct` provenance, sample floors lifted, red-lines still bind;
  revert lever `POST /snapshots/{name}/restore`). Self-study contesting a teaching- or
  user_direct-owned element is held for user adjudication; a mis-stamped `user_direct` op is
  refused at the waist. Live self-study forks-and-proposes (`EvolutionProposal`, user adopts in
  Sonia); in-place autonomy needs `--autonomous` **and** `ALPHA_UNSAFE_AUTONOMOUS=1`. Deviations
  ledger: `docs/superpowers/specs/2026-07-09-charter-conformance-live-governance.md` §5.
```

Check the whole file stays ≈56–59 lines.

- [ ] **Step 4: ROADMAP backlog bullet**

In `ROADMAP.md`, under `**Broader meta-agent follow-ups (also in spec §11):**`, add as the FIRST bullet:

```markdown
- [ ] **Cockpit UI for the user-direct hand** (2026-07-10) — the charter's second hand is live but
  HTTP-only (sonia `POST /edit`; no cockpit control). Add a direct Body-edit surface: form →
  `/edit`, an honest-limits line (a direct edit forgoes packet counsel), and the revert lever
  (`POST /snapshots/{name}/restore`) surfaced next to it. Own brainstorm→spec→plan round
  (deferred from the 2026-07-10 landing-doc adoption by user decision).
```

- [ ] **Step 5: PROJECT_STATE entry**

In `docs/PROJECT_STATE.md`, insert a new blockquote AFTER the `> **2026-07-10 — CLAUDE.md SPEC-COMPLIANCE ROUND SHIPPED (963 tests):**` block (leave a blank line between blocks); write `NNN` for the test count — Task 5 replaces it:

```markdown
> **2026-07-10 — LANDING-DOC ADOPTION (charter in-repo + the last two conformance gaps; NNN tests):**
> the design repo's 2026-07-08 landing manifest (`../Sonia-Kairos/docs/reviews/…-landing.md`)
> mapped onto this repo: its one code-behavioral amendment (user-direct Body write) had already
> shipped 2026-07-09 (D5); adopted now — the charter `Evolving-Agent-Design-SoniaKairos.md`
> lives at repo root (byte-identical to the design repo's committed copy; this copy is the live
> home, `../Sonia-Kairos/` frozen read-only with a committed settings write-deny), and the two
> remaining gaps are closed: (1) `is_conflict` protects `user_direct`-owned elements —
> self-study contesting the user's landed edit is HELD for adjudication (was: silently
> overwritable); (2) waist-side stamp coherence per the charter's extended drill roster —
> `path="user_direct"` without `proposer="user"` + `human_approver` is refused before dispatch,
> unlogged. Spec: `docs/superpowers/specs/2026-07-10-landing-doc-adoption-design.md`.
```

Do NOT commit.

---

### Task 5: Full suite, test-count refresh, commit ②

**Files:**
- Modify: `CLAUDE.md` (owner line count), `docs/PROJECT_STATE.md` (`NNN`)
- Commit: everything from Tasks 2–4 + the spec + this plan

- [ ] **Step 1: Full offline suite**

Run: `python -m pytest -q`
Expected: all pass, 0 failures; note the passing count `N` (963 + 6 new = expected 969).

- [ ] **Step 2: Eval byte-neutrality check**

Run: `git status --short tests/loop tests/eval alpha/loop alpha/eval`
Expected: no output (zero diffs).

- [ ] **Step 3: Write the real count**

- `CLAUDE.md` owner line → `> Owner: KairosPan · reviewed 2026-07-10 · N offline tests.`
- `docs/PROJECT_STATE.md` → replace `NNN tests` with `N tests` in the new entry.

- [ ] **Step 4: Commit ②**

```bash
git add alpha/refine/conflict.py alpha/refine/apply.py \
        tests/refine/test_conflict.py tests/refine/test_apply_provenance_held.py \
        tests/refine/test_user_direct_stamp.py \
        .claude/settings.json CLAUDE.md ROADMAP.md docs/PROJECT_STATE.md \
        docs/superpowers/specs/2026-07-10-landing-doc-adoption-design.md \
        docs/superpowers/plans/2026-07-10-landing-doc-adoption.md
git commit -m "$(cat <<'EOF'
feat: land the 2026-07-08 charter amendments — user_direct owner protection + stamp coherence

Landing-doc adoption round (spec: docs/superpowers/specs/2026-07-10-landing-doc-
adoption-design.md). The amendment's code core (sonia POST /edit, user_direct
provenance) shipped 2026-07-09; this closes the two remaining gaps and adopts
the charter's new home:

- is_conflict: user_direct joins teaching in the protected-owner set — the
  Refiner's self-study contesting an element the user landed directly is now
  HELD for user adjudication instead of silently overwriting it.
- try_apply_op: stamp coherence as the first gate check (charter drill roster,
  extended 2026-07-08) — path="user_direct" without proposer="user" AND
  human_approver is refused before dispatch, unlogged. Drill-pinned.
- .claude/settings.json: write-deny ../Sonia-Kairos/** (absolute form; bare
  patterns are cwd-relative). Machine-specific path accepted: single-operator
  repo. Read stays allowed (grep-able frozen reference).
- CLAUDE.md: charter pointer -> in-repo copy; Governance gotcha gains the
  second hand + held-ownership + stamp-refusal facts; test count refreshed.
- ROADMAP: cockpit UI for the user-direct hand queued (deferred by user);
  PROJECT_STATE: dated adoption entry.
EOF
)"
```

- [ ] **Step 5: Final state check**

Run: `git status --short && git log --oneline -3`
Expected: clean tree (no unstaged production files; stray scratch files are acceptable only if pre-existing); the two new commits on top.
