# [2026-10-15] 修复：SCENARIOS 已于 2026-06-18 改为 per-ETF 分档（spread_mult），
#             测试仍读已删除的 slippage_bps 键，自 6-18 起长期失败
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
        """总摩擦单调递增。

        总摩擦 = Σ(各 ETF 分档价差 bp × spread_mult) + 佣金率。
        价差为拉取时按成交量动态分档，故只校验其倍数与佣金率两个分量均不回退
        —— 二者同时单调 ⇒ 总摩擦必然单调。
        """
        mults = [s["spread_mult"] for s in SCENARIOS]
        comms = [s["commission_rate"] for s in SCENARIOS]
        for i in range(len(SCENARIOS) - 1):
            assert mults[i] <= mults[i + 1], f"价差倍数在第 {i} 档回退: {mults}"
            assert comms[i] <= comms[i + 1], f"佣金率在第 {i} 档回退: {comms}"
