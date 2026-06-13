# tests/test_refine_integration.py
from datetime import date
from pathlib import Path

import pandas as pd

from youzi.eval.decision import Candidate, DecisionPackage
from youzi.eval.walk_forward import WalkForwardEval
from youzi.harness.harness import HarnessState
from youzi.harness.loader import load_seeds
from youzi.refine.credit import apply_credit
from youzi.refine.signatures import extract_signatures
from tests.conftest import FakeSource

SEEDS = Path(__file__).resolve().parent.parent / "seeds"


def _src():
    """day0: LOSER 涨停(1板,即当日最高板);day1: LOSER 跌停(nuked)。"""
    d0, d1 = date(2024, 6, 26), date(2024, 6, 27)
    frames = {}
    frames[("zt", d0)] = pd.DataFrame({"code": ["LOSER"], "name": ["L"], "boards": [1]})
    frames[("blowup", d0)] = pd.DataFrame(); frames[("dt", d0)] = pd.DataFrame()
    frames[("zt", d1)] = pd.DataFrame(); frames[("blowup", d1)] = pd.DataFrame()
    frames[("dt", d1)] = pd.DataFrame({"code": ["LOSER"], "name": ["L"]})
    return FakeSource(frames, [d0, d1])


def test_pipeline_walk_credit_signatures_on_real_seeds():
    h = load_seeds(SEEDS)
    sid = h.skills.all()[0].skill_id            # 动态取真实种子技能,免硬编码
    assert h.skills.get(sid).stats.n == 0       # 载入即零,信用未跑

    class P:
        def decide(self, state, universe):
            return DecisionPackage(date=state.date,
                                   candidates=[Candidate(code="LOSER", pattern=sid)])

    traj = WalkForwardEval(_src(), date(2024, 6, 26), date(2024, 6, 27), horizon=1).walk(P())
    rep = apply_credit(traj, h)
    sigs = extract_signatures(traj, h)

    # day0 决策 LOSER → day1 跌停=nuked,归因到真实种子技能
    st = h.skills.get(sid).stats
    assert st.n == 1 and st.nukes == 1 and st.wins == 0
    assert rep.per_skill[sid].nukes == 1 and rep.n_scored == 1
    # boards=1 == 当日 max_board_height=1 → chased_into_nuke
    assert len(sigs) == 1 and sigs[0].kind == "chased_into_nuke" and sigs[0].skill_id == sid


def test_harness_roundtrips_after_credit():
    h = load_seeds(SEEDS)
    sid = h.skills.all()[0].skill_id

    class P:
        def decide(self, state, universe):
            return DecisionPackage(date=state.date,
                                   candidates=[Candidate(code="LOSER", pattern=sid)])

    traj = WalkForwardEval(_src(), date(2024, 6, 26), date(2024, 6, 27), horizon=1).walk(P())
    apply_credit(traj, h)
    h2 = HarnessState.from_dict(h.to_dict())            # 含 nukes 的 H 往返保真
    assert h2.skills.get(sid).stats.nukes == h.skills.get(sid).stats.nukes == 1
