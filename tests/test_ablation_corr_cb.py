# [2026-05-30] 新增：相关性熔断 ablation 测试

import os
import sys
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.ablation_corr_cb import (
    load_all_prices,
    compute_metrics,
    year_return,
    count_cb_triggers,
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


class TestCountCbTriggers:
    def test_no_triggers(self):
        records = pd.DataFrame({
            "circuit_breaker_triggered": [False] * 100,
        }, index=pd.date_range("2020-01-01", periods=100))
        assert count_cb_triggers(records) == 0

    def test_some_triggers(self):
        arr = [False] * 50 + [True] * 10 + [False] * 40
        records = pd.DataFrame({
            "circuit_breaker_triggered": arr,
        }, index=pd.date_range("2020-01-01", periods=100))
        assert count_cb_triggers(records) == 10

    def test_counts_by_year(self):
        """2022 年熔断次数可正确统计"""
        dates = pd.date_range("2022-01-01", "2022-12-31", freq="B")
        arr = [False] * len(dates)
        arr[100:105] = [True] * 5  # 5 天熔断
        records = pd.DataFrame({
            "circuit_breaker_triggered": arr,
        }, index=dates)
        assert count_cb_triggers(records) == 5
