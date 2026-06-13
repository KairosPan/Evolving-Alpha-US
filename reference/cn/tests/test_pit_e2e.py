# tests/test_pit_e2e.py
from youzi.data.cache import PITStore
from youzi.data.capture import capture_window
from youzi.data.snapshot_source import SnapshotSource
from youzi.eval.scorer import ReturnScorer
from youzi.loop.compare import compare_harnesses
from youzi.loop.inner_loop import LoopConfig
from youzi.harness.snapshot import SnapshotStore
from tests.test_compare import _w_src, _SeqFactory, _CountFactory, _PICK_W, _NO_TRADE
from tests.test_inner_loop import _seed_h


def test_offline_return_scoring_via_snapshot(tmp_path):
    # 1) capture 真实 live(FakeSource)→ PITStore
    live = _w_src()
    store = PITStore(tmp_path / "snap")
    capture_window(live, store, live.trading_calendar()[0], live.trading_calendar()[-1],
                   sleep=lambda d: None)
    # 2) 离线 SnapshotSource 跑四路收益对比(零 akshare)
    snap = SnapshotSource(store)
    rep = compare_harnesses(
        _CountFactory(_seed_h), snap, snap.trading_calendar()[0], snap.trading_calendar()[-1],
        agent_llm_factory=_SeqFactory([_PICK_W, _NO_TRADE]),
        refiner_llm_factory=_SeqFactory(['{"ops": []}']),
        store_factory=_CountFactory(lambda: SnapshotStore(tmp_path / "h")),
        loop_config=LoopConfig(horizon=1), scorer=ReturnScorer())
    assert set(rep.arms) == {"HCH", "Hexpert", "Hmin_highest", "Hmin_notrade"}
    assert rep.arms["HCH"].report.n_candidates >= 1     # W continued + OHLCV → 收益打分(候选>0)
