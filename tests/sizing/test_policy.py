"""L3 sizing decorator: size_decision assigns a per-candidate size_tier (confidence x regime risk_gate)
and attaches the Portfolio plan; SizingPolicy wraps any policy. Verdict-neutral — sizing never touches
scoring (proven in tests/eval/test_l3_sizing_acceptance.py)."""
from datetime import date, datetime
from alpha.eval.decision import Candidate, DecisionPackage
from alpha.regime.classifier import RegimeRead
from alpha.sizing.policy import SizingPolicy, size_decision
from alpha.state.market import MarketState
from alpha.universe.stock import StockSnapshot
from alpha.universe.universe import CandidateUniverse

CUR = date(2026, 6, 12)


def _state(**kw):
    return MarketState(date=CUR, gainer_count=1, gap_up_count=0, loser_count=0, failed_breakout_count=0,
                       max_runner_tier=0, echelon=[], breadth_raw=1.0, sentiment_norm=None,
                       as_of=datetime(2026, 6, 12, 16, 0), **kw)


def _pkg(*cands, regime=None):
    return DecisionPackage(date=CUR, candidates=list(cands), regime=regime)


def test_size_decision_assigns_tier_from_confidence_and_risk_gate():
    # risk_gate=0.8, confidence=0.9 -> score 0.72 -> 'heavy'; confidence=0.4 -> 0.32 -> 'probe'
    regime = RegimeRead(phase="trend", confidence=0.7, frontside=True, risk_gate=0.8)
    out = size_decision(_pkg(Candidate(symbol="RUN", confidence=0.9),
                             Candidate(symbol="LAG", confidence=0.4), regime=regime), state=_state())
    tiers = {c.symbol: c.size_tier for c in out.candidates}
    assert tiers == {"RUN": "heavy", "LAG": "probe"}
    assert out.portfolio is not None
    assert out.portfolio.total_exposure_budget == 0.8 * 4.0          # risk_gate x max_total_exposure


def test_size_decision_falls_back_to_gcycle_when_regime_absent():
    # no regime on the package (screen off) -> size_decision computes GCycle().read(state) itself
    out = size_decision(_pkg(Candidate(symbol="RUN", confidence=0.9)), state=_state())
    assert out.candidates[0].size_tier in {"flat", "probe", "core", "heavy"}
    assert out.portfolio is not None


def test_size_decision_nets_same_narrative_to_one_bet():
    # the narrative key now comes from candidate.narrative (set by the agent), activating L3 netting
    regime = RegimeRead(phase="trend", confidence=0.7, frontside=True, risk_gate=0.9)
    out = size_decision(_pkg(
        Candidate(symbol="GPUX", confidence=0.9, narrative="ai-compute"),
        Candidate(symbol="CHPS", confidence=0.9, narrative="ai-compute"),
        Candidate(symbol="SOLO", confidence=0.9, narrative=""), regime=regime), state=_state())
    assert out.portfolio.correlated_groups == [["CHPS", "GPUX"]]      # the two ai-compute names = one bet
    # netted: ai-compute (one bet, heavy=1.0) + SOLO (heavy=1.0) = 2.0, NOT 3.0
    assert out.portfolio.total_exposure == 2.0
    assert out.portfolio.capped is False


def test_size_decision_distinct_narratives_do_not_net():
    regime = RegimeRead(phase="trend", confidence=0.7, frontside=True, risk_gate=0.9)
    out = size_decision(_pkg(Candidate(symbol="A", confidence=0.9, narrative="x"),
                             Candidate(symbol="B", confidence=0.9, narrative="y"), regime=regime),
                        state=_state())
    assert out.portfolio.correlated_groups == []                     # different themes -> two bets
    assert out.portfolio.total_exposure == 2.0                       # 1.0 + 1.0


def test_sizing_policy_sizes_inner_decision():
    class _Stub:
        def decide(self, state, universe):
            return _pkg(Candidate(symbol="RUN", confidence=0.9),
                        regime=RegimeRead(phase="trend", confidence=0.7, frontside=True, risk_gate=0.9))
    out = SizingPolicy(_Stub()).decide(_state(), CandidateUniverse.from_stocks([]))
    assert out.candidates[0].size_tier == "heavy"                    # 0.9 x 0.9 = 0.81 -> heavy


# ── P0.6 trim-derisk action vocabulary (spec 2026-07-13-p06) ────────────────────────────────────
# Candidate now carries `action` directly (spec 2026-07-13-p05 §7), so these construct it inline.

