# [2026-05-29] 新增：步骤4 测试 — 条件性激活回测

import os
import sys
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from scripts.backtest_conditional import (
    build_conditional_nav,
    compute_metrics_from_nav,
    generate_activation_signal,
)


def make_nav_series(start_val: float, growth_rates: list[float]) -> pd.Series:
    """用给定增长率构造 NAV"""
    vals = [start_val]
    for r in growth_rates:
        vals.append(vals[-1] * (1 + r))
    dates = pd.date_range(start="2020-01-02", periods=len(vals), freq="B")
    return pd.Series(vals, index=dates)


class TestBuildConditionalNav:
    def test_always_on(self):
        """始终激活 → 结果等于 mixed NAV"""
        n = 500
        rng = np.random.default_rng(42)
        defense_ret = rng.normal(0.0005, 0.01, n)
        mixed_ret = rng.normal(0.0003, 0.012, n)

        defense = make_nav_series(1_000_000, defense_ret)
        mixed = make_nav_series(1_000_000, mixed_ret)

        # 始终激活
        signal = pd.Series(True, index=defense.index)

        cond_nav = build_conditional_nav(defense, mixed, signal)
        pd.testing.assert_series_equal(cond_nav, mixed, check_names=False)

    def test_always_off(self):
        """始终不激活 → 结果等于 defense NAV"""
        n = 500
        rng = np.random.default_rng(42)
        defense_ret = rng.normal(0.0005, 0.01, n)
        mixed_ret = rng.normal(0.0003, 0.012, n)

        defense = make_nav_series(1_000_000, defense_ret)
        mixed = make_nav_series(1_000_000, mixed_ret)

        signal = pd.Series(False, index=defense.index)
        cond_nav = build_conditional_nav(defense, mixed, signal)
        pd.testing.assert_series_equal(cond_nav, defense, check_names=False)

    def test_partial_activation(self):
        """部分激活 → 结果介于 defense 和 mixed 之间"""
        n = 500
        rng = np.random.default_rng(42)
        # 让 mixed 在前期表现更好
        defense_ret = rng.normal(0.0003, 0.01, n)
        mixed_ret = np.concatenate([
            rng.normal(0.001, 0.01, 250),
            rng.normal(0.0001, 0.01, 250),
        ])

        defense = make_nav_series(1_000_000, defense_ret)
        mixed = make_nav_series(1_000_000, mixed_ret)

        # 前半段激活，后半段不激活
        signal = pd.Series(
            [True] * 251 + [False] * 250,
            index=defense.index,
        )
        cond_nav = build_conditional_nav(defense, mixed, signal)

        # cond 应在 defense 之上（因为前半段激活用了更高的 mixed 增长）
        assert cond_nav.iloc[-1] > defense.iloc[-1]


class TestComputeMetrics:
    def test_steady_growth(self):
        """年化 10%，零波动 → Sharpe 应很大"""
        n = 1000
        daily_r = 0.10 / 252
        nav_vals = [1_000_000 * (1 + daily_r) ** i for i in range(n)]
        dates = pd.date_range(start="2018-01-02", periods=n, freq="B")
        nav = pd.Series(nav_vals, index=dates)
        m = compute_metrics_from_nav(nav)
        assert abs(m["年化"] - 0.10) < 0.01
        assert m["Sharpe"] > 5


class TestGenerateActivationSignal:
    def test_offense_count_rule(self):
        """offense_count <= 2 → 激活"""
        dates = pd.date_range(start="2020-01-02", periods=10, freq="B")
        offense_count = pd.Series([1, 3, 2, 4, 0, 3, 1, 5, 2, 3], index=dates)
        # 所有波动率都 < 0.18 确保不阻挡
        volatility = pd.Series([0.15] * 10, index=dates)
        signal = generate_activation_signal(offense_count, volatility)
        expected = pd.Series(
            [True, False, True, False, True, False, True, False, True, False],
            index=dates,
        )
        pd.testing.assert_series_equal(signal, expected, check_names=False)

    def test_vol_blocks(self):
        """高波动率时即使 offense_count 低也不激活"""
        dates = pd.date_range(start="2020-01-02", periods=5, freq="B")
        offense_count = pd.Series([1, 1, 1, 1, 1], index=dates)
        volatility = pd.Series([0.10, 0.20, 0.10, 0.30, 0.10], index=dates)
        signal = generate_activation_signal(offense_count, volatility)
        expected = pd.Series([True, False, True, False, True], index=dates)
        pd.testing.assert_series_equal(signal, expected, check_names=False)
