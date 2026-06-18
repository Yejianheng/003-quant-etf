# [2026-06-18] 新增：metrics 模块测试
import pytest
import numpy as np
import pandas as pd
from attribution.metrics import compute_metrics


class TestComputeMetrics:
    """基础路径：正常 NAV 序列"""

    def test_normal_uptrend(self):
        """上涨趋势 NAV → 所有指标为正"""
        dates = pd.date_range("2020-01-02", "2022-12-30", freq="B")
        rng = np.random.default_rng(42)
        daily_ret = rng.normal(0.0008, 0.012, len(dates))
        nav = 1_000_000 * np.cumprod(1 + daily_ret)
        nav = pd.Series(nav, index=dates)

        m = compute_metrics(nav)

        assert m["total_return"] > 0
        assert m["annual_return"] > 0
        assert m["annual_volatility"] > 0
        assert m["sharpe_ratio"] > 0
        assert m["max_drawdown"] < 0
        assert m["calmar_ratio"] > 0
        assert -3 < m["skewness"] < 3
        assert 0 < m["positive_month_ratio"] < 1
        assert m["n_days"] == len(dates)

    def test_known_sequence(self):
        """已知 NAV 序列，手工验算指标"""
        dates = pd.date_range("2020-01-02", "2020-01-10", freq="B")
        nav = pd.Series([1.0, 1.01, 1.02, 1.015, 1.005, 1.03, 1.04], index=dates[:7])

        m = compute_metrics(nav)

        assert m["total_return"] == pytest.approx(0.04)
        assert m["n_days"] == 7

    class TestBoundary:
        """边界：极端输入"""

        def test_single_day(self):
            nav = pd.Series([1.0], index=[pd.Timestamp("2020-01-02")])
            m = compute_metrics(nav)
            assert np.isnan(m["annual_return"])
            assert m["n_days"] == 1

        def test_flat_nav(self):
            """零波动 → Sharpe NaN, 波动率 0"""
            dates = pd.date_range("2020-01-02", "2020-06-30", freq="B")
            nav = pd.Series(1.0, index=dates)
            m = compute_metrics(nav)
            assert m["annual_volatility"] == pytest.approx(0.0, abs=1e-9)
            assert np.isnan(m["sharpe_ratio"])
            assert m["max_drawdown"] == pytest.approx(0.0, abs=1e-9)

        def test_exact_12_months(self):
            """恰好 12 个月 → positive_month_ratio 精确可算"""
            dates = pd.date_range("2020-01-02", "2020-12-31", freq="B")
            rng = np.random.default_rng(99)
            daily_ret = rng.normal(0.0003, 0.01, len(dates))
            nav = 1_000_000 * np.cumprod(1 + daily_ret)
            nav = pd.Series(nav, index=dates)

            m = compute_metrics(nav)
            assert m["monthly_returns"] is not None
            assert len(m["monthly_returns"]) == 11

    class TestEdgeCases:
        """异常：边界情况"""

        def test_empty_series(self):
            nav = pd.Series([], dtype=float)
            m = compute_metrics(nav)
            for v in m.values():
                if isinstance(v, float):
                    assert np.isnan(v)

        def test_negative_nav(self):
            """负 NAV → 回撤计算仍数学正确"""
            dates = pd.date_range("2020-01-02", "2020-01-10", freq="B")
            nav = pd.Series([-1.0, -0.9, -1.1, -1.05, -0.8], index=dates[:5])
            m = compute_metrics(nav)
            assert m["max_drawdown"] <= 0
