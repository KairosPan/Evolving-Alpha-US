from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from alpha.eval.metrics import ScoredCandidate
from alpha.eval.trajectory import Trajectory
from alpha.harness.state import HarnessState
from alpha.refine.credit import resolve_skill


class ContributionBucket(BaseModel):
    """Aggregate over one bucket of scored picks. expectancy = mean advantage (de-market-beta lens)."""
    model_config = ConfigDict(frozen=True)
    n: int = 0
    wins: int = 0
    nukes: int = 0
    hit_rate: float = 0.0
    nuke_rate: float = 0.0
    expectancy: float = 0.0
    expectancy_raw: float = 0.0


class ContributionReport(BaseModel):
    """Offense (pattern/feature) vs defense (failure_detector) vs unknown (unresolved pattern), plus a
    per-family breakdown — does self-evolution add edge (offense) or only trim risk (defense)? (§6/§9/§10)"""
    model_config = ConfigDict(frozen=True)
    offense: ContributionBucket = Field(default_factory=ContributionBucket)
    defense: ContributionBucket = Field(default_factory=ContributionBucket)
    unknown: ContributionBucket = Field(default_factory=ContributionBucket)
    by_family: dict[str, ContributionBucket] = Field(default_factory=dict)


class _BucketAcc:
    __slots__ = ("n", "wins", "nukes", "adv_sum", "score_sum")

    def __init__(self) -> None:
        self.n = self.wins = self.nukes = 0
        self.adv_sum = self.score_sum = 0.0

    def add(self, sc: ScoredCandidate) -> None:
        self.n += 1
        self.wins += int(sc.outcome == "continued")
        self.nukes += int(sc.outcome == "nuked")
        self.adv_sum += sc.advantage
        self.score_sum += sc.score

    def bucket(self) -> ContributionBucket:
        d = self.n or 1
        return ContributionBucket(n=self.n, wins=self.wins, nukes=self.nukes, hit_rate=self.wins / d,
                                  nuke_rate=self.nukes / d, expectancy=self.adv_sum / d,
                                  expectancy_raw=self.score_sum / d)


def contribution_split(traj: Trajectory, h: HarnessState) -> ContributionReport:
    """Bucket each scored candidate by its resolved skill: offense = Skill.type in {pattern, feature},
    defense = failure_detector, unknown = unresolved pattern; plus per Skill.family. Resolve against the
    H the trajectory was produced under (the EVOLVED HCH harness) so Refiner-minted/renamed skills
    bucket correctly. A non-empty `unknown` flags patterns the agent emitted that aren't in K."""
    off, dfn, unk = _BucketAcc(), _BucketAcc(), _BucketAcc()
    fam: dict[str, _BucketAcc] = {}
    for step in traj.scored_steps():
        for sc in step.outcomes.values():
            skill = resolve_skill(sc.pattern, h)
            if skill is None:
                unk.add(sc)
                continue
            (dfn if skill.type == "failure_detector" else off).add(sc)
            if skill.family:
                fam.setdefault(skill.family, _BucketAcc()).add(sc)
    return ContributionReport(offense=off.bucket(), defense=dfn.bucket(), unknown=unk.bucket(),
                              by_family={k: a.bucket() for k, a in fam.items()})
