# [2026-06-26] 新增：trend_threshold 扫描测试
"""测试趋势阈值过滤对回测绩效的影响"""

import sys
import os
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---- 小合成数据 ----

def _make_small_prices(n=200, seed=42):
    dates = pd.bdate_range("2024-01-01", periods=n)
    rng = np.random.RandomState(seed)
    returns = rng.normal(0.15 / 252, 0.18 / np.sqrt(252), n)
    prices = 1.0 * np.exp(np.cumsum(returns))
    return {
        name: pd.DataFrame({
            "open": prices * 0.99, "high": prices * 1.02,
            "low": prices * 0.98, "close": prices,
            "volume": np.full(n, 1e6),
        }, index=dates)
        for name in ["沪深300", "创业板", "纳指", "黄金", "国债ETF"]
    }


# ---- 带 threshold 的 trend_confirmation ----

def _threshold_tc(close, method="trend_strength", window=40, threshold=0.0):
    """替代 trend_confirmation：支持 threshold 参数。"""
    from src.trend_strength import trend_strength
    if method != "trend_strength":
        from src.trend_strength import trend_confirmation as _orig
        return _orig(close, method=method, window=window)
    return trend_strength(close, window=window) > threshold


# ---- 测试 ----

class TestTrendThresholdScan:
    """trend_threshold 参数扫描测试"""

    def _run_backtest(self, prices, threshold=0.0):
        from src.backtest_engine import run_backtest
        from src.signal_generator import DEFAULT_PARAMS
        import src.signal_generator as sg

        params = {**DEFAULT_PARAMS, "trend_confirmation_method": "trend_strength"}

        def _wrapped(close, method="trend_strength", window=40):
            return _threshold_tc(close, method=method, window=window,
                                 threshold=threshold)

        with patch.object(sg, "trend_confirmation", side_effect=_wrapped):
            result = run_backtest(prices=prices, initial_capital=1_000_000,
                                  params=params, min_days=60)
        return result["records_df"]

    def _count_whipsaws(self, records):
        """统计 defense_active 变化中的 whipsaw（5 日内进出）。"""
        da = records["defense_active"].fillna("").astype(str)

        def _parse(s):
            return {x.strip() for x in str(s).split(";") if x.strip()}

        total = 0
        prev = set()
        in_pos = {}
        for dt, val in da.items():
            curr = _parse(val)
            # 新加入
            for etf in curr - prev:
                in_pos[etf] = dt
            # 被剔除（检查是否 5 日内刚买入）
            for etf in prev - curr:
                if etf in in_pos:
                    hold_days = (dt - in_pos[etf]).days
                    if hold_days <= 5:
                        total += 1
                    del in_pos[etf]
            prev = curr
        return total

    def _compute_sharpe(self, nav):
        if len(nav) < 2 or nav.iloc[-1] <= 0:
            return 0.0
        returns = nav.pct_change().dropna()
        if len(returns) < 2:
            return 0.0
        ann_ret = (nav.iloc[-1] / nav.iloc[0]) ** (252 / len(nav)) - 1
        ann_vol = returns.std() * np.sqrt(252)
        return ann_ret / ann_vol if ann_vol > 0 else 0.0

    def _run_backtest_original(self, prices):
        """跑一次不回测，完全不 patch trend_confirmation（原始行为）。"""
        from src.backtest_engine import run_backtest
        from src.signal_generator import DEFAULT_PARAMS

        params = {**DEFAULT_PARAMS, "trend_confirmation_method": "trend_strength"}
        result = run_backtest(prices=prices, initial_capital=1_000_000,
                              params=params, min_days=60)
        return result["records_df"]

    def test_threshold_zero_unchanged(self):
        """threshold=0 时绩效与原始函数一致"""
        prices = _make_small_prices(n=200)

        rec_orig = self._run_backtest_original(prices)
        rec_th0 = self._run_backtest(prices, threshold=0.0)

        nav_orig = rec_orig["nav"]
        nav_th0 = rec_th0["nav"]

        diff = (nav_orig - nav_th0).abs().max()
        assert diff < 1.0, f"threshold=0 与原始 NAV 偏差 {diff:.2f}"

    def test_threshold_reduces_whipsaw(self):
        """threshold=0.5 时 whipsaw < threshold=0"""
        prices = _make_small_prices(n=300)

        rec_0 = self._run_backtest(prices, threshold=0.0)
        rec_05 = self._run_backtest(prices, threshold=0.5)

        whip_0 = self._count_whipsaws(rec_0)
        whip_05 = self._count_whipsaws(rec_05)

        print(f"\n  whipsaw threshold=0: {whip_0}")
        print(f"  whipsaw threshold=0.5: {whip_05}")

        assert whip_05 <= whip_0, (
            f"threshold=0.5 whipsaw {whip_05} > threshold=0 {whip_0}"
        )

    def test_threshold_sharpe_not_collapsed(self):
        """threshold=0.5 时 Sharpe 不低于 threshold=0 的 80%"""
        prices = _make_small_prices(n=250)

        rec_0 = self._run_backtest(prices, threshold=0.0)
        rec_05 = self._run_backtest(prices, threshold=0.5)

        sharpe_0 = self._compute_sharpe(rec_0["nav"])
        sharpe_05 = self._compute_sharpe(rec_05["nav"])

        print(f"\n  Sharpe threshold=0: {sharpe_0:.3f}")
        print(f"  Sharpe threshold=0.5: {sharpe_05:.3f}")

        if sharpe_0 > 0:
            ratio = sharpe_05 / sharpe_0
            print(f"  比率: {ratio:.2%}")
            assert ratio >= 0.8, (
                f"threshold=0.5 Sharpe {sharpe_05:.3f} < 80% × {sharpe_0:.3f}"
            )
