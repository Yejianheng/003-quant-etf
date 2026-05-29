# [2026-05-29] 新增：EWMA 协方差 ablation 测试

import os
import sys
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.ablation_ewma import (
    load_all_prices,
    compute_metrics,
    year_return,
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


class TestYearReturn:
    def test_extracts_year_return(self):
        dates = pd.date_range("2020-01-02", "2020-12-31", freq="B")
        nav = pd.Series(np.linspace(100, 110, len(dates)), index=dates)
        r = year_return(nav, 2020)
        assert r == pytest.approx(0.10, rel=0.01)

    def test_missing_year_returns_nan(self):
        nav = pd.Series([100, 105], index=pd.date_range("2020-01-01", periods=2))
        r = year_return(nav, 2018)
        assert np.isnan(r)
