from __future__ import annotations

from pathlib import Path

# PIT 缓存根目录(.gitignore 忽略 /data/,不影响 youzi/data/ 包)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = PROJECT_ROOT / "data" / "pit_cache"

# akshare 日线复权口径
ADJUST = "qfq"  # 前复权

# 情绪值 regime-relative 归一化的滚动窗口(交易日)
SENTIMENT_WINDOW = 250
# 窗口内最少样本数,不足则 sentiment_norm = None(不臆造)
SENTIMENT_MIN_SAMPLES = 60
