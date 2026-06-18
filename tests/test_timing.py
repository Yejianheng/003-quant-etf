# [2026-06-18] 新增：择时分解模块测试
import pytest
import numpy as np
import pandas as pd
from attribution.timing import timing_decomposition


def _make_data(seed, n, timing_skill=0.0):
    """构造策略 + 基准日收益。s[t] = 0.5*b[t] + skill*b[t-1]，cov(b[t-1],s[t]) = skill*var"""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2020-01-02", periods=n, freq="B")
    factor = rng.normal(0.0003, 0.012, n)
    factor_rets = pd.Series(factor, index=dates, name="benchmark")

    if timing_skill != 0:
        strategy = 0.5 * factor + timing_skill * np.roll(factor, 1)
        strategy[0] = 0.5 * factor[0]
    else:
        strategy = 0.5 * factor

    strategy_rets = pd.Series(strategy, index=dates, name="strategy")

    return strategy_rets, factor_rets


class TestTimingDecomposition:
    def test_perfect_timing_positive(self):
        """择时能力强 → timing_coefficient > 0"""
        strategy, bench = _make_data(42, 500, timing_skill=0.3)
        result = timing_decomposition(strategy, bench)
        assert result["timing_coefficient"] > 0

    def test_no_timing_skill(self):
        """恒权 → timing_coefficient ≈ 0"""
        strategy, bench = _make_data(7, 500, timing_skill=0.0)
        result = timing_decomposition(strategy, bench)
        assert abs(result["timing_coefficient"]) < 0.05

    def test_bad_timing_negative(self):
        """负择时 → timing_coefficient < 0"""
        strategy, bench = _make_data(13, 500, timing_skill=-0.3)
        result = timing_decomposition(strategy, bench)
        assert result["timing_coefficient"] < 0

    def test_decompose_up_down_months(self):
        """上涨月/下跌月分解 → 多赚 + 少亏 = 总超额"""
        strategy, bench = _make_data(42, 500, timing_skill=0.2)
        result = timing_decomposition(strategy, bench)

        total_excess = result["total_excess_return"]
        up_excess = result["up_month_excess"]
        down_excess = result["down_month_excess"]
        assert up_excess is not None
        assert down_excess is not None
        assert pytest.approx(up_excess + down_excess, abs=1e-9) == total_excess

    def test_win_rate_bounded(self):
        """月胜率在 0-1 之间"""
        strategy, bench = _make_data(42, 500, timing_skill=0.1)
        result = timing_decomposition(strategy, bench)
        assert 0 <= result["monthly_win_rate"] <= 1
