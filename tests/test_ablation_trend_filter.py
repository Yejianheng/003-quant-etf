# [2026-05-29] 新增：趋势过滤 ablation 测试

import os
import sys
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.ablation_trend_filter import (
    load_all_prices,
    compute_metrics,
    year_return,
    count_whipsaws,
    parse_etf_list,
)


class TestLoadPrices:
    def test_loads_all_etfs(self):
        """加载 11 个 ETF 数据"""
        prices = load_all_prices()
        expected = {"沪深300", "创业板", "纳指", "黄金", "国债ETF",
                    "消费ETF", "医药ETF", "证券ETF", "有色ETF", "科技ETF", "军工ETF"}
        assert set(prices.keys()) == expected

    def test_each_has_ohlc_columns(self):
        """每个 DataFrame 都有 OHLC 列"""
        prices = load_all_prices()
        for name, df in prices.items():
            for col in ["open", "high", "low", "close"]:
                assert col in df.columns, f"{name} 缺少 {col}"


class TestComputeMetrics:
    def test_returns_all_keys(self):
        """指标计算返回所有必需键"""
        nav = pd.Series([100, 101, 102, 103, 104, 105],
                        index=pd.date_range("2020-01-01", periods=6))
        m = compute_metrics(nav)
        for k in ["总收益", "年化", "波动率", "Sharpe", "最大回撤"]:
            assert k in m, f"缺少指标 {k}"

    def test_positive_return(self):
        """正收益正确计算"""
        nav = pd.Series([100, 110],
                        index=pd.date_range("2020-01-01", periods=2))
        m = compute_metrics(nav)
        assert m["总收益"] == pytest.approx(0.10, rel=0.01)

    def test_no_drawdown_when_rising(self):
        """持续上涨时回撤为 0"""
        nav = pd.Series(np.linspace(100, 200, 100),
                        index=pd.date_range("2020-01-01", periods=100))
        m = compute_metrics(nav)
        assert m["最大回撤"] == pytest.approx(0.0, abs=0.01)


class TestYearReturn:
    def test_extracts_year_return(self):
        """提取特定年份收益"""
        dates = pd.date_range("2018-01-02", "2018-12-31", freq="B")
        nav = pd.Series(np.linspace(100, 90, len(dates)), index=dates)
        r = year_return(nav, 2018)
        assert r == pytest.approx(-0.10, rel=0.01)

    def test_missing_year_returns_nan(self):
        """年份不在数据中返回 NaN"""
        nav = pd.Series([100, 105], index=pd.date_range("2020-01-01", periods=2))
        r = year_return(nav, 2018)
        assert np.isnan(r)


class TestParseEtfList:
    def test_semicolon_separated(self):
        assert parse_etf_list("沪深300;创业板;纳指") == ["沪深300", "创业板", "纳指"]

    def test_single_etf(self):
        assert parse_etf_list("国债ETF") == ["国债ETF"]

    def test_empty_string(self):
        assert parse_etf_list("") == []

    def test_nan_returns_empty(self):
        assert parse_etf_list(np.nan) == []
        assert parse_etf_list(float("nan")) == []

    def test_none_returns_empty(self):
        assert parse_etf_list(None) == []

    def test_string_nan(self):
        assert parse_etf_list("nan") == []


class TestCountWhipsaws:
    def test_no_whipsaws_stable(self):
        """稳定持仓无 whipsaw"""
        records = pd.DataFrame({
            "defense_active": ["沪深300;国债ETF"] * 100,
        }, index=pd.date_range("2020-01-01", periods=100))
        assert count_whipsaws(records) == 0

    def test_one_whipsaw(self):
        """快速 entry→exit 计为 whipsaw"""
        entries = ["沪深300"] * 5 + ["沪深300;创业板"] * 3 + ["沪深300"] * 92
        idx = pd.date_range("2020-01-01", periods=100)
        records = pd.DataFrame({"defense_active": entries}, index=idx)
        # 创业板在第6天进入，第9天退出，持有3天 < 20 → whipsaw
        n = count_whipsaws(records)
        assert n >= 1, f"应至少检测到 1 个 whipsaw，实际 {n}"

    def test_no_whipsaw_long_hold(self):
        """持有超过 20 天不算 whipsaw"""
        entries = ["沪深300"] * 5 + ["沪深300;创业板"] * 25 + ["沪深300"] * 70
        idx = pd.date_range("2020-01-01", periods=100)
        records = pd.DataFrame({"defense_active": entries}, index=idx)
        n = count_whipsaws(records)
        assert n == 0, f"持有超过20天不应为whipsaw，实际 {n}"
