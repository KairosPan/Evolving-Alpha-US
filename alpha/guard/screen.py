from __future__ import annotations

from collections.abc import Sequence
from datetime import date as Date
from typing import Callable

import pandas as pd

from alpha.data.calendar import prev_trading_day
from alpha.data.corp_actions import has_dilution_filing, has_reverse_split_pending
from alpha.data.firewall import AsOfGuard
from alpha.data.offerings import is_dilution_overhang
from alpha.data.source import GuardedSource
from alpha.eval.decision import DecisionPackage
from alpha.features.earnings import days_to_earnings, has_upcoming_earnings
from alpha.guard.panic import detect_panic_state
from alpha.guard.veto import CandidateContext, veto
from alpha.memory.aggregate import is_episode_taboo, summarize
from alpha.regime.classifier import GCycle
from alpha.regime.growth_clock import GrowthMarketClock
from alpha.sizing.action import candidate_action     # shared action vocabulary (leaf; no cycle)
from alpha.state.market import MarketState

SSR_DROP_PCT = -10.0   # Reg SHO Rule 201: a >=10% prior-day decline restricts short sales the next session
HALT_SPIKE_PCT = 0.15   # an intraday high >=15% above prior close ~ a LULD halt-up (Tier-1 band) event

# P3: surfaced into key_risks (warn-the-human, NOT a veto) when the corp-actions artifact is MISSING, so
# reverse-split-pending / dilution could not be checked — distinct from a checked-and-clean empty frame.
CORP_BLIND_NOTE = ("corp-actions guard ran blind: artifact missing — reverse-split-pending / dilution "
                   "checks did not run (an unflagged split or dilution overhang may have passed)")

EARNINGS_T_MINUS = 3   # §4.5 earnings_gap_discipline: the T-3 checklist window (has_upcoming_earnings default)


def earnings_checklist_note(symbol: str, days: int) -> str:
    """P5b: the §4.5 `earnings_gap_discipline` checklist requirement, surfaced into key_risks (warn-the-
    human, NOT a veto). A new-entry candidate reporting within T-3 opens a hold-through-earnings exposure;
    the doctrine mandates the thesis checklist be completed before carrying it. The guard can KNOW the date
    is within T-3 (骨) but cannot KNOW whether the prose checklist is done (魂) — so it surfaces the mandate
    at the human confirm point rather than vetoing (spec 2026-07-13-p5b, §4.8 red-line-candidate rationale)."""
    return (f"{symbol}: earnings in {days}d (within the §4.5 T-3 window) — hold-through requires the thesis "
            f"checklist: verification node registered? counter-thesis evidence? which number falsifies?")


def _num(value) -> float | None:
    """None-and-NaN-safe scalar float (snapshot rows can carry NaN)."""
    return None if value is None or pd.isna(value) else float(value)


def halt_then_dump_proxy(row) -> bool:
    """Daily-OHLC proxy for a halt-then-dump: the name spiked intraday >= HALT_SPIKE_PCT above its prior
    close (a likely LULD halt-up) but round-tripped to close at/below the prior close — a failed spike, do
    not chase it long. `row` is a daily-snapshot record (dict) or None. Real intraday LULD halts/halt-count
    need a tick feed (deferred); this is the daily-cadence proxy. Missing/NaN data -> False (never fabricated).

    Distinct from failed_breakout (gap-up at the OPEN that closes red): this keys on the intraday HIGH
    spike (the halt-up signature), so it also catches names that opened flat, spiked, and dumped."""
    if row is None:
        return False
    prev, high, close = _num(row.get("prev_close")), _num(row.get("high")), _num(row.get("close"))
    if prev is None or high is None or close is None or prev <= 0:
        return False
    spiked = (high - prev) / prev >= HALT_SPIKE_PCT
    dumped = close <= prev
    return spiked and dumped


def _prior_day_pct(source, symbol: str, prev: Date) -> float | None:
    """Close-to-close % change for `symbol` ENDING at `prev` (the trading day before the decision day).
    Missing/short data -> None (never fabricate). Reads only bars dated <= prev (firewall-safe)."""
    cal = source.trading_calendar()
    le = [d for d in cal if d <= prev]
    if len(le) < 2:
        return None
    bars = source.daily_bars(symbol, le[-2], prev)
    if bars is None or bars.empty or "date" not in bars.columns:
        return None
    df = bars.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    closes = list(pd.to_numeric(df[df["date"] <= prev].sort_values("date")["close"], errors="coerce").dropna())
    if len(closes) < 2 or closes[-2] == 0:
        return None
    return (closes[-1] - closes[-2]) / closes[-2] * 100.0


