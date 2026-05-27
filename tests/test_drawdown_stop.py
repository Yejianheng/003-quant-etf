# [2026-05-27] 新增：回撤硬止损模块测试 — 5 场景

import pandas as pd

from src.drawdown_stop import compute_drawdown, drawdown_stop


class TestNoDrawdown:
    """场景 1：无回撤 — 净值单调上涨"""

    def test_no_drawdown(self):
        values = pd.Series(
            [100, 101, 102, 103, 104, 105],
            index=pd.date_range("2024-01-01", periods=6, freq="B"),
            name="nav",
        )
        dd = compute_drawdown(values)
        assert dd.iloc[-1] == 0.0, f"单调上涨应无回撤，得到 {dd.iloc[-1]}"

        result = drawdown_stop(dd.iloc[-1])
        assert result["level"] == "normal"
        assert result["position_multiplier"] == 1.0


class TestEachLevelTrigger:
    """场景 2：各层触发 — 从峰值 100 跌到不同价位，逐一验证 level 和 multiplier"""

    def test_each_level(self):
        test_cases = [
            (93, "normal", 1.0),      # |d| = 7%
            (90, "warning", 1.0),     # |d| = 10%
            (86, "halve", 0.5),       # |d| = 14%
            (80, "liquidate", 0.0),   # |d| = 20%
        ]
        for price, expected_level, expected_mult in test_cases:
            drawdown_val = (price - 100) / 100
            result = drawdown_stop(drawdown_val)
            assert result["level"] == expected_level, (
                f"price={price}, dd={drawdown_val:.2f}: "
                f"期望 level={expected_level}，得到 {result['level']}"
            )
            assert result["position_multiplier"] == expected_mult, (
                f"price={price}, dd={drawdown_val:.2f}: "
                f"期望 multiplier={expected_mult}，得到 {result['position_multiplier']}"
            )


class TestNewHighThenDrawdown:
    """场景 3：先新高后回撤 — running_max 跟随新高"""

    def test_new_high_then_drawdown(self):
        values = pd.Series(
            [100, 150, 120],
            index=pd.date_range("2024-01-01", periods=3, freq="B"),
            name="nav",
        )
        dd = compute_drawdown(values)
        expected = (120 - 150) / 150  # -0.20
        assert abs(dd.iloc[-1] - expected) < 1e-10, (
            f"基于 150 峰值，回撤应为 {expected}，得到 {dd.iloc[-1]}"
        )
        result = drawdown_stop(dd.iloc[-1])
        assert result["level"] == "liquidate", (
            f"|d|=20% 应触发 liquidate，得到 {result['level']}"
        )
        assert result["position_multiplier"] == 0.0


class TestDrawdownRecovery:
    """场景 4：回撤恢复 — running_max 不下降，反弹不改变回撤计算"""

    def test_drawdown_recovery_no_recovery_in_multiplier(self):
        values = pd.Series(
            [100, 50, 90],
            index=pd.date_range("2024-01-01", periods=3, freq="B"),
            name="nav",
        )
        dd = compute_drawdown(values)
        expected = (90 - 100) / 100  # -0.10
        assert abs(dd.iloc[-1] - expected) < 1e-10, (
            f"回撤应基于 running_max=100，应为 {expected}，得到 {dd.iloc[-1]}"
        )
        result = drawdown_stop(dd.iloc[-1])
        assert result["level"] == "warning", f"反弹后回撤 10% 应为 warning，得到 {result['level']}"


class TestComputeDrawdownSequence:
    """场景 5：compute_drawdown 序列 — 固定序列逐日验证"""

    def test_compute_drawdown_sequence(self):
        values = pd.Series(
            [100, 110, 95, 85],
            index=pd.date_range("2024-01-01", periods=4, freq="B"),
            name="nav",
        )
        dd = compute_drawdown(values)
        expected = pd.Series(
            [0.0, 0.0, 95 / 110 - 1, 85 / 110 - 1],
            index=values.index,
            name="nav",
        )
        for i in range(len(expected)):
            assert abs(dd.iloc[i] - expected.iloc[i]) < 1e-10, (
                f"第 {i} 日：期望 {expected.iloc[i]:.6f}，得到 {dd.iloc[i]:.6f}"
            )
