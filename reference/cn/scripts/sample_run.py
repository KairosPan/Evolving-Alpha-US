# scripts/sample_run.py
"""离线造一个样本 run(MockLLM+FakeSource)存进 run-store,让研究看板有真东西看 + 当夹具。
Run: python scripts/sample_run.py   → runs/sample.json(或 YOUZI_RUNS_DIR)。不触网。"""
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # 让 `python scripts/sample_run.py` 也能 import tests.*

from youzi.harness.snapshot import SnapshotStore
from youzi.loop.compare import compare_harnesses
from youzi.loop.inner_loop import LoopConfig
from youzi.loop.run_store import RunStore
from tests.test_compare import _w_src, _SeqFactory, _CountFactory, _PICK_W, _NO_TRADE
from tests.test_inner_loop import _seed_h


def main() -> None:
    src = _w_src()
    rep = compare_harnesses(
        _CountFactory(_seed_h), src, src.trading_calendar()[0], src.trading_calendar()[-1],
        agent_llm_factory=_SeqFactory([_PICK_W, _NO_TRADE]),
        refiner_llm_factory=_SeqFactory(['{"ops": []}']),
        store_factory=_CountFactory(lambda: SnapshotStore(tempfile.mkdtemp())),
        # A3:evidence_min=1(样本 run 3 日窗候选少,默认 6 会让研究看板 refine 时间线空着)
        loop_config=LoopConfig(horizon=1, evidence_min=1))
    root = Path(os.environ.get("YOUZI_RUNS_DIR", "runs"))
    RunStore(root).save("sample", rep, {
        "window": "sample(离线)", "scorer": "pool", "horizon": 1,
        "created": datetime.now().isoformat(timespec="seconds")})
    print(f"已存 sample run → {root}/sample.json(HCH vs Hexpert,含 refine/trajectory)")


if __name__ == "__main__":
    main()