def test_size_decision_trim_caps_tier_at_core_and_excludes_from_exposure():
    regime = RegimeRead(phase="trend", confidence=0.7, frontside=True, risk_gate=0.9)
    out = size_decision(_pkg(
        Candidate(symbol="HELD", confidence=0.9, action="trim"),   # would size heavy -> capped core
        Candidate(symbol="NEW", confidence=0.9, action="enter"),   # a real new bet
        regime=regime), state=_state())
    tiers = {c.symbol: c.size_tier for c in out.candidates}
    assert tiers == {"HELD": "core", "NEW": "heavy"}
    # only the `enter` name is a new bet -> exposure counts NEW alone (1.0), not the trimmed HELD
    assert out.portfolio.total_exposure == 1.0


def test_size_decision_exit_goes_flat_and_adds_no_exposure():
    regime = RegimeRead(phase="trend", confidence=0.7, frontside=True, risk_gate=0.9)
    out = size_decision(_pkg(Candidate(symbol="GONE", confidence=0.9, action="exit"),
                             regime=regime), state=_state())
    assert out.candidates[0].size_tier == "flat"
    assert out.portfolio.total_exposure == 0.0                        # nothing entered


def test_size_decision_byte_identical_when_all_enter():
    # explicit annotation present but action=enter everywhere -> same as a plain Candidate package
    regime = RegimeRead(phase="trend", confidence=0.7, frontside=True, risk_gate=0.8)
    plain = size_decision(_pkg(Candidate(symbol="RUN", confidence=0.9),
                               Candidate(symbol="LAG", confidence=0.4), regime=regime), state=_state())
    annotated = size_decision(_pkg(Candidate(symbol="RUN", confidence=0.9, action="enter"),
                                   Candidate(symbol="LAG", confidence=0.4, action="enter"),
                                   regime=regime), state=_state())
    assert {c.symbol: c.size_tier for c in plain.candidates} == {c.symbol: c.size_tier for c in annotated.candidates}
    assert plain.portfolio == annotated.portfolio


def test_sizing_annotations_are_verdict_neutral():
    # scoring reads only symbol/pattern + forward returns; size_tier/action never enter the score
    from alpha.eval.scorer import PoolScorer
    from alpha.eval.oracle import DayMembership
    from datetime import date as _date
    regime = RegimeRead(phase="trend", confidence=0.7, frontside=True, risk_gate=0.9)
    plain = size_decision(_pkg(Candidate(symbol="RUN", confidence=0.9),
                               Candidate(symbol="LAG", confidence=0.6), regime=regime), state=_state())
    annotated = size_decision(_pkg(Candidate(symbol="RUN", confidence=0.9, action="trim"),
                                   Candidate(symbol="LAG", confidence=0.6, action="exit"),
                                   regime=regime), state=_state())
    dmem = DayMembership(gainers=frozenset({"RUN"}), losers=frozenset())
    emem = DayMembership(gainers=frozenset({"RUN"}), losers=frozenset({"LAG"}))
    kw = dict(decision_mem=dmem, exit_mem=emem, entry_day=CUR, exit_day=_date(2026, 6, 16), oracle=None)
    sp = PoolScorer()
    assert ({s: c.score for s, c in sp.score_step(plain, **kw).items()}
            == {s: c.score for s, c in sp.score_step(annotated, **kw).items()})


# ── P5b float-aware sizing (spec 2026-07-13-p5b-float-feed-design.md) ────────────────────────────────

_HOT = RegimeRead(phase="trend", confidence=0.7, frontside=True, risk_gate=0.9)   # 0.9 x 0.9 -> heavy


def test_size_decision_floats_none_is_byte_identical():
    # the default-off contract: passing floats=None must equal the no-floats call, package-for-package
    pkg = _pkg(Candidate(symbol="RUN", confidence=0.9), Candidate(symbol="LAG", confidence=0.4), regime=_HOT)
    assert size_decision(pkg, state=_state()) == size_decision(pkg, state=_state(), floats=None)


def test_size_decision_small_float_caps_tier_huge_float_unchanged():
    # non-vacuous: a small-float name drops heavy -> probe; a huge-float name is unconstrained
    out = size_decision(_pkg(Candidate(symbol="MICRO", confidence=0.9),
                             Candidate(symbol="BIG", confidence=0.9), regime=_HOT), state=_state(),
                        floats={"MICRO": 3_000_000.0, "BIG": 500_000_000.0})
    tiers = {c.symbol: c.size_tier for c in out.candidates}
    assert tiers == {"MICRO": "probe", "BIG": "heavy"}          # small capped, huge untouched
    # ... and without floats BOTH are heavy (proves the cap, not the confidence, moved MICRO)
    base = size_decision(_pkg(Candidate(symbol="MICRO", confidence=0.9),
                              Candidate(symbol="BIG", confidence=0.9), regime=_HOT), state=_state())
    assert {c.symbol: c.size_tier for c in base.candidates} == {"MICRO": "heavy", "BIG": "heavy"}


