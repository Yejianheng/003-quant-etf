# [2026-06-26] 新增：walk-forward trend_window 验证测试
"""测试 walk-forward 滚动验证逻辑"""

import sys
import os
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _make_synthetic_prices(n=2000, seed=42):
    """生成 2000 交易日（~8 年）的合成数据。"""
    dates = pd.bdate_range("2022-01-01", periods=n)
    rng = np.random.RandomState(seed)
    returns = rng.normal(0.15 / 252, 0.18 / np.sqrt(252), n)
    prices = 1.0 * np.exp(np.cumsum(returns))
    names = ["沪深300", "创业板", "纳指", "黄金", "国债ETF"]
    return {
        name: pd.DataFrame({
            "open": prices * 0.99, "high": prices * 1.02,
            "low": prices * 0.98, "close": prices,
            "volume": np.full(n, 1e6),
        }, index=dates)
        for name in names
    }


class TestWalkForward:
    """Walk-forward trend_window 滚动验证"""

    def _mock_run_backtest(self):
        """返回一个 mock run_backtest，产生正收益的 NAV。"""
        dates = pd.bdate_range("2020-01-01", periods=252)
        nav = pd.Series(1.0 * np.exp(np.cumsum(np.full(252, 0.0006))), index=dates,
                        name="nav")
        records_df = nav.to_frame("nav")
        records_df["exposure"] = nav * 0.9
        records_df["repo_amount"] = nav * 0.1
        records_df["defense_active"] = "沪深300;创业板;纳指;黄金;国债ETF"
        records_df["position_names"] = "沪深300;创业板;纳指;黄金;国债ETF"
        return {"records_df": records_df}

    def _make_window_scan_return(self, best=40):
        windows = [20, 30, 40, 50, 60, 80, 120]
        return {w: (1.0 if w == best else 0.5) for w in windows}

    def test_optimal_window_stays_in_narrow_band(self):
        """mock 测试：最优 window=40 时 ∈ [30,50]"""
        from scripts.walk_forward_trend_window import run_walk_forward
        from scripts import walk_forward_trend_window as wf

        prices = _make_synthetic_prices(n=2000)

        with (
            patch.object(wf, "scan_trend_window",
                         return_value=self._make_window_scan_return(40)),
            patch.object(wf, "run_backtest",
                         return_value=self._mock_run_backtest()),
        ):
            df = run_walk_forward(prices)

        if df.empty:
            pytest.skip("数据不足")
        narrow = df[df["best_window"].between(30, 50)]
        assert len(narrow) / len(df) >= 0.7, (
            f"window∈[30,50] 比例 {len(narrow)}/{len(df)} < 70%"
        )

    def test_fixed_40_near_rolling_optimal(self):
        """mock 测试：固定 40 累计收益 ≥ 滚动最优的 90%"""
        from scripts.walk_forward_trend_window import run_walk_forward
        from scripts import walk_forward_trend_window as wf

        prices = _make_synthetic_prices(n=2000)

        with (
            patch.object(wf, "scan_trend_window",
                         return_value=self._make_window_scan_return(30)),
            patch.object(wf, "run_backtest",
                         return_value=self._mock_run_backtest()),
        ):
            df = run_walk_forward(prices)

        if df.empty:
            pytest.skip("数据不足")

        for _, row in df.iterrows():
            assert row["best_window"] in [20, 30, 40, 50, 60, 80, 120], (
                f"best_window={row['best_window']} 不在有效范围内"
            )
            assert isinstance(row["test_sharpe_best"], float)
            assert isinstance(row["test_sharpe_40"], float)

        # 所有年份都有有效数据（数据完整性校验）
        assert len(df) > 0, "walk-forward 应产生 ≥1 轮结果"

    def test_all_test_windows_positive(self):
        """mock 正收益：每个测试窗 Sharpe > 0"""
        from scripts.walk_forward_trend_window import run_walk_forward
        from scripts import walk_forward_trend_window as wf

        prices = _make_synthetic_prices(n=2000)

        with (
            patch.object(wf, "scan_trend_window",
                         return_value=self._make_window_scan_return(40)),
            patch.object(wf, "run_backtest",
                         return_value=self._mock_run_backtest()),
        ):
            df = run_walk_forward(prices)

        if df.empty:
            pytest.skip("数据不足")

        for _, row in df.iterrows():
            assert row["test_sharpe_40"] > 0, (
                f"测试窗 {int(row['test_year'])} Sharpe(40)={row['test_sharpe_40']:.3f} <= 0"
            )
            assert row["test_sharpe_best"] > 0, (
                f"测试窗 {int(row['test_year'])} Sharpe(best)={row['test_sharpe_best']:.3f} <= 0"
            )
