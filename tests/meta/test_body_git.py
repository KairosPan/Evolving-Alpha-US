"""A5 — Body-Store-as-git. The Body (brain.json) under one git repo per instance: every landed
op = one commit carrying provenance; audit = the commit trail; rollback reconciled with the
existing snapshot/epoch restore; opt-in/default-off (byte-identical when off); Applier-alone
(only save/restore commit; the observation channel never does)."""
from __future__ import annotations

import shutil
import subprocess

import pytest

from alpha.harness.edit_log import EditProvenance
from alpha.meta.body_git import _GITIGNORE, GitBodyStore, make_brain_store
from alpha.meta.store import LiveBrainStore

requires_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def _git(root, *args) -> str:
    return subprocess.run(["git", "-C", str(root), *args],
                          capture_output=True, text=True, check=True).stdout.strip()


def _commit_count(root) -> int:
    out = subprocess.run(["git", "-C", str(root), "rev-list", "--count", "HEAD"],
                         capture_output=True, text=True)
    return int(out.stdout.strip()) if out.returncode == 0 else 0


# ---------------------------------------------------------------- opt-in / default-off

def test_factory_off_returns_plain_livebrainstore(tmp_path):
    store = make_brain_store(tmp_path)                      # git defaults False
    assert type(store) is LiveBrainStore                    # exact class, not a subclass
    h, log = store.load()
    store.save(h, log)
    assert not (tmp_path / ".git").exists()                 # no repo created when off


def test_factory_off_is_byte_identical_to_livebrainstore(tmp_path):
    # Two independent runs of the same op sequence — one via the factory (off), one via the raw
    # class — must produce byte-identical brain.json.
    a, b = tmp_path / "a", tmp_path / "b"
    for root, store in ((a, make_brain_store(a)), (b, LiveBrainStore(b))):
        h, log = store.load()
        log.append("promote_skill", "skill", "base_breakout", "promote", "x", rationale="why")
        store.save(h, log)
    assert (a / "brain.json").read_bytes() == (b / "brain.json").read_bytes()


def test_factory_on_returns_git_store(tmp_path):
    store = make_brain_store(tmp_path, git=True)
    assert isinstance(store, GitBodyStore)


def test_factory_on_without_git_binary_raises(tmp_path, monkeypatch):
    monkeypatch.setattr("alpha.meta.body_git.shutil.which", lambda _n: None)
    with pytest.raises(RuntimeError, match="git"):
        make_brain_store(tmp_path, git=True)


# ---------------------------------------------------------------- commit-per-apply

@requires_git
def test_genesis_then_one_op_is_one_commit(tmp_path):
    store = GitBodyStore(tmp_path)
    h, log = store.load()
    store.save(h, log)                                      # genesis (empty log)
    n0 = _commit_count(tmp_path)
    assert n0 == 1
    log.append("promote_skill", "skill", "base_breakout", "promote", "x", rationale="why")
    store.save(h, log)                                      # one landed op
    assert _commit_count(tmp_path) == n0 + 1               # exactly one new commit


@requires_git
def test_commit_carries_provenance_and_anchors(tmp_path):
    store = GitBodyStore(tmp_path)
    h, log = store.load()
    store.save(h, log)
    log.append("promote_skill", "skill", "base_breakout", "promote", "x", rationale="deliberate")
    log.stamp_last(EditProvenance(path="teaching", proposer="sonia", human_approver="alice"))
    store.save(h, log)
    msg = _git(tmp_path, "log", "-1", "--format=%B")
    assert "promote_skill" in msg and "base_breakout" in msg
    assert "teaching" in msg and "sonia" in msg and "alice" in msg
    assert "deliberate" in msg
    assert "Body-Head-Seq:" in msg
    assert f"Body-Chain-Head: {log.chain_head()}" in msg      # A4 external anchor


@requires_git
def test_no_op_save_makes_no_empty_commit(tmp_path):
    store = GitBodyStore(tmp_path)
    h, log = store.load()
    store.save(h, log)                                      # genesis
    n0 = _commit_count(tmp_path)
    store.save(h, log)                                      # identical content — no new commit
    assert _commit_count(tmp_path) == n0


@requires_git
def test_committer_is_the_applier(tmp_path):
    store = GitBodyStore(tmp_path)
    h, log = store.load()
    store.save(h, log)
    assert _git(tmp_path, "log", "-1", "--format=%an") == "Kairos Applier"


# ---------------------------------------------------------------- git tip == brain.json

