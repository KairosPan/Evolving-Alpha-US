"""§1.4 three-clock authority CASCADE — the PURE composition (no source).

Exercises the full theme × stock matrix + the two load-bearing invariants of the downward cascade:
  - safety-only-tightens: the composed veto set is a SUPERSET and the tier cap only ever falls;
  - downward-only authority: a higher clock dominates a lower one (theme exhaustion overrides a
    stock:advance; a lower clock never re-enables / raises).
The source-driven integration (screen_decision wiring) lives in tests/guard/test_clock_authority_wiring.py;
the verdict symmetry in tests/loop/test_clock_authority_symmetry.py.
"""
from __future__ import annotations

from alpha.regime.clock_authority import (
    ClockCascade, clock_tier_cap, compose_downward_cascade, stock_stage_cap, theme_appetite_cap,
)
from alpha.regime.stock_clock import StockStageReading
from alpha.sizing.position import SIZE_TIER_WEIGHT


def _stock(stage: str, *, climax: bool = False) -> StockStageReading:
    return StockStageReading(symbol="AAA", stage=stage, confidence=0.6, climax_run=climax)


# ── abstain: no read → no gate (禁止补格) ─────────────────────────────────────────────────────────────

def test_full_abstain_is_a_noop_cascade():
    c = compose_downward_cascade(theme_phase=None, stock=None)
    assert c == ClockCascade()                       # empty veto, no cap, no reduce flag
    assert c.vetoed is False and c.tier_cap is None and c.reduce_flag is False


# ── stock (finest) LONG-ELIGIBILITY gate: only advance is long-eligible ──────────────────────────────

def test_stock_advance_is_long_eligible_no_veto():
    c = compose_downward_cascade(theme_phase=None, stock=_stock("stock:advance"))
    assert c.vetoed is False and c.tier_cap is None and c.reduce_flag is False


def test_stock_base_vetoes_a_new_entry():
    c = compose_downward_cascade(theme_phase=None, stock=_stock("stock:base"))
    assert c.vetoed is True and any("advance" in r for r in c.veto_reasons)


def test_stock_top_vetoes():
    c = compose_downward_cascade(theme_phase=None, stock=_stock("stock:top"))
    assert c.vetoed is True and any("distribution" in r for r in c.veto_reasons)


def test_stock_decline_vetoes():
    assert compose_downward_cascade(theme_phase=None, stock=_stock("stock:decline")).vetoed is True


def test_climax_run_on_advance_stays_eligible_but_caps_and_flags():
    """climax is REDUCE language: the name stays long-eligible (advance, NOT vetoed) but the tier is
    capped and the reduce flag is raised — never an add."""
    c = compose_downward_cascade(theme_phase=None, stock=_stock("stock:advance", climax=True))
    assert c.vetoed is False                          # still long-eligible (advance)
    assert c.reduce_flag is True                      # but flagged reduce
    assert c.tier_cap == "core"                       # and capped (never heavy)


# ── theme (middle) appetite modulation, tighten-only ─────────────────────────────────────────────────

def test_theme_institutional_full_appetite():
    assert theme_appetite_cap("theme:institutional") is None    # 主战场 — no cap
    c = compose_downward_cascade(theme_phase="theme:institutional", stock=_stock("stock:advance"))
    assert c.vetoed is False and c.tier_cap is None


def test_theme_emerging_is_probe_only():
    assert theme_appetite_cap("theme:emerging") == "probe"


def test_theme_public_laggard_caps_appetite():
    assert theme_appetite_cap("theme:public_laggard") == "core"
    c = compose_downward_cascade(theme_phase="theme:public_laggard", stock=_stock("stock:advance"))
    assert c.vetoed is False and c.tier_cap == "core"           # laggard_timer: no chasing


def test_theme_exhaustion_vetoes_the_theme():
    c = compose_downward_cascade(theme_phase="theme:exhaustion", stock=_stock("stock:advance"))
    assert c.vetoed is True and any("exhaustion" in r for r in c.veto_reasons)


