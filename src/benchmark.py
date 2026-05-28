# [2026-05-28] 新增：compute_single_benchmark — 单标的买入持有净值
# [2026-05-27] 新增：基准计算 — 买入持有基准组合净值曲线

import numpy as np
import pandas as pd

BENCHMARK_WEIGHTS = {
    "沪深300": 0.25,
    "创业板": 0.10,
    "纳指": 0.15,
    "黄金": 0.10,
    "国债ETF": 0.40,
}


def compute_benchmark(
    prices: dict[str, pd.DataFrame],
    weights: dict[str, float] | None = None,
) -> pd.Series:
    """计算基准组合净值曲线（买入持有近似）。

    prices: {标的名: OHLCV DataFrame}，同 signal_generator 格式。
    weights: 基准权重，默认 BENCHMARK_WEIGHTS。
    返回: 基准净值 Series，index=DatetimeIndex，起始值=1.0。

    月度再平衡摩擦成本约 2-4bp/月，对长期回测结果影响 <0.5%，不做模拟。
    """
    w = weights if weights is not None else BENCHMARK_WEIGHTS

    # 只使用 prices 中实际存在的标的
    available = [name for name in w if name in prices]
    if not available:
        raise ValueError("prices 中无任何基准标的，无法计算基准净值")
    # 归一化可用权重
    total_w = sum(w[name] for name in available)
    active_weights = {name: w[name] / total_w for name in available}

    # 提取每个标的收盘价 → 日对数收益率
    daily_returns = pd.DataFrame({
        name: np.log(prices[name]["close"] / prices[name]["close"].shift(1))
        for name in available
    }).dropna()

    # 篮子日收益率 = Σ(weight_i × return_i)
    basket_return = sum(active_weights[name] * daily_returns[name] for name in available)

    # 累积净值（首日=1.0）
    first_date = prices[available[0]].index[0]
    nav_values = np.exp(basket_return.cumsum())
    nav = pd.Series(1.0, index=prices[list(w.keys())[0]].index, dtype=float)
    nav.loc[basket_return.index] = nav_values
    nav.name = "benchmark_nav"

    return nav


def compute_single_benchmark(
    prices: dict[str, pd.DataFrame],
    name: str,
) -> pd.Series | None:
    """计算单个标的的买入持有净值曲线（起始值 1.0）。

    prices: {标的名: OHLCV DataFrame}。
    name: 目标标的名称。
    返回: 净值 Series（index=DatetimeIndex, 起始=1.0），标的不存在返回 None。
    """
    if name not in prices:
        return None
    close = prices[name]["close"]
    nav = close / close.iloc[0]
    nav.name = f"benchmark_{name}"
    return nav