@requires_git
def test_git_tip_equals_brainjson(tmp_path):
    store = GitBodyStore(tmp_path)
    h, log = store.load()
    store.save(h, log)
    for i in range(3):
        log.append("promote_skill", "skill", f"s{i}", "promote", "x", rationale="r")
        store.save(h, log)
    assert _git(tmp_path, "show", "HEAD:brain.json") == (tmp_path / "brain.json").read_text().strip()


# ---------------------------------------------------------------- rollback / revert

@requires_git
def test_restore_makes_forward_revert_commit_and_rolls_back(tmp_path):
    store = GitBodyStore(tmp_path)
    h, log = store.load()
    store.save(h, log)                                      # genesis
    snap = store.snapshot("pre")                            # pre-op history copy (log empty)
    log.append("promote_skill", "skill", "base_breakout", "promote", "x", rationale="why")
    store.save(h, log)                                      # op1
    assert store.edit_count() == 1
    n_before = _commit_count(tmp_path)
    store.restore(snap)                                     # the revert lever's mechanism
    assert store.edit_count() == 0                          # rolled back (epoch = len(log))
    assert _commit_count(tmp_path) == n_before + 1          # append-only: a NEW revert commit
    assert _git(tmp_path, "log", "-1", "--format=%s").startswith("revert")
    # git tip still mirrors the on-disk brain exactly
    assert _git(tmp_path, "show", "HEAD:brain.json") == (tmp_path / "brain.json").read_text().strip()


# ---------------------------------------------------------------- Applier-alone

@requires_git
def test_only_brainjson_tracked_observation_channel_excluded(tmp_path):
    store = GitBodyStore(tmp_path)
    h, log = store.load()
    store.save(h, log)                                      # genesis
    n0 = _commit_count(tmp_path)
    # The observation channel + operational scaffolding drop files INTO the brain dir:
    (tmp_path / "brain.db").write_bytes(b"sqlite-observation-store")   # EpisodeStore
    (tmp_path / ".brain.lock").write_bytes(b"")                        # fcntl lock
    store.snapshot("hist")                                             # history/ pre-apply copy
    # Even a blanket add stages nothing but the Body — the whitelist .gitignore enforces it.
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    tracked = set(_git(tmp_path, "ls-files").splitlines())
    assert tracked == {".gitignore", "brain.json"}
    assert _commit_count(tmp_path) == n0                    # observation writes made no commit


@requires_git
def test_inplace_mutation_without_save_makes_no_commit(tmp_path):
    # apply_credit-style: mutate in-memory SkillStats, never call save() -> no commit.
    store = GitBodyStore(tmp_path)
    h, log = store.load()
    store.save(h, log)
    n0 = _commit_count(tmp_path)
    sk = h.skills.all()[0]
    sk.stats.record(True)                                  # observation channel, in-place
    # no store.save(...)
    assert _commit_count(tmp_path) == n0


@requires_git
def test_adopt_proposal_commits_via_polymorphism(tmp_path):
    """The TCB adopt path (alpha/meta/evolution.py) gets Body-git for FREE: it calls bstore.save()
    polymorphically, so passing a GitBodyStore makes the landing a commit — evolution.py unchanged."""
    from alpha.harness.metatools import MetaTools
    from alpha.meta.evolution import adopt_proposal, run_forked_evolution
    from alpha.meta.proposal_store import ProposalQueue
    from alpha.refine.apply import PASS_TOOLS, try_apply_op
    from alpha.refine.ops import RefineOp

    store = GitBodyStore(tmp_path)
    h, log = store.load()
    store.save(h, log)                                      # genesis (seeds)
    n0 = _commit_count(tmp_path)

    def runner(fh, flog):
        op = RefineOp(tool="process_memory",
                      args={"lesson_id": "m-forked", "phases": ["trend"], "outcome": "win", "lesson": "x"},
                      rationale="fork evidence")
        rec, reason = try_apply_op(MetaTools(fh, flog), fh, op, allowed=PASS_TOOLS["M"],
                                   min_retire_samples=5, min_promote_samples=3,
                                   provenance=EditProvenance(path="self_study", proposer="refiner"))
        assert rec is not None, reason
        return fh, flog

    prop = run_forked_evolution(store, runner, queue=ProposalQueue(str(tmp_path / "p")), kind="refine")
    assert prop is not None
    ok, reason = adopt_proposal(store, prop)               # snapshot() + save() -> ONE commit
    assert ok, reason
    assert _commit_count(tmp_path) == n0 + 1
    msg = _git(tmp_path, "log", "-1", "--format=%B")
    assert "process_memory" in msg and "self_study" in msg and "m-forked" in msg


