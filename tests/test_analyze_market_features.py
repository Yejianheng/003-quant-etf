# [2026-05-29] 新增：步骤2 测试 — 市场环境特征提取

import os
import sys
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE = os.path.join(os.path.dirname(__file__), "..")


def make_hs300_prices(n: int = 500, trend: str = "up") -> pd.DataFrame:
    """构造沪深300 OHLCV 数据"""
    dates = pd.date_range(start="2020-01-02", periods=n, freq="B")
    if trend == "up":
        close = 3.0 + np.cumsum(np.random.randn(n) * 0.01 + 0.003)
    elif trend == "down":
        close = 3.0 + np.cumsum(np.random.randn(n) * 0.01 - 0.003)
    else:
        close = 3.0 + np.cumsum(np.random.randn(n) * 0.02)
    close = np.maximum(close, 0.5)
    df = pd.DataFrame({
        "open": close * 0.99,
        "high": close * 1.02,
        "low": close * 0.98,
        "close": close,
        "volume": np.ones(n) * 1e6,
    }, index=dates)
    return df


def make_records(n: int = 500) -> pd.DataFrame:
    """构造 records DataFrame"""
    dates = pd.date_range(start="2020-01-02", periods=n, freq="B")
    offense_counts = np.random.randint(0, 7, size=n)
    offense_names = ["消费ETF", "医药ETF", "证券ETF", "有色ETF", "科技ETF", "军工ETF"]
    defense_counts = np.random.randint(1, 5, size=n)

    def rand_offense(k):
        return ";".join(offense_names[:k]) if k > 0 else ""

    return pd.DataFrame({
        "offense_top": [rand_offense(c) for c in offense_counts],
        "defense_active": ["沪深300;纳指;" + ";".join(["国债ETF"] * (d - 2)) for d in defense_counts],
        "nav": np.ones(n) * 1000000,
    }, index=dates)


class TestMarketFeatures:
    def test_hs300_trend_up(self):
        """场景1a：上涨市场中趋势方向为正"""
        from scripts.analyze_market_features import compute_trend_direction
        prices = make_hs300_prices(500, trend="up")
        trend = compute_trend_direction(prices, window=60).dropna()
        assert len(trend) > 0
        assert trend.mean() > 0

    def test_hs300_trend_down(self):
        """场景1b：下跌市场中趋势方向为负"""
        from scripts.analyze_market_features import compute_trend_direction
        prices = make_hs300_prices(500, trend="down")
        trend = compute_trend_direction(prices, window=60).dropna()
        assert len(trend) > 0
        assert trend.mean() < 0

    def test_hs300_volatility(self):
        """场景1c：波动率在合理范围"""
        from scripts.analyze_market_features import compute_market_volatility
        prices = make_hs300_prices(500)
        vol = compute_market_volatility(prices, window=60)
        assert len(vol) > 0
        assert (vol.dropna() > 0).all()

    def test_offense_count_from_records(self):
        """场景2：从 records 解析进攻 ETF 通过数"""
        from scripts.analyze_market_features import extract_offense_counts
        records = make_records(500)
        counts = extract_offense_counts(records)
        assert len(counts) == 500
        assert counts.min() >= 0
        assert counts.max() <= 6

    def test_defense_count_from_records(self):
        """场景2b：从 records 解析防御 ETF 数量"""
        from scripts.analyze_market_features import extract_defense_counts
        records = make_records(500)
        counts = extract_defense_counts(records)
        assert len(counts) == 500
        assert counts.min() >= 1

    def test_regime_feature_aggregation(self):
        """场景3：时段特征聚合"""
        from scripts.analyze_market_features import aggregate_regime_features

        dates = pd.date_range(start="2020-01-02", periods=200, freq="B")
        regimes = [
            {"start": dates[0], "end": dates[99], "regime": "outperform", "mean_excess": 0.05},
            {"start": dates[100], "end": dates[199], "regime": "underperform", "mean_excess": -0.03},
        ]
        # 特征数据：前半段高波动+强趋势，后半段低波动+弱趋势
        feature = pd.Series(
            [0.02] * 100 + [0.005] * 100,
            index=dates,
            name="volatility",
        )

        agg = aggregate_regime_features(regimes, {"volatility": feature})
        assert len(agg) == 2
        assert agg[0]["volatility_mean"] > agg[1]["volatility_mean"]
