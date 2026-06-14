from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from alpha.eval.trajectory import Trajectory
from alpha.harness.skill import Skill
from alpha.harness.state import HarnessState

UNATTRIBUTED = "__unattributed__"


def resolve_skill(pattern: str, h: HarnessState) -> Skill | None:
    """Map a policy-declared (free-text) pattern to a skill: exact id, then normalized id, then name."""
    if not pattern:
        return None
    direct = h.skills.get(pattern)
    if direct is not None:
        return direct
    key = pattern.strip().casefold()
    if not key:
        return None
    for s in h.skills.all():
        if s.skill_id.strip().casefold() == key or s.name.strip().casefold() == key:
            return s
    return None


class SkillCredit(BaseModel):
    """Per-skill incremental credit for one window (read-only; H stats are the cumulative truth)."""
    model_config = ConfigDict(frozen=True)
    skill_id: str
    n: int = 0
    wins: int = 0
    losses: int = 0
    nukes: int = 0
    hit_rate: float = 0.0
    nuke_rate: float = 0.0
    expectancy: float = 0.0       # mean advantage (de-market-beta excess)
    expectancy_raw: float = 0.0   # mean raw score


class CreditReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    per_skill: dict[str, SkillCredit] = Field(default_factory=dict)
    unattributed: SkillCredit | None = None
    n_scored: int = 0


class _Acc:
    __slots__ = ("skill_id", "n", "wins", "losses", "nukes", "adv_sum", "score_sum")

    def __init__(self, skill_id: str) -> None:
        self.skill_id = skill_id
        self.n = self.wins = self.losses = self.nukes = 0
        self.adv_sum = 0.0
        self.score_sum = 0.0

    def add(self, win: bool, nuked: bool, advantage: float, score: float) -> None:
        self.n += 1
        self.wins += int(win)
        self.losses += int(not win)
        self.nukes += int(nuked)
        self.adv_sum += advantage
        self.score_sum += score

    def absorb(self, c: SkillCredit) -> None:
        self.n += c.n
        self.wins += c.wins
        self.losses += c.losses
        self.nukes += c.nukes
        self.adv_sum += c.expectancy * c.n
        self.score_sum += c.expectancy_raw * c.n

    def to_credit(self) -> SkillCredit:
        d = self.n or 1
        return SkillCredit(skill_id=self.skill_id, n=self.n, wins=self.wins, losses=self.losses,
                           nukes=self.nukes, hit_rate=self.wins / d, nuke_rate=self.nukes / d,
                           expectancy=self.adv_sum / d, expectancy_raw=self.score_sum / d)


def apply_credit(traj: Trajectory, h: HarnessState, decay: float = 0.1) -> CreditReport:
    """Walk the scored steps and update each matched skill's SkillStats IN PLACE (observation channel,
    NOT a meta-tool edit, NOT logged). CONTRACT: call once per trajectory; re-calling on the SAME
    trajectory double-counts. Calling on successive DISJOINT trajectories is the intended cumulative
    online path (US-2c) and keeps the running mean correct (n and the means co-evolve).
    expectancy = running mean ADVANTAGE; expectancy_raw = running mean raw score."""
    accs: dict[str, _Acc] = {}
    unattr = _Acc(UNATTRIBUTED)
    n_scored = 0
    for step in traj.scored_steps():
        for sc in step.outcomes.values():
            n_scored += 1
            win = sc.outcome == "continued"
            nuked = sc.outcome == "nuked"
            skill = resolve_skill(sc.pattern, h)
            if skill is None:
                unattr.add(win, nuked, sc.advantage, sc.score)
                continue
            st = skill.stats
            st.record(win, decay)                       # n/wins/losses/ewma_winrate
            nn = st.n
            prev_e = st.expectancy or 0.0
            prev_er = st.expectancy_raw or 0.0
            st.expectancy = prev_e + (sc.advantage - prev_e) / nn      # Welford running mean (advantage)
            st.expectancy_raw = prev_er + (sc.score - prev_er) / nn    # Welford running mean (raw)
            if nuked:
                st.nukes += 1
            accs.setdefault(skill.skill_id, _Acc(skill.skill_id)).add(win, nuked, sc.advantage, sc.score)
    return CreditReport(per_skill={sid: a.to_credit() for sid, a in accs.items()},
                        unattributed=(unattr.to_credit() if unattr.n else None), n_scored=n_scored)


def merge_credit_reports(reports: list[CreditReport]) -> CreditReport:
    """Read-only merge of incremental reports for a refine window. Does NOT touch H stats."""
    accs: dict[str, _Acc] = {}
    unattr = _Acc(UNATTRIBUTED)
    n_scored = 0
    for r in reports:
        n_scored += r.n_scored
        for sid, c in r.per_skill.items():
            accs.setdefault(sid, _Acc(sid)).absorb(c)
        if r.unattributed:
            unattr.absorb(r.unattributed)
    return CreditReport(per_skill={sid: a.to_credit() for sid, a in accs.items()},
                        unattributed=(unattr.to_credit() if unattr.n else None), n_scored=n_scored)
