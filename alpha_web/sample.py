"""Deterministic SAMPLE artifacts for the Decisions / Verdict pages.

When no real artifact is wired (env vars in `app.py`), these render so the console is meaningful
out of the box. They are built from the REAL models and stay internally consistent with the live
logic: every `size_tier` is the actual `size_tier(confidence, risk_gate)` mapping, and the regime
is the actual `GCycle` read of the sample state — nothing hand-faked. Illustrative tickers only.
"""
from __future__ import annotations

from datetime import date as Date, datetime as DateTime

from alpha.eval.decision import (
    Candidate, DecisionPackage, FillFeasibility, Portfolio, TabooCheck,
)
from alpha.regime.classifier import GCycle, RegimeRead
from alpha.sizing.correlation import Pick
from alpha.sizing.portfolio import plan_portfolio
from alpha.sizing.position import SizingConfig, size_tier
from alpha.state.market import MarketState, RunnerRung

_AS_OF = DateTime(2026, 3, 17, 16, 0, 0)
_DAY = Date(2026, 3, 17)


def sample_market_state() -> MarketState:
    """A frontside-trend session: broad gainers, follow-through holding, low failed-breakout rate."""
    return MarketState(
        date=_DAY,
        gainer_count=210,
        gap_up_count=88,
        loser_count=120,
        failed_breakout_count=40,          # fb_rate = 40/210 = 0.19 -> below the 0.4 distribution line
        max_runner_tier=5,
        echelon=[
            RunnerRung(tier=5, count=1, representatives=["GPUX"]),
            RunnerRung(tier=4, count=2, representatives=["CHPS", "VLTX"]),
            RunnerRung(tier=3, count=6, representatives=["NEUR", "ARClabs", "QBIT"]),
            RunnerRung(tier=2, count=14, representatives=["BIOX", "SOLR"]),
            RunnerRung(tier=1, count=37, representatives=[]),
        ],
        breadth_raw=0.64,
        sentiment_norm=0.62,               # proxy -> risk_gate 0.62, phase = trend
        sentiment_raw=0.71,
        follow_through_rate=0.58,
        gap_and_go_count=52,
        as_of=_AS_OF,
    )


def sample_regime() -> RegimeRead:
    """The actual GCycle read of the sample state (derived, never hand-typed)."""
    return GCycle().read(sample_market_state())


def sample_decision() -> DecisionPackage:
    """A realistic day's package: four picks spanning every size tier, a netted correlated pair,
    a guard-vetoed/unbuyable pick the system keeps visible but flattens, and the portfolio budget."""
    reg = sample_regime()
    rg = reg.risk_gate

    def cand(symbol, name, pattern, skill_id, family, conf, entry, exit_stop, counterview,
             taboos, fill=None, narrative=""):
        return Candidate(
            symbol=symbol, name=name, pattern=pattern, skill_id=skill_id, family=family,
            confidence=conf, size_tier=size_tier(conf, rg), narrative=narrative,
            reason=counterview.split(".")[0] + "." if counterview else "",
            entry=entry, exit_stop=exit_stop, counterview=counterview,
            fill_feasibility=fill or FillFeasibility(buyable=True, reason=""),
            taboo_check=[TabooCheck(rule=r, status=st) for r, st in taboos],
        )

    candidates = [
        cand("GPUX", "Helio GPU Systems", "Gap and Go", "gap_and_go", "runner", 0.98,
             "Buy the opening-range-high reclaim that holds VWAP.",
             "Lose VWAP / opening-range low.",
             "Lead AI-compute runner, day 5. Extended ~12% over VWAP — a failed reclaim flips this to no-trade.",
             [("chase extended far above VWAP", "pass"), ("enter in risk-off / backside", "pass")],
             narrative="ai-compute"),
        cand("CHPS", "Chipset Labs", "Pullback to Moving Average", "pullback_to_ma", "swing", 0.80,
             "Buy the reclaim of the rising 10 EMA.",
             "Decisive loss of the 10 EMA.",
             "First sympathy to GPUX — same AI-compute narrative, so it is netted into one bet, not stacked.",
             [("catch a knife below a broken MA", "pass")],
             narrative="ai-compute"),
        cand("BIOX", "Biox Therapeutics", "Earnings Gap Continuation", "earnings_gap_continuation", "event", 0.45,
             "Buy the gap-and-hold above the opening range.",
             "Lose the gap / fill.",
             "Holds its earnings gap, but a binary PDUFA prints inside the 2-day horizon — probe and size for a total loss.",
             [("chase a gap that is already fading", "pass"), ("hold a biotech binary naked over the event", "pass")]),
        cand("MEMR", "Memetic Resources", "Short Squeeze", "short_squeeze", "meme", 0.22,
             "Buy the reclaim with strength.",
             "Exit on squeeze exhaustion / loss of the reclaim.",
             "Parabolic squeeze into resistance. Halted LULD at the open — no realistic fill — and conviction is thin.",
             [("chase a parabolic squeeze top", "fail")],
             fill=FillFeasibility(buyable=False, reason="Halted (LULD) at the open; no realistic entry.")),
    ]

    # the portfolio is the REAL netting of these picks (GPUX+CHPS net to one ai-compute bet)
    plan = plan_portfolio([Pick(symbol=c.symbol, narrative=c.narrative, confidence=c.confidence)
                           for c in candidates], rg, SizingConfig())

    return DecisionPackage(
        date=_DAY,
        as_of=_AS_OF,
        candidates=candidates,
        regime=reg,
        regime_read=("Frontside trend — leaders trending, follow-through holding (0.58), "
                     "failed-breakout rate low (0.19)."),
        key_risks=[
            "GPUX + CHPS are one AI-compute narrative — netted as a single bet, never two.",
            "BIOX carries a binary PDUFA inside the 2-day hold horizon.",
            "Tape is frontside but extended; one distribution day on the leaders flips the gate.",
        ],
        portfolio=Portfolio(
            total_exposure_budget=plan.total_exposure_budget,
            correlated_groups=plan.correlated_groups,
            total_exposure=plan.total_exposure,
            capped=plan.capped,
        ),
    )


