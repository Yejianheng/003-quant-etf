# [2026-06-26] 修改：从 synthetic 改为真实数据全量回测
# [2026-06-26] 新增：trend_threshold 扫描测试
"""测试趋势阈值过滤对回测绩效的影响（真实数据）"""

import sys
import os
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.compare_trend_confirmation import run_config, load_all_prices

BAD_DATE = pd.Timestamp("2022-01-13")


def _clean_prices(raw):
    cleaned = {}
    for name, df in raw.items():
        cleaned[name] = df[df.index != BAD_DATE].copy()
    return cleaned


# ---- 辅助函数 ----

def _compute_sharpe(nav: pd.Series) -> float:
    if len(nav) < 2 or nav.iloc[-1] <= 0:
        return 0.0
    returns = nav.pct_change().dropna()
    if len(returns) < 2:
        return 0.0
    ann_ret = (nav.iloc[-1] / nav.iloc[0]) ** (252 / len(nav)) - 1
    ann_vol = returns.std() * np.sqrt(252)
    return ann_ret / ann_vol if ann_vol > 0 else 0.0


def _count_whipsaws_records(records: pd.DataFrame) -> int:
    from scripts.compare_trend_confirmation import DEFENSE_NAMES, parse_etf_list
    WHIPSAW_WINDOW = 20
    da_col = records["defense_active"].fillna("").astype(str)
    total = 0
    for etf in DEFENSE_NAMES:
        mask = da_col.apply(lambda s: etf in parse_etf_list(s))
        changed = mask != mask.shift(1)
        changed.iloc[0] = False
        flips = changed[changed]
        if len(flips) < 2:
            continue
        flip_list = [(dt, mask.loc[dt]) for dt in flips.index]
        i = 0
        while i < len(flip_list) - 1:
            dt_a, active_a = flip_list[i]
            dt_b, active_b = flip_list[i + 1]
            if active_a and not active_b:
                delta = (dt_b - dt_a).days
                if delta <= WHIPSAW_WINDOW:
                    total += 1
                    i += 2
                    continue
            i += 1
    return total


def _threshold_tc(close, method="trend_strength", window=40, threshold=0.0):
    """替代 trend_confirmation：支持 threshold 参数。"""
    from src.trend_strength import trend_strength
    if method != "trend_strength":
        from src.trend_strength import trend_confirmation as _orig
        return _orig(close, method=method, window=window)
    return trend_strength(close, window=window) > threshold


def _avg_active_etfs(records: pd.DataFrame) -> float:
    """回测期内 defense_active 的平均 ETF 数量。"""
    counts = []
    for val in records["defense_active"]:
        if not val or (isinstance(val, float) and np.isnan(val)):
            counts.append(0)
        else:
            counts.append(len(str(val).split(";")))
    return float(np.mean(counts))


THRESHOLDS = [0, 0.3, 0.5, 1.0, 1.5, 2.0]


# ---- 测试 ----

class TestTrendThresholdScanReal:
    """trend_threshold 参数扫描测试（真实数据）"""

    @pytest.fixture(scope="class")
    def prices(self):
        return _clean_prices(load_all_prices())

    def _run_threshold_backtest(self, prices, threshold=0.0):
        from src.backtest_engine import run_backtest
        from src.signal_generator import DEFAULT_PARAMS
        import src.signal_generator as sg

        params = {**DEFAULT_PARAMS, "trend_confirmation_method": "trend_strength"}

        def _wrapped(close, method="trend_strength", window=40):
            return _threshold_tc(close, method=method, window=window,
                                 threshold=threshold)

        with patch.object(sg, "trend_confirmation", side_effect=_wrapped):
            result = run_backtest(prices=prices, initial_capital=1_000_000,
                                  params=params, min_days=120)
        return result["records_df"]

    def test_threshold_scan_table(self, prices):
        """输出 threshold 扫描对比表"""
        rows = []
        for th in THRESHOLDS:
            records = self._run_threshold_backtest(prices, threshold=th)
            nav = records["nav"]
            sharpe = _compute_sharpe(nav)
            mdd = (nav - nav.expanding().max()) / nav.expanding().max()
            max_dd = mdd.min()
            whip = _count_whipsaws_records(records)
            avg_active = _avg_active_etfs(records)
            rows.append((th, sharpe, max_dd, whip, avg_active))

        print(f"\n{'=' * 80}")
        print(f"  trend_threshold 扫描对比（真实数据全量回测）")
        print(f"{'=' * 80}")
        print(f"{'threshold':>10} {'Sharpe':>10} {'最大回撤':>10} {'Whipsaw':>10} {'active均值':>10}")
        print("-" * 55)
        for th, sharpe, max_dd, whip, avg_act in rows:
            print(f"{th:>10.1f} {sharpe:>10.3f} {max_dd:>9.1%} {whip:>10} {avg_act:>10.1f}")

        # threshold=0 时 Sharpe 应为正
        assert rows[0][1] > 0, (
            f"threshold=0 Sharpe={rows[0][1]:.3f} <= 0"
        )

    def test_threshold_reduces_whipsaw(self, prices):
        """threshold=0.5 时 whipsaw <= threshold=0"""
        rec_0 = self._run_threshold_backtest(prices, threshold=0.0)
        rec_05 = self._run_threshold_backtest(prices, threshold=0.5)

        whip_0 = _count_whipsaws_records(rec_0)
        whip_05 = _count_whipsaws_records(rec_05)

        print(f"\n  whipsaw threshold=0: {whip_0}")
        print(f"  whipsaw threshold=0.5: {whip_05}")

        assert whip_05 <= whip_0, (
            f"threshold=0.5 whipsaw {whip_05} > threshold=0 {whip_0}"
        )
