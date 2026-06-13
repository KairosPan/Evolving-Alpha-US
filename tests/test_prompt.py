from datetime import date, datetime
from youzi.harness.loader import load_seeds
from youzi.schemas.market import MarketState, EchelonRung
from youzi.universe.stock import StockSnapshot
from youzi.universe.universe import CandidateUniverse
from youzi.agent.prompt import build_system_prompt, build_user_prompt
from pathlib import Path

SEEDS = Path(__file__).resolve().parent.parent / "seeds"


def test_system_prompt_injects_harness_sections():
    h = load_seeds(SEEDS)
    sys = build_system_prompt(h)
    # 关键段落都在
    assert "纪律红线" in sys
    assert "模式库" in sys and "复盘教训" in sys
    assert "情绪周期" in sys
    assert "JSON" in sys                       # 输出契约
    # 至少注入了一条 immutable doctrine 与一个 active 技能名
    core = h.doctrine.immutable_core()[0]
    assert core.guidance in sys
    an_active = h.skills.by_status("active")[0]
    assert an_active.name_cn in sys


def test_user_prompt_lists_candidate_codes():
    state = MarketState(date=date(2024, 6, 27), max_board_height=7, limit_up_count=2,
                        blowup_count=1, blowup_rate=0.33, limit_down_count=1,
                        echelon=[EchelonRung(height=7, count=1, representatives=["龙头"])],
                        money_effect_raw=1.5, sentiment_raw=10.0, sentiment_norm=None,
                        as_of=datetime(2024, 6, 27, 15, 0))
    uni = CandidateUniverse.from_stocks([
        StockSnapshot(code="000001", name="甲", status="limit_up", boards=7, industry="芯片"),
        StockSnapshot(code="300002", name="乙", status="limit_up", boards=2),
        StockSnapshot(code="000003", name="跌", status="limit_down")])
    user = build_user_prompt(state, uni)
    assert "2024-06-27" in user
    assert "000001" in user and "300002" in user        # 涨停候选列出
    assert "000003" not in user                          # 跌停不在候选池
    assert "7" in user                                   # 连板高度等盘面量
