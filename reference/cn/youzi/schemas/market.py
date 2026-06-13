from __future__ import annotations

from datetime import date as Date, datetime as DateTime

from pydantic import BaseModel, ConfigDict, Field


class EchelonRung(BaseModel):
    """连板梯队的一档:某连板高度上有几只票及代表票。"""
    model_config = ConfigDict(frozen=True)
    height: int = Field(ge=1)        # 连板数
    count: int = Field(ge=0)
    representatives: list[str] = Field(default_factory=list)


class MarketState(BaseModel):
    """某交易日收盘的 point-in-time 市场状态(Phase-0a 最小集)。"""
    model_config = ConfigDict(frozen=True)
    date: Date
    max_board_height: int = Field(ge=0)     # 最高连板高度
    limit_up_count: int = Field(ge=0)       # 涨停家数
    blowup_count: int = Field(ge=0)         # 炸板家数
    blowup_rate: float = Field(ge=0.0, le=1.0)   # 炸板率
    limit_down_count: int = Field(ge=0)     # 跌停家数
    echelon: list[EchelonRung]              # 连板梯队(按 height 降序)
    money_effect_raw: float                 # 昨日涨停今表现均值(%)
    sentiment_raw: float                    # 原始情绪复合分
    sentiment_norm: float | None = Field(default=None, ge=0.0, le=1.0)  # regime-relative 归一化[0,1];样本不足为 None
    as_of: DateTime                         # 数据快照时点(防未来函数审计)
