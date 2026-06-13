from __future__ import annotations

from youzi.harness.errors import InvalidTransitionError
from youzi.harness.regime import split_regimes
from youzi.harness.skill import Skill


class SkillRegistry:
    """技能库 K(按 id 索引)。Phase-0b-1 只读/查询;CRUD 编辑见 Phase-0b-2。"""

    def __init__(self, skills: dict[str, Skill]) -> None:
        self._skills = dict(skills)          # 防御性拷贝

    @classmethod
    def from_skills(cls, skills: list[Skill]) -> "SkillRegistry":
        index: dict[str, Skill] = {}
        for s in skills:
            if s.skill_id in index:
                raise ValueError(f"重复 skill_id: {s.skill_id}")
            index[s.skill_id] = s
        return cls(index)

    def get(self, skill_id: str) -> Skill | None:
        return self._skills.get(skill_id)

    def all(self) -> list[Skill]:
        return list(self._skills.values())

    def by_status(self, status: str) -> list[Skill]:
        return [s for s in self._skills.values() if s.status == status]

    def by_type(self, type_: str) -> list[Skill]:
        return [s for s in self._skills.values() if s.type == type_]

    def by_phase(self, phase: str) -> list[Skill]:
        return [s for s in self._skills.values() if phase in s.phases or s.applies_all]

    def by_ecology(self, ecology: str) -> list[Skill]:
        return [s for s in self._skills.values() if ecology in s.ecologies]

    def __len__(self) -> int:
        return len(self._skills)

    def __bool__(self) -> bool:
        return True

    # ── CRUD + 生命周期 ──────────────────────────────────────────────────

    _PATCH_FORBIDDEN = {"status", "phases", "ecologies", "applies_all", "stats"}

    def _require(self, skill_id: str) -> Skill:
        s = self._skills.get(skill_id)
        if s is None:
            raise KeyError(f"无此 skill_id: {skill_id}")
        return s

    def write(self, skill: Skill) -> None:
        if skill.skill_id in self._skills:
            raise ValueError(f"重复 skill_id: {skill.skill_id}")
        self._skills[skill.skill_id] = skill

    def patch(self, skill_id: str, **fields) -> Skill:
        s = self._require(skill_id)
        bad = self._PATCH_FORBIDDEN & fields.keys()
        if bad:
            raise ValueError(f"不可直接 patch {sorted(bad)}:status 用 retire/revive/promote;phases/ecologies 派生自 applicable_regime;stats 是观测字段(由 apply_credit 维护,Refiner 不可改)")
        snapshot = {k: getattr(s, k) for k in fields if k in type(s).model_fields}
        try:
            for k, v in fields.items():
                setattr(s, k, v)                 # validate_assignment 走校验
        except Exception:
            for k, v in snapshot.items():   # 回滚已改字段(旧值合法,setattr 不会再失败)
                setattr(s, k, v)
            raise
        if "applicable_regime" in fields:           # 改了原始 regime -> 重算派生 applies_all/phases/ecologies
            raw = s.applicable_regime
            s.applies_all = "all" in raw
            s.phases, s.ecologies = split_regimes([r for r in raw if r != "all"])
        return s

    def retire(self, skill_id: str, permanent: bool = False) -> Skill:
        """退役:默认 -> dormant(保指纹待轮回复活);permanent -> retired。"""
        s = self._require(skill_id)
        if s.status == "retired" and not permanent:
            raise InvalidTransitionError(f"{skill_id} 已永久退役(retired),不接受非永久 retire")
        s.status = "retired" if permanent else "dormant"
        return s

    def revive(self, skill_id: str) -> Skill:
        """复活:仅允许 dormant -> incubating。"""
        s = self._require(skill_id)
        if s.status != "dormant":
            raise InvalidTransitionError(f"{skill_id} 非 dormant(当前 {s.status}),不能 revive")
        s.status = "incubating"
        return s

    def promote(self, skill_id: str) -> Skill:
        """晋升:仅允许 incubating -> active。"""
        s = self._require(skill_id)
        if s.status != "incubating":
            raise InvalidTransitionError(f"{skill_id} 非 incubating(当前 {s.status}),不能 promote")
        s.status = "active"
        return s
