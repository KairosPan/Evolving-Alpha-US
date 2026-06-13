# tests/test_refiner_real_seeds.py
"""真实种子端到端:load_seeds → 已打分 Trajectory → apply_credit + extract_signatures
→ Refiner 4-pass(p/G/K/M)经 MetaTools CRUD 编辑真实 H,断言:applied/EditLog 带
rationale/H 真变/G-pass reserved;并单独验证改 immutable 红线被拒、H 未变、EditLog 未记。

全离线(MockLLMClient 脚本化 p/K/M 三次 live 调用;G-pass 不发调用)。
"""
import json
from datetime import date
from pathlib import Path

import pandas as pd

from youzi.eval.decision import Candidate, DecisionPackage
from youzi.eval.trajectory import Trajectory
from youzi.eval.walk_forward import WalkForwardEval
from youzi.harness.loader import load_seeds
from youzi.harness.metatools import MetaTools
from youzi.llm.client import MockLLMClient
from youzi.refine.credit import CreditReport, apply_credit
from youzi.refine.refiner import Refiner, RefinerConfig
from youzi.refine.signatures import extract_signatures
from tests.conftest import FakeSource

SEEDS = Path(__file__).resolve().parent.parent / "seeds"

# 真实种子里实际存在的标识符(取自 seeds/{skills,doctrine}.json)
SKILL_W2S = "w2s_weak_to_strong"               # active pattern
SKILL_INCUBATING = "highest_board_breakthrough"  # incubating pattern → 可 retire
DOCTRINE_MUTABLE = "主升相位作战指导"            # immutable=false → 可 rewrite
DOCTRINE_IMMUTABLE = "纪律红线:退潮不接力不做卡位"  # immutable=true  → rewrite 必拒
NEW_LESSON_ID = "loss_refine_chased_into_nuke"


def _src():
    """day0: LOSER 涨停(boards=1,即当日最高板);day1: LOSER 跌停(nuked)。"""
    d0, d1 = date(2024, 6, 26), date(2024, 6, 27)
    frames = {}
    frames[("zt", d0)] = pd.DataFrame({"code": ["LOSER"], "name": ["L"], "boards": [1]})
    frames[("blowup", d0)] = pd.DataFrame()
    frames[("dt", d0)] = pd.DataFrame()
    frames[("zt", d1)] = pd.DataFrame()
    frames[("blowup", d1)] = pd.DataFrame()
    frames[("dt", d1)] = pd.DataFrame({"code": ["LOSER"], "name": ["L"]})
    return FakeSource(frames, [d0, d1])


def _scored_evidence(h):
    """构造一条已打分轨迹(决策真实种子技能 w2s),apply_credit + extract_signatures。"""
    class P:
        def decide(self, state, universe):
            return DecisionPackage(
                date=state.date,
                candidates=[Candidate(code="LOSER", pattern=SKILL_W2S)])

    traj = WalkForwardEval(_src(), date(2024, 6, 26), date(2024, 6, 27), horizon=1).walk(P())
    credit = apply_credit(traj, h)
    sigs = extract_signatures(traj, h)
    return traj, credit, sigs


def _happy_scripts():
    """p/K/M 三次 live 调用的 LLM 响应(各含 1 条合法编辑,target 均为真实种子条目)。"""
    p_ops = json.dumps({"ops": [{
        "tool": "rewrite_doctrine",
        "args": {"section": DOCTRINE_MUTABLE, "new_guidance": "主升期只满仓核心唯一龙头,杂毛追高一律不碰。"},
        "rationale": "w2s 追最高板被闷,主升纪律需收紧到只做核心龙头",
    }]})
    k_ops = json.dumps({"ops": [{
        "tool": "retire_skill",
        "args": {"skill_id": SKILL_INCUBATING},
        "rationale": "孵化期技能近期信用为负,退役待轮回",
    }]})
    m_ops = json.dumps({"ops": [{
        "tool": "process_memory",
        "args": {
            "lesson_id": NEW_LESSON_ID,
            "regime": "主升",
            "outcome": "loss",
            "lesson": "追当日最高板(boards==max)次日跌停被闷,主升期非核心龙头不接力。",
        },
        "rationale": "chased_into_nuke 签名反复出现,固化为教训",
    }]})
    return [p_ops, k_ops, m_ops]