# ── downward-only authority: a higher clock dominates a lower one ────────────────────────────────────

def test_theme_exhaustion_overrides_a_stock_advance():
    """A theme in exhaustion vetoes even a stock that is a clean advance — 高尺度否决低尺度."""
    c = compose_downward_cascade(theme_phase="theme:exhaustion", stock=_stock("stock:advance"))
    assert c.vetoed is True                            # the (higher) theme veto stands over the advance


def test_a_lower_clock_never_re_enables_or_raises():
    """A stock:advance (the finest, most permissive read) can neither drop a theme veto nor lift a theme
    appetite cap — a lower clock does not score a higher one."""
    exhausted = compose_downward_cascade(theme_phase="theme:exhaustion", stock=_stock("stock:advance"))
    laggard = compose_downward_cascade(theme_phase="theme:public_laggard", stock=_stock("stock:advance"))
    assert exhausted.vetoed is True                    # advance did not re-enable the exhausted theme
    assert laggard.tier_cap == "core"                  # advance did not lift the laggard cap


def test_tightest_cap_wins_across_clocks():
    """When two clocks each cap, the composed cap is the TIGHTER (min weight) — probe (emerging) beats
    core (climax)."""
    c = compose_downward_cascade(theme_phase="theme:emerging",
                                 stock=_stock("stock:advance", climax=True))
    assert c.tier_cap == "probe"                       # min(probe, core) = probe
    assert SIZE_TIER_WEIGHT["probe"] < SIZE_TIER_WEIGHT["core"]


# ── safety-only-tightens as a PROPERTY across the whole matrix ────────────────────────────────────────

_THEMES = [None, "theme:emerging", "theme:institutional", "theme:public_laggard", "theme:exhaustion"]
_STAGES = [None, "stock:base", "stock:advance", "stock:top", "stock:decline"]


def test_cascade_only_tightens_over_the_full_matrix():
    """For every (theme, stock, climax) combination: the cascade adds ≥0 veto reasons and the tier cap is
    never LOOSER than either clock's own cap — the composed gate is always a tightening."""
    for theme in _THEMES:
        for stage in _STAGES:
            for climax in (False, True):
                stock = None if stage is None else _stock(stage, climax=climax)
                c = compose_downward_cascade(theme_phase=theme, stock=stock)
                # veto set ⊇ each leg's veto (superset / additive)
                theme_vetoes = theme == "theme:exhaustion"
                stock_vetoes = stage in {"stock:base", "stock:top", "stock:decline"}
                assert c.vetoed == (theme_vetoes or stock_vetoes)
                # tier cap is the tightest of the two legs (min weight), never looser
                legs = [theme_appetite_cap(theme),
                        stock_stage_cap(stage, climax_run=climax)]
                weights = [SIZE_TIER_WEIGHT[t] for t in legs if t is not None]
                if weights:
                    assert c.tier_cap is not None
                    assert SIZE_TIER_WEIGHT[c.tier_cap] == min(weights)
                else:
                    assert c.tier_cap is None


# ── clock_tier_cap (the sizing-side string consumer) mirrors the cascade cap ─────────────────────────

def test_clock_tier_cap_empty_reads_is_no_cap():
    """The flag-off / abstain case: empty attached reads → no cap (byte-identical sizing)."""
    assert clock_tier_cap("", "", climax_run=False) is None
    assert clock_tier_cap(None, None) is None


def test_clock_tier_cap_matches_compose_for_kept_candidates():
    """For a KEPT candidate (advance, non-exhaustion theme) the sizing-side string cap equals the
    cascade's tier cap — one source of truth."""
    for theme in ["theme:institutional", "theme:public_laggard", "theme:emerging"]:
        for climax in (False, True):
            stock = _stock("stock:advance", climax=climax)
            cascade = compose_downward_cascade(theme_phase=theme, stock=stock)
            sizing = clock_tier_cap("stock:advance", theme, climax_run=climax)
            assert sizing == cascade.tier_cap
