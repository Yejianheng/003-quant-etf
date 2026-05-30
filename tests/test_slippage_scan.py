# [2026-05-30] 新增：滑点手续费扫描脚本测试

import os
import sys
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.slippage_scan import compute_metrics, SCENARIOS


class TestComputeMetrics:
    def test_returns_expected_keys(self):
        nav = pd.Series([100, 101, 102, 103, 104, 105],
                        index=pd.date_range("2020-01-01", periods=6))
        m = compute_metrics(nav)
        for k in ["总收益", "年化", "波动率", "Sharpe", "最大回撤"]:
            assert k in m


class TestScenarios:
    def test_four_scenarios(self):
        assert len(SCENARIOS) == 4

    def test_scenario_order(self):
        """场景按摩擦递增"""
        labels = [s["label"] for s in SCENARIOS]
        assert labels == ["理想", "乐观", "中性", "悲观"]

    def test_friction_increases(self):
        """总摩擦单调递增"""
        costs = [s["slippage_bps"] + s["commission_rate"] * 10000 for s in SCENARIOS]
        for i in range(len(costs) - 1):
            assert costs[i] <= costs[i + 1]
