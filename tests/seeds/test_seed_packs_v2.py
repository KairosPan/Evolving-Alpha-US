import json
from pathlib import Path

import pytest

from alpha.harness.errors import ImmutableDoctrineError
from alpha.harness.growth_regime import GROWTH_TOKENS as _TOKENS
from alpha.harness.loader import (
    SEED_PACK_ENV,
    active_pack_name,
    load_pack,
    load_seeds,
    resolve_pack,
)

ROOT = Path(__file__).resolve().parents[2]
SEEDS = ROOT / "seeds"
SEEDS_V2 = ROOT / "seeds_v2"


def _growth():
    return load_pack("growth")


# ── the growth pack distills + loads offline ───────────────────────────────
def test_growth_pack_loads_with_expected_counts():
    h = _growth()
    assert len(h.doctrine.entries) == 39
    assert len(h.skills) == 6
    assert len(h.memory) == 21    # 13 base + 8 Appendix-A named_analog rows (A-01/02/04/06/09/13/20/23)


def test_growth_immutable_red_lines_are_the_4_8_set():
    h = _growth()
    core = {e.section for e in h.doctrine.immutable_core()}
    assert core == {
        # 5 存续 (rewritten in growth terms)
        "stop_discipline", "one_correlated_bet", "loss_circuit_breaker",
        "survivorship_pit", "fill_feasibility",
        # 4 新增
        "panic_state_ban", "thesis_first", "earnings_checklist_gate", "scale_disambiguation",
    }
    # the two 墓碑 (momo language) are NOT migrated
    assert h.doctrine.get("no_chase_risk_off") is None
    assert h.doctrine.get("dont_fight_ssr") is None


def test_growth_red_lines_are_write_protected():
    h = _growth()
    entry = h.doctrine.get("scale_disambiguation")
    assert entry.immutable is True
    with pytest.raises(ImmutableDoctrineError):
        entry.guidance = "loosen"


def test_scale_disambiguation_preset_present():
    # preset 1: the scale_disambiguation immutable doctrine entry lives in the pack (§0.5 / §4.8)
    e = _growth().doctrine.get("scale_disambiguation")
    assert e is not None and e.immutable is True
    assert "scale" in e.guidance.lower() and "market" in e.guidance.lower()


def test_growth_defense_heavy():
    h = _growth()
    detectors = len(h.skills.by_type("failure_detector"))
    patterns = len(h.skills.by_type("pattern"))
    assert detectors > patterns, f"not defense-heavy: {detectors} detectors vs {patterns} patterns"


def test_growth_phases_are_scale_typed_or_all():
    # every non-all tag on every element is a legal growth scale:phase token (no dropped/typo'd tag)
    h = _growth()
    elems = list(h.doctrine.entries) + h.skills.all() + h.memory.all()
    for el in elems:
        for p in el.phases:
            assert p in _TOKENS, f"{el} carries non-growth token {p!r}"
    # scoped skills must actually classify (not silently empty out under the growth normalizer)
    empty = [s.skill_id for s in h.skills.all() if not s.phases and not s.applies_all_phases]
    assert empty == []


def test_all_three_scales_are_represented():
    h = _growth()
    scales = {p.split(":", 1)[0] for e in h.doctrine.entries for p in e.phases}
    assert scales == {"market", "theme", "stock"}


def test_laggard_launch_incubates_on_a_feed():
    # a skill that needs an unbuilt feed ships incubating, like the momo squeeze skills
    s = _growth().skills.get("laggard_launch")
    assert s.status == "incubating" and s.depends_on == ["theme_breadth"]


# ── the co-residence bar is enforced by types ──────────────────────────────
def test_growth_pack_under_momo_vocab_drops_every_phase():
    # loading the growth seeds with the MOMO normalizer drops all scale-typed tokens -> proves the
    # namespaces are physically disjoint (the tripwire the momo/growth bar relies on).
    h = load_seeds(SEEDS_V2, vocabulary="momo")
    assert all(e.phases == [] for e in h.doctrine.entries)
    assert all(s.phases == [] for s in h.skills.all())
    assert all(l.phases == [] for l in h.memory.all())


# ── selection mechanism ────────────────────────────────────────────────────
def test_resolve_pack_maps_names_to_dir_and_vocab():
    assert resolve_pack("momo") == (SEEDS, "momo")
    assert resolve_pack("growth") == (SEEDS_V2, "growth")
    with pytest.raises(ValueError):
        resolve_pack("nope")


def test_active_pack_defaults_to_momo(monkeypatch):
    monkeypatch.delenv(SEED_PACK_ENV, raising=False)
    assert active_pack_name() == "momo"
    monkeypatch.setenv(SEED_PACK_ENV, "growth")
    assert active_pack_name() == "growth"
    assert resolve_pack() == (SEEDS_V2, "growth")


def test_env_selects_growth_pack_end_to_end(monkeypatch):
    monkeypatch.setenv(SEED_PACK_ENV, "growth")
    h = load_pack()                                   # no explicit name -> reads env
    assert h.doctrine.get("cycle_eye") is not None    # growth-only section
    assert h.doctrine.get("trend_play") is None       # momo-only section absent


# ── byte-identity when the switch is unset (the P0 acceptance gate) ─────────
def test_momo_path_byte_identical_when_switch_unset(monkeypatch):
    monkeypatch.delenv(SEED_PACK_ENV, raising=False)
    baseline = json.dumps(load_seeds(SEEDS).to_dict(), sort_keys=True)      # old call, unchanged
    via_vocab = json.dumps(load_seeds(SEEDS, vocabulary="momo").to_dict(), sort_keys=True)
    via_pack = json.dumps(load_pack().to_dict(), sort_keys=True)            # env unset -> momo
    assert baseline == via_vocab == via_pack
