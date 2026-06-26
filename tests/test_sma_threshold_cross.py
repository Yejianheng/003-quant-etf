# [2026-06-26] 新增：SMA × threshold 交叉扫描（sma=3）
"""测试 sma=3 固定下 threshold 的交叉效果（真实数据全量 2014-2026）"""

import sys
import os
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.compare_trend_confirmation import load_all_prices


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


def _max_drawdown(nav: pd.Series) -> float:
    peak = nav.expanding().max()
    dd = (nav - peak) / peak
    return dd.min()


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


def _precompute_ts(prices_dict: dict, window=40):
    from src.trend_strength import trend_strength as _ts
    from src.signal_generator import DEFENSE_NAMES

    result = {}
    for name in DEFENSE_NAMES:
        if name not in prices_dict:
            continue
        close = prices_dict[name]["close"]
        ts_vals = {}
        for i in range(window, len(close) + 1):
            seg = close.iloc[:i]
            ts_vals[close.index[i - 1]] = _ts(seg, window=window)
        result[name] = pd.Series(ts_vals)
    return result


def _run_smooth_threshold_backtest(prices, sma_window=3, threshold=0.0):
    """运行带 SMA 平滑 + threshold 过滤的回测。"""
    import src.signal_generator as sg
    from src.backtest_engine import run_backtest
    from src.signal_generator import DEFAULT_PARAMS, DEFENSE_NAMES

    precomputed_ts = _precompute_ts(prices, window=40)

    # 生成信号：sma(trend_strength) > threshold
    signals = {}
    for name, ts_series in precomputed_ts.items():
        if sma_window <= 1:
            signals[name] = ts_series > threshold
        else:
            s = ts_series.rolling(sma_window, min_periods=1).mean()
            signals[name] = s > threshold

    close_cache = {
        name: prices[name]["close"]
        for name in DEFENSE_NAMES
        if name in prices
    }

    def _custom_trend_confirmation(close_series, method="trend_strength", window=40):
        if method != "trend_strength":
            from src.trend_strength import trend_confirmation as _orig
            return _orig(close_series, method=method, window=window)

        last_date = close_series.index[-1]
        last_val = close_series.iloc[-1]

        for etf_name, full_close in close_cache.items():
            if last_date in full_close.index:
                if abs(full_close.loc[last_date] - last_val) / max(abs(last_val), 1e-8) < 1e-6:
                    sig = signals.get(etf_name)
                    if sig is not None and last_date in sig.index:
                        return bool(sig.loc[last_date])
                    break

        from src.trend_strength import trend_strength as _ts
        return _ts(close_series, window=window) > threshold

    params = {**DEFAULT_PARAMS, "trend_confirmation_method": "trend_strength"}

    with patch.object(sg, "trend_confirmation", side_effect=_custom_trend_confirmation):
        result = run_backtest(prices=prices, initial_capital=1_000_000,
                              params=params, min_days=120)
    return result["records_df"]


# ---- 测试 ----

class TestSmaThresholdCross:
    """SMA × threshold 交叉扫描"""

    @pytest.fixture(scope="class")
    def prices(self):
        return _clean_prices(load_all_prices())

    def test_cross_table(self, prices):
        """输出 sma=3 × threshold 交叉对比表"""
        thresholds = [0, 0.3, 0.5, 1.0]
        rows = []

        for th in thresholds:
            records = _run_smooth_threshold_backtest(prices, sma_window=3, threshold=th)
            nav = records["nav"]
            sharpe = _compute_sharpe(nav)
            mdd = _max_drawdown(nav)
            whip = _count_whipsaws_records(records)
            rows.append((th, sharpe, mdd, whip))

        print(f"\n{'=' * 70}")
        print(f"  SMA×Threshold 交叉扫描（sma=3，真实数据全量回测）")
        print(f"{'=' * 70}")
        print(f"{'threshold':>10} {'Sharpe':>10} {'最大回撤':>10} {'Whipsaw':>10}")
        print("-" * 45)
        for th, sharpe, mdd, whip in rows:
            print(f"{th:>10.1f} {sharpe:>10.3f} {mdd:>9.1%} {whip:>10}")

        print(f"\n  【与纯 sma=3 对比】threshold=0 即纯 sma=3")
        base_sharpe = rows[0][1]
        for th, sharpe, mdd, whip in rows[1:]:
            print(f"  threshold={th:.1f}: ΔSharpe={sharpe - base_sharpe:+.3f}, "
                  f"Whipsaw 比 sma=3 纯版 {'↓' if whip <= rows[0][3] else '↑'}{abs(whip - rows[0][3])}")

    def test_threshold_no_collapse(self, prices):
        """threshold=1.0 时仍保持正 Sharpe"""
        records = _run_smooth_threshold_backtest(prices, sma_window=3, threshold=1.0)
        sharpe = _compute_sharpe(records["nav"])
        assert sharpe > 0, f"threshold=1.0 sma=3 Sharpe={sharpe:.3f} <= 0"
