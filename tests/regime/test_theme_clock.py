"""P5b-consumer growth theme-lifecycle clock — the per-group lifecycle classifier.

Truth table + hysteresis + warm-up/abstain + boundary probes for
`alpha/regime/theme_clock.py::GrowthThemeClock`. The clock reads the manuscript's §1.2 theme lifecycle
(`emerging → institutional → public_laggard → exhaustion`) from P5b's per-group breadth signals
(`GroupBreadthReading`), as a state machine replayed forward over each group's determined-reading
history + today (P2's no-flicker lesson, one scale down). Readings are constructed directly from signal
values (not bar tapes) — the clock is a pure function of the signals P5b emits, tested here in isolation.

Scale note (pinned in the clock): `pct_above_200dma` / `breadth_trend` are fractions in [0,1]; the RS
fields (`rs_dispersion`, `rs_trend`, `laggard_rs_mean`) are cross-sectional percentiles in [0,100].
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from alpha.features.theme_breadth import GroupBreadthReading, ThemeBreadthReading
from alpha.regime.theme_clock import (
    BREADTH_HIGH, BREADTH_LOW_BASE, BREADTH_RISING, BREADTH_ROLLING_OVER, DISPERSION_COMPRESS,
    DISPERSION_WIDE, EXHAUSTION_CONFIRM, MIN_HISTORY, RS_FALLING, RS_RISING, GrowthThemeClock,
    ThemeLifecycleRead, _run_theme_machine, theme_lifecycle,
)
from alpha.state.market import MarketState

DAY0 = date(2026, 6, 1)


def _state(reading: ThemeBreadthReading | None, i: int = 0) -> MarketState:
    """A minimal MarketState carrying (or not) a threaded ThemeBreadthReading, for the read() adapter."""
    day = DAY0 + timedelta(days=i)
    return MarketState(date=day, gainer_count=0, gap_up_count=0, loser_count=0, failed_breakout_count=0,
                       max_runner_tier=0, echelon=[], breadth_raw=0.0, theme_breadth=reading,
                       as_of=datetime(day.year, day.month, day.day, 16, 0))


def _grp(group: str = "ai", *, determined: bool = True, breadth: float | None = None,
         breadth_trend: float | None = None, rs_trend: float | None = None,
         dispersion: float | None = None, laggard: float | None = None,
         member_count: int = 5) -> GroupBreadthReading:
    return GroupBreadthReading(
        group=group, member_count=member_count, determined=determined,
        pct_above_200dma=breadth, breadth_trend=breadth_trend, rs_trend=rs_trend,
        rs_dispersion=dispersion, laggard_rs_mean=laggard)


# canonical per-phase signal snapshots (each a determined GroupBreadthReading for group "ai")
EMERGING_SIG = dict(breadth=0.40, breadth_trend=0.10, rs_trend=5.0, dispersion=30.0, laggard=40.0)
INSTITUTIONAL_SIG = dict(breadth=0.70, breadth_trend=0.02, rs_trend=5.0, dispersion=25.0, laggard=45.0)
WIDE_INST_SIG = dict(breadth=0.70, breadth_trend=0.02, rs_trend=3.0, dispersion=40.0, laggard=30.0)
COMPRESSED_SIG = dict(breadth=0.70, breadth_trend=0.0, rs_trend=0.0, dispersion=10.0, laggard=60.0)
WEAK_SIG = dict(breadth=0.62, breadth_trend=-0.10, rs_trend=-5.0, dispersion=25.0, laggard=45.0)
DORMANT_SIG = dict(breadth=0.30, breadth_trend=0.0, rs_trend=0.0, dispersion=5.0, laggard=20.0)


def _series(*sigs: dict) -> list[GroupBreadthReading]:
    return [_grp(**s) for s in sigs]


def _readings(*sigs: dict, group: str = "ai") -> list[ThemeBreadthReading]:
    """One ThemeBreadthReading per signal snapshot, chronological, one group."""
    return [ThemeBreadthReading(day=DAY0 + timedelta(days=i), groups={group: _grp(group=group, **s)})
            for i, s in enumerate(sigs)]


def _read(*sigs: dict, group: str = "ai"):
    """Classify `group` as of the LAST snapshot given the earlier ones as history (readings-level API)."""
    reads = _readings(*sigs, group=group)
    return theme_lifecycle(reads[:-1], reads[-1])


# ── truth table: each §1.2 phase classified on a synthetic per-group tape ────────────────────────────

def test_emerging_rising_off_low_base_with_wide_dispersion():
    """breadth rising off a low base (< BREADTH_HIGH) + leaders leading (wide rs_dispersion) = emerging."""
    read = _read(EMERGING_SIG, EMERGING_SIG, EMERGING_SIG)
    assert read["ai"] == ThemeLifecycleRead(group="ai", phase="theme:emerging", confidence=read["ai"].confidence)
    assert read["ai"].phase == "theme:emerging"


def test_institutional_broad_participation():
    """Broad participation (pct_above_200dma high) + RS trending up = institutional (the main phase),
    reachable directly (arrive-late) when the group is already broad."""
    read = _read(INSTITUTIONAL_SIG, INSTITUTIONAL_SIG, INSTITUTIONAL_SIG)
    assert read["ai"].phase == "theme:institutional"


def test_emerging_progresses_to_institutional_when_participation_broadens():
    """emerging → institutional the reading the group broadens (breadth crosses BREADTH_HIGH), forward
    progression — the clock is a lifecycle, not a per-day band."""
    read = _read(EMERGING_SIG, EMERGING_SIG, dict(EMERGING_SIG, breadth=0.70))
    assert read["ai"].phase == "theme:institutional"


def test_public_laggard_when_dispersion_compresses_the_laggard_timer():
    """The laggard_timer (§3.4): after leaders dominated (wide dispersion, institutional), the gap
    COMPRESSES while breadth stays high — laggards catching up rings the timer -> public_laggard."""
    read = _read(WIDE_INST_SIG, WIDE_INST_SIG, COMPRESSED_SIG)
    assert read["ai"].phase == "theme:public_laggard"


def test_exhaustion_needs_a_sustained_rollover_plus_rs_down():
    """breadth rolling over AND RS trend down, sustained for EXHAUSTION_CONFIRM readings -> exhaustion."""
    sigs = [INSTITUTIONAL_SIG, INSTITUTIONAL_SIG] + [WEAK_SIG] * EXHAUSTION_CONFIRM
    read = _read(*sigs)
    assert read["ai"].phase == "theme:exhaustion"


# ── the P2 no-flicker lesson: an isolated weak reading does NOT flip institutional -> exhaustion ──────

def test_isolated_weak_reading_holds_institutional_no_flicker():
    """A SINGLE weak reading (roll-over + RS down for one reading, run < EXHAUSTION_CONFIRM) must NOT
    un-confirm institutional — the pinned no-flicker property (the P1/P2 stability lesson)."""
    assert EXHAUSTION_CONFIRM >= 2                        # the guarantee is only meaningful if > 1
    read = _read(INSTITUTIONAL_SIG, INSTITUTIONAL_SIG, WEAK_SIG)
    assert read["ai"].phase == "theme:institutional"


def test_exhaustion_run_resets_on_a_recovering_reading():
    """A weak reading, then a NON-weak reading, then a weak reading is NOT two CONSECUTIVE weak readings —
    the run resets, so institutional holds (only a sustained run flips it)."""
    read = _read(INSTITUTIONAL_SIG, WEAK_SIG, INSTITUTIONAL_SIG, WEAK_SIG)
    assert read["ai"].phase == "theme:institutional"


def test_same_final_reading_reads_differently_by_history():
    """The identical final reading reads institutional after a narrow-dispersion backdrop but
    public_laggard after a wide-then-compressing one — proving the read is cross-history, not memoryless."""
    narrow = dict(INSTITUTIONAL_SIG, dispersion=10.0)    # never a wide (leaders-dominate) peak
    healthy = _read(narrow, narrow, COMPRESSED_SIG)
    ringing = _read(WIDE_INST_SIG, WIDE_INST_SIG, COMPRESSED_SIG)
    # the narrow backdrop never had a WIDE dispersion peak, so compression does NOT ring the timer
    assert healthy["ai"].phase == "theme:institutional"
    assert ringing["ai"].phase == "theme:public_laggard"


# ── the peak anchor: compression without a prior WIDE peak does not ring (P2's anchor lesson) ─────────

def test_compression_without_a_wide_peak_does_not_ring_the_timer():
    """public_laggard requires the cycle to have SEEN a wide-dispersion (leaders-dominate) peak first —
    a group that was never leader-dominated cannot 'have laggards catch up'. Mirrors P2's FTD anchor:
    the compression is measured from a real peak, not from nothing."""
    narrow = dict(INSTITUTIONAL_SIG, dispersion=10.0)    # never wide; peak stays < DISPERSION_WIDE
    read = _read(narrow, narrow, dict(narrow, dispersion=2.0))
    assert read["ai"].phase == "theme:institutional"     # no wide peak -> no laggard_timer


# ── abstain is explicit — never silently a phase (§0.2 禁止补格) ───────────────────────────────────────

def test_undetermined_today_abstains():
    """A group undetermined in `today` (P5b determined=False) is ABSENT from the read — not a phase."""
    hist = _readings(INSTITUTIONAL_SIG, INSTITUTIONAL_SIG)
    today = ThemeBreadthReading(day=DAY0 + timedelta(days=9), groups={"ai": _grp(determined=False, member_count=1)})
    assert "ai" not in theme_lifecycle(hist, today)


def test_warmup_too_few_determined_readings_abstains():
    """Fewer than MIN_HISTORY determined readings -> no trajectory -> abstain (absent), even though the
    signals look emerging. Abstention (silence), not a conservative fabricated phase."""
    sigs = [EMERGING_SIG] * (MIN_HISTORY - 1)
    assert "ai" not in _read(*sigs)


def test_dormant_determined_but_no_active_theme_abstains():
    """A determined group with no active theme (breadth not rising, not broad) stays dormant -> abstains.
    Labeling a flat sector 'emerging' would fabricate a story; it is absent instead."""
    assert "ai" not in _read(DORMANT_SIG, DORMANT_SIG, DORMANT_SIG)


def test_exhaustion_resets_to_dormant_and_abstains_when_breadth_collapses():
    """After exhaustion, breadth falling to a low base returns the machine to dormant -> the group
    abstains (ready for a fresh cycle), not stuck labeled exhaustion forever."""
    sigs = ([INSTITUTIONAL_SIG, INSTITUTIONAL_SIG] + [WEAK_SIG] * EXHAUSTION_CONFIRM
            + [dict(WEAK_SIG, breadth=0.20)])
    assert "ai" not in _read(*sigs)


# ── undetermined days are dropped from the series (like P2 drops 0/0 feed-outage days) ────────────────

def test_intervening_undetermined_day_does_not_change_the_read():
    """An undetermined reading in the middle of history is filtered (not evidence), so it cannot change a
    later read — the theme-clock analog of P2's 'ignore an intervening empty day'."""
    clean = _readings(EMERGING_SIG, EMERGING_SIG, EMERGING_SIG)
    with_gap = (clean[:2]
                + [ThemeBreadthReading(day=DAY0 + timedelta(days=5), groups={"ai": _grp(determined=False)})]
                + clean[2:])
    a = theme_lifecycle(clean[:-1], clean[-1])
    b = theme_lifecycle(with_gap[:-1], with_gap[-1])
    assert a["ai"].phase == b["ai"].phase == "theme:emerging"


