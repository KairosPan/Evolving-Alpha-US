"""A5 — Body-Store-as-git (spec docs/superpowers/specs/2026-07-13-a5-body-store-git-design.md).

The Body (brain.json) as ONE git repository per Kairos instance. `GitBodyStore` extends
`LiveBrainStore` so a landed op reaches disk through exactly one `save()` — and that is where the
Applier's commit rides. Because every landing path (Sonia /edit·/apply, workbench /approve, and the
TCB `adopt_proposal`) already calls `bstore.save()`, passing a GitBodyStore in makes them all commit
through polymorphism with ZERO change to those callers or to any TCB file.

Failure posture (A5 review): the git repo is an AUDIT MIRROR of brain.json, never the live-read
source, so the git leg must NEVER abort the actual apply/restore. brain.json is written FIRST
(atomic, authoritative) and the commit is BEST-EFFORT — a transient git failure (index.lock,
disk-full-on-.git, a hostile global hook) is logged and swallowed, leaving the mirror one save
behind; the delta is computed against the last COMMITTED brain.json, so the next successful save
catches up automatically. The two fail-LOUD conditions are permanent misconfigurations that would
silently empty the audit forever: git absent (caught at the factory) and brain.json git-ignored
(caught pre-write, so the apply aborts cleanly with nothing persisted — no lag, no duplicate).

Opt-in / default-off: `make_brain_store(root, git=False)` returns a plain `LiveBrainStore` (today,
byte-identical). Only when `ALPHA_BODY_GIT` (via `Settings.body_git`) is set does the git-backed
store activate. Not a security boundary (T2-shell operator-trust posture); the git-remote /
read-only-checkout / commit-signing hardening is A9/A10. See the spec for honest limits.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path

from alpha.harness.edit_log import EditLog, EditRecord
from alpha.harness.state import HarnessState
from alpha.meta.store import LiveBrainStore

_log = logging.getLogger(__name__)

# The committer literally names the Applier — reinforcing "write access is the Applier's alone" at
# the identity layer. Forced via the GIT_{AUTHOR,COMMITTER}_* ENV VARS (which outrank both `-c` and
# repo/global config, so an operator/CI that exported an ambient GIT_AUTHOR_* cannot re-attribute
# Body commits); the `-c` flags are belt-and-suspenders + gpgsign=false so a global
# commit.gpgsign=true can't make an unattended apply hang.
_IDENTITY = ["-c", "user.name=Kairos Applier", "-c", "user.email=applier@kairos.local",
             "-c", "commit.gpgsign=false"]
_ENV_IDENTITY = {
    "GIT_AUTHOR_NAME": "Kairos Applier", "GIT_AUTHOR_EMAIL": "applier@kairos.local",
    "GIT_COMMITTER_NAME": "Kairos Applier", "GIT_COMMITTER_EMAIL": "applier@kairos.local",
}

# Whitelist: version ONLY brain.json (the Body). Everything else — the history/ pre-apply snapshots,
# the episodic observation store (brain.db / *.db), the fcntl .brain.lock, tmp files — is excluded,
# so the Applier's commit can carry only the Body. This enforces the Applier-alone /
# observation-channel-separate invariant at the git level: even a blanket `git add -A` stages nothing
# else. brain.json sits at the repo root (no excluded parent), so the re-include is honoured. It is
# (re)asserted on EVERY save (not only at init) so an absent/edited-away whitelist self-repairs.
_GITIGNORE = ("# A5 Body Store — version ONLY the Body (brain.json). See body_git.py.\n"
              "*\n!.gitignore\n!brain.json\n")


class GitBodyStore(LiveBrainStore):
    """LiveBrainStore whose save()/restore() also mirror the Body into a per-instance git repo.

    save()  -> the unchanged atomic brain.json write, then a BEST-EFFORT commit carrying the landed
               op(s)' provenance + the A4 chain-head anchor (the commit trail is the physical audit).
    restore() -> the unchanged file-restore, then a BEST-EFFORT FORWARD 'revert' commit (git history
               stays append-only; the git tip mirrors brain.json). Rollback semantics — which
               snapshot, the cross-face reconcile sweep keyed on len(log) — are untouched.
    snapshot() -> inherited; the history/ copies stay untracked (they are the operational restore
               targets, not the versioned Body)."""

    # ---- git plumbing (stdlib subprocess; no gitpython) -------------------------------------
    def _run(self, *args, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(self._root), *_IDENTITY, *args],
                              capture_output=True, text=True, check=check,
                              env={**os.environ, **_ENV_IDENTITY})

    def _write_whitelist(self) -> None:
        gi = self._root / ".gitignore"
        if not gi.exists() or gi.read_text(encoding="utf-8") != _GITIGNORE:
            gi.write_text(_GITIGNORE, encoding="utf-8")   # self-repair (write-if-absent/if-changed)

    def _prepare_audit(self) -> None:
        """Ready the repo for a commit. Fail LOUD only for the permanent 'brain.json is ignored'
        misconfig — checked PRE-write, so a raise aborts the apply cleanly (nothing persisted, no
        lag/duplicate). Transient init/whitelist errors are swallowed: the commit is best-effort and
        self-heals next save. (git-absent is the other fail-loud, caught at the factory.)"""
        self._root.mkdir(parents=True, exist_ok=True)
        try:
            if not (self._root / ".git").exists():
                self._run("init", "-q")
            self._write_whitelist()
        except (subprocess.CalledProcessError, OSError) as e:
            _log.warning("Body-git setup failed (audit retries next save): %s", e)
            return
        # Definitive returncode 0 == brain.json is ignored -> the audit would be silently empty.
        # A transient error (128) leaves returncode != 0 -> treated as not-ignored, no false abort.
        if self._run("check-ignore", "-q", "brain.json", check=False).returncode == 0:
            raise RuntimeError(
                "Body repo ignores brain.json — the audit trail would be silently empty; refusing to "
                "proceed (repair the repo's .gitignore/excludes). A5 audit-integrity fail-loud guard.")

    def _has_head(self) -> bool:
        return self._run("rev-parse", "--verify", "-q", "HEAD", check=False).returncode == 0

    def _nothing_staged(self) -> bool:
        return self._run("diff", "--cached", "--quiet", check=False).returncode == 0

    def _head_log_len(self) -> int:
        """Log length of the currently-COMMITTED brain.json (0 before the first commit). Used to
        slice the delta (records landed since the last SUCCESSFUL commit) — reading HEAD, not
        in-process state, is what lets a lagged mirror self-heal: the next commit's delta spans every
        record since the last one that actually landed."""
        r = self._run("show", "HEAD:brain.json", check=False)
        if r.returncode != 0:
            return 0
        try:
            return len(json.loads(r.stdout).get("log", []))
        except (json.JSONDecodeError, KeyError, TypeError):
            return 0

    def head_commit(self) -> str | None:
        """The Body version = the HEAD commit hash (charter: 'a Body version *is* the commit hash').
        None on an empty repo. The external anchor A4 asked for, surfaced for /evolution."""
        return self._run("rev-parse", "-q", "--verify", "HEAD", check=False).stdout.strip() or None

    # ---- commit messages -------------------------------------------------------------------
    @staticmethod
    def _record_block(r: EditRecord) -> str:
        p = r.provenance
        prov = (f"path={p.path} proposer={p.proposer} approver={p.human_approver} "
                f"evidence={p.evidence_kind}") if p is not None else "path=<unstamped>"
        return (f"seq={r.seq} tool={r.tool} target={r.target_kind}/{r.target_id} op={r.op}\n"
                f"  provenance: {prov}\n"
                f"  rationale: {r.rationale}")

    def _apply_message(self, delta: list[EditRecord], log: EditLog) -> str:
        head_seq = f"{len(log) - 1}" if len(log) else "none"
        trailers = f"Body-Head-Seq: {head_seq}\nBody-Chain-Head: {log.chain_head() or 'none'}"
        if delta:
            if len(delta) == 1:
                r = delta[0]
                subject = f"apply seq {r.seq}: {r.tool} {r.target_kind}/{r.target_id}"
            else:
                subject = f"apply seq {delta[0].seq}..{delta[-1].seq}: {len(delta)} records"
            body = "\n".join(self._record_block(r) for r in delta)
            return f"{subject}\n\n{body}\n\n{trailers}"
        subject = (f"genesis: materialize seeds ({len(log)} records)" if not self._has_head()
                   else f"checkpoint: {len(log)} records (chain finalized)")
        return f"{subject}\n\n{trailers}"

    @staticmethod
    def _revert_message(name: str, log: EditLog) -> str:
        head_seq = f"{len(log) - 1}" if len(log) else "none"
        return (f"revert: restore {name} (head seq {head_seq})\n\n"
                f"restored brain.json to snapshot {name}; log truncated to {len(log)} records\n\n"
                f"Body-Head-Seq: {head_seq}\nBody-Chain-Head: {log.chain_head() or 'none'}")

    # ---- the write-waist commit seam (best-effort mirror) ----------------------------------
    def _commit(self, kind: str, *, log: EditLog | None = None, name: str = "") -> None:
        """Stage + commit the Body. BEST-EFFORT: a transient git failure is logged and swallowed so
        it can NEVER abort the apply/restore that already advanced brain.json (the authoritative
        state). The mirror lags one save and self-heals on the next successful commit."""
        try:
            self._run("add", "-A")                 # whitelist -> only brain.json/.gitignore stageable
            if self._nothing_staged():
                return                             # identical content -> no empty commit
            if kind == "apply":
                delta = log.records()[self._head_log_len():]
                msg = self._apply_message(delta, log)
            else:                                  # revert
                _, rlog = self.load()
                msg = self._revert_message(name, rlog)
            self._run("commit", "-q", "-m", msg)
        except (subprocess.CalledProcessError, OSError) as e:
            _log.warning("Body-git %s commit failed; brain.json is authoritative, the audit mirror "
                         "will catch up on the next save: %s", kind, e)

    def save(self, harness: HarnessState, log: EditLog) -> Path:
        self._prepare_audit()                      # pre-write: fail loud on ignored brain.json (#4),
        path = super().save(harness, log)          # repair whitelist (#3); then the unchanged write.
        self._commit("apply", log=log)             # best-effort mirror (#1) — never aborts the apply
        return path

    def restore(self, snapshot_path: str) -> None:
        self._prepare_audit()
        super().restore(snapshot_path)             # unchanged file-restore (the rollback substrate)
        self._commit("revert", name=Path(snapshot_path).stem)


def make_brain_store(root, *, seeds_dir=None, git: bool = False) -> LiveBrainStore:
    """The one construction seam. git=False (default) -> a plain LiveBrainStore, byte-identical to
    today. git=True (ALPHA_BODY_GIT via Settings.body_git) -> the git-backed Body store; if the git
    binary is absent we FAIL LOUD rather than silently drop the audit trail the flag asked for."""
    if not git:
        return LiveBrainStore(root, seeds_dir=seeds_dir)
    if shutil.which("git") is None:
        raise RuntimeError("ALPHA_BODY_GIT is set but `git` is not installed; "
                           "refusing to run the Body store without its audit trail")
    return GitBodyStore(root, seeds_dir=seeds_dir)
