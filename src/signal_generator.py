# [2026-05-30] 修改：defense 返回新增 predicted_vol — Vol Target 触发审计
# [2026-05-29] 新增：vol_scaling_enabled 参数 — ablation 开关，关闭后固定等权不缩放
# [2026-05-29] 新增：trend_filter_enabled 参数 — ablation 开关，关闭后防御/进攻全仓等权
# [2026-05-29] 修改：进攻层切换为时间序列动量 — 取消截面排名，price>MA 即通过等权
# [2026-05-29] 新增：进攻层绝对趋势过滤 — price > MA(trend_window) 才进入截面排名
# [2026-05-28] 修改：trend_threshold/defense_ratio 参数化、进攻层波动率缩放、drawdown_stop 自定义阈值
# [2026-05-27] 新增：信号生成器 — Step 2-6 编排层，回测引擎与实盘执行共用入口

import numpy as np
import pandas as pd

from src.trend_strength import trend_strength, trend_confirmation
from src.target_volatility import ewma_covariance, portfolio_volatility, scaling_factor
from src.correlation_circuit_breaker import correlation_circuit_breaker
from src.drawdown_stop import compute_drawdown, drawdown_stop

DEFENSE_NAMES = ["沪深300", "创业板", "纳指", "黄金", "国债ETF"]

# [2026-05-29] 修改：trend_window 60→40（阶段2跨12年扫描最优）、defense_ratio 0.70→1.00（纯防御最优）
DEFAULT_PARAMS = {
    "trend_window": 40,
    "momentum_short": 20,
    "momentum_long": 60,
    "offense_top_k": 3,
    "target_vol_beta": 0.10,
    "target_vol_alpha": 0.20,
    "vol_tolerance": 0.015,
    "ewma_lambda": 0.94,
    "corr_window": 60,
    "corr_sma_window": 5,
    "corr_threshold": 0.0,
    "trend_threshold": 0.0,
    "trend_confirmation_method": "trend_strength",
    "trend_filter_enabled": True,
    "vol_scaling_enabled": True,
    "covariance_method": "ewma",
    "drawdown_thresholds": None,
    "defense_ratio": 1.00,
}


def generate_signal(
    prices: dict[str, pd.DataFrame],
    portfolio_value: pd.Series,
    params: dict | None = None,
) -> dict:
    """编排 Step 2-6 模块，生成当日调仓信号。"""
    p = {**DEFAULT_PARAMS, **(params or {})}

    # 1. 提取各资产收盘价
    close = {name: df["close"] for name, df in prices.items()}

    # 2. 防御层趋势强度
    trend_strengths = {}
    for name in DEFENSE_NAMES:
        if name in close:
            trend_strengths[name] = trend_strength(close[name], window=p["trend_window"])
    if p.get("trend_filter_enabled", True):
        method = p.get("trend_confirmation_method", "trend_strength")
        active = [
            name for name in DEFENSE_NAMES
            if name in close and trend_confirmation(close[name], method=method, window=p["trend_window"])
        ]
    else:
        active = [name for name in DEFENSE_NAMES if name in close]

    # 3. 防御层目标波动率（等权参考权重）
    predicted_vol = 0.0
    if active:
        active_close = pd.DataFrame({name: close[name] for name in active})
        raw_weights = np.ones(len(active)) / len(active)
        if p.get("vol_scaling_enabled", True):
            cov = ewma_covariance(active_close, lambda_=p["ewma_lambda"],
                                   method=p.get("covariance_method", "ewma"))
            predicted_vol = portfolio_volatility(raw_weights, cov)
            sf = scaling_factor(p["target_vol_beta"], predicted_vol, p["vol_tolerance"])
        else:
            sf = 1.0
        defense_target_weights = dict(zip(active, raw_weights))
    else:
        sf = 1.0
        defense_target_weights = {}

    # 4. 进攻层时间序列动量（price > MA → 通过，等权分配）
    offense_names = [name for name in close if name not in DEFENSE_NAMES]
    offense_weights = {}
    rankings = []
    if offense_names:
        if p.get("trend_filter_enabled", True):
            trend_filtered = []
            for name in offense_names:
                series = close[name]
                if len(series) >= p["trend_window"]:
                    ma = series.rolling(window=p["trend_window"]).mean()
                    if series.iloc[-1] > ma.iloc[-1]:
                        trend_filtered.append(name)
            if trend_filtered:
                offense_weights = {name: 1.0 / len(trend_filtered) for name in trend_filtered}
                rankings = [{"name": name} for name in trend_filtered]
        else:
            # 趋势过滤关闭 → 全仓等权
            offense_weights = {name: 1.0 / len(offense_names) for name in offense_names}
            rankings = [{"name": name} for name in offense_names]

    # 4b. 进攻层目标波动率缩放（与防御层对称）
    if offense_weights:
        if p.get("vol_scaling_enabled", True):
            selected_close = pd.DataFrame({name: close[name] for name in offense_weights})
            offense_w_array = np.array(list(offense_weights.values()))
            offense_cov = ewma_covariance(selected_close, lambda_=p["ewma_lambda"],
                                           method=p.get("covariance_method", "ewma"))
            offense_pred_vol = portfolio_volatility(offense_w_array, offense_cov)
            sf_alpha = scaling_factor(p["target_vol_alpha"], offense_pred_vol, p["vol_tolerance"])
            offense_weights = {name: w * sf_alpha for name, w in offense_weights.items()}

    # 5. 相关性熔断
    stock_basket = {name: close[name] for name in ["沪深300", "创业板", "纳指"] if name in close}
    bond_close = close.get("国债ETF")

    if stock_basket and bond_close is not None:
        cb = correlation_circuit_breaker(
            stock_basket, bond_close,
            corr_window=p["corr_window"],
            sma_window=p["corr_sma_window"],
            threshold=p["corr_threshold"],
        )
    else:
        cb = {"triggered": False, "smoothed_corr": 0.0}

    # 6. 回撤硬止损
    dd_series = compute_drawdown(portfolio_value)
    current_dd = float(dd_series.iloc[-1])
    ds = drawdown_stop(current_dd, thresholds=p.get("drawdown_thresholds"))

    # 7. execution 汇总
    if cb["triggered"]:
        final_multiplier = 0.0
        funds_to_repo = True
    else:
        final_multiplier = min(sf, ds["position_multiplier"])
        funds_to_repo = False

    return {
        "date": str(portfolio_value.index[-1].date()),
        "defense": {
            "trend_strengths": trend_strengths,
            "active": active,
            "target_weights": defense_target_weights,
            "scaling_factor": sf,
            "predicted_vol": predicted_vol,
        },
        "offense": {
            "rankings": rankings,
            "target_weights": offense_weights,
        },
        "circuit_breaker": {
            "triggered": cb["triggered"],
            "smoothed_corr": cb["smoothed_corr"],
        },
        "drawdown_stop": {
            "level": ds["level"],
            "position_multiplier": ds["position_multiplier"],
            "drawdown": current_dd,
        },
        "execution": {
            "final_multiplier": final_multiplier,
            "funds_to_repo": funds_to_repo,
        },
    }
