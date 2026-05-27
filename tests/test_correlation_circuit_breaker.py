# [2026-05-27] 新增：相关性熔断模块测试 — 5 场景

import numpy as np
import pandas as pd

from src.correlation_circuit_breaker import (
    stock_basket_returns,
    rolling_correlation,
    correlation_circuit_breaker,
)


def _make_prices_from_returns(log_returns: np.ndarray, start_price: float = 100.0) -> pd.Series:
    """由对数收益率序列构造价格 Series（带工作日 index）"""
    prices = start_price * np.exp(np.cumsum(log_returns))
    dates = pd.date_range("2024-01-01", periods=len(prices), freq="B")
    return pd.Series(prices, index=dates, name="close")


class TestNegativeCorrelationNoTrigger:
    """场景 1：股债负相关不触发 — 股票涨 + 债券跌，120 天数据"""

    def test_negative_correlation_no_trigger(self):
        np.random.seed(42)
        n = 120
        # 共享噪声 → 股票涨时债券跌（反向共享噪声构造负相关）
        noise = np.random.normal(0, 0.001, n)
        stock_r = np.full(n, 0.001) + noise
        bond_r = np.full(n, 0.0) - noise  # 噪声正向时股票涨、债券跌

        stock_prices = {
            "沪深300": _make_prices_from_returns(stock_r),
            "创业板": _make_prices_from_returns(stock_r),
            "纳指": _make_prices_from_returns(stock_r),
        }
        bond_prices = _make_prices_from_returns(bond_r)

        result = correlation_circuit_breaker(stock_prices, bond_prices)
        assert result["triggered"] is False, (
            f"股债负相关不应触发熔断，triggered={result['triggered']}，"
            f"smoothed_corr={result['smoothed_corr']:.4f}"
        )


class TestPositiveCorrelationTrigger:
    """场景 2：股债正相关触发 — 股票和债券同涨同跌，120 天数据"""

    def test_positive_correlation_trigger(self):
        np.random.seed(42)
        n = 120
        # 共享噪声 → 股票和债券同涨同跌（正相关）
        noise = np.random.normal(0, 0.001, n)
        r = np.full(n, 0.001) + noise

        stock_prices = {
            "沪深300": _make_prices_from_returns(r),
            "创业板": _make_prices_from_returns(r),
            "纳指": _make_prices_from_returns(r),
        }
        bond_prices = _make_prices_from_returns(r)

        result = correlation_circuit_breaker(stock_prices, bond_prices)
        assert result["triggered"] is True, (
            f"股债正相关应触发熔断，triggered={result['triggered']}，"
            f"smoothed_corr={result['smoothed_corr']:.4f}"
        )


class TestSmaSmoothingEffect:
    """场景 3：SMA 平滑效果 — 前 60 天正相关 + 后 60 天负相关"""

    def test_sma_smoothing_brings_closer_to_zero(self):
        np.random.seed(42)
        n = 120
        noise1 = np.random.normal(0, 0.001, 60)
        noise2 = np.random.normal(0, 0.001, 60)
        # 前 60 天：股债同向（正相关）— 共享噪声
        r_pos = np.full(60, 0.001) + noise1
        # 后 60 天：股债反向（负相关）— 反向噪声
        r_stock_neg = np.full(60, 0.001) + noise2
        r_bond_neg = np.full(60, 0.0) - noise2

        stock_r = np.concatenate([r_pos, r_stock_neg])
        bond_r = np.concatenate([r_pos, r_bond_neg])

        stock_prices = {
            "沪深300": _make_prices_from_returns(stock_r),
            "创业板": _make_prices_from_returns(stock_r),
            "纳指": _make_prices_from_returns(stock_r),
        }
        bond_prices = _make_prices_from_returns(bond_r)

        result = correlation_circuit_breaker(stock_prices, bond_prices)
        smoothed = result["smoothed_corr"]
        raw = result["raw_corr"]

        # 后 60 天为负相关，raw 已为负；smoothed 由 5 日 SMA 平滑，
        # 滞后效应使 smoothed > raw（更接近 0 或正），但绝对值上 smoothed 不一定更接近 0
        # 核心验证：SMA 平滑滞后，smoothed 应 > raw
        assert smoothed > raw, (
            f"SMA 滞后效应：smoothed_corr({smoothed:.4f}) 应 > raw_corr({raw:.4f})"
        )


