# [2026-05-29] 新增：2022 股债双杀专项分析 — 单元测试

import os
import sys
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from analyze_2022_bear import (
    track_etf_transitions,
    classify_migration_stage,
    compute_6040_nav,
    find_circuit_breaker_periods,
)


class TestTrackEtfTransitions:
    """track_etf_transitions 追踪单只 ETF 在一年内的 active/inactive 转变。"""

    def test_entry_exit_sequence(self):
        dates = pd.date_range("2022-01-04", periods=20, freq="B")
        da = pd.Series(
            ["沪深300;国债ETF"] * 5
            + ["国债ETF"] * 5
            + ["沪深300;国债ETF"] * 5
            + [""] * 5,
            index=dates,
        )
        events = track_etf_transitions(da, "沪深300")
        # exit at d5, entry at d10, exit at d15
        assert len(events) >= 3
        assert events.iloc[0]["event"] == "inactive"
        assert events.iloc[1]["event"] == "active"
        assert events.iloc[2]["event"] == "inactive"

    def test_fully_active(self):
        dates = pd.date_range("2022-01-04", periods=10, freq="B")
        da = pd.Series(["沪深300;国债ETF"] * 10, index=dates)
        events = track_etf_transitions(da, "沪深300")
        assert len(events) == 0

    def test_never_active(self):
        dates = pd.date_range("2022-01-04", periods=10, freq="B")
        da = pd.Series(["国债ETF"] * 10, index=dates)
        events = track_etf_transitions(da, "纳指")
        assert len(events) == 0


class TestClassifyMigrationStage:
    """classify_migration_stage 根据 defense_active 分类资金所处阶段。"""

    def test_stocks_stage(self):
        assert classify_migration_stage("沪深300;创业板;纳指") == "权益重仓"

    def test_stocks_bonds_stage(self):
        assert classify_migration_stage("沪深300;国债ETF") == "股债混合"

    def test_bonds_gold_stage(self):
        assert classify_migration_stage("黄金;国债ETF") == "避险资产"

    def test_only_bonds_stage(self):
        assert classify_migration_stage("国债ETF") == "纯债"

    def test_empty_stage(self):
        assert classify_migration_stage("") == "空仓/repo"


class TestCompute6040Nav:
    """compute_6040_nav 构建 60/40 组合的模拟 NAV。"""

    def test_basic(self):
        dates = pd.date_range("2022-01-04", periods=10, freq="B")
        stock_prices = pd.Series(100.0 + np.arange(10) * 0.5, index=dates)
        bond_prices = pd.Series(100.0 + np.arange(10) * 0.1, index=dates)
        nav = compute_6040_nav(stock_prices, bond_prices, rebalance_freq=5)
        assert len(nav) == len(dates)
        assert nav.iloc[0] == 1.0


class TestFindCircuitBreakerPeriods:
    """find_circuit_breaker_periods 找出熔断（进入 repo）的时间段。"""

    def test_one_breaker_period(self):
        dates = pd.date_range("2022-01-04", periods=30, freq="B")
        exposure = pd.Series(
            [1e6] * 10 + [0.0] * 10 + [1e6] * 10,
            index=dates,
        )
        periods = find_circuit_breaker_periods(exposure)
        assert len(periods) == 1
        assert periods[0]["start"] == dates[10]
        assert periods[0]["end"] == dates[20]
