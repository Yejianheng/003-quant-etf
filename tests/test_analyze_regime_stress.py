# [2026-05-29] 新增：regime 压力测试 — 单元测试

import os
import sys
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from analyze_regime_stress import (
    compute_metrics,
    slice_nav,
    align_to_nav,
    _count_whipsaws,
    compute_regime_table,
)


class TestComputeMetrics:
    """compute_metrics 从 NAV 序列计算核心指标。"""

    def test_normal_sequence(self):
        nav = pd.Series([1.0, 1.01, 0.99, 1.02],
                        index=pd.date_range("2020-01-02", periods=4, freq="B"))
        result = compute_metrics(nav)
        assert result["区间收益"] == pytest.approx(0.02)
        assert result["最大回撤"] < 0
        assert result["交易日"] == 3

    def test_single_day(self):
        nav = pd.Series([1.0], index=[pd.Timestamp("2020-01-02")])
        result = compute_metrics(nav)
        assert result == {}

    def test_empty(self):
        nav = pd.Series([], dtype=float)
        result = compute_metrics(nav)
        assert result == {}


class TestSliceNav:
    """slice_nav 按日期区间切片。"""

    def test_fully_within_range(self):
        idx = pd.date_range("2020-01-02", "2020-01-10", freq="B")
        nav = pd.Series(range(len(idx)), index=idx, dtype=float)
        sliced = slice_nav(nav, "2020-01-03", "2020-01-06")
        assert len(sliced) >= 1
        assert sliced.index[0] >= pd.Timestamp("2020-01-03")
        assert sliced.index[-1] <= pd.Timestamp("2020-01-06")

    def test_out_of_range(self):
        idx = pd.date_range("2020-01-02", "2020-01-10", freq="B")
        nav = pd.Series(range(len(idx)), index=idx, dtype=float)
        sliced = slice_nav(nav, "2010-01-01", "2010-12-31")
        assert len(sliced) == 0


class TestAlignToNav:
    """align_to_nav 将基准价格对齐到 NAV 日期。"""

    def test_basic_alignment(self):
        nav_idx = pd.DatetimeIndex([pd.Timestamp("2020-01-02"),
                                     pd.Timestamp("2020-01-03"),
                                     pd.Timestamp("2020-01-06")])
        bench_idx = pd.date_range("2020-01-02", "2020-01-06", freq="B")
        bench = pd.Series([100.0, 101.0, 102.0], index=bench_idx[:3])
        aligned = align_to_nav(bench, nav_idx)
        assert len(aligned) >= 1


class TestCountWhipsaws:
    """_count_whipsaws 统计窗口内信号翻转次数。"""

    def test_rapid_flips(self):
        dates = pd.date_range("2020-01-02", periods=50, freq="B")
        status = pd.Series(["A", "B", "A", "B", "A"] + ["A"] * 45,
                           index=dates[:50])
        count = _count_whipsaws(status, window=20)
        assert count >= 1

    def test_no_flips(self):
        dates = pd.date_range("2020-01-02", periods=50, freq="B")
        status = pd.Series(["A"] * 50, index=dates)
        count = _count_whipsaws(status, window=20)
        assert count == 0

    def test_single_flip(self):
        dates = pd.date_range("2020-01-02", periods=100, freq="B")
        # one flip, then stable for 50+ days
        status = pd.Series(["A"] * 50 + ["B"] * 50, index=dates[:100])
        count = _count_whipsaws(status, window=20)
        assert count == 0


class TestComputeRegimeTable:
    """compute_regime_table 计算单个 regime 的完整指标表。"""

    def test_returns_dataframe_with_required_labels(self):
        dates = pd.date_range("2020-01-02", periods=60, freq="B")
        nav = pd.Series(1.0 + np.cumsum(np.random.randn(60) * 0.01),
                        index=dates)
        records = pd.DataFrame({
            "exposure": [100000.0] * 60,
            "final_multiplier": [0.5] * 60,
            "position_names": ["A;B"] * 60,
            "defense_active": ["A;B"] * 60,
        }, index=dates)
        benchmarks = {
            "沪深300": pd.Series(100.0 + np.cumsum(np.random.randn(60) * 0.5),
                                index=dates),
        }
        df = compute_regime_table(nav, benchmarks, records,
                                  "test", [("2020-01-02", "2020-03-31")])
        assert "纯防御" in df.index
        assert "沪深300" in df.index
        assert "区间收益" in df.columns
        assert "Sharpe" in df.columns
        assert "最大回撤" in df.columns
        assert "空仓天数占比" in df.columns
        assert "换手次数" in df.columns

    def test_empty_period_returns_empty_df(self):
        dates = pd.date_range("2020-01-02", periods=10, freq="B")
        nav = pd.Series(1.0, index=dates)
        records = pd.DataFrame({
            "exposure": [0.0] * 10,
            "final_multiplier": [0.0] * 10,
            "position_names": [""] * 10,
            "defense_active": [""] * 10,
        }, index=dates)
        benchmarks = {}
        df = compute_regime_table(nav, benchmarks, records,
                                  "test", [("2010-01-01", "2010-12-31")])
        assert len(df) == 0