# ── per-group independence: groups are classified independently ──────────────────────────────────────

def test_groups_classified_independently():
    """Two groups on the same days get their own phases (per-group replay, no cross-contamination)."""
    def bundle(i, ai_sig, biotech_sig):
        return ThemeBreadthReading(day=DAY0 + timedelta(days=i),
                                   groups={"ai": _grp("ai", **ai_sig), "biotech": _grp("biotech", **biotech_sig)})
    hist = [bundle(i, EMERGING_SIG, INSTITUTIONAL_SIG) for i in range(2)]
    today = bundle(2, EMERGING_SIG, INSTITUTIONAL_SIG)
    read = theme_lifecycle(hist, today)
    assert read["ai"].phase == "theme:emerging"
    assert read["biotech"].phase == "theme:institutional"


# ── purity: same (history, today) always yields the same read (no hidden state) ──────────────────────

def test_read_is_pure_function_of_inputs():
    reads = _readings(WIDE_INST_SIG, WIDE_INST_SIG, COMPRESSED_SIG)
    a = theme_lifecycle(reads[:-1], reads[-1])
    b = theme_lifecycle(reads[:-1], reads[-1])
    assert a["ai"] == b["ai"]


# ── PIT / trailing-only: the read never inspects a future reading (history is strictly prior) ────────

