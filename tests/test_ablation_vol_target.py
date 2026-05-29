# [2026-05-29] 新增：波动率目标 ablation 测试

import os
import sys
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.ablation_vol_target import (
    load_all_prices,
    compute_metrics,
    compute_volatility_metrics,
)


class TestLoadPrices:
    def test_loads_all_etfs(self):
        prices = load_all_prices()
        expected = {"沪深300", "创业板", "纳指", "黄金", "国债ETF",
                    "消费ETF", "医药ETF", "证券ETF", "有色ETF", "科技ETF", "军工ETF"}
        assert set(prices.keys()) == expected


class TestComputeMetrics:
    def test_returns_all_keys(self):
        nav = pd.Series([100, 101, 102, 103, 104, 105],
                        index=pd.date_range("2020-01-01", periods=6))
        m = compute_metrics(nav)
        for k in ["总收益", "年化", "波动率", "Sharpe", "最大回撤"]:
            assert k in m


class TestVolatilityMetrics:
    def test_returns_annual_vol_and_variance(self):
        """波动率指标返回年化波动率和方差"""
        nav = pd.Series(np.cumprod(1 + np.random.randn(252) * 0.01),
                        index=pd.date_range("2020-01-01", periods=252))
        m = compute_volatility_metrics(nav)
        assert "年化波动率" in m
        assert "日波动率方差" in m
        assert m["年化波动率"] > 0
        assert m["日波动率方差"] > 0

    def test_constant_nav_zero_vol(self):
        """净值不变时波动率为 0"""
        nav = pd.Series([100] * 252,
                        index=pd.date_range("2020-01-01", periods=252))
        m = compute_volatility_metrics(nav)
        assert m["年化波动率"] == pytest.approx(0.0, abs=0.001)
        assert m["日波动率方差"] == pytest.approx(0.0, abs=0.001)
