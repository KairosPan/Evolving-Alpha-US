"""Hcredit (C4) ablation (P6 spec §3). `ablate_credit` is a drop-in for `apply_credit` that updates NO
SkillStats and returns an empty CreditReport — injected as `InnerLoop(credit_fn=...)` to build the
Hcredit ABLATION arm (an HCH with the credit-assignment seam removed), isolating how much of HCH's edge
is the credit seam vs the raw Refiner.

The credit seam contributes to HCH three ways, all removed here: (1) the per-skill `SkillStats` mutation,
(2) the `CreditReport` fed to the Refiner's prompt, (3) the gate's `min_retire/promote_samples` floors
that read `skill.stats.n`. In the verdict/compare context `episode_store` is always None, so this arm
writes nothing anywhere (SSOT preserved). The signature mirrors `apply_credit` exactly."""
from __future__ import annotations

from alpha.eval.trajectory import Trajectory
from alpha.harness.state import HarnessState
from alpha.refine.credit import CreditReport


def ablate_credit(traj: Trajectory, h: HarnessState, decay: float = 0.1,
                  *, episode_store=None) -> CreditReport:
    """No-op credit function: mutates no SkillStats, writes no episodes, returns an empty CreditReport."""
    return CreditReport()
