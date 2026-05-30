# [2026-05-30] 新增：趋势确认机制对比脚本测试

import os
import sys
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.compare_trend_confirmation import (
    compute_metrics,
    year_return,
    count_whipsaws,
    parse_etf_list,
    METHOD_LABELS,
)


class TestComputeMetrics:
    def test_returns_expected_keys(self):
        nav = pd.Series([100, 101, 102, 103, 104, 105],
                        index=pd.date_range("2020-01-01", periods=6))
        m = compute_metrics(nav)
        for k in ["总收益", "年化", "波动率", "Sharpe", "最大回撤"]:
            assert k in m


class TestYearReturn:
    def test_extracts_year(self):
        dates = pd.date_range("2020-01-02", "2020-12-31", freq="B")
        nav = pd.Series(np.linspace(100, 110, len(dates)), index=dates)
        r = year_return(nav, 2020)
        assert r == pytest.approx(0.10, rel=0.01)

    def test_missing_year_returns_nan(self):
        dates = pd.date_range("2020-01-02", "2020-12-31", freq="B")
        nav = pd.Series(np.linspace(100, 110, len(dates)), index=dates)
        r = year_return(nav, 2021)
        assert np.isnan(r)


class TestParseEtfList:
    def test_semicolon_separated(self):
        assert parse_etf_list("沪深300;创业板;纳指") == ["沪深300", "创业板", "纳指"]

    def test_empty_string(self):
        assert parse_etf_list("") == []

    def test_nan_returns_empty(self):
        assert parse_etf_list(float("nan")) == []


class TestCountWhipsaws:
    def test_no_whipsaws(self):
        records = pd.DataFrame({
            "defense_active": ["沪深300;国债ETF"] * 100,
        }, index=pd.date_range("2020-01-01", periods=100))
        assert count_whipsaws(records) == 0


class TestMethodLabels:
    def test_all_five_methods(self):
        assert len(METHOD_LABELS) == 5
        for m in ["trend_strength", "price_ma", "dual_ma", "ma_slope", "breakout"]:
            assert m in METHOD_LABELS