def sample_verdict() -> dict:
    """A SAMPLE HCH-vs-Hexpert report in the bespoke UI dict shape that `verdict.html` consumes — NOT
    `ComparisonReport`'s shape (that has flat fields + arm metrics nested under `.report`; this is a
    flattened view dict). The honest expectation is parity (HCH ~= Hexpert) — so the headline is a
    hair positive, the stat verdict inconclusive. `ALPHA_WEB_VERDICT` must point at JSON in THIS shape."""
    return {
        "window": {"start": "2026-01-02", "end": "2026-03-31", "horizon": 2, "windows": 3, "screen": True},
        "arms": {
            "HCH": {"n_decisions": 41, "n_candidates": 96, "mean_excess": 0.0034, "hit_rate": 0.54,
                    "nuke_rate": 0.07, "refines": 3, "trips": 1, "frozen_from": None},
            "Hexpert": {"n_decisions": 41, "n_candidates": 94, "mean_excess": 0.0029, "hit_rate": 0.53,
                        "nuke_rate": 0.08},
            "Hmin_chase": {"n_decisions": 41, "n_candidates": 121, "mean_excess": -0.0061, "hit_rate": 0.46,
                           "nuke_rate": 0.13},
            "Hmin_notrade": {"n_decisions": 41, "n_candidates": 0, "mean_excess": 0.0, "hit_rate": 0.0,
                             "nuke_rate": 0.0},
        },
        "headline": {"hch_minus_hexpert": 0.0005, "hch_beats_hexpert": True},
        "stat_verdict": {"verdict": "inconclusive", "n_days": 41, "mean_diff": 0.0005,
                         "ci_low": -0.0021, "ci_high": 0.0031, "p_value": 0.71, "mde": 0.004},
        "contribution": {
            "offense": {"n": 58, "hit_rate": 0.57, "nuke_rate": 0.05, "expectancy": 0.0091},
            "defense": {"n": 23, "hit_rate": 0.48, "nuke_rate": 0.09, "expectancy": 0.0042},
            "unknown": {"n": 15, "hit_rate": 0.40, "nuke_rate": 0.13, "expectancy": -0.0030},
        },
    }


def sample_evolution() -> dict:
    """A SAMPLE inner-loop edit trajectory in the shape `scripts/save_evolution.py` writes: the audit
    of how the Refiner changed H (doctrine / skills / memory) across a run. Each entry is an
    `EditRecord.model_dump()`. A real run replaces this (set `ALPHA_WEB_EVOLUTION`)."""
    edits = [
        {"seq": 0, "tool": "promote_skill", "target_kind": "skill", "target_id": "short_squeeze",
         "op": "promote", "summary": "incubating → active",
         "payload": {"status": {"before": "incubating", "after": "active"}},
         "rationale": "Cleared the evidence gate: positive expectancy over 7 short-interest days, nuke-rate 0.05."},
        {"seq": 1, "tool": "patch_skill", "target_kind": "skill", "target_id": "gap_and_go",
         "op": "update", "summary": "tightened the chase taboo",
         "payload": {"taboo": {"before": ["chase extended far above VWAP"],
                                "after": ["chase extended >8% above VWAP", "enter in risk-off / backside"]}},
         "rationale": "Two chased_blowoff nukes on extended gap-and-go entries — codify the distance bound."},
        {"seq": 2, "tool": "rewrite_doctrine", "target_kind": "doctrine", "target_id": "trend_play",
         "op": "rewrite", "summary": "add the first-distribution-day exit",
         "payload": {"guidance": {
             "before": "Ride the lead runner and first sympathy; add on reclaims; trim into blowoffs.",
             "after": "Ride the lead runner and first sympathy; add on reclaims; trim into blowoffs; honor the first distribution day."}},
         "rationale": "Held through a leader breakdown on volume; encode the first-distribution-day trim."},
        {"seq": 3, "tool": "process_memory", "target_kind": "memory", "target_id": "weak_laggard_nuke",
         "op": "create", "summary": "new lesson",
         "payload": {"lesson": "In an ignition, the edge is the lead runner and first sympathy — not the fifth laggard."},
         "rationale": "Recurring weak_laggard_nuke signature across ignition-phase decisions."},
        {"seq": 4, "tool": "retire_skill", "target_kind": "skill", "target_id": "reverse_split_pump",
         "op": "retire", "summary": "active → dormant",
         "payload": {"status": {"before": "active", "after": "dormant"}},
         "rationale": "No qualifying setups in-window; decayed importance — parked to cut prompt noise."},
    ]
    # A4 external anchor: the real integrity-chain head over these edits (finalized at persist time).
    from alpha.harness.edit_log import EditLog
    _log = EditLog()
    for e in edits:
        _log.append(e["tool"], e["target_kind"], e["target_id"], e["op"],
                    summary=e.get("summary", ""), payload=e.get("payload"), rationale=e.get("rationale", ""))
    _log.finalize_chain()
    return {
        "window": {"start": "2026-01-02", "end": "2026-03-31"},
        "summary": {"refines": 3, "breaker_trips": 0, "frozen_from": None, "n_edits": len(edits)},
        "edits": edits,
        "chain_head": _log.chain_head(),
    }