def test_size_decision_float_caps_portfolio_exposure():
    # the aggregate exposure reflects the same caps: MICRO probe (0.25) + BIG heavy (1.0) = 1.25, not 2.0
    out = size_decision(_pkg(Candidate(symbol="MICRO", confidence=0.9),
                             Candidate(symbol="BIG", confidence=0.9), regime=_HOT), state=_state(),
                        floats={"MICRO": 3_000_000.0, "BIG": 500_000_000.0})
    assert out.portfolio.total_exposure == 1.25
    base = size_decision(_pkg(Candidate(symbol="MICRO", confidence=0.9),
                              Candidate(symbol="BIG", confidence=0.9), regime=_HOT), state=_state())
    assert base.portfolio.total_exposure == 2.0                 # uncapped baseline (non-vacuous)


def test_float_refinement_is_verdict_neutral_non_vacuously():
    # mirrors test_sizing_annotations_are_verdict_neutral: float caps the tier, but the scorer ignores it
    from alpha.eval.scorer import PoolScorer
    from alpha.eval.oracle import DayMembership
    from datetime import date as _date
    plain = size_decision(_pkg(Candidate(symbol="RUN", confidence=0.9),
                               Candidate(symbol="LAG", confidence=0.9), regime=_HOT), state=_state())
    capped = size_decision(_pkg(Candidate(symbol="RUN", confidence=0.9),
                                Candidate(symbol="LAG", confidence=0.9), regime=_HOT), state=_state(),
                           floats={"RUN": 3_000_000.0, "LAG": 3_000_000.0})
    # non-vacuous: the float cap genuinely changed the tiers (heavy -> probe)
    assert {c.symbol: c.size_tier for c in plain.candidates} != {c.symbol: c.size_tier for c in capped.candidates}
    dmem = DayMembership(gainers=frozenset({"RUN"}), losers=frozenset())
    emem = DayMembership(gainers=frozenset({"RUN"}), losers=frozenset({"LAG"}))
    kw = dict(decision_mem=dmem, exit_mem=emem, entry_day=CUR, exit_day=_date(2026, 6, 16), oracle=None)
    sp = PoolScorer()
    assert ({s: c.score for s, c in sp.score_step(plain, **kw).items()}
            == {s: c.score for s, c in sp.score_step(capped, **kw).items()})    # size never enters the score


def _uni(*stocks):
    return CandidateUniverse.from_stocks(list(stocks))


def _snap(symbol, free_float):
    return StockSnapshot(symbol=symbol, name=symbol, status="gainer", free_float=free_float)


class _HotStub:
    """A policy returning a heavy-conviction pick for each requested symbol (regime already hot)."""
    def __init__(self, *symbols):
        self._symbols = symbols
    def decide(self, state, universe):
        return _pkg(*[Candidate(symbol=s, confidence=0.9) for s in self._symbols], regime=_HOT)


def test_sizing_policy_float_aware_caps_from_universe():
    # float_aware=True derives the float map from the universe (StockSnapshot.free_float millions x1e6):
    # MICRO at 3.0M shares -> probe; BIG at 500M -> heavy
    uni = _uni(_snap("MICRO", 3.0), _snap("BIG", 500.0))
    out = SizingPolicy(_HotStub("MICRO", "BIG"), float_aware=True).decide(_state(), uni)
    assert {c.symbol: c.size_tier for c in out.candidates} == {"MICRO": "probe", "BIG": "heavy"}


def test_sizing_policy_float_aware_off_is_byte_identical():
    # default float_aware=False -> the universe's free_float is IGNORED -> tier-only (both heavy)
    uni = _uni(_snap("MICRO", 3.0), _snap("BIG", 500.0))
    off = SizingPolicy(_HotStub("MICRO", "BIG")).decide(_state(), uni)
    assert {c.symbol: c.size_tier for c in off.candidates} == {"MICRO": "heavy", "BIG": "heavy"}


def test_sizing_policy_float_aware_no_float_in_universe_byte_identical():
    # float_aware=True but the snapshot has no free_float -> no cap for that name (byte-identical)
    uni = _uni(_snap("PLAIN", None))
    out = SizingPolicy(_HotStub("PLAIN"), float_aware=True).decide(_state(), uni)
    assert out.candidates[0].size_tier == "heavy"


def test_sizing_policy_decorator_order_preserved_with_float_aware():
    # SizingPolicy still wraps its inner (order = size the post-veto survivors); float_aware is orthogonal
    class _Guard:
        def __init__(self):
            self.seen = False
        def decide(self, state, universe):
            self.seen = True                                     # the inner (guard) runs first
            return _pkg(Candidate(symbol="RUN", confidence=0.9), regime=_HOT)
    guard = _Guard()
    sp = SizingPolicy(guard, float_aware=True)
    assert sp._inner is guard                                    # sizing is the OUTER decorator
    out = sp.decide(_state(), _uni(_snap("RUN", 3.0)))
    assert guard.seen and out.candidates[0].size_tier == "probe"  # guard ran, then float-aware sizing capped
