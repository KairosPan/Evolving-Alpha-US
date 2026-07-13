"""P0.5 — the write-waist (try_apply_op) normalizes create-path phases with the vocabulary stamped
ON THE H being edited (`h.vocabulary`), NOT the process env, so a live growth-H edit keeps its
scale-typed tokens and a momo-H edit stays momo even under a divergent ALPHA_SEED_PACK. Pack identity
rides WITH the harness (closes the P0.3 §5 known limitation, and the cross-face env-divergence class).
"""
from alpha.harness.doctrine import Doctrine
from alpha.harness.edit_log import EditLog
from alpha.harness.growth_regime import normalize_growth_phases
from alpha.harness.metatools import MetaTools
from alpha.harness.registry import MemoryStore, SkillRegistry
from alpha.harness.state import HarnessState
from alpha.refine.apply import try_apply_op
from alpha.refine.ops import PASS_TOOLS, RefineOp


def _h(vocabulary="momo"):
    return HarnessState(
        doctrine=Doctrine.from_seed_list([]),
        skills=SkillRegistry.from_skills([]),
        memory=MemoryStore.from_lessons([]),
        vocabulary=vocabulary,
    )


def _write_skill_op(skill_id, phases):
    return RefineOp(tool="write_skill",
                    args={"skill_id": skill_id, "name": skill_id, "type": "pattern",
                          "trigger": "t", "entry": "e", "exit_stop": "x", "phases": phases},
                    rationale="grow the growth H")


def _apply(meta, h, op, **kw):
    return try_apply_op(meta, h, op, allowed=PASS_TOOLS["K"],
                        min_retire_samples=5, min_promote_samples=3, **kw)


def test_growth_tokens_survive_the_waist_on_a_growth_h():
    # a growth-vocabulary H edits with the growth normalizer -> scale-typed tokens are kept.
    h = _h("growth"); meta = MetaTools(h, EditLog())
    rec, reason = _apply(meta, h, _write_skill_op("s_growth", ["stock:advance", "stock:base"]))
    assert rec is not None and reason is None
    assert h.skills.get("s_growth").phases == ["stock:advance", "stock:base"]   # kept, not dropped


def test_momo_h_edited_under_growth_env_normalizes_with_momo_vocab(monkeypatch):
    """Regression (would have FAILED before the P0.5 fix): the waist resolved the normalizer from the
    process env, so a momo brain edited under exported ALPHA_SEED_PACK=growth mis-normalized. Now the
    vocabulary rides with the H — a momo H drops growth tokens even when the env says growth. This is
    the cross-face / cross-process corruption class the fix closes."""
    monkeypatch.setenv("ALPHA_SEED_PACK", "growth")
    h = _h("momo"); meta = MetaTools(h, EditLog())        # a momo H...
    rec, reason = _apply(meta, h, _write_skill_op("s_growth_under_momo", ["stock:advance"]))
    assert rec is not None and reason is None
    assert h.skills.get("s_growth_under_momo").phases == []   # ...env says growth, but the H is momo -> dropped


def test_growth_tokens_survive_via_explicit_normalize():
    """The seam is also injectable directly (deterministic; independent of both env and h.vocabulary)."""
    h = _h("momo"); meta = MetaTools(h, EditLog())
    rec, reason = _apply(meta, h, _write_skill_op("s_growth", ["theme:emerging"]),
                         normalize=normalize_growth_phases)
    assert rec is not None and reason is None
    assert h.skills.get("s_growth").phases == ["theme:emerging"]


def test_momo_h_keeps_momo_tokens_drops_growth_tokens():
    """A momo H (default vocabulary): a momo token is kept; a growth token is dropped — the pre-P0.5
    momo behaviour, now bound to the H's vocabulary rather than the (unset) env."""
    h = _h("momo"); meta = MetaTools(h, EditLog())
    rec, _ = _apply(meta, h, _write_skill_op("s_momo", ["trend"]))
    assert rec is not None and h.skills.get("s_momo").phases == ["trend"]        # momo token kept

    rec2, _ = _apply(meta, h, _write_skill_op("s_growth_on_momo", ["stock:advance"]))
    assert rec2 is not None
    assert h.skills.get("s_growth_on_momo").phases == []                          # growth token dropped


def test_process_memory_growth_tokens_survive_on_a_growth_h():
    """The other create path (process_memory) resolves the normalizer from h.vocabulary too."""
    h = _h("growth"); meta = MetaTools(h, EditLog())
    op = RefineOp(tool="process_memory",
                  args={"lesson_id": "L-x", "outcome": "loss", "lesson": "theme died",
                        "phases": ["theme:exhaustion"]},
                  rationale="record the failure card")
    rec, reason = try_apply_op(meta, h, op, allowed=PASS_TOOLS["M"],
                               min_retire_samples=5, min_promote_samples=3)
    assert rec is not None and reason is None
    assert h.memory.get("L-x").phases == ["theme:exhaustion"]
