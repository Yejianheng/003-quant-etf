# [2026-06-18] 新增：因子归因模块测试
import pytest
import numpy as np
import pandas as pd
from attribution.factor_return import factor_attribution


def _make_returns(seed, n, betas, alpha=0.0):
    """构造已知 β 的合成数据。返回 strategy_returns, factor_returns_df"""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2020-01-02", periods=n, freq="B")
    factors = pd.DataFrame({
        "沪深300": rng.normal(0.0003, 0.015, n),
        "创业板": rng.normal(0.0004, 0.020, n),
        "纳指": rng.normal(0.0005, 0.014, n),
        "黄金": rng.normal(0.0001, 0.010, n),
        "国债ETF": rng.normal(0.0001, 0.004, n),
    }, index=dates)

    strategy = alpha + sum(betas[k] * factors[k] for k in betas)
    strategy += rng.normal(0, 0.001, n)
    strategy = pd.Series(strategy, index=dates, name="strategy")

    return strategy, factors


class TestFactorAttribution:
    """基础路径"""

    def test_recovers_known_betas(self):
        """已知 β → OLS 恢复精度在 ±0.05 内"""
        betas = {"沪深300": 0.4, "创业板": 0.2, "纳指": 0.15, "黄金": 0.1, "国债ETF": 0.15}
        strategy, factors = _make_returns(42, 500, betas)

        result = factor_attribution(strategy, factors)

        for k, true_val in betas.items():
            assert result["betas"][k] == pytest.approx(true_val, abs=0.05)
        assert result["r_squared"] > 0.9
        assert abs(result["alpha"]) < 0.001

    def test_alpha_is_zero(self):
        """α ≈ 0 的合成数据 → α 不应显著偏离零"""
        betas = {"沪深300": 0.5, "创业板": 0.3, "纳指": 0.2, "黄金": 0.0, "国债ETF": 0.0}
        strategy, factors = _make_returns(99, 300, betas, alpha=0.0)

        result = factor_attribution(strategy, factors)

        assert abs(result["alpha"]) < 0.002


class TestBoundary:
    """边界"""

    def test_single_factor(self):
        """单因子 → R² 应较高"""
        betas = {"沪深300": 0.6}
        strategy, factors = _make_returns(7, 200, betas)
        factors_single = factors[["沪深300"]]

        result = factor_attribution(strategy, factors_single)

        assert result["r_squared"] > 0.8
        assert result["betas"]["沪深300"] == pytest.approx(0.6, abs=0.05)

    def test_mismatched_dates(self):
        """因子比策略多几天 → 对齐到共同日期"""
        rng = np.random.default_rng(1)
        strategy_dates = pd.date_range("2020-06-01", "2020-12-31", freq="B")
        factor_dates = pd.date_range("2020-01-02", "2020-12-31", freq="B")

        strategy = pd.Series(rng.normal(0.0005, 0.01, len(strategy_dates)), index=strategy_dates)
        factors = pd.DataFrame({
            "沪深300": rng.normal(0.0003, 0.012, len(factor_dates)),
        }, index=factor_dates)

        result = factor_attribution(strategy, factors)
        assert result["n_obs"] == len(strategy_dates)
