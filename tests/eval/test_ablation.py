from datetime import date
from pathlib import Path

from alpha.eval.ablation import ablate_credit
from alpha.eval.trajectory import Trajectory
from alpha.refine.credit import apply_credit, CreditReport, resolve_skill
from alpha.harness.loader import load_seeds
from tests.eval._fixtures import step

SEEDS = Path(__file__).resolve().parents[2] / "seeds"


def _one_scored_traj():
    return Trajectory(steps=[step(date(2026, 6, 1), scored=True, pattern="gap_and_go", advantage=1.0)])


def test_ablate_credit_returns_empty_report_and_matches_apply_signature():
    rep = ablate_credit(_one_scored_traj(), load_seeds(SEEDS), decay=0.1, episode_store=None)
    assert isinstance(rep, CreditReport)
    assert rep.per_skill == {} and rep.n_scored == 0 and rep.unattributed is None


def test_ablate_credit_leaves_skillstats_untouched_while_apply_credit_moves_them():
    traj = _one_scored_traj()

    h_real = load_seeds(SEEDS)
    n_before = resolve_skill("gap_and_go", h_real).stats.n
    apply_credit(traj, h_real)                                # the REAL seam mutates SkillStats
    assert resolve_skill("gap_and_go", h_real).stats.n == n_before + 1

    h_ablated = load_seeds(SEEDS)
    n0 = resolve_skill("gap_and_go", h_ablated).stats.n
    ablate_credit(traj, h_ablated)                            # the ablation seam mutates NOTHING
    assert resolve_skill("gap_and_go", h_ablated).stats.n == n0
