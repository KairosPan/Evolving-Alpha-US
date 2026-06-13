# youzi_web/data_access.py
from __future__ import annotations

import os
from pathlib import Path

from youzi.harness.harness import HarnessState
from youzi.harness.loader import load_seeds
from youzi.harness.snapshot import SnapshotStore
from youzi.loop.run_store import RunStore
from youzi.refine.credit import resolve_skill

SEEDS_DIR = Path(__file__).resolve().parent.parent / "seeds"


def harness_view(h: HarnessState) -> dict:
    """领域 H → 视图 dict;补算 Skill 没有的 hit_rate/nuke_rate(=wins/n、nukes/n;n=0→None)。

    注:stats.expectancy 语义=超额(advantage,score−当日池基线;C2 起),模板标签同步注明;
    原始口径在 stats.expectancy_raw,随 to_dict 透传。
    """
    d = h.to_dict()
    for s in d["skills"]:
        st = s["stats"]
        n = st["n"]
        st["hit_rate"] = (st["wins"] / n) if n else None
        st["nuke_rate"] = (st["nukes"] / n) if n else None
    return d


def seed_harness() -> HarnessState:
    return load_seeds(SEEDS_DIR)


def snapshot_harness(store: SnapshotStore, version: int) -> HarnessState:
    h, _ = store.load(version)
    return h


def _runs_dir() -> Path:
    return Path(os.environ.get("YOUZI_RUNS_DIR",
                               str(Path(__file__).resolve().parent.parent / "runs")))


def list_runs() -> list[dict]:
    return RunStore(_runs_dir()).list()


def load_run(run_id: str):
    """-> (ComparisonReport, meta);不存在 → (None, None)。"""
    try:
        return RunStore(_runs_dir()).load(run_id)
    except FileNotFoundError:
        return None, None


def skill_plan(pattern: str, harness) -> dict | None:
    """候选 pattern → 种子技能的"计划"。join 不到 → None(模板降级)。"""
    sk = resolve_skill(pattern, harness)
    if sk is None:
        return None
    return {"name_cn": sk.name_cn, "trigger": sk.trigger, "entry": sk.entry,
            "exit_stop": sk.exit_stop, "taboo": list(sk.taboo)}
