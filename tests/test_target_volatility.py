# [2026-05-27] 新增：目标波动率模块测试 — 5 场景

import numpy as np
import pandas as pd

from src.target_volatility import ewma_covariance, portfolio_volatility, scaling_factor


class TestEwmaRecentWeightDominance:
    """场景 1：EWMA 近期权重更大 — 前 200 天剧烈波动 + 后 52 天零波动，验证 EWMA 协方差 ≈ 0"""

    def test_ewma_cov_near_zero(self):
        np.random.seed(42)
        T = 252
        # 前 200 天：剧烈波动（日均收益率 std ~5%）
        high_vol = np.random.normal(0, 0.05, 200)
        # 后 52 天：零波动（价格恒定）
        zero_vol = np.zeros(52)
        log_returns = np.concatenate([high_vol, zero_vol])
        prices = 100 * np.exp(np.cumsum(log_returns))
        dates = pd.date_range("2024-01-01", periods=T, freq="B")
        df = pd.DataFrame({"ETF_A": prices, "ETF_B": prices}, index=dates)

        cov_ewma = ewma_covariance(df, lambda_=0.94, window=252)
        cov_ewma_val = cov_ewma.iloc[0, 0]

        # 等权协方差：对最近 252 天所有日收益率等权
        log_rets = np.log(df / df.shift(1)).dropna()
        cov_equal = float(np.cov(log_rets["ETF_A"], log_rets["ETF_B"], ddof=1)[0, 0]) * 252

        assert float(cov_ewma_val) < cov_equal * 0.3, (
            f"EWMA 协方差应远小于等权协方差（近期零波主导），"
            f"EWMA={cov_ewma_val:.6f}，等权={cov_equal:.6f}"
        )

    def test_ewma_returns_dataframe(self):
        np.random.seed(42)
        dates = pd.date_range("2024-01-01", periods=100, freq="B")
        r = np.random.normal(0.001, 0.01, 100)
        prices = 100 * np.exp(np.cumsum(r))
        df = pd.DataFrame({"X": prices, "Y": prices * np.exp(np.random.normal(0, 0.005, 100))}, index=dates)

        result = ewma_covariance(df)
        assert isinstance(result, pd.DataFrame)
        assert list(result.columns) == ["X", "Y"]
        assert list(result.index) == ["X", "Y"]


class TestPerfectCorrelation:
    """场景 2：完美正相关 — 2 只 ETF 价格完全相同，相关系数 ≈ 1"""

    def test_correlation_near_one(self):
        np.random.seed(42)
        dates = pd.date_range("2024-01-01", periods=100, freq="B")
        r = np.random.normal(0.001, 0.01, 100)
        prices = 100 * np.exp(np.cumsum(r))
        df = pd.DataFrame({"ETF_1": prices, "ETF_2": prices}, index=dates)

        cov = ewma_covariance(df)
        sigma_12 = float(cov.iloc[0, 1])
        sigma_1 = float(np.sqrt(cov.iloc[0, 0]))
        sigma_2 = float(np.sqrt(cov.iloc[1, 1]))
        corr = sigma_12 / (sigma_1 * sigma_2)

        assert abs(corr - 1.0) < 1e-6, f"相同价格序列相关系数应 ≈ 1.0，得到 {corr:.12f}"


class TestPortfolioVolatility:
    """场景 3：组合波动率计算 — 3 资产、给定权重、已知协方差矩阵，验证 sqrt(w^T Σ w)"""

    def test_manual_match(self):
        cov = pd.DataFrame(
            {
                "A": [0.04, 0.01, 0.02],
                "B": [0.01, 0.09, 0.03],
                "C": [0.02, 0.03, 0.16],
            },
            index=["A", "B", "C"],
        )
        weights = np.array([0.5, 0.3, 0.2])
        result = portfolio_volatility(weights, cov)
        # 手动计算 sqrt(w^T Σ w)
        expected = np.sqrt(weights @ cov.values @ weights)
        assert abs(result - expected) < 1e-10, f"应等于手动计算值 {expected}，得到 {result}"


class TestToleranceBandInside:
    """场景 4：容忍带内不操作 — 偏离 0.8% < 1.5%，返回 1.0"""

    def test_inside_band_returns_one(self):
        result = scaling_factor(target_vol=0.10, predicted_vol=0.108, tolerance=0.015)
        assert result == 1.0, f"容忍带内应返回 1.0，得到 {result}"

    def test_lower_bound_inside_band(self):
        result = scaling_factor(target_vol=0.10, predicted_vol=0.092, tolerance=0.015)
        assert result == 1.0, f"下偏差在容忍带内应返回 1.0，得到 {result}"

    def test_exact_boundary_inside(self):
        result = scaling_factor(target_vol=0.10, predicted_vol=0.115, tolerance=0.015)
        assert result == 1.0, f"偏差恰好等于容忍带宽应返回 1.0，得到 {result}"

    def test_zero_predicted_vol_protection(self):
        result = scaling_factor(target_vol=0.10, predicted_vol=0.0, tolerance=0.015)
        assert result == 1.0, f"预测波动率 ≤ 0 应返回 1.0，得到 {result}"

    def test_negative_predicted_vol_protection(self):
        result = scaling_factor(target_vol=0.10, predicted_vol=-0.05, tolerance=0.015)
        assert result == 1.0, f"负预测波动率应返回 1.0，得到 {result}"


class TestToleranceBandOutside:
    """场景 5：容忍带外缩放 — 偏离 5% > 1.5%，返回 target / predicted"""

    def test_outside_band_scales_down(self):
        result = scaling_factor(target_vol=0.10, predicted_vol=0.15, tolerance=0.015)
        expected = 0.10 / 0.15
        assert abs(result - expected) < 1e-10, f"应返回 {expected}，得到 {result}"

    def test_outside_band_scales_up(self):
        result = scaling_factor(target_vol=0.10, predicted_vol=0.05, tolerance=0.015)
        expected = 0.10 / 0.05
        assert abs(result - expected) < 1e-10, f"应返回 {expected}，得到 {result}"