def test_read_only_consumes_history_and_today():
    """The clock is a pure replay of (history, today); it holds no reference to any later reading. Passing
    only strictly-prior history + today (the caller's contract) is the whole input — pinned by purity +
    the by-construction that read() never receives a >today reading."""
    reads = _readings(EMERGING_SIG, EMERGING_SIG, EMERGING_SIG)
    # a future-looking reading appended to `today.groups` is impossible: today is a single-day bundle.
    assert theme_lifecycle(reads[:-1], reads[-1])["ai"].phase == "theme:emerging"


# ── the GrowthThemeClock.read(MarketState) adapter: reads the additive MarketState.theme_breadth ─────

def test_read_adapter_abstains_all_when_theme_breadth_none():
    """The default-off state: `today.theme_breadth is None` (no feed threaded / an off-cadence day) ⇒ the
    clock abstains on every group (empty mapping) — byte-identical to a run with no theme clock."""
    hist = [_state(r, i) for i, r in enumerate(_readings(INSTITUTIONAL_SIG, INSTITUTIONAL_SIG))]
    today = _state(None, 9)                              # today carries no theme feed
    assert GrowthThemeClock().read(hist, today) == {}


def test_read_adapter_classifies_from_threaded_marketstate():
    """When `MarketState.theme_breadth` is threaded, read() delegates to the per-group logic and places
    each group — the same result as calling theme_lifecycle on the extracted readings."""
    reads = _readings(EMERGING_SIG, EMERGING_SIG, EMERGING_SIG)
    states = [_state(r, i) for i, r in enumerate(reads)]
    read = GrowthThemeClock().read(states[:-1], states[-1])
    assert read["ai"].phase == "theme:emerging"
    assert read == theme_lifecycle(reads[:-1], reads[-1])


