# [2026-05-30] 新增：样本外验证测试

import os
import sys
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.out_of_sample_validation import (
    filter_prices_by_dates,
    compute_metrics,
    find_best_params,
)


class TestFilterPricesByDates:
    def test_filters_date_range(self):
        dates = pd.date_range("2018-01-01", "2022-12-31", freq="B")
        df = pd.DataFrame({"close": np.random.randn(len(dates)) + 100}, index=dates)
        prices = {"测试ETF": df}
        result = filter_prices_by_dates(prices, "2014-01-01", "2020-12-31")
        # 数据从 2018 开始，过滤到 2020 截止
        assert result["测试ETF"].index[0] >= pd.Timestamp("2014-01-01")
        assert result["测试ETF"].index[-1] <= pd.Timestamp("2020-12-31")


class TestComputeMetrics:
    def test_returns_expected_keys(self):
        nav = pd.Series([100, 101, 102, 103, 104, 105],
                        index=pd.date_range("2020-01-01", periods=6))
        m = compute_metrics(nav)
        for k in ["总收益", "年化", "波动率", "Sharpe", "最大回撤"]:
            assert k in m

    def test_flat_nav_zero_return(self):
        nav = pd.Series([100] * 20, index=pd.date_range("2020-01-01", periods=20))
        m = compute_metrics(nav)
        assert m["总收益"] == pytest.approx(0.0, abs=1e-6)
        assert m["Sharpe"] == pytest.approx(0.0, abs=1e-6)

    def test_positive_return(self):
        dates = pd.date_range("2020-01-01", periods=252, freq="B")
        nav = pd.Series(np.linspace(100, 120, 252), index=dates)
        m = compute_metrics(nav)
        assert m["总收益"] > 0
        assert m["Sharpe"] > 0


class TestFindBestParams:
    def test_selects_highest_sharpe(self):
        results = [
            {"trend_window": 20, "sharpe_ratio": 0.5},
            {"trend_window": 40, "sharpe_ratio": 1.2},
            {"trend_window": 60, "sharpe_ratio": 0.8},
        ]
        best = find_best_params(results)
        assert best["trend_window"] == 40
        assert best["sharpe_ratio"] == 1.2
