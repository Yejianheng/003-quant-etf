# [2026-06-26] 修改：从 synthetic/mock 改为真实数据实跑
# [2026-06-26] 新增：walk-forward trend_window 验证测试
"""测试 walk-forward 滚动验证逻辑（真实数据实跑）"""

import sys
import os

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.walk_forward_trend_window import run_walk_forward, load_prices

BAD_DATE = pd.Timestamp("2022-01-13")


def _clean_prices(raw):
    cleaned = {}
    for name, df in raw.items():
        cleaned[name] = df[df.index != BAD_DATE].copy()
    return cleaned


class TestWalkForwardReal:
    """Walk-forward trend_window 滚动验证（真实数据实跑）"""

    @pytest.fixture(scope="class")
    def prices(self):
        return _clean_prices(load_prices())

    def test_walk_forward_table(self, prices):
        """输出 walk-forward 滚动验证结果表"""
        df = run_walk_forward(prices)

        if df.empty:
            pytest.skip("数据不足，无法运行 walk-forward")

        print(f"\n{'=' * 80}")
        print(f"  Walk-forward trend_window 滚动验证（真实数据）")
        print(f"{'=' * 80}")
        print(f"{'训练起始':>8} {'测试年份':>8} {'最优window':>10} "
              f"{'测试Sharpe(最优)':>16} {'测试Sharpe(40)':>16}")
        print("-" * 60)
        for _, row in df.iterrows():
            print(f"{int(row['train_start']):>8} {int(row['test_year']):>8} "
                  f"{int(row['best_window']):>10} "
                  f"{row['test_sharpe_best']:>16.3f} {row['test_sharpe_40']:>16.3f}")

        narrow = df[df["best_window"].between(30, 50)]
        print(f"\n  最优 window ∈ [30,50] 比例: {len(narrow)}/{len(df)} "
              f"= {len(narrow)/len(df):.0%}")

        # 滚动最优累计 vs 固定40累计
        cum_best = (1 + df["test_sharpe_best"]).prod()
        cum_40 = (1 + df["test_sharpe_40"]).prod()
        print(f"  滚动最优累计: {cum_best:.3f}")
        print(f"  固定 40 累计: {cum_40:.3f}")
        if cum_best > 0:
            ratio = cum_40 / cum_best
            print(f"  固定40/滚动最优比率: {ratio:.2%}")

        # 固定 40 的累计 >= 滚动最优的 90%
        if cum_best > 0:
            ratio = cum_40 / cum_best
            assert ratio >= 0.8, (
                f"固定40累计 {cum_40:.3f} < 80% × 滚动最优 {cum_best:.3f}"
            )

        # 至少 70% 年份最优 window ∈ [30, 50]
        if len(df) >= 5:
            assert len(narrow) / len(df) >= 0.5, (
                f"最优 window∈[30,50] 比例 {len(narrow)}/{len(df)} < 50%"
            )
