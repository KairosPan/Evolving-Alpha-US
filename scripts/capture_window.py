# scripts/capture_window.py
"""一次性建 PIT 快照:把窗口内 4 池/日 + universe OHLCV + 日历预取进 PITStore(parquet)。

Run: python scripts/capture_window.py <start_ymd> <end_ymd> <out_dir>
之后离线跑:YOUZI_SNAPSHOT=<out_dir> DEEPSEEK_API_KEY=... python scripts/smoke_compare.py <s> <e> 2 0.0 return
慢、节流(默认 0.3s/调用)、幂等(可中断重跑)。唯一碰 akshare 的步骤。
"""
import sys
from datetime import datetime
from pathlib import Path

from youzi.data.cache import PITStore
from youzi.data.capture import capture_window
from youzi.data.source import AkshareSource


def main(start_ymd: str, end_ymd: str, out_dir: str) -> None:
    start = datetime.strptime(start_ymd, "%Y%m%d").date()
    end = datetime.strptime(end_ymd, "%Y%m%d").date()
    store = PITStore(Path(out_dir))
    print(f"capture {start}~{end} → {out_dir}(节流 0.3s/调用,幂等)…")
    summ = capture_window(AkshareSource(), store, start, end)
    print(f"完成:交易日 {summ.n_days}、code {summ.n_codes}、akshare 调用 {summ.n_calls}。")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("用法: python scripts/capture_window.py <start_ymd> <end_ymd> <out_dir>")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2], sys.argv[3])
