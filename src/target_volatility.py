# [2026-05-27] 新增：目标波动率模块 — EWMA 协方差矩阵 / 组合波动率 / 仓位缩放系数

import numpy as np
import pandas as pd


def ewma_covariance(prices: pd.DataFrame, lambda_: float = 0.94, window: int = 252) -> pd.DataFrame:
    """EWMA 加权的年化协方差矩阵。prices: 多资产收盘价 DataFrame。lambda_: 衰减因子。window: 历史窗口。"""
    # 取最近 window 个交易日，计算日对数收益率
    recent = prices.iloc[-window:]
    log_returns = np.log(recent / recent.shift(1)).dropna()
    T = len(log_returns)
    if T < 2:
        n = len(prices.columns)
        return pd.DataFrame(np.zeros((n, n)), index=prices.columns, columns=prices.columns)

    # EWMA 权重：w_t = (1-λ) × λ^(T-1-t)，最新观测权重最大
    raw_weights = np.array([(1 - lambda_) * lambda_ ** (T - 1 - t) for t in range(T)])
    weights = raw_weights / raw_weights.sum()

    assets = prices.columns
    n = len(assets)
    rets = log_returns.values  # shape (T, n)

    # EWMA 加权均值
    means = np.average(rets, axis=0, weights=weights)

    # EWMA 加权协方差
    centered = rets - means  # (T, n)
    cov = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            cov[i, j] = np.sum(weights * centered[:, i] * centered[:, j])

    # 年化
    cov *= 252
    return pd.DataFrame(cov, index=assets, columns=assets)


def portfolio_volatility(weights: np.ndarray, cov_matrix: pd.DataFrame) -> float:
    """组合预测波动率 = sqrt(w^T Σ w)。"""
    w = np.asarray(weights, dtype=float)
    sigma = cov_matrix.values
    var = w @ sigma @ w
    return float(np.sqrt(max(var, 0.0)))


def scaling_factor(target_vol: float, predicted_vol: float, tolerance: float = 0.015) -> float:
    """仓位缩放系数，含容忍带。|predicted - target| ≤ tolerance → 1.0。predicted ≤ 0 → 1.0。"""
    if predicted_vol <= 0:
        return 1.0
    if abs(predicted_vol - target_vol) <= tolerance:
        return 1.0
    return target_vol / predicted_vol
