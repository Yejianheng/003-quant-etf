# [2026-05-27] 新增：相关性熔断模块 — 股债滚动相关性 + SMA 熔断判断

import numpy as np
import pandas as pd


def stock_basket_returns(stock_prices: dict[str, pd.Series]) -> pd.Series:
    """
    计算股票篮子等权日对数收益率。
    stock_prices: {"沪深300": Series, "创业板": Series, "纳指": Series}，
      每个 Series index=日期 DatetimeIndex，values=close 价格。
    返回: 日对数收益率 Series（等权平均），index=日期。
    """
    # 每只 ETF 独立计算日对数收益率
    returns = {}
    for name, prices in stock_prices.items():
        returns[name] = np.log(prices / prices.shift(1))
    df = pd.DataFrame(returns)
    # 按日期横向等权平均（skipna：某 ETF 某日缺数据不拖垮整体）
    basket = df.mean(axis=1, skipna=True)
    return basket.dropna()


def rolling_correlation(series_a: pd.Series, series_b: pd.Series, window: int = 60) -> pd.Series:
    """
    滚动 Pearson 相关系数。
    series_a, series_b: 两个等长日收益率 Series，index 对齐。
    window: 滚动窗口（交易日数）。
    返回: 滚动相关系数 Series，index=日期，长度 < window 的位置为 NaN。
    """
    return series_a.rolling(window).corr(series_b)


def correlation_circuit_breaker(
    stock_prices: dict[str, pd.Series],
    bond_prices: pd.Series,
    corr_window: int = 60,
    sma_window: int = 5,
    threshold: float = 0.0,
) -> dict:
    """
    相关性熔断判断。
    返回: {
        "triggered": bool,          # 是否触发熔断
        "smoothed_corr": float,     # 最新平滑相关性
        "raw_corr": float,          # 最新原始 60 日相关性（调试用）
    }
    """
    # 1. 股票篮子日收益率
    stock_rets = stock_basket_returns(stock_prices)
    # 2. 债券日对数收益率
    bond_rets = np.log(bond_prices / bond_prices.shift(1)).dropna()
    # 日期对齐（中美交易日不同，取交集）
    common_idx = stock_rets.index.intersection(bond_rets.index)
    stock_aligned = stock_rets.loc[common_idx]
    bond_aligned = bond_rets.loc[common_idx]
    # 数据不足检查
    if len(common_idx) < corr_window + sma_window:
        return {"triggered": False, "smoothed_corr": 0.0, "raw_corr": 0.0}
    # 3. 滚动相关性
    roll_corr = rolling_correlation(stock_aligned, bond_aligned, corr_window)
    # 4. SMA 平滑
    smoothed = roll_corr.rolling(sma_window).mean()
    # 取最新值
    raw_corr = float(roll_corr.dropna().iloc[-1])
    smoothed_corr = float(smoothed.dropna().iloc[-1])
    # 5. 熔断判断
    triggered = smoothed_corr > threshold
    return {"triggered": triggered, "smoothed_corr": smoothed_corr, "raw_corr": raw_corr}
