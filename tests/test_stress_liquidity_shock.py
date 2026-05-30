# [2026-05-30] 新增：stress_liquidity_shock.py 测试
import os
import sys
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.stress_liquidity_shock import build_gap_down_prices, compute_exposure_timeline


def _make_base_prices(n_days: int = 20) -> pd.DataFrame:
    """构造冲击前的正常价格。"""
    np.random.seed(42)
    dates = pd.date_range("2022-01-03", periods=n_days, freq="B")
    close = 100 * (1 + np.random.randn(n_days).cumsum() * 0.01).reshape(-1)
    close = close - close.min() + 50
    df = pd.DataFrame({
        "open": close * 0.99,
        "high": close * 1.02,
        "low": close * 0.98,
        "close": close,
    }, index=dates)
    return df


class TestBuildGapDownPrices:
    """构造断层下跌合成价格。"""

    def test_creates_consecutive_gap_downs(self):
        """连续 5 天每天跌 7%，验证价格逐日下降。"""
        base = _make_base_prices(21)
        # 用 base 的最后一天作为冲击起点
        shock = build_gap_down_prices(base, n_shock_days=5, daily_drop=0.07, seed=42)
        assert len(shock) == len(base) + 5
        # 最后 5 天是冲击日 → close 应连续下降
        shock_closes = shock["close"].iloc[-5:].values
        for i in range(1, len(shock_closes)):
            assert shock_closes[i] < shock_closes[i - 1], \
                f"冲击日 {i} close {shock_closes[i]} 应小于前日 {shock_closes[i-1]}"

    def test_single_shock_day(self):
        """只有 1 天冲击。"""
        base = _make_base_prices(20)
        shock = build_gap_down_prices(base, n_shock_days=1, daily_drop=0.07, seed=42)
        assert len(shock) == len(base) + 1

    def test_ohlc_columns_present(self):
        """返回 DataFrame 含 OHLC 列。"""
        base = _make_base_prices(20)
        shock = build_gap_down_prices(base, n_shock_days=3, daily_drop=0.07, seed=42)
        for col in ["open", "high", "low", "close"]:
            assert col in shock.columns

    def test_drop_exceeds_100_percent_raises(self):
        """daily_drop >= 1.0 抛出 ValueError。"""
        base = _make_base_prices(20)
        with pytest.raises(ValueError, match="daily_drop"):
            build_gap_down_prices(base, n_shock_days=3, daily_drop=1.0, seed=42)

    def test_prices_remain_positive(self):
        """即使连续跌，价格仍为正。"""
        base = _make_base_prices(20)
        shock = build_gap_down_prices(base, n_shock_days=5, daily_drop=0.07, seed=42)
        assert (shock["close"] > 0).all()


class TestComputeExposureTimeline:
    """计算冲击期间每日风险暴露。"""

    def test_returns_daily_exposure(self):
        """给定持仓和价格，返回每日暴露序列。"""
        dates = pd.date_range("2022-01-03", periods=10, freq="B")
        prices = pd.DataFrame({
            "close": [100, 95, 90, 85, 80, 75, 70, 65, 60, 55],
        }, index=dates)
        positions = {"asset": 1000.0}  # 持有 1000 股

        exposure = compute_exposure_timeline(prices, positions)
        assert len(exposure) == len(prices)
        # 暴露 = position × close
        assert exposure.iloc[0] == pytest.approx(100_000, rel=1e-6)
        assert exposure.iloc[-1] == pytest.approx(55_000, rel=1e-6)

    def test_empty_positions_returns_zero_exposure(self):
        """空持仓 → 暴露全为 0。"""
        dates = pd.date_range("2022-01-03", periods=5, freq="B")
        prices = pd.DataFrame({"close": [100, 95, 90, 85, 80]}, index=dates)
        exposure = compute_exposure_timeline(prices, {})
        assert (exposure == 0).all()
