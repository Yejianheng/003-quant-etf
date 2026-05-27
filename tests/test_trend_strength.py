# [2026-05-27] 新增：趋势强度模块测试 — 4 场景

import numpy as np
import pandas as pd

from src.trend_strength import annualized_return, annualized_volatility, trend_strength


class TestUptrend:
    """场景 1：上涨趋势 — 120 天单边上涨，对数收益率恒定正 + 微小噪声"""

    def test_uptrend_positive_strength(self):
        np.random.seed(42)
        r_daily = 0.001  # 日均对数收益率 ~0.1%
        log_returns = np.full(120, r_daily)
        log_returns += np.random.normal(0, 0.0001, 120)
        prices = 100 * np.exp(np.cumsum(log_returns))
        close = pd.Series(prices, index=pd.date_range("2024-01-01", periods=120, freq="B"), name="close")

        result = trend_strength(close, window=60)
        assert result > 0, f"上涨趋势的趋势强度应 > 0，得到 {result}"

    def test_uptrend_annualized_return_close_to_expected(self):
        np.random.seed(42)
        r_daily = 0.001
        log_returns = np.full(120, r_daily)
        log_returns += np.random.normal(0, 0.0001, 120)
        prices = 100 * np.exp(np.cumsum(log_returns))
        close = pd.Series(prices, index=pd.date_range("2024-01-01", periods=120, freq="B"), name="close")

        ann_ret = annualized_return(close, window=60)
        expected_annual = r_daily * 252
        assert abs(ann_ret - expected_annual) < 0.05, f"年化收益率应接近 {expected_annual:.4f}，得到 {ann_ret:.4f}"

    def test_uptrend_volatility_near_zero(self):
        np.random.seed(42)
        r_daily = 0.001
        log_returns = np.full(120, r_daily)
        log_returns += np.random.normal(0, 0.0001, 120)
        prices = 100 * np.exp(np.cumsum(log_returns))
        close = pd.Series(prices, index=pd.date_range("2024-01-01", periods=120, freq="B"), name="close")

        ann_vol = annualized_volatility(close, window=60)
        assert ann_vol < 0.02, f"微小噪声下年化波动率应 < 0.02，得到 {ann_vol:.4f}"


class TestDowntrend:
    """场景 2：下跌趋势 — 120 天单边下跌"""

    def test_downtrend_negative_strength(self):
        np.random.seed(42)
        r_daily = -0.001
        log_returns = np.full(120, r_daily)
        log_returns += np.random.normal(0, 0.0001, 120)
        prices = 100 * np.exp(np.cumsum(log_returns))
        close = pd.Series(prices, index=pd.date_range("2024-01-01", periods=120, freq="B"), name="close")

        result = trend_strength(close, window=60)
        assert result < 0, f"下跌趋势的趋势强度应 < 0，得到 {result}"


class TestInsufficientData:
    """场景 3：数据不足 — 价格序列长度 < window"""

    def test_insufficient_data_returns_zero(self):
        np.random.seed(42)
        prices = 100 * np.exp(np.cumsum(np.random.normal(0.001, 0.01, 30)))
        close = pd.Series(prices, index=pd.date_range("2024-01-01", periods=30, freq="B"), name="close")

        result = trend_strength(close, window=60)
        assert result == 0.0, f"数据不足应返回 0.0，得到 {result}"


class TestRealDataRoundtrip:
    """场景 4：真实数据往返 — fetch_etf_daily + trend_strength"""

    def test_real_data_returns_valid_float(self):
        import pytest
        from src.data_pipeline import fetch_etf_daily

        df = fetch_etf_daily("510300", "2024-01-01", "2024-06-30")
        if df.empty:
            pytest.skip("AKShare 返回空数据（网络或接口问题）")
        close = df["close"]
        result = trend_strength(close, window=60)
        assert isinstance(result, float), f"应返回 float，得到 {type(result)}"
        assert not np.isnan(result), "结果不应为 NaN"
