"""US-2b acceptance: the agent's realized trajectory feeds credit assignment + signatures, and the
Refiner edits the SEEDED harness H via the manager's MetaTools under discipline — audited in the
EditLog and reversible via checkpoint/rollback. This is the Refiner the US-2c InnerLoop will drive."""
from pathlib import Path
from datetime import date
import pandas as pd
from alpha.data.source import FakeSource
from alpha.harness.loader import load_seeds
from alpha.harness.snapshot import SnapshotStore
from alpha.harness.manager import HarnessManager
from alpha.llm.client import MockLLMClient
from alpha.agent.agent import LLMAgentPolicy
from alpha.eval.walk_forward import WalkForwardEval
from alpha.eval.scorer import ReturnScorer
from alpha.refine.credit import apply_credit
from alpha.refine.signatures import extract_signatures
from alpha.refine.refiner import Refiner, RefinerConfig

SEEDS = Path(__file__).resolve().parents[2] / "seeds"


def _source():
    cal = [date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 12), date(2026, 6, 15)]
    rows = {date(2026, 6, 10): [("RUN", 14.0, 10.0)], date(2026, 6, 11): [("RUN", 18.0, 14.0)],
            date(2026, 6, 12): [("RUN", 17.0, 18.0)], date(2026, 6, 15): [("RUN", 20.0, 17.0)]}
    snaps = {d: pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [r[2] for r in v],
                              "high": [r[1] for r in v], "low": [r[2] for r in v], "close": [r[1] for r in v],
                              "volume": [1], "prev_close": [r[2] for r in v]}) for d, v in rows.items()}
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10.0, 14.0, 18.0, 17.0], "high": [14, 18, 18, 20],
                                 "low": [10, 14, 17, 17], "close": [14.0, 18.0, 17.0, 20.0], "volume": [1, 1, 1, 1]})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


def test_refiner_edits_seeded_harness_end_to_end(tmp_path):
    mgr = HarnessManager(load_seeds(SEEDS), SnapshotStore(tmp_path))
    v0 = mgr.checkpoint("seed")
    original = mgr.harness.doctrine.get("trend_play").guidance       # capture seed text (not brittle)

    # 1) agent walks -> trajectory of realized outcomes (agent always picks RUN as gap_and_go)
    agent = LLMAgentPolicy(mgr.harness, MockLLMClient('{"regime_read": "trend", "candidates": '
                           '[{"symbol": "RUN", "pattern": "gap_and_go", "confidence": 0.7}]}'))
    traj = WalkForwardEval(_source(), date(2026, 6, 10), date(2026, 6, 15), horizon=2,
                           scorer=ReturnScorer()).walk(agent)

    # 2) credit assignment populates SkillStats on the real seed skill
    #    (RUN screens as a gainer on 6/10 [+40%] & 6/11 [+28.6%], so the pick is in-universe and both
    #     decisions reach their t+2 exit -> 2 scored candidates attributed to gap_and_go by exact-id match)
    credit = apply_credit(traj, mgr.harness)
    assert mgr.harness.skills.get("gap_and_go").stats.n >= 1
    sigs = extract_signatures(traj, mgr.harness)

    # 3) the Refiner edits H via the manager's MetaTools, under discipline (scripted: rewrite a mutable
    #    doctrine line in p; no-op K/M). Edits are audited + reversible.
    refiner = Refiner(mgr.harness, MockLLMClient([
        '{"ops": [{"tool": "rewrite_doctrine", "args": {"section": "trend_play", '
        '"new_guidance": "ride the lead runner; trim into blowoffs (refined)"}, "rationale": "evidence"}]}',
        '{"ops": []}', '{"ops": []}']), mgr.tools, RefinerConfig())
    report = refiner.refine(traj, credit, sigs)
    assert any(e.tool == "rewrite_doctrine" for e in report.applied)
    assert len(mgr.log) == 1 and "refined" in mgr.harness.doctrine.get("trend_play").guidance

    # 4) an immutable red-line cannot be rewritten (discipline holds)
    bad = Refiner(mgr.harness, MockLLMClient([
        '{"ops": [{"tool": "rewrite_doctrine", "args": {"section": "stop_discipline", '
        '"new_guidance": "loosen"}, "rationale": "x"}]}', '{"ops": []}', '{"ops": []}']),
        mgr.tools, RefinerConfig())
    rep2 = bad.refine(traj, credit, sigs)
    assert rep2.applied == [] and any("Immutable" in e.reason or "immutable" in e.reason for e in rep2.rejected)

    # 5) rollback reverts the structural edit (US-2c's safety net works on this Refiner's output)
    mgr.rollback_to(v0)
    assert mgr.harness.doctrine.get("trend_play").guidance == original   # structural edit reverted
