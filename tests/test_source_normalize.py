import pandas as pd
from youzi.data.source import _normalize


def test_normalize_dedupes_duplicate_boards_columns():
    df = pd.DataFrame({"代码": ["1"], "连板数": [3], "昨日连板数": [2]})
    out = _normalize(df)
    # 两个中文列都映射到 boards -> 去重后只剩一列,不崩
    assert list(out.columns).count("boards") == 1
    assert out["code"].iloc[0] == "000001"


def test_normalize_empty_has_blowups_column():
    out = _normalize(pd.DataFrame())
    assert "blowups" in out.columns


def test_normalize_maps_per_stock_fields():
    df = pd.DataFrame({"代码": ["000001"], "名称": ["甲"], "连板数": [3],
                       "涨跌幅": [10.0], "封板资金": [8.0e8], "换手率": [5.5],
                       "首次封板时间": ["09:31:00"], "所属行业": ["银行"], "流通市值": [1.2e10]})
    out = _normalize(df)
    for col in ["code", "name", "boards", "pct", "seal_amount",
                "turnover_rate", "first_seal_time", "industry", "float_mcap"]:
        assert col in out.columns, f"缺列 {col}"
    assert out["seal_amount"].iloc[0] == 8.0e8
    assert out["industry"].iloc[0] == "银行"
