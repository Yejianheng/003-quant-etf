# [2026-10-15] 新增：分红再投复权（后复权式），修正不复权序列在除息日的假跌幅
"""分红再投复权模块。

背景：库内 parquet 长期为「不复权」口径（除息日股价跳水、分红现金从未计入），
导致收益率被系统性低估。510300 在 2013-07-31~2026-10-15 区间少算约 34% 累计收益。

口径选择：**后复权式**（因子锚定在序列首日，f=1），而非前复权。
理由：前复权以最新价为锚，每次除息都会追溯改写全部历史行；而数据管线是纯追加
（旧行永不重写），两者相遇必然产生接缝——即 2026-09-29 的数据事故。
后复权只让除息日之后的行乘上因子，历史行永不被改写，与追加式写入兼容。

不变量：
- 只有除息日（含）之后的价格被上调；之前的价格逐位不变
- 复权后序列的收益率 == 含分红的真实收益率
- volume 不参与复权（成交量是股数，不是价格）
- 长度 / index / 列名 与输入完全一致
"""
from __future__ import annotations

import pandas as pd

# 参与复权的价格列（volume 不在此列）
_PRICE_COLUMNS = ("open", "high", "low", "close")


def build_adjustment_factor(prices: pd.DataFrame, dividends: pd.DataFrame) -> pd.Series:
    """计算后复权因子序列。

    prices: OHLCV DataFrame，index 为交易日。
    dividends: 除息表，index 为除息日，第一列为每股分红。空表或 None → 全 1 因子。

    除息日 d 当日因子跳变 = (close_d + 分红) / close_d，其后所有行沿用该因子。
    除息日不在 prices.index 中（非交易日/超范围）→ 跳过该笔。
    """
    factor = pd.Series(1.0, index=prices.index, dtype="float64")
    if dividends is None or len(dividends) == 0:
        return factor

    amounts = dividends.iloc[:, 0].astype(float)
    close = prices["close"]
    for ex_date, amount in amounts.items():
        if ex_date not in prices.index or amount == 0:
            continue
        close_on_ex = close.at[ex_date]
        factor.loc[ex_date:] *= (close_on_ex + amount) / close_on_ex
    return factor


def adjust_prices_for_dividends(prices: pd.DataFrame,
                                dividends: pd.DataFrame) -> pd.DataFrame:
    """将不复权 OHLCV 转为「分红再投」等效序列（后复权式）。

    prices: 原始 OHLCV DataFrame（不复权）。
    dividends: 除息表，index 为除息日，第一列为每股分红；空表/None → 原样返回。
    返回: 新的 DataFrame，OHLC 已乘复权因子，volume 与 index 不变。
    """
    factor = build_adjustment_factor(prices, dividends)
    out = prices.copy()
    for column in _PRICE_COLUMNS:
        if column in out.columns:
            out[column] = out[column] * factor
    return out
