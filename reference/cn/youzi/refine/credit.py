from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from youzi.eval.trajectory import Trajectory
from youzi.harness.harness import HarnessState
from youzi.harness.skill import Skill

UNATTRIBUTED = "__unattributed__"


class SkillCredit(BaseModel):
    """本次 trajectory 对某技能(或 unattributed 桶)的增量信用汇总(frozen)。

    expectancy 语义=advantage(score−当日池基线)均值,去市场β的"选股技能"信号;
    expectancy_raw=原始 score 均值(第二字段,保留旧口径;旧构造缺省 → 0.0)。
    """
    model_config = ConfigDict(frozen=True)
    skill_id: str
    n: int
    wins: int
    losses: int
    nukes: int
    hit_rate: float
    nuke_rate: float
    expectancy: float
    expectancy_raw: float = 0.0


class CreditReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    per_skill: dict[str, SkillCredit] = Field(default_factory=dict)
    unattributed: SkillCredit | None = None
    n_scored: int = 0

    def __bool__(self) -> bool:
        return True


def resolve_skill(pattern: str, harness: HarnessState) -> Skill | None:
    """pattern → Skill:先 skill_id 精确,再归一比对 skill_id,再归一比对 name_cn;都不中 → None。

    归一(A1)= strip()+casefold():agent 引用技能时的大小写/首尾空白变体不再漏进
    unattributed——孵化技能靠试验位攒样本,孵化期样本稀缺经不起精确匹配再漏。
    多命中取第一个(registry 插入序,稳定)。
    """
    key = (pattern or "").strip()
    if not key:
        return None
    s = harness.skills.get(pattern) or harness.skills.get(key)
    if s is not None:
        return s
    norm = key.casefold()
    for sk in harness.skills.all():
        if sk.skill_id.strip().casefold() == norm:
            return sk
    for sk in harness.skills.all():
        if sk.name_cn.strip().casefold() == norm:
            return sk
    return None


def _classify(outcome: str) -> tuple[bool, bool]:
    """oracle outcome → (是否 win, 是否 nuked)。score 改由 ScoredCandidate.score 提供(支持收益 oracle)。"""
    return outcome == "continued", outcome == "nuked"


class _Acc:
    __slots__ = ("n", "wins", "losses", "nukes", "score_sum", "adv_sum")

    def __init__(self) -> None:
        self.n = 0
        self.wins = 0
        self.losses = 0
        self.nukes = 0
        self.score_sum = 0.0    # 原始 score 口径累计
        self.adv_sum = 0.0      # advantage(截面超额)口径累计

    def add(self, oc: str, score: float, advantage: float) -> None:
        win, nuked = _classify(oc)
        self.n += 1
        self.score_sum += score
        self.adv_sum += advantage
        if win:
            self.wins += 1
        else:
            self.losses += 1
        if nuked:
            self.nukes += 1

    def to_credit(self, skill_id: str) -> SkillCredit:
        return SkillCredit(skill_id=skill_id, n=self.n, wins=self.wins,
                           losses=self.losses, nukes=self.nukes,
                           hit_rate=self.wins / self.n, nuke_rate=self.nukes / self.n,
                           expectancy=self.adv_sum / self.n,
                           expectancy_raw=self.score_sum / self.n)


def apply_credit(traj: Trajectory, harness: HarnessState, decay: float = 0.1) -> CreditReport:
    """对已打分轨迹做信用分配:就地更新被引用技能的 SkillStats(观测,不入 EditLog),返回本次增量汇总。

    口径(C2):SkillStats.expectancy 语义=**advantage**(score−当日池基线,截面超额)
    的累计均值——Refiner 拿到的是"选股技能"而非"市场方向"信号;原始 score 口径同步
    Welford 进 expectancy_raw(第二字段)。基线缺失日 advantage 已在打分侧回退=score。
    契约:对一条 trajectory **调用一次**;重复调用会重复计入(stats 设计为累计)。
    防火墙:输入是走完轨迹的已实现结果,纯事后分析,不回灌 ≤t 推理。
    """
    per: dict[str, _Acc] = {}
    unattr = _Acc()
    n_scored = 0
    for step in traj.scored_steps():                  # 按 step 顺序=决策日序,忠实 ewma 衰减
        for code, sc in step.outcomes.items():
            n_scored += 1
            skill = resolve_skill(sc.pattern, harness)
            if skill is None:
                unattr.add(sc.outcome, sc.score, sc.advantage)   # 未匹配:进 unattributed
                continue
            win, nuked = _classify(sc.outcome)
            skill.stats.record(win, decay)
            # Welford 双口径同步:expectancy=advantage(去β);expectancy_raw=原始 score(支持收益)
            m = skill.stats.expectancy if skill.stats.expectancy is not None else 0.0
            skill.stats.expectancy = m + (sc.advantage - m) / skill.stats.n
            mr = skill.stats.expectancy_raw if skill.stats.expectancy_raw is not None else 0.0
            skill.stats.expectancy_raw = mr + (sc.score - mr) / skill.stats.n
            if nuked:
                skill.stats.nukes += 1
            per.setdefault(skill.skill_id, _Acc()).add(sc.outcome, sc.score, sc.advantage)
    return CreditReport(
        per_skill={sid: acc.to_credit(sid) for sid, acc in per.items()},
        unattributed=unattr.to_credit(UNATTRIBUTED) if unattr.n else None,
        n_scored=n_scored,
    )


def merge_credit_reports(reports: list[CreditReport]) -> CreditReport:
    """把多份增量 CreditReport 合并为一份(纯只读,不触 SkillStats)。

    per_skill 按 skill_id 累加 n/wins/losses/nukes 与双口径和(adv_sum=expectancy*n、
    score_sum=expectancy_raw*n),经 _Acc.to_credit 重算 hit_rate/nuke_rate/双 expectancy;
    unattributed 同法;n_scored 累加。
    给内环 refiner 当"本窗口谁在亏"的只读证据,区别于 H 内由 apply_credit 直写的累计 stats。
    """
    per: dict[str, _Acc] = {}
    unattr = _Acc()
    n_scored = 0

    def _absorb(acc: _Acc, sc: SkillCredit) -> None:
        acc.n += sc.n
        acc.wins += sc.wins
        acc.losses += sc.losses
        acc.nukes += sc.nukes
        acc.adv_sum += sc.expectancy * sc.n
        acc.score_sum += sc.expectancy_raw * sc.n

    for rep in reports:
        n_scored += rep.n_scored
        for sid, sc in rep.per_skill.items():
            _absorb(per.setdefault(sid, _Acc()), sc)
        if rep.unattributed is not None:
            _absorb(unattr, rep.unattributed)
    return CreditReport(
        per_skill={sid: acc.to_credit(sid) for sid, acc in per.items()},
        unattributed=unattr.to_credit(UNATTRIBUTED) if unattr.n else None,
        n_scored=n_scored,
    )
