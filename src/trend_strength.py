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


def trend_confirmation(prices: pd.Series, method: str = "trend_strength", window: int = 40) -> bool:
    """趋势确认机制开关——用指定方法判断是否处于上升趋势。

    method:
      - "trend_strength": 趋势强度 > 0（当前默认）
      - "price_ma": close > MA(window)
      - "dual_ma": MA(window//2) > MA(window)
      - "ma_slope": MA(window) 斜率 > 0（今日 > window 日前）
      - "breakout": close > 最高价(window)
    """
    if len(prices) < window:
        return False

    if method == "trend_strength":
        return trend_strength(prices, window) > 0.0

    elif method == "price_ma":
        ma = prices.rolling(window=window).mean()
        return bool(prices.iloc[-1] > ma.iloc[-1])

    elif method == "dual_ma":
        short_window = max(window // 2, 2)
        ma_short = prices.rolling(window=short_window).mean()
        ma_long = prices.rolling(window=window).mean()
        return bool(ma_short.iloc[-1] > ma_long.iloc[-1])

    elif method == "ma_slope":
        ma = prices.rolling(window=window).mean().dropna()
        if len(ma) < 2:
            return False
        return bool(ma.iloc[-1] > ma.iloc[0])

    elif method == "breakout":
        highest = prices.shift(1).rolling(window=window).max()
        return bool(prices.iloc[-1] > highest.iloc[-1])

    else:
        return trend_strength(prices, window) > 0.0
