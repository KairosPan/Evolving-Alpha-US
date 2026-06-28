from __future__ import annotations

from datetime import date, datetime

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
                        episode_store=None, episode_budget: int = DEFAULT_EPISODE_BUDGET) -> str:
    """Render H=(p,K,M) + the regime cycle + the output contract into the system prompt.

    injection='full' renders all active skills + all lessons; 'retrieval' renders a budgeted slice
    (phase-prior hit first). Rebuilt every decide() so Refiner edits to H are immediately visible.
    """
    asof_d = asof.date() if isinstance(asof, datetime) else asof   # PIT key compares date<=date
    if injection == "retrieval":
        sel = select_for_prompt(h, phase_prior=phase_prior, skill_budget=skill_budget,
                                memory_budget=memory_budget, trial_slots=trial_slots, asof=asof_d)
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
        skills = [s for s in skills if _depends_on_satisfied(s, available_signals)]
        # filtering runs after select_for_prompt's trial-slot budget, so it may leave fewer trials than
        # trial_slots — acceptable (a data-less trial skill carries no signal worth a slot anyway).
        trials = [s for s in trials if _depends_on_satisfied(s, available_signals)]

    parts: list[str] = [
        "You are a US speculative-momentum trading co-pilot. Read the day's state and the candidate "
        "universe and propose ranked candidates with a plan. A human confirms; you never place orders.",
        "\nMARKET REGIME CYCLE (per-day phase): " + " -> ".join(CANONICAL_PHASES)
        + " (frontside/backside is a per-line momentum-direction read — early/healthy vs late/topping"
        + " — not a fixed function of phase).",
        "\nDOCTRINE (immutable red-lines are absolute):",
    ]
    for e in h.doctrine.immutable_core():
        if getattr(e, "domain", "trading") == "trading":
            parts.append(f"- [RED-LINE] {e.section}: {e.guidance}")
    for e in h.doctrine.mutable_entries():
        if getattr(e, "domain", "trading") == "trading":
            parts.append(f"- {e.section} [{'/'.join(e.phases) or 'all'}]: {e.guidance}")
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
                                         budget=episode_budget)
        if eps:
            parts.append("\nRECALLED EPISODES (what happened last time in this regime):")
            for e in eps:
                refl = f": {e.reflection_text}" if e.reflection_text else ""
                parts.append(f"- [{e.phase}] {e.symbol}/{e.skill_id} -> {e.outcome} "
                             f"(adv {e.advantage:+.1f}){refl}")
    parts.append("\n" + _OUTPUT_CONTRACT)
    return "\n".join(parts)


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