def test_read_adapter_skips_history_states_without_a_theme_reading():
    """History states whose `theme_breadth` is None (off the weekly clock_cadence) are skipped, not treated
    as a reading — the analog of P2 dropping a feed-outage day. The determined readings that remain still
    place the group (here: warm-up on the two real readings is avoided by threading three)."""
    reads = _readings(WIDE_INST_SIG, WIDE_INST_SIG, COMPRESSED_SIG)
    hist = [_state(reads[0], 0), _state(None, 1), _state(reads[1], 2), _state(None, 3)]
    read = GrowthThemeClock().read(hist, _state(reads[2], 4))
    assert read["ai"].phase == "theme:public_laggard"    # the two None history days did not break the series


# ── boundary probes: each threshold pinned so mutating it trips a test ────────────────────────────────

def test_breadth_high_boundary_for_institutional():
    """A broad group crosses to institutional at exactly BREADTH_HIGH; just below stays emerging."""
    at = dict(EMERGING_SIG, breadth=BREADTH_HIGH)
    below = dict(EMERGING_SIG, breadth=round(BREADTH_HIGH - 0.01, 4))
    assert _read(EMERGING_SIG, EMERGING_SIG, at)["ai"].phase == "theme:institutional"
    assert _read(EMERGING_SIG, EMERGING_SIG, below)["ai"].phase == "theme:emerging"


def test_dispersion_wide_boundary_for_emerging():
    """Leaders 'lead' at exactly DISPERSION_WIDE; just below, a low-base rising group has no emergence
    signature -> dormant -> abstains."""
    at = dict(breadth=0.40, breadth_trend=0.10, rs_trend=5.0, dispersion=DISPERSION_WIDE, laggard=40.0)
    below = dict(at, dispersion=round(DISPERSION_WIDE - 0.01, 4))
    assert _read(at, at, at)["ai"].phase == "theme:emerging"
    assert "ai" not in _read(below, below, below)


def test_exhaustion_confirm_count_boundary():
    """Exactly EXHAUSTION_CONFIRM consecutive weak readings flip to exhaustion; one fewer does not."""
    at = [INSTITUTIONAL_SIG, INSTITUTIONAL_SIG] + [WEAK_SIG] * EXHAUSTION_CONFIRM
    below = [INSTITUTIONAL_SIG, INSTITUTIONAL_SIG] + [WEAK_SIG] * (EXHAUSTION_CONFIRM - 1)
    assert _read(*at)["ai"].phase == "theme:exhaustion"
    assert _read(*below)["ai"].phase == "theme:institutional"


def test_dispersion_compress_boundary_for_public_laggard():
    """Compression at exactly DISPERSION_COMPRESS below the wide peak rings the timer; less does not."""
    peak = 40.0
    at = dict(WIDE_INST_SIG, dispersion=peak - DISPERSION_COMPRESS)
    below = dict(WIDE_INST_SIG, dispersion=round(peak - DISPERSION_COMPRESS + 0.01, 4))
    assert _read(dict(WIDE_INST_SIG, dispersion=peak), WIDE_INST_SIG, at)["ai"].phase == "theme:public_laggard"
    assert _read(dict(WIDE_INST_SIG, dispersion=peak), WIDE_INST_SIG, below)["ai"].phase == "theme:institutional"


def test_thresholds_are_named_constants():
    """Thresholds are 文献值待verdict校准 named constants across the two scales, not magic literals."""
    assert 0.0 < BREADTH_LOW_BASE < BREADTH_HIGH < 1.0       # breadth fractions in [0,1]
    assert BREADTH_RISING > 0.0 > BREADTH_ROLLING_OVER
    assert RS_RISING > 0.0 > RS_FALLING                       # RS percentile-point trends
    assert 0.0 < DISPERSION_COMPRESS <= DISPERSION_WIDE <= 100.0
    assert EXHAUSTION_CONFIRM >= 2 and MIN_HISTORY >= 2


# ── the machine is a pure function of the reading series (exposed for oracle auditing, like P2) ───────

def test_run_theme_machine_is_pure_and_forward():
    """_run_theme_machine replays forward: dormant -> emerging -> institutional over a broadening tape."""
    series = _series(EMERGING_SIG, EMERGING_SIG, dict(EMERGING_SIG, breadth=0.70), INSTITUTIONAL_SIG)
    assert _run_theme_machine(series) == "institutional"
    assert _run_theme_machine(series) == _run_theme_machine(series)   # pure
