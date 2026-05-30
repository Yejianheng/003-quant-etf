# [2026-05-30] 新增：趋势确认机制对比测试

import os
import sys
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.trend_strength import trend_confirmation


class TestTrendConfirmation:
    """趋势确认机制——4 种方法正确性"""

    def test_price_ma_uptrend(self):
        """上升趋势中 price > MA"""
        prices = pd.Series(np.linspace(100, 120, 60))
        assert trend_confirmation(prices, method="price_ma", window=40)

    def test_price_ma_downtrend(self):
        """下降趋势中 price < MA"""
        prices = pd.Series(np.linspace(120, 100, 60))
        assert not trend_confirmation(prices, method="price_ma", window=40)

    def test_dual_ma_uptrend(self):
        """上升趋势中 MA(20) > MA(40)"""
        prices = pd.Series(np.linspace(100, 120, 60))
        assert trend_confirmation(prices, method="dual_ma", window=40)

    def test_dual_ma_downtrend(self):
        """下降趋势中 MA(20) < MA(40)"""
        prices = pd.Series(np.linspace(120, 100, 60))
        assert not trend_confirmation(prices, method="dual_ma", window=40)

    def test_ma_slope_uptrend(self):
        """上升趋势中 MA slope > 0"""
        prices = pd.Series(np.linspace(100, 120, 60))
        assert trend_confirmation(prices, method="ma_slope", window=40)

    def test_ma_slope_downtrend(self):
        """下降趋势中 MA slope < 0"""
        prices = pd.Series(np.linspace(120, 100, 60))
        assert not trend_confirmation(prices, method="ma_slope", window=40)

    def test_breakout_uptrend(self):
        """突破新高 close > highest(40)"""
        # 先横盘，最后一天创新高
        prices = pd.Series([100.0] * 59 + [101.0])
        assert trend_confirmation(prices, method="breakout", window=40)

    def test_breakout_no_breakout(self):
        """未突破"""
        prices = pd.Series([100.0] * 60)
        assert not trend_confirmation(prices, method="breakout", window=40)

    def test_trend_strength_default(self):
        """默认方法 = trend_strength > 0"""
        prices = pd.Series(np.linspace(100, 120, 60))
        assert trend_confirmation(prices, method="trend_strength", window=40)

    def test_insufficient_data(self):
        """数据不足返回 False"""
        prices = pd.Series(np.linspace(100, 120, 10))
        assert not trend_confirmation(prices, method="price_ma", window=40)

    def test_default_method_is_trend_strength(self):
        """不指定 method 时使用 trend_strength"""
        prices = pd.Series(np.linspace(100, 120, 60))
        result = trend_confirmation(prices, window=40)
        # trend_strength > 0 for uptrend
        assert result
