# [2026-06-26] 新增：趋势信号 SMA 平滑效果验证测试
"""测试 trend_strength SMA 平滑对零轴穿越和 Sharpe 的影响"""

import sys
import os
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---- 小合成数据（加速回测） ----

def _make_small_prices(n=200, trend=0.15, vol=0.18, seed=42):
    """生成 n 天的合成 OHLCV 数据。"""
    dates = pd.bdate_range("2024-01-01", periods=n)
    rng = np.random.RandomState(seed)
    returns = np.full(n, trend / 252) + rng.normal(0, vol / np.sqrt(252), n)
    prices = 1.0 * np.exp(np.cumsum(returns))
    return {
        name: pd.DataFrame({
            "open": prices * 0.99, "high": prices * 1.02,
            "low": prices * 0.98, "close": prices,
            "volume": np.full(n, 1e6),
        }, index=dates)
        for name in ["沪深300", "创业板", "纳指", "黄金", "国债ETF"]
    }


# ---- 平滑辅助函数 ----

def _smooth_trend_confirmation(prices, window=40, method="trend_strength",
                               sma_window=1):
    from src.trend_strength import trend_strength

    if method != "trend_strength":
        from src.trend_strength import trend_confirmation as _orig
        return _orig(prices, method=method, window=window)

    if sma_window <= 1:
        return trend_strength(prices, window=window) > 0

    ts_series = [trend_strength(prices.iloc[:i], window=window)
                 for i in range(window, len(prices) + 1)]
    smoothed = pd.Series(ts_series).rolling(sma_window, min_periods=1).mean()
    return float(smoothed.iloc[-1]) > 0


def _count_zero_crossings(prices, window=40, sma_window=1):
    """计算指定平滑参数下的零轴穿越次数。"""
    results = []
    for i in range(window + 1, len(prices) + 1):
        seg = prices.iloc[:i]
        if isinstance(seg, pd.DataFrame):
            seg = seg["close"]
        results.append(_smooth_trend_confirmation(
            seg, window=window, sma_window=sma_window))
    return sum(1 for i in range(1, len(results)) if results[i] != results[i - 1])


# ---- 测试 ----

class TestTrendSmoothing:
    """趋势信号 SMA 平滑效果验证"""

    def _run_backtest(self, prices, sma_window=1):
        from src.backtest_engine import run_backtest
        from src.signal_generator import DEFAULT_PARAMS
        import src.signal_generator as sg

        params = {**DEFAULT_PARAMS, "trend_confirmation_method": "trend_strength"}

        def _wrapped(close, method="trend_strength", window=40):
            return _smooth_trend_confirmation(
                close, method=method, window=window, sma_window=sma_window)

        with patch.object(sg, "trend_confirmation", side_effect=_wrapped):
            result = run_backtest(prices=prices, initial_capital=1_000_000,
                                  params=params, min_days=60)
        nav = result["records_df"]["nav"]
        return nav

    def _compute_sharpe(self, nav):
        if len(nav) < 2 or nav.iloc[-1] <= 0:
            return 0.0
        returns = nav.pct_change().dropna()
        if len(returns) < 2:
            return 0.0
        ann_ret = (nav.iloc[-1] / nav.iloc[0]) ** (252 / len(nav)) - 1
        ann_vol = returns.std() * np.sqrt(252)
        return ann_ret / ann_vol if ann_vol > 0 else 0.0

    def test_smoothing_reduces_zero_crossings(self):
        """sma=3 时零轴穿越次数 < 不平滑（噪声序列）"""
        rng = np.random.RandomState(42)
        n = 300
        noise = rng.normal(0, 0.008, n)
        dates = pd.bdate_range("2024-01-01", periods=n)
        close = pd.Series(1.0 + np.cumsum(noise), index=dates)

        n_orig = _count_zero_crossings(close, window=40, sma_window=1)
        n_smooth = _count_zero_crossings(close, window=40, sma_window=3)

        assert n_smooth < n_orig, (
            f"sma=3 穿越 {n_smooth} >= sma=1 穿越 {n_orig}"
        )

    def test_smoothing_no_sharpe_collapse(self):
        """sma=3 时 Sharpe 不低于不平滑的 90%"""
        prices = _make_small_prices(n=250)

        nav_orig = self._run_backtest(prices, sma_window=1)
        nav_smooth = self._run_backtest(prices, sma_window=3)

        sharpe_orig = self._compute_sharpe(nav_orig)
        sharpe_smooth = self._compute_sharpe(nav_smooth)

        print(f"\n  Sharpe 不平滑: {sharpe_orig:.3f}")
        print(f"  Sharpe sma=3: {sharpe_smooth:.3f}")

        if sharpe_orig > 0:
            ratio = sharpe_smooth / sharpe_orig
            print(f"  比率: {ratio:.2%}")
            assert ratio >= 0.9, (
                f"sma=3 Sharpe {sharpe_smooth:.3f} < 90% × {sharpe_orig:.3f}"
            )

    def test_patch_isolation(self):
        """unpatch 后原函数恢复"""
        from src.trend_strength import trend_confirmation as original
        from src.signal_generator import trend_confirmation as sg_original

        self._run_backtest(_make_small_prices(n=100), sma_window=3)

        from src.trend_strength import trend_confirmation as after_ts
        assert after_ts is original, "trend_strength 未恢复"

        from src.signal_generator import trend_confirmation as after_sg
        assert after_sg is sg_original, "signal_generator 未恢复"
