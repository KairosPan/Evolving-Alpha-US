"""手动冒烟:拉一天真实数据,打印规整后列与行数。Run: python scripts/smoke_akshare.py 20240627"""
from __future__ import annotations

import sys
from datetime import datetime

from youzi.data.source import AkshareSource
from youzi.features.builder import build_market_state


def main(ymd: str) -> None:
    day = datetime.strptime(ymd, "%Y%m%d").date()
    src = AkshareSource()
    for name, fn in [("zt", src.zt_pool), ("prev", src.zt_pool_previous),
                     ("blowup", src.zt_pool_blowup), ("dt", src.dt_pool)]:
        df = fn(day)
        print(f"[{name}] rows={len(df)} cols={list(df.columns)}")
    st = build_market_state(day, src, history=[], as_of=datetime.now())
    print("MarketState:", st.model_dump())


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "20240627")
