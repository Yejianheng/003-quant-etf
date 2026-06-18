# [2026-06-18] 新增：稳定性矩阵模块测试
import pytest
import numpy as np
import pandas as pd
from attribution.stability import stability_matrix


class TestStabilityMatrix:
    def test_param_sensitivity_ranking(self):
        """参数敏感度按 ΔSharpe 降序排列"""
        param_sweep = {
            "trend_window": [
                (40, 1.10), (32, 1.08), (48, 1.12),
            ],
            "ewma_lambda": [
                (0.94, 1.10), (0.75, 1.05), (1.0, 1.09),
            ],
            "target_vol": [
                (0.08, 1.10), (0.064, 1.09), (0.096, 1.11),
            ],
        }

        result = stability_matrix(param_sweep=param_sweep)

        sensitivity = result["parameter_sensitivity"]
        assert len(sensitivity) == 3
        # 按 ΔSharpe 降序：target_vol 跨 0.02, trend_window 跨 0.04, ewma_lambda 跨 0.05
        assert sensitivity[0]["param"] == "ewma_lambda"
        assert sensitivity[0]["delta_sharpe"] == pytest.approx(0.05)

    def test_rolling_sharpe_stats(self):
        """滚动 Sharpe 统计：min/mean/max 在合理范围"""
        rng = np.random.default_rng(42)
        dates = pd.date_range("2015-01-02", "2025-12-31", freq="B")
        daily_ret = rng.normal(0.0004, 0.012, len(dates))
        rets = pd.Series(daily_ret, index=dates)

        result = stability_matrix(daily_returns=rets)

        rs = result["rolling_sharpe"]
        assert "min" in rs
        assert "mean" in rs
        assert "max" in rs
        assert rs["min"] <= rs["mean"] <= rs["max"]

    def test_extreme_periods_present(self):
        """极端行情区间全部覆盖"""
        rets = _make_simple_rets(seed=1, n=3000)
        periods = {
            "2015暴跌": (pd.Timestamp("2015-06-12"), pd.Timestamp("2015-08-26")),
            "2018熊市": (pd.Timestamp("2018-01-24"), pd.Timestamp("2018-12-28")),
        }

        result = stability_matrix(daily_returns=rets, extreme_periods=periods)

        ep = result["extreme_periods"]
        assert "2015暴跌" in ep
        assert "2018熊市" in ep
        for p in ep.values():
            assert "total_return" in p
            assert "max_drawdown" in p

    def test_empty_param_sweep(self):
        """无参数扫描 → sensitivity 为空列表"""
        result = stability_matrix()
        assert result["parameter_sensitivity"] == []


def _make_simple_rets(seed, n):
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2014-01-02", periods=n, freq="B")
    return pd.Series(rng.normal(0.0003, 0.012, n), index=dates)
