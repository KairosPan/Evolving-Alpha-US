from __future__ import annotations

import pandas as pd

from youzi.schemas.market import EchelonRung


def max_board_height(zt: pd.DataFrame) -> int:
    if zt is None or zt.empty or "boards" not in zt.columns:
        return 0
    s = pd.to_numeric(zt["boards"], errors="coerce").dropna()
    return int(s.max()) if not s.empty else 0


def build_echelon(zt: pd.DataFrame, top_reps: int = 3) -> list[EchelonRung]:
    """从涨停股池按连板数分档,height 降序;每档取最多 top_reps 个代表票名。"""
    if zt is None or zt.empty or "boards" not in zt.columns:
        return []
    df = zt.copy()
    df["boards"] = pd.to_numeric(df["boards"], errors="coerce")
    df = df.dropna(subset=["boards"])
    df = df[df["boards"] > 0]
    if df.empty:
        return []
    rungs: list[EchelonRung] = []
    for height, grp in df.groupby("boards"):
        names = grp["name"].astype(str).head(top_reps).tolist() if "name" in grp else []
        rungs.append(EchelonRung(height=int(height), count=len(grp),
                                 representatives=names))
    rungs.sort(key=lambda r: r.height, reverse=True)
    return rungs
