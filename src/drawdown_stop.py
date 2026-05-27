# [2026-05-27] 新增：回撤硬止损模块 — compute_drawdown + drawdown_stop

import pandas as pd


def compute_drawdown(portfolio_values: pd.Series) -> pd.Series:
    """
    计算滚动回撤序列。
    portfolio_values: 组合净值 Series，index=日期 DatetimeIndex，按时间升序。
    返回: 回撤 Series（负小数，如 -0.12 表示回撤 12%），index 同输入。
    公式: (value - running_max) / running_max
    """
    running_max = portfolio_values.expanding().max()
    drawdown = (portfolio_values - running_max) / running_max
    drawdown.name = portfolio_values.name
    return drawdown


def drawdown_stop(drawdown: float) -> dict:
    """
    根据当前回撤返回止损信号。
    drawdown: 当前回撤值（负小数，如 -0.12 表示回撤 12%）。
    返回: {"level": ..., "position_multiplier": ...}
    """
    abs_dd = abs(drawdown)

    if abs_dd < 0.08:
        return {"level": "normal", "position_multiplier": 1.0}
    elif abs_dd < 0.12:
        return {"level": "warning", "position_multiplier": 1.0}
    elif abs_dd < 0.18:
        return {"level": "halve", "position_multiplier": 0.5}
    else:
        return {"level": "liquidate", "position_multiplier": 0.0}
