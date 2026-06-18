# [2026-06-18] 新增：尾部审计模块 — 偏度、最差月、回撤持续期、卖保险检测
import numpy as np
import pandas as pd
from scipy import stats


def tail_risk_audit(daily_returns: pd.Series, benchmark_returns: pd.Series = None) -> dict:
    """
    尾部风险审计。

    daily_returns: 策略日收益
    benchmark_returns: 基准日收益（可选，用于对照）
    """
    result = {
        "skewness": np.nan,
        "max_drawdown": np.nan,
        "max_dd_duration_days": 0,
        "worst_5_months": [],
        "monthly_max_drawdown": np.nan,
        "insurance_sell_warning": False,
        "benchmark_skewness": np.nan,
        "benchmark_max_dd_duration": 0,
        "n_obs": 0,
    }

    rets = daily_returns.dropna()
    n = len(rets)
    result["n_obs"] = n

    if n < 3:
        return result

    result["skewness"] = float(stats.skew(rets))

    nav = (1 + rets).cumprod()
    running_max = nav.cummax()
    drawdowns = (nav - running_max) / running_max
    result["max_drawdown"] = float(drawdowns.min())

    result["max_dd_duration_days"] = _max_drawdown_duration(nav)

    monthly = rets.resample("ME").apply(lambda x: (1 + x).prod() - 1)
    monthly = monthly.dropna()
    if len(monthly) >= 5:
        worst = monthly.nsmallest(5)
        result["worst_5_months"] = [
            {"date": str(idx.date()), "return": float(val)}
            for idx, val in worst.items()
        ]
        result["monthly_max_drawdown"] = float(monthly.min())

    if result["skewness"] < -0.3:
        pos_ratio = float((rets > 0).mean())
        if pos_ratio > 0.52:
            result["insurance_sell_warning"] = True

    if benchmark_returns is not None:
        b_rets = benchmark_returns.dropna()
        common = rets.index.intersection(b_rets.index)
        if len(common) >= 3:
            result["benchmark_skewness"] = float(stats.skew(b_rets.loc[common]))
            b_nav = (1 + b_rets.loc[common]).cumprod()
            result["benchmark_max_dd_duration"] = _max_drawdown_duration(b_nav)

    return result


def _max_drawdown_duration(nav: pd.Series) -> int:
    """计算最大回撤持续天数（peak 到 recovery 的天数）"""
    running_max = nav.cummax()
    in_drawdown = nav < running_max

    max_duration = 0
    current = 0
    for t in in_drawdown:
        if t:
            current += 1
            max_duration = max(max_duration, current)
        else:
            current = 0

    return max_duration
