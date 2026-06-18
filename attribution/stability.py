# [2026-06-18] 新增：稳定性矩阵模块 — 参数敏感度 × 滚动窗口 × 极端行情
import numpy as np
import pandas as pd
from attribution.metrics import compute_metrics

ROLLING_YEARS = 3
TRADING_DAYS = 252


def stability_matrix(
    daily_returns: pd.Series = None,
    param_sweep: dict = None,
    extreme_periods: dict = None,
) -> dict:
    """
    策略稳定性审计。

    daily_returns: 策略日收益
    param_sweep: {param_name: [(value, sharpe), ...]}  参数扫描结果
    extreme_periods: {label: (start, end)}  极端行情区间
    """
    result = {
        "parameter_sensitivity": [],
        "rolling_sharpe": {"min": np.nan, "mean": np.nan, "max": np.nan, "min_3yr_period": None},
        "extreme_periods": {},
    }

    if param_sweep:
        result["parameter_sensitivity"] = _compute_param_sensitivity(param_sweep)

    if daily_returns is not None:
        result["rolling_sharpe"] = _compute_rolling_sharpe(daily_returns)

    if extreme_periods and daily_returns is not None:
        result["extreme_periods"] = _compute_extreme_periods(daily_returns, extreme_periods)

    return result


def _compute_param_sensitivity(param_sweep: dict) -> list:
    """计算参数敏感度，按 ΔSharpe 降序排列"""
    sensitivity = []
    for param_name, values in param_sweep.items():
        sharpes = [v[1] for v in values]
        delta = max(sharpes) - min(sharpes)
        baseline = values[0][1] if values else np.nan
        sensitivity.append({
            "param": param_name,
            "delta_sharpe": round(delta, 4),
            "baseline_sharpe": round(baseline, 4),
            "values": values,
        })

    sensitivity.sort(key=lambda x: x["delta_sharpe"], reverse=True)
    return sensitivity


def _compute_rolling_sharpe(daily_returns: pd.Series) -> dict:
    """滚动 3 年 Sharpe"""
    rets = daily_returns.dropna()
    window = ROLLING_YEARS * TRADING_DAYS

    if len(rets) < window:
        return {"min": np.nan, "mean": np.nan, "max": np.nan, "min_3yr_period": None}

    rolling_sharpes = []
    min_sharpe = float("inf")
    min_period = None

    for i in range(window, len(rets)):
        window_rets = rets.iloc[i - window:i]
        nav = (1 + window_rets).cumprod()
        nav_series = pd.Series(nav.values, index=window_rets.index)
        m = compute_metrics(nav_series)
        s = m["sharpe_ratio"]
        if not np.isnan(s):
            rolling_sharpes.append(s)
            if s < min_sharpe:
                min_sharpe = s
                min_period = f"{window_rets.index[0].date()} ~ {window_rets.index[-1].date()}"

    if rolling_sharpes:
        return {
            "min": round(float(min(rolling_sharpes)), 4),
            "mean": round(float(np.mean(rolling_sharpes)), 4),
            "max": round(float(max(rolling_sharpes)), 4),
            "min_3yr_period": min_period,
        }
    return {"min": np.nan, "mean": np.nan, "max": np.nan, "min_3yr_period": None}


def _compute_extreme_periods(daily_returns: pd.Series, periods: dict) -> dict:
    """计算各极端行情区间的表现"""
    result = {}
    for label, (start, end) in periods.items():
        mask = (daily_returns.index >= start) & (daily_returns.index <= end)
        period_rets = daily_returns.loc[mask]
        if len(period_rets) < 2:
            result[label] = {"total_return": np.nan, "max_drawdown": np.nan, "n_days": len(period_rets)}
            continue

        nav = (1 + period_rets).cumprod()
        nav_series = pd.Series(nav.values, index=period_rets.index)
        m = compute_metrics(nav_series)
        result[label] = {
            "total_return": round(m["total_return"], 4),
            "max_drawdown": round(m["max_drawdown"], 4),
            "annual_return": round(m["annual_return"], 4),
            "sharpe_ratio": round(m["sharpe_ratio"], 4),
            "n_days": m["n_days"],
        }

    return result
