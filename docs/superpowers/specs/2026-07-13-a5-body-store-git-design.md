# A5 — Body-Store-as-git (design)

Status: spec, 2026-07-13. Closes Backend-Design §4 **G2**; DEVELOPMENT-PLAN §2 **A5**.
Charter: *Second Founding Principle* ("the **Body Store**, one git repository per Kairos instance";
"Write access to the Body remote is the **Applier's alone**") + *Body Persistence & Versioning*
("Applier's apply = commit; the deliberation-ID … lives in the commit message"; "revert = checkout
of an earlier approved commit + reconcile the other stores"; "a **Body version** *is* the commit
hash").

Composes with **A4** (hash-chained `EditLog`): the A4 chain is the *logical* audit (each record salted
by its predecessor); git is the *physical/storage* audit + rollback substrate. A4 asked for "an
external chain-head anchor (git-committed head hash …)" — A5 supplies it: every Body commit message
carries `Body-Chain-Head: <chain_hash>`.

## 1. What the Body is, today

The live evolving Body is `brain.json` (`HarnessState` + `EditLog`, one JSON) under
`LiveBrainStore` (`alpha/meta/store.py`, root `ALPHA_LIVE_BRAIN_DIR`, default `./state/brain`). The
two faces (Sonia :8810, workbench :8820) mutate the ONE shared brain through `LiveBrainStore` file
locks. The apply→persist flow is always: `bstore.lock()` → `load()` → (`snapshot(pre-apply)`) →
`try_apply_op(...)` (mutates in-memory) → `save(h, log)` (atomic `brain.json` write). Rollback =
`restore(history_path)` + a cross-face reconcile sweep keyed on `len(log)`.

Two things the Body is **not**, and A5 must keep them out of the Body git:

- **`SnapshotStore`** (`alpha/harness/snapshot.py`, TCB) — the refine-loop's in-run versioned
  checkpoints (`snap_NNNN.json`), used by `HarnessManager`. A *different* mechanism from the live
  brain; A5 does not touch it.
- **The observation channel** — `apply_credit`'s in-place `SkillStats` and the `EpisodeStore`
  (`brain.db`, SQLite, default `./state/brain.db` — a **sibling** of the brain dir, not inside it).
  These are the deliberate ungated bypasses (CLAUDE.md); they must NEVER produce a Body commit.

## 2. The seam: commit rides `save()`/`restore()`, polymorphically

`try_apply_op` (the write-waist, TCB) mutates **in-memory** — it never persists. Persistence is the
store's `save()`. So the commit-per-apply seam is **the store, not the gate**: a landed op reaches
disk through exactly one `save()`, and that is where the commit belongs. This means **A5 touches
zero TCB files** — the gate, `SnapshotStore`, `metatools`, `edit_log`, `conflict`, `evolution` all
stay byte-identical.

Design: a thin subclass

```
class GitBodyStore(LiveBrainStore):
    def save(self, harness, log):   # super().save() then commit the delta
    def restore(self, path):        # super().restore() then commit a forward "revert"
```

Because every landing path already calls `bstore.save()` on a `LiveBrainStore` handle —
`sonia/app.py` (`/edit`, `/apply`), `workbench/app.py` (`/edits/{id}/approve`), and crucially
`alpha/meta/evolution.py::adopt_proposal` (**TCB**, calls `bstore.save(new_h, log)`) — passing a
`GitBodyStore` in makes all of them commit **through polymorphism, with no change to the callee**.
`adopt_proposal` gets Body-git for free; `evolution.py` is not edited.

### 2.1 Factory + opt-in flag (default-off, byte-identical)

```
def make_brain_store(root, *, seeds_dir=None, git=False):
    if not git: return LiveBrainStore(root, seeds_dir=seeds_dir)   # today, unchanged
    if shutil.which("git") is None: raise RuntimeError(...)        # fail loud, never drop audit
    return GitBodyStore(root, seeds_dir=seeds_dir)
```

The flag is `Settings.body_git` ← env **`ALPHA_BODY_GIT`** (default `False`). Only the three
`_brain_store()`/live-brain construction sites route through the factory (Sonia, workbench, and the
two self-study scripts `refine_live`/`evolve_from_episodes`); `alpha_web` stays a plain read-only
`LiveBrainStore` (it never saves). **Unset ⇒ `make_brain_store` returns a plain `LiveBrainStore` —
the exact class shipping today — so every existing brain.json test is byte-identical.** Merging A5
activates nothing.

## 3. Git layout

**One git repo rooted at `ALPHA_LIVE_BRAIN_DIR`.** Tracked content is **`brain.json` only** (the
Body). A whitelist `.gitignore`, written at init, enforces it:

```
*
!.gitignore
!brain.json
```

Rationale for tracking brain.json ALONE (not `history/`):

- The **commit trail IS the version history** the charter wants ("a Body version *is* the commit
  hash"). Committing the `history/` pre-apply snapshots too would duplicate that history and bloat
  the repo unboundedly (keep-last-K pruning is still a deferred small-pool item).
- The whitelist makes the observation channel **physically incapable** of entering the Body git:
  `brain.db` (even if mis-pointed inside the dir), `.brain.lock`, `*.tmp`, `history/` are all
  excluded — even a `git add -A` stages nothing but `brain.json`. This is the Applier-alone /
  observation-channel-separate invariant enforced **at the git level**, not merely by convention.

`history/` snapshot files remain exactly as today — the operational restore targets the faces
reference by path — living alongside the repo, untracked.

**Committer identity is fixed**: `Kairos Applier <applier@kairos.local>`, passed per-commit via
the `GIT_{AUTHOR,COMMITTER}_{NAME,EMAIL}` **env vars** (which outrank both `-c` and repo/global
config, so an operator/CI that exported an ambient `GIT_AUTHOR_*` cannot re-attribute Body commits),
with `-c user.name/email` as belt-and-suspenders and `-c commit.gpgsign=false` so a global
`commit.gpgsign=true` can't hang an unattended apply. Commits are then independent of machine git
config (offline-test-safe) and the committer literally *names the Applier* — reinforcing "write
access is the Applier's alone" at the identity layer.

## 4. Commit-per-apply + provenance-in-commit

On `save(h, log)`:
1. `_prepare_audit()` (PRE-write) — `mkdir` + `git init` on first use + **(re)assert** the whitelist
   `.gitignore` every save (self-repairs an absent/edited-away whitelist), then the fail-loud audit
   guard: if `git check-ignore brain.json` reports it ignored, raise **before** anything is written
   (§6.1) — a clean all-or-nothing abort, no partial state.
2. `super().save(h, log)` — the unchanged atomic `brain.json` write (finalizes the A4 chain).
   brain.json is now authoritative.
3. `_commit("apply")` — **best-effort** (§6.2). `git add -A` (whitelist ⇒ only `brain.json`/
   `.gitignore` stageable). If `git diff --cached --quiet` reports **no staged change**, skip (never
   an empty commit). Else commit. The **delta** = records with `seq ≥ prev_len`, where `prev_len` =
   the log length in `git show HEAD:brain.json` (0 on the unborn branch / genesis). Message:

```
apply seq <a>..<b>: <tool> <kind>/<id>          # single op: "apply seq N: <tool> <kind>/<id>"

seq=<n> tool=<tool> target=<kind>/<id> op=<op>
  provenance: path=<path> proposer=<proposer> approver=<human_approver> evidence=<evidence_kind>
  rationale: <rationale>
...
Body-Head-Seq: <len(log)-1>
Body-Chain-Head: <log.chain_head() or none>
```

`provenance` is read straight off each delta `EditRecord.provenance` (stamped at the gate). The
`Body-Head-Seq` / `Body-Chain-Head` trailers are machine-parseable: the head-seq is the git-native
epoch pointer, the chain-head is A4's external anchor. Genesis (materialize seeds, empty log) commits
as `genesis: materialize seeds (0 records)`.

**Granularity.** One `save()` ⇒ one commit. The single-op landing paths (`/edit`, workbench
`/approve`) are therefore strictly **one landed op ↔ one commit** (the acceptance gate). The Sonia
`/apply` batch lands a whole accepted set in one `save()` ⇒ one commit **listing every delta record**
— which is exactly the charter's model (a *deliberation* is one commit; "the deliberation-ID … lives
in the commit message"). No landed op ever escapes the git trail.

## 5. Rollback reconciled with snapshot/epoch semantics

The existing rollback is **one mechanism**: `restore(history_path)` rewrites `brain.json` from a
pre-apply `history/` snapshot, then the face runs the cross-face reconcile sweep keyed on `len(log)`
(the "epoch"). A5 does **not** add a second, divergent rollback path. Instead:

`GitBodyStore.restore(path)` = `super().restore(path)` (the unchanged file-restore) **then a forward
commit** `revert: restore <name> (head seq <N>)`. Git history is **append-only**: a revert is a new
commit restoring earlier content, never a branch reset. Consequences:

- The git tip **equals** on-disk `brain.json` — after apply *and* after revert — whenever the
  best-effort commit succeeds. So the reconcile sweep (which reads `len(log)` off the just-restored
  brain) and the git trail agree. (On a transient commit failure the mirror lags one save and
  self-heals next commit — §6.2; brain.json is always authoritative.)
- The audit stays complete: `git log` shows the applies AND the revert, in order. You can see that a
  rollback happened and to what head-seq.
- The revert lever `POST /snapshots/{name}/restore` and `rollback_message` / workbench `/rollback`
  are **unchanged** — they call `bstore.restore()`, which now also emits the revert commit. The
  cross-face derived-state reconcile ("still reconciles derived state across both faces") is
  untouched.

**Honest limit (registered).** A5 restores content from the `history/` snapshot **file** and
reconciles git *to* it, rather than doing a true `git checkout <commit>`-driven revert. The history
snapshots are keyed by face message ids (`{sid}-{mid}`, `approve-{eid}`, `user-edit-{id}`), not
commit hashes, and the faces persist `snapshot_before` as a file path; migrating rollback to be
git-checkout-driven would rewrite the (TCB-adjacent) restore flow and both faces — out of scope for
an opt-in, tight-footprint arc. The append-only-mirror keeps the git trail faithful without touching
the rollback substrate. A future arc (natural fit: A10's joint `(H-version, body-digest)` change-set
rollback) can promote history snapshots to first-class commits so revert becomes a checkout.

## 6. The Applier-alone invariant

"Write access is the Applier's alone." In this single-machine, no-remote build, that reduces to:
**only the write-waist persistence path (`save`/`restore`) commits to the Body git; nothing else
does.** Enforced three ways:

1. The **only** code that runs `git commit` on the Body repo is `GitBodyStore.save`/`restore`. There
   is no other caller of the git wrapper on this repo.
2. The observation channel writes a **different file** (`brain.db`, SQLite) which is (a) a sibling of
   the brain dir by default and (b) whitelist-excluded even if mis-pointed inside — so `EpisodeStore`
   writes can never be committed. `apply_credit`'s in-place `SkillStats` mutation touches only
   in-memory `HarnessState`; with no `save()` it produces no commit (and when a later legitimate
   `save()` does persist, that is the Applier's commit, not the observation channel's).
3. The commit runs **inside** `bstore.lock()` (the faces already hold the fcntl flock across
   load→apply→save), so commits are serialized — no concurrent git-index corruption, no extra lock.

### 6.1 The git leg must NEVER abort a landed op (audit-mirror, not source of truth)

brain.json is the live-read source; git is its mirror. If a git failure could raise out of `save()`
*after* `super().save()` advanced brain.json, the face handler would abort **between** the brain
write and its derived-record put (`applied_seqs` / `sstore.put`) → a 500 for a *landed* op, a derived
audit that lags the brain, and a retry that re-applies the still-"accepted" edit → **duplicate
EditRecords**. So:

- **Best-effort commit (§6.2).** `_commit()` wraps `git add`/`commit` (and restore's revert) in
  try/except; a transient failure (`.git/index.lock`, disk-full-on-`.git`, a hostile global hook) is
  **logged and swallowed**, `save()` returns normally, brain.json stays authoritative. The delta is
  computed against the **last committed** `brain.json` (`git show HEAD:brain.json`), so the next
  successful save's commit spans every record since the last one that actually landed — the mirror
  **self-heals** with no lag at the operation level. This makes plain `LiveBrainStore`'s
  all-or-nothing property hold for the apply even with the git leg bolted on.
- **Two fail-LOUD exceptions** — permanent misconfigurations that would silently empty the audit
  *forever* (never self-healing), so refusal is correct: **git absent** (caught at the factory,
  before construction) and **brain.json git-ignored** (caught in `_prepare_audit` PRE-write, so the
  apply aborts cleanly — nothing persisted, no lag, no duplicate). `git check-ignore` reports only an
  *untracked* ignored path (a tracked brain.json still commits), which is exactly the silent-drop
  case; a transient `check-ignore` error is treated as not-ignored (no false abort).

## 7. Honest limits & deferrals

- **Not a security boundary.** Under the accepted T2-shell operator-trust posture (CLAUDE.md;
  A4 §), a live shell can reach the brain dir and `git`-mutate it around the store. A5 is
  audit/versioning, not enforcement; the compensating control (kernel `SandboxedEnv` + a writer
  sidecar so the Body volume is read-only to the sandbox) is A10, deferred/commercial. Commit-signing
  ("Body write-path hardening", charter) is likewise deferred.
- **Git-repo, not remote.** The charter's "Body **remote** … Applier's alone; sandboxes get a
  read-only checkout and no push credential" needs a remote + credential split — that is A9
  (two-class credentials) + A10. A5 is the local-repo leg only.
- **Single-store, not cross-store.** The charter's apply-commit-last / boot-reconcile spans three
  stores (git · vault · Mem0). Vault is A9; Mem0 is A11 (undecided). A5 delivers the **git leg**; the
  cross-store reconcile is explicitly future work.
- **`history/` untracked** (§3) → the git repo alone does not carry the pre-apply snapshots; they
  remain file-side. Acceptable because the commit trail already versions every landed state.
- **Batch = one commit** (§4) — not one-commit-per-op for the Sonia `/apply` batch; documented as the
  charter deliberation model.

## 8. TCB accounting

| File | TCB? | A5 change |
|---|---|---|
| `alpha/refine/apply.py` (gate) | yes | none — commit rides `save()`, not the gate |
| `alpha/harness/snapshot.py` (version authority) | yes | none — different mechanism |
| `alpha/harness/{metatools,edit_log,manager,doctrine}.py` | yes | none |
| `alpha/refine/{ops,conflict}.py` | yes | none |
| `alpha/meta/evolution.py` (adopt) | yes | none — polymorphic `bstore.save()` |
| `alpha/meta/proposal_store.py` | yes | none |
| `alpha/{memory,arena,agent,data}/…` TCB files | yes | none |
| `alpha/meta/store.py` (`LiveBrainStore`) | **no** (already excluded) | none — subclassed, not edited |
| `alpha/meta/body_git.py` | **no** (new) | new: `GitBodyStore` + `make_brain_store` |
| `alpha/settings.py` | no | +`body_git` field / `ALPHA_BODY_GIT` |
| `sonia/app.py`, `workbench/app.py`, `scripts/refine_live.py`, `scripts/evolve_from_episodes.py` | no | `_brain_store()` → factory |

**Zero TCB files change ⇒ `tcb.lock` stays valid ⇒ `gen_tcb_lock.py --check` stays 0; no regen.**
`GitBodyStore` is deliberately **not** added to the TCB, matching the existing exclusion of
`LiveBrainStore` (the actual brain writer): it is a storage/audit wrapper, not an
enforcement/immutability surface, and it is opt-in/default-off. Whether the Body-write mechanism
*should* eventually join the TCB is a human call (TCB additions are human-only) — flagged for the
user, not taken unilaterally.

## 9. Test plan (offline; real-git where the mechanism is exercised, skip-if-absent)

- factory off ⇒ plain `LiveBrainStore`, no `.git`; byte-identical roundtrip.
- one landed op ⇒ exactly one new commit; message carries tool/target/provenance + trailers.
- restore ⇒ a forward `revert` commit; git tip == restored brain.json; log append-only (count up).
- Applier-alone: an `EpisodeStore`/`brain.db` write inside the repo dir is untracked (gitignored),
  commit count unchanged; an in-place mutation with no `save()` ⇒ no commit.
- only `brain.json` (+`.gitignore`) tracked; `git show HEAD:brain.json` == on-disk bytes.
- `ALPHA_BODY_GIT` requested but git absent ⇒ `RuntimeError` (fail loud).
- face wiring (Sonia): with `ALPHA_BODY_GIT=1`, `/edit` lands one commit; `/snapshots/{name}/restore`
  emits a revert commit and the cross-face sweep still runs.
- **§6.1 failure posture (review):** a failing `git commit` (injected) does NOT raise out of `save()`,
  brain.json advances, and the next successful save's commit spans the lagged record + the new one
  (self-heal); the committer identity holds even under ambient `GIT_AUTHOR_*/GIT_COMMITTER_*`; a wiped
  whitelist self-repairs on the next save (brain.db stays untracked); an untracked ignored brain.json
  ⇒ `RuntimeError` pre-write (brain.json never advances).
