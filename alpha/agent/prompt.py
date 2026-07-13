from __future__ import annotations

from datetime import date, datetime
from typing import Callable

from alpha.agent.retrieval import (
    DEFAULT_MEMORY_BUDGET, DEFAULT_SKILL_BUDGET, DEFAULT_TRIAL_SLOTS,
    DEFAULT_EPISODE_BUDGET, Selection, select_for_prompt,
    select_episodes_for_prompt,
)
from alpha.harness.regime import CANONICAL_PHASES
from alpha.harness.skill import Skill
from alpha.harness.state import HarnessState
from alpha.state.market import MarketState
from alpha.universe.universe import CandidateUniverse

# Bump when the prompt template changes (used by the future LLM cache key to invalidate old records).
PROMPT_FINGERPRINT = "us5-v1"


def available_data_signals(universe: CandidateUniverse) -> frozenset[str]:
    """Live data signals: StockSnapshot fields with a `= None` default (OHLCV + enrichments — close,
    prev_close, pct_change, gap_pct, volume, rvol, consecutive_up_days, short_interest, days_to_cover,
    free_float, options_flow, social_sentiment)
    that are non-None for at least one candidate today. Required fields (symbol/name/status — whose
    FieldInfo.default is PydanticUndefined, not None) are excluded, so a skill's depends_on names a real
    data dependency rather than an always-present structural field. A skill is surfaced only when its
    depends_on is a subset of these signals."""
    sigs: set[str] = set()
    for snap in universe.all():
        for field, info in snap.__class__.model_fields.items():
            if info.default is None and getattr(snap, field) is not None:   # optional enrichment, present
                sigs.add(field)
    return frozenset(sigs)


def _depends_on_satisfied(skill: Skill, signals: frozenset[str]) -> bool:
    """A skill is eligible to be surfaced iff every data dependency it declares is a live signal.
    Empty depends_on (the common case) is always satisfied. Enforces the previously-decorative
    Skill.depends_on (e.g. short_squeeze needs short_interest+days_to_cover; gamma_squeeze needs
    options_flow)."""
    return set(skill.depends_on) <= signals

_OUTPUT_CONTRACT = (
    'Output STRICT JSON (no markdown fences): '
    '{"regime_read": "<one of the 6 phases + frontside/backside>", '
    '"candidates": [{"symbol": "<MUST be a ticker from the candidate universe>", '
    '"pattern": "<the matched skill_id>", "reason": "<brief>", "confidence": <0..1>, '
    '"narrative": "<short sympathy/theme key, e.g. ai-compute; the SAME key on two names means they '
    'are ONE correlated bet (sized together, not stacked); empty if the name stands alone>"}], '
    '"no_trade_reason": "<reason if no trade, else empty string>"}'
)

# ── momo (default) persona + cycle line, factored out so the growth branch is a clean sibling. The
# momo strings are the pre-P0.5 literals verbatim, so the momo prompt stays byte-identical. ──
_MOMO_PERSONA = (
    "You are a US speculative-momentum trading co-pilot. Read the day's state and the candidate "
    "universe and propose ranked candidates with a plan. A human confirms; you never place orders."
)
_MOMO_CYCLE_LINE = (
    "\nMARKET REGIME CYCLE (per-day phase): " + " -> ".join(CANONICAL_PHASES)
    + " (frontside/backside is a per-line momentum-direction read — early/healthy vs late/topping"
    + " — not a fixed function of phase)."
)

# ── growth pack (P0.5): thesis-first sector-growth persona, the three scale-typed clocks, and an
# output contract whose regime_read enum carries the growth market-clock tokens (Option B). ──
_GROWTH_PERSONA = (
    "You are a US sector-growth investing co-pilot (weeks-to-months horizon, earnings- and "
    "industry-cycle driven). Reason thesis-first: read the market clock, the theme's lifecycle "
    "stage, and the leading stock's stage, then propose ranked candidates whose primary reason is "
    "an industry thesis, never an indicator. A human confirms; you never place orders."
)
_GROWTH_CLOCK_LINE = (
    "\nMARKET CLOCK (weeks-to-months): market:confirmed_uptrend -> market:under_pressure -> "
    "market:correction, cross-cut by the market:panic_state flag (a momentum-crash regime). Also "
    "read the theme lifecycle (theme:emerging -> theme:institutional -> theme:public_laggard -> "
    "theme:exhaustion) and the stock stage (stock:base -> stock:advance -> stock:top -> "
    "stock:decline). A higher scale vetoes a lower one; a lower scale never scores a higher one."
)
_GROWTH_OUTPUT_CONTRACT = (
    'Output STRICT JSON (no markdown fences): '
    '{"regime_read": "<the market-clock state: one of market:confirmed_uptrend / '
    'market:under_pressure / market:correction, optionally noting market:panic_state>", '
    '"candidates": [{"symbol": "<MUST be a ticker from the candidate universe>", '
    '"pattern": "<the matched skill_id>", "reason": "<cite the thesis card, not an indicator>", '
    '"confidence": <0..1>, '
    '"narrative": "<the theme key, e.g. ai-compute; the SAME key on two names means they are ONE '
    'correlated bet (sized together, not stacked); empty if the name stands alone>"}], '
    '"no_trade_reason": "<reason if no trade, else empty string>"}'
)