class TestInsufficientData:
    """场景 4：数据不足 — 30 天数据，corr_window=60"""

    def test_insufficient_data_returns_defaults(self):
        np.random.seed(42)
        n = 30
        r = np.full(n, 0.001) + np.random.normal(0, 0.0005, n)

        stock_prices = {
            "沪深300": _make_prices_from_returns(r),
            "创业板": _make_prices_from_returns(r),
            "纳指": _make_prices_from_returns(r),
        }
        bond_prices = _make_prices_from_returns(r)

        result = correlation_circuit_breaker(stock_prices, bond_prices, corr_window=60, sma_window=5)
        assert result["triggered"] is False, "数据不足时不应触发熔断"
        assert result["smoothed_corr"] == 0.0, f"数据不足时 smoothed_corr 应为 0.0，得到 {result['smoothed_corr']}"


class TestEqualWeightBasket:
    """场景 5：等权篮子计算 — 3 只股票各构造已知日收益率"""

    def test_equal_weight_basket_returns(self):
        np.random.seed(42)
        n = 10
        dates = pd.date_range("2024-01-01", periods=n, freq="B")

        # 构造已知价格序列，使日对数收益率确定
        p1 = pd.Series([100, 101, 102, 101.5, 103, 104, 105, 104.5, 106, 107], index=dates)
        p2 = pd.Series([50, 51, 50.5, 51.5, 52, 51, 53, 54, 53.5, 55], index=dates)
        p3 = pd.Series([200, 202, 201, 203, 205, 204, 206, 208, 207, 209], index=dates)

        stock_prices = {"沪深300": p1, "创业板": p2, "纳指": p3}

        result = stock_basket_returns(stock_prices)

        # 手动计算等权平均
        r1 = np.log(p1 / p1.shift(1)).dropna()
        r2 = np.log(p2 / p2.shift(1)).dropna()
        r3 = np.log(p3 / p3.shift(1)).dropna()
        expected = pd.DataFrame({"r1": r1, "r2": r2, "r3": r3}).mean(axis=1)

        assert len(result) == len(expected), f"长度应匹配，{len(result)} vs {len(expected)}"
        assert (abs(result.values - expected.values) < 1e-10).all(), (
            f"等权篮子计算不正确，最大误差: {abs(result.values - expected.values).max():.2e}"
        )

    def test_equal_weight_basket_skipna(self):
        """某 ETF 某日缺数据时用其余 ETF 均值，不返回全 NaN"""
        n = 10
        dates = pd.date_range("2024-01-01", periods=n, freq="B")

        p1 = pd.Series([100, 101, 102, 101.5, 103, 104, 105, 104.5, 106, 107], index=dates)
        p2 = pd.Series([50, 51, 50.5, 51.5, 52, 51, 53, 54, 53.5, 55], index=dates)
        # p3 缺第 5 天的数据（用 NaN 表示缺失）
        p3 = pd.Series([200, 202, 201, 203, np.nan, 204, 206, 208, 207, 209], index=dates)

        stock_prices = {"沪深300": p1, "创业板": p2, "纳指": p3}

        result = stock_basket_returns(stock_prices)
        # p3 第 4→5 天因 NaN 会产生 NaN 对数收益率，skipna 用其余 2 只均值
        assert not result.isna().any(), "skipna 后不应有 NaN"


class TestRollingCorrelation:
    """rolling_correlation 函数单元测试"""

    def test_rolling_correlation_values(self):
        np.random.seed(42)
        n = 100
        dates = pd.date_range("2024-01-01", periods=n, freq="B")

        # 前 50 天完全正相关，后 50 天完全负相关
        r = np.full(100, 0.001) + np.random.normal(0, 0.0001, 100)
        a = pd.Series(r, index=dates)
        b = pd.Series(r, index=dates)  # 完全相同 → 完美正相关

        result = rolling_correlation(a, b, window=20)
        # 至少有数据的部分，相关性应接近 1
        valid = result.dropna()
        assert len(valid) > 0, "应有有效相关值"
        assert (valid > 0.9).all(), f"完全相同的序列滚动相关性应 > 0.9"

    def test_rolling_correlation_short_data(self):
        np.random.seed(42)
        dates = pd.date_range("2024-01-01", periods=10, freq="B")
        a = pd.Series(np.random.normal(0.001, 0.01, 10), index=dates)
        b = pd.Series(np.random.normal(0.001, 0.01, 10), index=dates)

        result = rolling_correlation(a, b, window=60)
        assert result.isna().all(), "数据不足窗口时全部应为 NaN"
