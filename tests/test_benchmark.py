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
