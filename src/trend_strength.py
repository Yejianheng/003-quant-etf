# [2026-05-27] 新增：趋势强度模块 — 年化收益率/年化波动率/趋势强度

import numpy as np
import pandas as pd


def annualized_return(prices: pd.Series, window: int = 60) -> float:
    """计算年化收益率。公式：ln(P_t / P_{t-N}) × (252 / window)"""
    if len(prices) < window:
        return 0.0
    recent = prices.iloc[-window:]
    p_start = recent.iloc[0]
    p_end = recent.iloc[-1]
    return np.log(p_end / p_start) * (252 / window)


def annualized_volatility(prices: pd.Series, window: int = 60) -> float:
    """计算年化波动率。公式：std(日对数收益率, ddof=1) × √252"""
    if len(prices) < 2:
        return 0.0
    if len(prices) > window:
        prices = prices.iloc[-window:]
    log_returns = np.log(prices / prices.shift(1)).dropna()
    if len(log_returns) < 2:
        return 0.0
    return float(np.std(log_returns, ddof=1) * np.sqrt(252))


def trend_strength(prices: pd.Series, window: int = 60) -> float:
    """计算趋势强度 = 年化收益率 / 年化波动率。数据不足或波动率为 0 返回 0.0。"""
    if len(prices) < window:
        return 0.0
    ann_ret = annualized_return(prices, window)
    ann_vol = annualized_volatility(prices, window)
    if ann_vol == 0.0:
        return 0.0
    return ann_ret / ann_vol
