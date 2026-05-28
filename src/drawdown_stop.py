# [2026-05-28] 修改：drawdown_stop 支持自定义阈值参数
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


def drawdown_stop(drawdown: float, thresholds: list[tuple[float, float]] | None = None) -> dict:
    """
    根据当前回撤返回止损信号。
    drawdown: 当前回撤值（负小数，如 -0.12 表示回撤 12%）。
    thresholds: 可选自定义阈值 [(abs_dd_boundary, position_multiplier), ...]，
                如 [(0.08, 1.0), (0.12, 0.5), (0.18, 0.0)]。
                传入 None 时使用默认四级阈值。
    返回: {"level": ..., "position_multiplier": ...}
    """
    abs_dd = abs(drawdown)

    if thresholds is None:
        if abs_dd < 0.08:
            return {"level": "normal", "position_multiplier": 1.0}
        elif abs_dd < 0.12:
            return {"level": "warning", "position_multiplier": 1.0}
        elif abs_dd < 0.18:
            return {"level": "halve", "position_multiplier": 0.5}
        else:
            return {"level": "liquidate", "position_multiplier": 0.0}

    multiplier = 1.0
    for boundary, mult in thresholds:
        if abs_dd < boundary:
            multiplier = mult
            break
    else:
        multiplier = thresholds[-1][1]

    if multiplier >= 1.0:
        level = "normal"
    elif multiplier >= 0.5:
        level = "halve"
    else:
        level = "liquidate"

    return {"level": level, "position_multiplier": multiplier}