def ssr_active(source, symbol: str, as_of: Date) -> bool:
    """Reg SHO Rule 201: True iff `symbol` fell >= 10% (close-to-close) on the PRIOR trading day, so a
    short-sale restriction is in effect on `as_of` (don't chase a one-sided tape). Missing data -> False."""
    prev = prev_trading_day(source.trading_calendar(), as_of)
    if prev is None:
        return False
    pct = _prior_day_pct(source, symbol, prev)
    return pct is not None and pct <= SSR_DROP_PCT


def screen_decision(decision: DecisionPackage, *, source, state: MarketState, episode_store=None,
                    history: Sequence[MarketState] | None = None,
                    vocabulary: str = "momo") -> DecisionPackage:
    """Apply the L4 hard veto to a freshly-produced DecisionPackage: DROP candidates the immutable-core
    guard blocks (SSR / reverse-split-pending / risk-off / backside regime) — plus, when an `episode_store`
    is wired, an §6 episode-taboo (a symbol with a strong PIT-masked nuke history). Record dropped reasons
    in key_risks, and populate the structured regime. Frozen models -> rebuilt via model_copy.

    `vocabulary` (P2) selects the regime reader — the pack rides WITH the H being run (`h.vocabulary`),
    never the process env. "growth" reads the three-state MARKET clock (`GrowthMarketClock`: FTD /
    distribution-day counting over `history`, expressed through the SAME frontside/risk_gate veto surface,
    so the immutable veto is unchanged); anything else reads the momo `GCycle` (byte-identical).

    `history` (P1/P2): the strictly-prior daily `MarketState`s. When threaded, a panic-state read (bear +
    high-vol backdrop + sharp rebound — the momentum-crash window a single-day GCycle reads as frontside
    `trend`) vetoes every new entry, AND the growth clock counts its FTD/distribution window over it.
    Default None -> the panic detector never runs and the growth clock is warm-up (byte-identical to every
    pre-P1 caller under the momo default).

    The new-entry veto applies to `enter` candidates only (P0.6): a `trim`/`exit` recommendation is a
    derisk on a HELD name, not a new chase, so it passes through unvetoed. `Candidate.action` exists
    (default "enter"); no producer emits trim/exit yet (holdings aren't modeled), so this is inert /
    byte-identical today and activates the moment a producer sets the field (spec 2026-07-13-p06 §3.3).

    P5b: when an earnings feed is present, a KEPT new-entry candidate reporting within T-3 surfaces the
    §4.5 `earnings_gap_discipline` checklist requirement into key_risks — warn-the-human, NOT a veto (the
    checklist's completeness is a prose/human judgment the code-side guard cannot make; see
    `earnings_checklist_note` and spec 2026-07-13-p5b). No earnings feed -> byte-identical (no note).

    P5: the dilution veto is lifecycle-aware when the offerings feed is present — a withdrawn/expired
    shelf stops vetoing as of its own process_date (`is_dilution_overhang`), while an active announce
    still drops the candidate. Absent -> `has_dilution_filing` (veto-forever fail-closed, byte-identical).
    Safety-only-tightens: the lifecycle lifts a veto only with dated proof of closure, never adds one.

    PIT-safe: all data reads go through a fresh GuardedSource(AsOfGuard(state.date)); SSR reads only
    prior-day bars (< as_of) and corp actions are announce-keyed (<= as_of); episode recall is masked at
    `for_asof(state.date)`. Vetoed candidates are dropped (never entered/scored) rather than annotated — a
    kept-but-failed candidate would still be scored as an entry by the drivers, defeating the hard veto."""
    as_of = state.date
    guarded = GuardedSource(source, AsOfGuard(as_of))
    regime = (GrowthMarketClock().read(history or (), state) if vocabulary == "growth"
              else GCycle().read(state))
    corp = guarded.corporate_actions_known(as_of)
    corp_available = guarded.corp_actions_available()  # P3: False -> corp artifact MISSING (reverse-split /
                                                       #   dilution ran blind); an empty-but-present frame is True
    earnings_available = guarded.earnings_available()  # P5b: False -> no earnings feed -> no T-3 note (byte-
    earnings_cal = (guarded.earnings_calendar(as_of)   #   identical). The calendar is PIT-guarded (known_asof
                    if earnings_available else [])     #   <= as_of) exactly like corporate_actions_known.
    offerings_available = guarded.offerings_available()  # P5: present -> lifecycle-aware dilution overhang
                                                         #   (a withdrawn/expired shelf stops vetoing as of its
                                                         #   own process_date); absent -> has_dilution_filing
                                                         #   (veto-forever fail-closed default, byte-identical).
    snap = guarded.daily_snapshot(as_of)               # day's OHLC for the halt-then-dump proxy (guard-safe)
    rows = ({str(r["symbol"]): r for r in snap.to_dict("records")}
            if snap is not None and not snap.empty else {})
    taboo_stats = (summarize(episode_store.for_asof(as_of, limit=None), key=lambda e: e.symbol)
                   if episode_store is not None else {})   # limit=None: full PIT history (past the 50-cap)
    panic = detect_panic_state(history, state) if history else False   # P1: momentum-crash window (per-day, not per-name)
    kept, notes = [], []
    for c in decision.candidates:
        if candidate_action(c) != "enter":     # P0.6: a trim/exit is a derisk on a HELD name, not a
            kept.append(c)                     #   new chase -> the L4 new-entry veto doesn't apply.
            continue                           #   Inert today (no producer emits trim/exit yet).
        # P5: lifecycle-aware dilution when the offerings feed is present (a proven withdrawn/expired
        # shelf lifts the veto as of its process_date); else veto-forever has_dilution_filing (unchanged).
        # The feed reads ride the SAME guarded source both verdict arms wrap -> symmetric + PIT-guarded.
        dilution = (is_dilution_overhang(guarded.offering_events_known(c.symbol, as_of), c.symbol, as_of)
                    if offerings_available else has_dilution_filing(corp, c.symbol, as_of))
        ctx = CandidateContext(symbol=c.symbol, regime=regime,
                               ssr=ssr_active(guarded, c.symbol, as_of),
                               reverse_split_pending=has_reverse_split_pending(corp, c.symbol, as_of),
                               dilution=dilution,
                               halt_then_dump=halt_then_dump_proxy(rows.get(c.symbol)),
                               episode_taboo=is_episode_taboo(taboo_stats.get(c.symbol)),
                               panic_state=panic)
        v = veto(ctx)
        if v.vetoed:
            notes.append(f"vetoed {c.symbol}: {'; '.join(v.reasons)}")
        else:
            kept.append(c)
            if earnings_available and has_upcoming_earnings(earnings_cal, c.symbol, as_of, EARNINGS_T_MINUS):
                # P5b: a KEPT new entry reporting within T-3 -> surface the §4.5 checklist requirement
                # (warn-the-human, not a veto). Only here: a trim/exit never reaches this branch (P0.6
                # continue above), and a vetoed candidate is dropped, not warned about.
                notes.append(earnings_checklist_note(c.symbol, days_to_earnings(earnings_cal, c.symbol, as_of)))
    if not corp_available and any(candidate_action(c) == "enter" for c in decision.candidates):
        notes.append(CORP_BLIND_NOTE)   # P3: once per package, and only when a blind check gated an entry
    update = {"candidates": kept, "regime": regime, "key_risks": list(decision.key_risks) + notes}
    if not kept and decision.candidates:
        update["no_trade_reason"] = decision.no_trade_reason or "all candidates vetoed by L4 guard"
    return decision.model_copy(update=update)