def _red_line(e) -> str:
    return f"- [RED-LINE] {e.section}: {e.guidance}"


def _mutable_doctrine_line(e) -> str:
    return f"- {e.section} [{'/'.join(e.phases) or 'all'}]: {e.guidance}"


def _skill_line(s: Skill) -> str:
    line = (f"- {s.name} ({s.skill_id}) [{s.type}, {s.family or 'any'}] phases[{'/'.join(s.phases)}] "
            f"trigger: {s.trigger} | entry: {s.entry} | exit: {s.exit_stop} "
            f"| taboo: {'; '.join(s.taboo)}")
    st = s.stats
    if st.n > 0:                                   # show track record (incl. losses/nukes)
        bits = f"n={st.n} nukes={st.nukes}"
        if st.ewma_winrate is not None:
            bits += f" win={st.ewma_winrate:.2f}"
        if st.expectancy is not None:
            bits += f" exp={st.expectancy:+.2f}"
        line += f" [{bits}]"
    return line


def build_system_prompt(h: HarnessState, *, injection: str = "full", phase_prior: str | None = None,
                        skill_budget: int = DEFAULT_SKILL_BUDGET,
                        memory_budget: int = DEFAULT_MEMORY_BUDGET,
                        trial_slots: int = DEFAULT_TRIAL_SLOTS,
                        available_signals: frozenset[str] | None = None,
                        asof: date | datetime | None = None,
                        episode_store=None, episode_budget: int = DEFAULT_EPISODE_BUDGET,
                        collect: Callable[[dict], None] | None = None,
                        pack: str | None = None) -> str:
    """Render H=(p,K,M) + the regime cycle + the output contract into the system prompt.

    injection='full' renders all active skills + all lessons; 'retrieval' renders a budgeted slice
    (phase-prior hit first). Rebuilt every decide() so Refiner edits to H are immediately visible.

    `pack` (P0.5) selects the persona / clock line / doctrine order / output contract. None reads
    the vocabulary stamped ON THE H being rendered (`h.vocabulary`; momo default = byte-identical to
    the pre-P0.5 prompt) — the pack rides WITH the harness, not the process env, so a momo H always
    renders the momo persona even under ALPHA_SEED_PACK=growth (and vice-versa). The growth pack
    rewrites the persona (sector-growth, thesis-first), injects the doctrine prose before the
    quantitative skill panel, moves the red-lines to tail constraints, and swaps the output-contract
    regime enum to the growth market-clock tokens.

    `collect`: D3 prompt-audit hook (observe-only; default None is byte-identical to omitting it — no
    other logic changes). When set, receives one dict per skill/lesson/episode this call considers —
    `{"kind": "skill"|"lesson"|"episode", "id": ..., "status": "offered"|"dropped", "reason": ...}`
    (every "dropped" record names a reason: depends_on-unmet / budget-cut / weight-cut) — plus a final
    `{"kind": "assembled", "text": <the returned prompt>}`.
    """
    asof_d = asof.date() if isinstance(asof, datetime) else asof   # PIT key compares date<=date
    if injection == "retrieval":
        sel = select_for_prompt(h, phase_prior=phase_prior, skill_budget=skill_budget,
                                memory_budget=memory_budget, trial_slots=trial_slots, asof=asof_d,
                                collect=collect)
        skills, trials, lessons = sel.skills, sel.trials, sel.lessons
    else:
        skills = [s for s in h.skills.all()
                  if s.status == "active" and getattr(s, "domain", "trading") == "trading"]
        trials = [s for s in h.skills.all()
                  if s.status == "incubating" and getattr(s, "domain", "trading") == "trading"]
        lessons = [l for l in h.memory.all()
                   if (asof_d is None or l.learned_asof is None or l.learned_asof <= asof_d)
                   and getattr(l, "domain", "trading") == "trading"]

    if available_signals is not None:                    # US-3c: enforce Skill.depends_on (None = off)
        if collect is not None:
            for s in skills:
                if not _depends_on_satisfied(s, available_signals):
                    collect({"kind": "skill", "id": s.skill_id, "status": "dropped",
                            "reason": "depends_on-unmet"})
            for s in trials:
                if not _depends_on_satisfied(s, available_signals):
                    collect({"kind": "skill", "id": s.skill_id, "status": "dropped",
                            "reason": "depends_on-unmet"})
        skills = [s for s in skills if _depends_on_satisfied(s, available_signals)]
        # filtering runs after select_for_prompt's trial-slot budget, so it may leave fewer trials than
        # trial_slots — acceptable (a data-less trial skill carries no signal worth a slot anyway).
        trials = [s for s in trials if _depends_on_satisfied(s, available_signals)]

    if collect is not None:                               # what's left after every filter = offered
        for s in skills:
            collect({"kind": "skill", "id": s.skill_id, "status": "offered"})
        for s in trials:
            collect({"kind": "skill", "id": s.skill_id, "status": "offered"})
        for l in lessons:
            collect({"kind": "lesson", "id": l.lesson_id, "status": "offered"})

    is_growth = (pack or h.vocabulary) == "growth"   # pack rides with the H, not the process env (P0.5)
    _trading = lambda e: getattr(e, "domain", "trading") == "trading"
    reds = [e for e in h.doctrine.immutable_core() if _trading(e)]
    muts = [e for e in h.doctrine.mutable_entries() if _trading(e)]

    if is_growth:
        # Isomorphism: thesis/cycle doctrine prose leads, before the quantitative skill panel; the
        # red-lines (guard/limit state) inject as tail constraints only (below).
        parts = [_GROWTH_PERSONA, _GROWTH_CLOCK_LINE,
                 "\nDOCTRINE (thesis & cycle reasoning — read this before the detectors):"]
        parts += [_mutable_doctrine_line(e) for e in muts]
    else:
        parts = [_MOMO_PERSONA, _MOMO_CYCLE_LINE, "\nDOCTRINE (immutable red-lines are absolute):"]
        parts += [_red_line(e) for e in reds]
        parts += [_mutable_doctrine_line(e) for e in muts]
    parts.append("\nSKILLS (K):")
    parts += [_skill_line(s) for s in skills]
    if trials:
        parts.append("\nINCUBATING (trial — use sparingly to gather evidence):")
        parts += [_skill_line(s) for s in trials]
    if lessons:
        parts.append("\nMEMORY (M):")
        for l in lessons:
            tag = {"principle": "PRINCIPLE", "loss": "LOSS", "win": "WIN"}.get(l.outcome, l.outcome.upper())
            analog = f"{l.named_analog}: " if l.named_analog else ""
            parts.append(f"- [{tag}] {analog}{l.lesson}")
    if episode_store is not None:
        eps = select_episodes_for_prompt(episode_store, phase_prior=phase_prior, asof=asof_d,
                                         budget=episode_budget, collect=collect)
        if collect is not None:
            for e in eps:
                collect({"kind": "episode", "id": e.episode_id, "status": "offered"})
        if eps:
            parts.append("\nRECALLED EPISODES (what happened last time in this regime):")
            for e in eps:
                refl = f": {e.reflection_text}" if e.reflection_text else ""
                parts.append(f"- [{e.phase}] {e.symbol}/{e.skill_id} -> {e.outcome} "
                             f"(adv {e.advantage:+.1f}){refl}")
    if is_growth:                                        # guard/limit state as tail constraints only
        parts.append("\nHARD CONSTRAINTS (red-lines — absolute; they override everything above):")
        parts += [_red_line(e) for e in reds]
    parts.append("\n" + (_GROWTH_OUTPUT_CONTRACT if is_growth else _OUTPUT_CONTRACT))
    prompt = "\n".join(parts)
    if collect is not None:
        collect({"kind": "assembled", "text": prompt})
    return prompt


