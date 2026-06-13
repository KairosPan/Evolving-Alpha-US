from __future__ import annotations


def raw_sentiment(
    max_board_height: int,
    limit_up_count: int,
    money_effect: float,
    blowup_rate: float,
    limit_down_count: int,
) -> float:
    """原始情绪复合分(无量纲,仅用于跨日相对比较)。

    正向:最高连板高度、涨停数、赚钱效应;负向:炸板率、跌停数。
    权重是先验初值,后续作为可进化技能参数(蓝图 §6.1)。
    """
    return (
        2.0 * max_board_height
        + 0.1 * limit_up_count
        + 1.5 * money_effect
        - 8.0 * blowup_rate
        - 0.3 * limit_down_count
    )


def normalize_sentiment(
    value: float, history: list[float], min_samples: int
) -> float | None:
    """regime-relative 归一化:value 在 history(仅 ≤ 当日)里的分位 ∈[0,1]。

    样本不足返回 None(不臆造绝对阈值)。
    """
    if history is None or len(history) < min_samples:
        return None
    le = sum(1 for h in history if h <= value)
    return le / len(history)
