# [2026-05-27] 新增：截面动量模块测试 — 5 场景

import numpy as np
import pandas as pd

from src.cross_sectional_momentum import momentum_score, cross_sectional_zscore, composite_momentum


class TestUptrendVsFlat:
    """场景 1：上涨 vs 横盘排名 — A 单边上涨 + B 横盘，A 的 composite_momentum 得分 > B"""

    def test_uptrend_beats_flat(self):
        np.random.seed(42)
        dates = pd.date_range("2024-01-01", periods=60, freq="B")
        # A: 日均对数收益率 ~0.002，单边上涨
        r_a = np.full(60, 0.002) + np.random.normal(0, 0.0005, 60)
        prices_a = 10 * np.exp(np.cumsum(r_a))
        # B: 日均对数收益率 ~0，横盘
        r_b = np.random.normal(0, 0.0005, 60)
        prices_b = 10 * np.exp(np.cumsum(r_b))

        df = pd.DataFrame({"ETF_A": prices_a, "ETF_B": prices_b}, index=dates)
        result = composite_momentum(df, window_short=20, window_long=60)
        assert result["ETF_A"] > result["ETF_B"], (
            f"上涨 ETF 得分应 > 横盘 ETF，A={result['ETF_A']:.4f}, B={result['ETF_B']:.4f}"
        )


class TestIdenticalPrices:
    """场景 2：全部相同价格 — 3 只 ETF 完全相同，所有 z-score 接近 0"""

    def test_all_zscore_near_zero(self):
        np.random.seed(42)
        dates = pd.date_range("2024-01-01", periods=60, freq="B")
        r = np.full(60, 0.001) + np.random.normal(0, 0.0001, 60)
        prices = 10 * np.exp(np.cumsum(r))

        df = pd.DataFrame({"ETF_X": prices, "ETF_Y": prices, "ETF_Z": prices}, index=dates)
        result = composite_momentum(df, window_short=20, window_long=60)
        for etf in ["ETF_X", "ETF_Y", "ETF_Z"]:
            assert abs(result[etf]) < 0.001, f"{etf} z-score 应接近 0，得到 {result[etf]:.6f}"


class TestSingleAsset:
    """场景 3：单资产 — 只有 1 只 ETF，z-score = 0.0"""

    def test_single_asset_zscore_zero(self):
        np.random.seed(42)
        dates = pd.date_range("2024-01-01", periods=60, freq="B")
        r = np.full(60, 0.001) + np.random.normal(0, 0.0001, 60)
        prices = 10 * np.exp(np.cumsum(r))

        df = pd.DataFrame({"ETF_SOLO": prices}, index=dates)
        scores_20 = momentum_score(df, window=20)
        z_20 = cross_sectional_zscore(scores_20)
        assert z_20["ETF_SOLO"] == 0.0, f"单资产 z-score 应为 0.0，得到 {z_20['ETF_SOLO']}"

    def test_single_asset_composite_non_empty(self):
        np.random.seed(42)
        dates = pd.date_range("2024-01-01", periods=60, freq="B")
        r = np.full(60, 0.001) + np.random.normal(0, 0.0001, 60)
        prices = 10 * np.exp(np.cumsum(r))

        df = pd.DataFrame({"ETF_SOLO": prices}, index=dates)
        result = composite_momentum(df, window_short=20, window_long=60)
        assert not result.empty, "单资产 composite_momentum 不应为空"
        assert len(result) == 1


class TestInsufficientData:
    """场景 4：数据不足 — 价格长度 30 天，window=60，返回空 Series"""

    def test_insufficient_data_empty(self):
        np.random.seed(42)
        dates = pd.date_range("2024-01-01", periods=30, freq="B")
        r = np.random.normal(0.001, 0.01, 30)
        prices = 10 * np.exp(np.cumsum(r))

        df = pd.DataFrame({"ETF_SHORT": prices}, index=dates)
        result = composite_momentum(df, window_short=60, window_long=60)
        assert result.empty, f"数据不足应返回空 Series，得到 {len(result)} 条"


class TestZscoreProperties:
    """场景 5：z-score 性质 — 5 只 ETF 不同涨幅，mean ≈ 0，std ≈ 1"""

    def test_zscore_mean_near_zero(self):
        np.random.seed(42)
        dates = pd.date_range("2024-01-01", periods=120, freq="B")
        # 5 只 ETF 不同日均收益率
        daily_returns = {
            "ETF_1": np.full(120, 0.0005),
            "ETF_2": np.full(120, 0.0010),
            "ETF_3": np.full(120, 0.0015),
            "ETF_4": np.full(120, -0.0005),
            "ETF_5": np.full(120, 0.0000),
        }
        data = {}
        for name, r_base in daily_returns.items():
            r = r_base + np.random.normal(0, 0.0002, 120)
            data[name] = 10 * np.exp(np.cumsum(r))
        df = pd.DataFrame(data, index=dates)

        scores = momentum_score(df, window=20)
        z = cross_sectional_zscore(scores)
        assert abs(z.mean()) < 1e-10, f"z-score 均值应接近 0，得到 {z.mean():.12f}"

    def test_zscore_std_near_one(self):
        np.random.seed(42)
        dates = pd.date_range("2024-01-01", periods=120, freq="B")
        daily_returns = {
            "ETF_1": np.full(120, 0.0005),
            "ETF_2": np.full(120, 0.0010),
            "ETF_3": np.full(120, 0.0015),
            "ETF_4": np.full(120, -0.0005),
            "ETF_5": np.full(120, 0.0000),
        }
        data = {}
        for name, r_base in daily_returns.items():
            r = r_base + np.random.normal(0, 0.0002, 120)
            data[name] = 10 * np.exp(np.cumsum(r))
        df = pd.DataFrame(data, index=dates)

        scores = momentum_score(df, window=20)
        z = cross_sectional_zscore(scores)
        assert abs(1.0 - z.std(ddof=1)) < 0.01, f"z-score 样本标准差应接近 1.0，得到 {z.std(ddof=1):.4f}"
