# [2026-06-18] 新增：收益归因共享指标模块（去重 compute_metrics）
import numpy as np
import pandas as pd
from scipy import stats

RISK_FREE = 0.02
TRADING_DAYS = 252


def compute_metrics(nav: pd.Series) -> dict:
    """
    给定净值序列，返回标准化指标 dict。
    nav: pd.Series，index 为日期，values 为净值。
    """
    result = {
        "total_return": np.nan,
        "annual_return": np.nan,
        "annual_volatility": np.nan,
        "sharpe_ratio": np.nan,
        "max_drawdown": np.nan,
        "calmar_ratio": np.nan,
        "skewness": np.nan,
        "positive_month_ratio": np.nan,
        "n_days": 0,
        "monthly_returns": None,
        "start_date": None,
        "end_date": None,
    }

    nav = nav.dropna()
    n = len(nav)
    if n < 2:
        result["n_days"] = n
        return result

    result["n_days"] = n
    result["start_date"] = nav.index[0]
    result["end_date"] = nav.index[-1]

    daily_returns = nav.pct_change().dropna()
    if len(daily_returns) == 0:
        return result

    total_return = nav.iloc[-1] / nav.iloc[0] - 1
    result["total_return"] = float(total_return)

    ann_return = (1 + total_return) ** (TRADING_DAYS / n) - 1
    result["annual_return"] = float(ann_return)

    ann_vol = float(np.std(daily_returns, ddof=1) * np.sqrt(TRADING_DAYS))
    result["annual_volatility"] = ann_vol

    if ann_vol > 1e-12:
        result["sharpe_ratio"] = float((ann_return - RISK_FREE) / ann_vol)
    else:
        result["sharpe_ratio"] = np.nan

    running_max = nav.cummax()
    drawdowns = (nav - running_max) / running_max
    result["max_drawdown"] = float(drawdowns.min())

    if abs(result["max_drawdown"]) > 1e-12:
        result["calmar_ratio"] = float(ann_return / abs(result["max_drawdown"]))
    else:
        result["calmar_ratio"] = np.nan

    if len(daily_returns) >= 3:
        result["skewness"] = float(stats.skew(daily_returns))
    else:
        result["skewness"] = 0.0

    monthly = nav.resample("ME").last().dropna()
    if len(monthly) >= 2:
        monthly_ret = monthly.pct_change().dropna()
        result["positive_month_ratio"] = float((monthly_ret > 0).mean())
        result["monthly_returns"] = monthly_ret
    elif len(monthly) == 1:
        result["positive_month_ratio"] = np.nan
        result["monthly_returns"] = None
    else:
        result["monthly_returns"] = None

    return result
