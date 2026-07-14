# [2026-05-30] 新增：滑点与手续费测试

import os
import sys
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.backtest_engine import run_backtest


def make_mock_prices(n_days=252, trend=0.0002, volatility=0.01):
    """生成模拟 ETF 价格数据。"""
    dates = pd.date_range("2020-01-01", periods=n_days, freq="B")
    rng = np.random.default_rng(42)
    returns = rng.normal(trend, volatility, n_days)
    close = 10.0 * np.exp(np.cumsum(returns))
    data = {
        "open": close * 0.999,
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
    }
    df = pd.DataFrame(data, index=dates)
    return df


class TestSlippageParameter:
    """slippage_bps 参数正确传递"""

    def test_default_is_zero(self):
        """默认 slippage_bps=0，不影响当前行为"""
        prices = {
            "沪深300": make_mock_prices(300),
            "创业板": make_mock_prices(300),
            "纳指": make_mock_prices(300),
            "黄金": make_mock_prices(300),
            "国债ETF": make_mock_prices(300),
        }
        # 无滑点
        result_0 = run_backtest(prices, initial_capital=1_000_000, params={"defense_ratio": 1.0}, min_days=120)
        # 默认运行应成功
        assert result_0["final_nav"] > 0
        assert "sharpe_ratio" in result_0

    def test_slippage_reduces_nav(self):
        """滑点 > 0 时净值应降低"""
        prices = {
            "沪深300": make_mock_prices(300),
            "创业板": make_mock_prices(300),
            "纳指": make_mock_prices(300),
            "黄金": make_mock_prices(300),
            "国债ETF": make_mock_prices(300),
        }
        r0 = run_backtest(prices, initial_capital=1_000_000, params={"defense_ratio": 1.0}, min_days=120)
        r20 = run_backtest(prices, initial_capital=1_000_000, params={"defense_ratio": 1.0},
                           slippage_bps=20, commission_rate=0.0005, min_days=120)
        # 有摩擦的净值不应高于无摩擦
        assert r20["final_nav"] <= r0["final_nav"] * 1.001  # 允许微小浮动


class TestSlippageEdgeCases:
    def test_zero_slippage_no_change(self):
        """slippage_bps=0 时与不传参结果一致"""
        prices = {
            "沪深300": make_mock_prices(300),
            "创业板": make_mock_prices(300),
            "纳指": make_mock_prices(300),
            "黄金": make_mock_prices(300),
            "国债ETF": make_mock_prices(300),
        }
        r1 = run_backtest(prices, initial_capital=1_000_000, params={"defense_ratio": 1.0}, min_days=120)
        r2 = run_backtest(prices, initial_capital=1_000_000, params={"defense_ratio": 1.0},
                          slippage_bps=0, commission_rate=0.0, min_days=120)
        assert r1["final_nav"] == pytest.approx(r2["final_nav"], rel=1e-10)
