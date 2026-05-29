# [2026-05-29] 新增：步骤1 测试 — analyze_offense_vs_defense.py

import os
import sys
import tempfile
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from scripts.analyze_offense_vs_defense import (
    compute_relative_stats,
    list_regime_periods,
)


def make_nav(values: list, start_date: str = "2020-01-02") -> pd.Series:
    """构造 NAV 序列，日期从 start_date 开始逐日递增"""
    dates = pd.date_range(start=start_date, periods=len(values), freq="B")
    return pd.Series(values, index=dates, name="test")


class TestComputeRelativeStats:
    def test_identical_series(self):
        """场景1：两序列完全相同 → 所有窗口相对收益为 0"""
        offense = make_nav([1.0 + i * 0.001 for i in range(300)])
        defense = make_nav([1.0 + i * 0.001 for i in range(300)])
        stats = compute_relative_stats(offense, defense)

        assert len(stats) == 3
        for _, row in stats.iterrows():
            assert abs(row["跑赢占比"]) < 0.01 or abs(row["跑赢时均值超额"]) < 0.0001
            assert abs(row["跑输时均值超额"]) < 0.0001

    def test_offense_always_beats(self):
        """场景2：进攻每日收益是防御的 2 倍 → 跑赢占比 100%"""
        offense = make_nav([1.0 + i * 0.002 for i in range(300)])
        defense = make_nav([1.0 + i * 0.001 for i in range(300)])
        stats = compute_relative_stats(offense, defense)

        for _, row in stats.iterrows():
            # 250日窗口需要足够数据
            if row["总交易日"] > 0:
                assert row["跑赢占比"] > 0.9

    def test_very_short_series(self):
        """边界：只有 5 天数据 → 所有窗口返回 NaN 但不抛异常"""
        offense = make_nav([1.0, 1.001, 1.002, 1.003, 1.004])
        defense = make_nav([1.0, 1.001, 1.002, 1.003, 1.004])
        stats = compute_relative_stats(offense, defense)

        assert len(stats) == 3
        for _, row in stats.iterrows():
            assert row["总交易日"] == 0  # 5天数据 滚动60日无有效值


class TestListRegimePeriods:
    def test_first_win_then_lose(self):
        """场景5：进攻先跑赢后跑输 → 两个时段"""
        n = 500
        # 前半段进攻强，后半段进攻弱
        o_vals = [1.0]
        d_vals = [1.0]
        for i in range(1, n):
            if i < 250:
                o_vals.append(o_vals[-1] * 1.002)
                d_vals.append(d_vals[-1] * 1.001)
            else:
                o_vals.append(o_vals[-1] * 1.0005)
                d_vals.append(d_vals[-1] * 1.001)
        offense = make_nav(o_vals)
        defense = make_nav(d_vals)

        regimes = list_regime_periods(offense, defense, window=60)
        assert len(regimes) >= 2
        types = [r["regime"] for r in regimes]
        assert "outperform" in types
        assert "underperform" in types

    def test_empty_input(self):
        """边界：空序列 → 不抛异常"""
        offense = pd.Series([], name="empty")
        defense = pd.Series([], name="empty")
        regimes = list_regime_periods(offense, defense, window=60)
        assert regimes == []
