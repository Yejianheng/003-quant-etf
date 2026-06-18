# [2026-06-18] 新增：择时分解模块 — 动态 vs 静态等权
import numpy as np
import pandas as pd


def timing_decomposition(strategy_returns: pd.Series, benchmark_returns: pd.Series) -> dict:
    """
    分解策略相对静态等权的择时增量。

    strategy_returns: 策略日收益（小数，如 0.001）
    benchmark_returns: 静态等权基准日收益
    """
    common_idx = strategy_returns.index.intersection(benchmark_returns.index)
    s = strategy_returns.loc[common_idx]
    b = benchmark_returns.loc[common_idx]

    result = {
        "timing_coefficient": np.nan,
        "total_excess_return": 0.0,
        "up_month_excess": np.nan,
        "down_month_excess": np.nan,
        "monthly_win_rate": np.nan,
        "up_months_count": 0,
        "down_months_count": 0,
        "n_months": 0,
        "strategy_total_return": 0.0,
        "benchmark_total_return": 0.0,
    }

    n = len(s)
    if n < 2:
        return result

    strategy_cum = (1 + s).prod()
    bench_cum = (1 + b).prod()
    result["strategy_total_return"] = float(strategy_cum - 1)
    result["benchmark_total_return"] = float(bench_cum - 1)

    if n > 1:
        cov = np.cov(b.values[:-1], s.values[1:])[0, 1]
        result["timing_coefficient"] = float(cov * n)
    else:
        result["timing_coefficient"] = 0.0

    monthly = pd.DataFrame({"strategy": s, "benchmark": b})
    monthly_agg = monthly.resample("ME").apply(lambda x: (1 + x).prod() - 1)

    if len(monthly_agg) < 2:
        return result

    result["n_months"] = len(monthly_agg)

    up_mask = monthly_agg["benchmark"] > 0
    down_mask = ~up_mask
    result["up_months_count"] = int(up_mask.sum())
    result["down_months_count"] = int(down_mask.sum())

    monthly_excess = monthly_agg["strategy"] - monthly_agg["benchmark"]
    result["total_excess_return"] = float(monthly_excess.sum())

    if up_mask.sum() > 0:
        result["up_month_excess"] = float(monthly_excess[up_mask].sum())
    else:
        result["up_month_excess"] = 0.0

    if down_mask.sum() > 0:
        result["down_month_excess"] = float(monthly_excess[down_mask].sum())
    else:
        result["down_month_excess"] = 0.0

    result["monthly_win_rate"] = float((monthly_excess > 0).mean())

    return result
