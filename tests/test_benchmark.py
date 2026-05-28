# [2026-05-28] 新增：test_single_benchmark — 单标的买入持有
# [2026-05-27] 新增：基准计算测试 — 2 场景

import numpy as np
import pandas as pd
import pytest
from src.benchmark import compute_benchmark, BENCHMARK_WEIGHTS


def _make_ohlcv(close_series):
    """收盘价 Series → OHLCV DataFrame。"""
    close = close_series.values
    idx = close_series.index
    return pd.DataFrame({
        "open": close * 0.99,
        "high": close * 1.02,
        "low": close * 0.98,
        "close": close,
        "volume": np.full(len(close), 1e6),
    }, index=idx)


def _make_benchmark_prices(n=60, daily_return=0.001, per_name_returns=None):
    """构造 5 只基准标的各 n 天价格，全部单边上涨。

    per_name_returns: 可选，{标的名: 日收益率}，用于区分各标的表现。
    """
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    returns_map = per_name_returns or {}
    prices = {}
    for name in BENCHMARK_WEIGHTS:
        r_val = returns_map.get(name, daily_return)
        r = np.full(n, r_val)
        close = 1.0 * np.exp(np.cumsum(r))
        prices[name] = _make_ohlcv(pd.Series(close, index=dates, name="close"))
    return prices


class TestBenchmarkNav:
    """场景 1：基准净值计算 — 单调递增，净值≈exp(0.001×60)≈1.062"""

    def test_benchmark_nav(self):
        prices = _make_benchmark_prices(n=60, daily_return=0.001)
        nav = compute_benchmark(prices)

        assert len(nav) == 60, f"应 60 行，实际 {len(nav)}"
        assert isinstance(nav.index, pd.DatetimeIndex), "index 应为 DatetimeIndex"

        # 净值起始值=1.0
        assert nav.iloc[0] == pytest.approx(1.0, rel=1e-6), (
            f"起始净值应为 1.0，实际 {nav.iloc[0]}"
        )

        # 净值单调递增
        assert (nav.diff().dropna() > 0).all(), "单边上涨时净值应单调递增"

        # 近似值检验：exp(0.001×59) ≈ 1.0608
        expected_final = np.exp(0.001 * 59)
        assert nav.iloc[-1] == pytest.approx(expected_final, rel=1e-2), (
            f"最终净值应≈{expected_final:.4f}，实际 {nav.iloc[-1]:.4f}"
        )


class TestCustomWeights:
    """场景 2：权重自定义 — 等权结果与默认权重不同"""

    def test_custom_weights(self):
        # 各标的不同日收益率，权重差异才会产生不同结果
        per_name = {
            "沪深300": 0.0010,
            "创业板": 0.0015,
            "纳指": 0.0012,
            "黄金": 0.0003,
            "国债ETF": 0.0005,
        }
        prices = _make_benchmark_prices(n=60, per_name_returns=per_name)
        nav_default = compute_benchmark(prices)

        equal_weights = {name: 0.2 for name in BENCHMARK_WEIGHTS}
        nav_equal = compute_benchmark(prices, weights=equal_weights)

        assert not np.allclose(nav_default.values, nav_equal.values), (
            "等权与默认权重结果应不同"
        )


class TestSingleBenchmark:
    """场景 3：单标的买入持有净值计算。"""

    def test_single_benchmark(self):
        """compute_single_benchmark 返回起始 1.0 的净值 Series。"""
        from src.benchmark import compute_single_benchmark

        # 模拟沪深300 价格：10 天单边上涨
        dates = pd.date_range("2024-01-01", periods=10, freq="B")
        close = pd.Series(np.linspace(1.0, 1.1, 10), index=dates)
        prices = {"沪深300": pd.DataFrame({
            "open": close * 0.99,
            "high": close * 1.02,
            "low": close * 0.98,
            "close": close,
            "volume": np.full(10, 1e6),
        }, index=dates)}

        nav = compute_single_benchmark(prices, "沪深300")
        assert nav.iloc[0] == pytest.approx(1.0, rel=1e-6), "起始净值应为 1.0"
        assert nav.iloc[-1] == pytest.approx(1.1, rel=1e-6), "最终净值 = 1.1/1.0 = 1.1"
        assert len(nav) == 10

    def test_single_benchmark_missing_name(self):
        """标的不存在时返回 None。"""
        from src.benchmark import compute_single_benchmark

        dates = pd.date_range("2024-01-01", periods=5, freq="B")
        close = pd.Series([1.0, 1.01, 1.02, 1.03, 1.04], index=dates)
        prices = {"沪深300": pd.DataFrame({
            "open": close * 0.99, "high": close * 1.02,
            "low": close * 0.98, "close": close, "volume": np.full(5, 1e6),
        }, index=dates)}

        result = compute_single_benchmark(prices, "不存在的标的")
        assert result is None

    def test_single_benchmark_monotonic(self):
        """单边上涨时净值单调递增。"""
        from src.benchmark import compute_single_benchmark

        dates = pd.date_range("2024-01-01", periods=30, freq="B")
        r = np.full(30, 0.001)
        close = 1.0 * np.exp(np.cumsum(r))
        prices = {"纳指": pd.DataFrame({
            "open": close * 0.99, "high": close * 1.02,
            "low": close * 0.98, "close": close, "volume": np.full(30, 1e6),
        }, index=dates)}

        nav = compute_single_benchmark(prices, "纳指")
        assert nav is not None
        assert (nav.diff().dropna() > 0).all(), "单边上涨时净值应单调递增"