class GuardedPolicy:
    """Composable L4 guard: wraps any DecisionPolicy; runs it, then applies screen_decision so the
    immutable-core hard veto overrides the agent. Works in any driver that calls policy.decide()."""

    def __init__(self, inner, source, *, episode_store=None,
                 state_history: Sequence[MarketState] | None = None,
                 vocabulary: str = "momo", track_history: bool = False) -> None:
        self._inner = inner
        self._source = source
        self._episode_store = episode_store
        self._vocabulary = vocabulary               # P2: pick the regime reader (rides with the H)
        self._track_history = track_history
        # The strictly-prior daily MarketStates: the panic veto's backdrop AND the growth clock's
        # FTD/distribution window. P2 activates both by ACCUMULATING them across decide() calls
        # (track_history=True). A passed list is grown IN PLACE — InnerLoop's persistent history survives
        # a rollback-rebuild; otherwise each policy owns a fresh accumulator, so both verdict arms build
        # their own identical history from the same source (symmetric, like the screen flag / recall).
        # track_history=False keeps the P1 semantics: `state_history` is a FIXED prior context (or None =
        # detectors off -> byte-identical to every pre-P1/P2 caller).
        self._state_history = (state_history if state_history is not None else []) \
            if track_history else state_history

    def decide(self, state: MarketState, universe, *,
              collect: Callable[[dict], None] | None = None) -> DecisionPackage:
        # `collect`: D3 prompt-audit pass-through (default None = byte-identical). Forwarded to the
        # inner policy only when set, so stub/baseline inners without a `collect` kwarg are unaffected.
        kw = {} if collect is None else {"collect": collect}
        decision = self._inner.decide(state, universe, **kw)
        out = screen_decision(decision, source=self._source, state=state,
                              episode_store=self._episode_store, history=self._state_history,
                              vocabulary=self._vocabulary)
        if self._track_history:
            self._state_history.append(state)       # grow AFTER using as the strictly-prior context
        return out