def test_refiner_real_seeds_end_to_end_applies_and_logs():
    h = load_seeds(SEEDS)
    meta = MetaTools(h)

    # 前置真值:三个 target 在编辑前的真实状态
    assert h.doctrine.get(DOCTRINE_MUTABLE).immutable is False
    old_guidance = h.doctrine.get(DOCTRINE_MUTABLE).guidance
    assert h.skills.get(SKILL_INCUBATING).status == "incubating"
    # 退役证据门(Phase-1b-3d):该技能本轨迹未被引用、stats.n=0 会被门拦下;
    # 本端到端测试意在验证 retire 流(refine→H→EditLog),故预置足够样本让其过门。
    h.skills.get(SKILL_INCUBATING).stats.n = 5
    assert h.memory.get(NEW_LESSON_ID) is None

    # credit + signatures(观测填 SkillStats;H 因 apply_credit 已变)
    assert h.skills.get(SKILL_W2S).stats.n == 0
    traj, credit, sigs = _scored_evidence(h)
    assert credit.n_scored == 1 and credit.per_skill[SKILL_W2S].nukes == 1
    assert h.skills.get(SKILL_W2S).stats.n == 1 and h.skills.get(SKILL_W2S).stats.nukes == 1
    assert len(sigs) == 1 and sigs[0].kind == "chased_into_nuke" and sigs[0].skill_id == SKILL_W2S

    llm = MockLLMClient(_happy_scripts())
    rep = Refiner(h, llm, meta, RefinerConfig()).refine(traj, credit, sigs)

    # G-pass 不发 LLM 调用 → 恰好 3 次 live 调用(p/K/M)
    assert len(llm.calls) == 3
    assert any("G-pass reserved" in n for n in rep.notes)

    # applied 含这三条且无 rejected
    assert rep.rejected == []
    applied = {(e.pass_kind, e.tool, e.target_id) for e in rep.applied}
    assert applied == {
        ("p", "rewrite_doctrine", DOCTRINE_MUTABLE),
        ("K", "retire_skill", SKILL_INCUBATING),
        ("M", "process_memory", NEW_LESSON_ID),
    }
    assert all(e.rationale.strip() for e in rep.applied)

    # H 真的变了
    assert h.doctrine.get(DOCTRINE_MUTABLE).guidance == "主升期只满仓核心唯一龙头,杂毛追高一律不碰。"
    assert h.doctrine.get(DOCTRINE_MUTABLE).guidance != old_guidance
    assert h.skills.get(SKILL_INCUBATING).status == "dormant"          # incubating → retire(非永久)→ dormant
    new_lesson = h.memory.get(NEW_LESSON_ID)
    assert new_lesson is not None and new_lesson.outcome == "loss"

    # EditLog 记录这三条且每条带非空 rationale
    recs = meta.log.records()
    assert len(recs) == 3
    assert {(r.tool, r.target_id) for r in recs} == {
        ("rewrite_doctrine", DOCTRINE_MUTABLE),
        ("retire_skill", SKILL_INCUBATING),
        ("process_memory", NEW_LESSON_ID),
    }
    assert all(r.rationale.strip() for r in recs)
    # rationale 真的回灌到 EditLog(不是占位)
    assert any("chased_into_nuke" in r.rationale for r in recs)


def test_refiner_real_seeds_rejects_immutable_red_line():
    h = load_seeds(SEEDS)
    meta = MetaTools(h)

    entry = h.doctrine.get(DOCTRINE_IMMUTABLE)
    assert entry.immutable is True
    frozen_guidance = entry.guidance

    p_ops = json.dumps({"ops": [{
        "tool": "rewrite_doctrine",
        "args": {"section": DOCTRINE_IMMUTABLE, "new_guidance": "退潮也可以接力(违规篡改红线)"},
        "rationale": "想放松红线",
    }]})
    # p / K / M 三次 live 调用:K、M 给空 ops
    llm = MockLLMClient([p_ops, '{"ops": []}', '{"ops": []}'])
    rep = Refiner(h, llm, meta, RefinerConfig()).refine(
        traj=Trajectory(steps=[], horizon=1), credit=CreditReport(n_scored=0), signatures=[])

    # 被拒:applied 空,rejected 含 1 条 Immutable
    assert rep.applied == []
    assert len(rep.rejected) == 1
    rj = rep.rejected[0]
    assert rj.pass_kind == "p" and rj.tool == "rewrite_doctrine"
    assert rj.target_id == DOCTRINE_IMMUTABLE and "Immutable" in rj.reason

    # H 未变 + EditLog 未记
    assert h.doctrine.get(DOCTRINE_IMMUTABLE).guidance == frozen_guidance
    assert len(meta.log) == 0