# ---------------------------------------------------------------- review fix 1: best-effort mirror

@requires_git
def test_commit_failure_does_not_abort_apply_and_self_heals(tmp_path, monkeypatch):
    """The git leg is an audit MIRROR — a transient commit failure must NOT abort a LANDED op (else
    the face raises between the brain save and the derived-record put -> a 500 for a landed op + a
    retry that re-applies -> duplicate records). brain.json is authoritative; the mirror self-heals."""
    store = GitBodyStore(tmp_path)
    h, log = store.load()
    store.save(h, log)                                     # genesis (commits)
    n_genesis = _commit_count(tmp_path)

    real_run, fail = store._run, {"on": True}

    def flaky(*args, **kw):                                # break ONLY `git commit`
        if fail["on"] and args and args[0] == "commit":
            raise subprocess.CalledProcessError(1, ["git", "commit"])
        return real_run(*args, **kw)
    monkeypatch.setattr(store, "_run", flaky)

    log.append("promote_skill", "skill", "s0", "promote", "x", rationale="r")
    store.save(h, log)                                     # commit FAILS — save must NOT raise
    assert _commit_count(tmp_path) == n_genesis            # mirror lagged one save
    assert store.edit_count() == 1                         # brain.json advanced (authoritative)

    fail["on"] = False                                     # git healthy again
    log.append("promote_skill", "skill", "s1", "promote", "x", rationale="r")
    store.save(h, log)                                     # next save catches up
    assert _commit_count(tmp_path) == n_genesis + 1        # exactly ONE catch-up commit
    msg = _git(tmp_path, "log", "-1", "--format=%B")
    assert "s0" in msg and "s1" in msg                     # delta spans the lagged record + the new one


# ---------------------------------------------------------------- review fix 2: forced identity

@requires_git
def test_committer_identity_forced_over_ambient_env(tmp_path, monkeypatch):
    """GIT_AUTHOR_*/GIT_COMMITTER_* outrank `-c user.*`; an operator/CI that exported them must not
    re-attribute Body commits away from the Applier."""
    for k in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        monkeypatch.setenv(k, "Ambient Impostor")
    for k in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        monkeypatch.setenv(k, "impostor@evil.test")
    store = GitBodyStore(tmp_path)
    h, log = store.load()
    store.save(h, log)
    assert _git(tmp_path, "log", "-1", "--format=%an|%cn") == "Kairos Applier|Kairos Applier"
    assert _git(tmp_path, "log", "-1", "--format=%ae|%ce") == "applier@kairos.local|applier@kairos.local"


# ---------------------------------------------------------------- review fix 3: whitelist self-repair

@requires_git
def test_whitelist_self_repairs_every_save(tmp_path):
    """The observation-channel exclusion must not be conditional on init having run: an absent/
    edited-away whitelist is repaired on the next save, so brain.db stays out of the Body."""
    store = GitBodyStore(tmp_path)
    h, log = store.load()
    store.save(h, log)                                     # genesis writes the whitelist
    (tmp_path / ".gitignore").write_text("", encoding="utf-8")   # operator wipes it
    (tmp_path / "brain.db").write_bytes(b"observation-store")    # + drops an observation file
    log.append("promote_skill", "skill", "s0", "promote", "x", rationale="r")
    store.save(h, log)                                     # next save repairs + still excludes
    assert (tmp_path / ".gitignore").read_text() == _GITIGNORE
    assert set(_git(tmp_path, "ls-files").splitlines()) == {".gitignore", "brain.json"}


# ---------------------------------------------------------------- review fix 4: fail loud if ignored

@requires_git
def test_ignored_brainjson_fails_loud_and_does_not_advance(tmp_path, monkeypatch):
    """An UNTRACKED brain.json under a hostile ignore rule would make `git add` silently skip it —
    the audit empty forever (not self-healing). That permanent misconfig fails loud PRE-write, so the
    apply aborts cleanly (nothing persisted, no lag/duplicate)."""
    # A pre-existing repo whose .gitignore hides brain.json, with the whitelist repair disabled so
    # the hostile rule survives (brain.json never gets tracked).
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
    (tmp_path / ".gitignore").write_text("brain.json\n", encoding="utf-8")
    store = GitBodyStore(tmp_path)
    monkeypatch.setattr(store, "_write_whitelist", lambda: None)
    h, log = store.load()
    with pytest.raises(RuntimeError, match="ignores brain.json"):
        store.save(h, log)
    assert not (tmp_path / "brain.json").exists()          # clean abort: brain.json never written