def build_user_prompt(state: MarketState, universe: CandidateUniverse) -> str:
    """Render the day's MarketState + the candidate universe into the user prompt."""
    sn = f"{state.sentiment_norm:.2f}" if state.sentiment_norm is not None else "n/a"
    ft = f"{state.follow_through_rate:.2f}" if state.follow_through_rate is not None else "n/a"
    head = (f"Date {state.date}. gainers={state.gainer_count} gap_ups={state.gap_up_count} "
            f"losers={state.loser_count} failed_breakouts={state.failed_breakout_count} "
            f"max_runner_tier={state.max_runner_tier} follow_through={ft} sentiment_norm={sn}.")
    lines = ["\nCANDIDATE UNIVERSE (only these symbols are tradeable today):"]
    for s in sorted(universe.all(), key=lambda x: x.symbol):
        pct = f"{s.pct_change:+.0f}%" if s.pct_change is not None else "?"
        rvol = f"{s.rvol:.1f}" if s.rvol is not None else "?"
        cud = s.consecutive_up_days if s.consecutive_up_days is not None else "?"
        line = f"- {s.symbol} ({s.name}) [{s.status}] pct={pct} rvol={rvol} up_days={cud}"
        if s.short_interest is not None:                 # squeeze fuel — only shown when data is live
            dtc = f" dtc={s.days_to_cover:.1f}" if s.days_to_cover is not None else ""
            line += f" si={s.short_interest:.0f}%{dtc}"
        if s.free_float is not None:                      # low-float context (dilution-pump fuel)
            line += f" float={s.free_float:.0f}M"
        if s.options_flow is not None:                    # gamma fuel (near-the-money call flow)
            line += f" optflow={s.options_flow:.1f}"
        if s.social_sentiment is not None:                # social-euphoria context
            line += f" social={s.social_sentiment:.1f}"
        lines.append(line)
    return head + "\n".join(lines)
