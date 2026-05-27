# [2026-05-27] 新增：截面动量模块 — momentum_score / cross_sectional_zscore / composite_momentum

import numpy as np
import pandas as pd


def momentum_score(prices: pd.DataFrame, window: int) -> pd.Series:
    """计算单窗口动量得分（对数收益率）。prices: 多资产收盘价。window: 回看窗口。"""
    result = {}
    for col in prices.columns:
        series = prices[col].dropna()
        if len(series) < window:
            result[col] = np.nan
        else:
            p_start = series.iloc[-window]
            p_end = series.iloc[-1]
            result[col] = np.log(p_end / p_start)
    return pd.Series(result, name=f"momentum_{window}d")


def cross_sectional_zscore(scores: pd.Series) -> pd.Series:
    """截面上 z-score 标准化。公式: (x - mean) / std(ddof=1)。NaN 输入 → NaN 输出。"""
    mean = scores.mean()
    std = scores.std(ddof=1)
    if std == 0 or pd.isna(std):
        result = scores.copy()
        result[~result.isna()] = 0.0
        return result
    return (scores - mean) / std


def composite_momentum(prices: pd.DataFrame, window_short: int = 20, window_long: int = 60) -> pd.Series:
    """双窗口截面动量合成。20 日 + 60 日 z-score 等权，按得分降序排列。"""
    s20 = momentum_score(prices, window_short)
    z20 = cross_sectional_zscore(s20)
    s60 = momentum_score(prices, window_long)
    z60 = cross_sectional_zscore(s60)
    composite = (z20 + z60) / 2
    composite = composite.dropna()
    if composite.empty:
        return pd.Series(dtype=float)
    return composite.sort_values(ascending=False)
