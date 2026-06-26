# [2026-06-26] 新增：SMA 参数细化扫描（2/3/4/5/7/10）
"""测试 SMA 平滑参数对回测绩效的影响（真实数据全量 2014-2026）"""

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


def _count_zero_crossings(ts_series: pd.Series) -> int:
    """统计趋势信号过零轴次数（相邻两日方向不同的次数）。"""
    if len(ts_series) < 2:
        return 0
    pos = ts_series > 0
    changed = pos != pos.shift(1)
    changed.iloc[0] = False
    return int(changed.sum())


def _estimate_annual_turnover(records: pd.DataFrame) -> float:
    """估算年化换手率。计算 defense_active 的变化频率 / 年数。"""
    if len(records) < 2:
        return 0.0
    da_col = records["defense_active"].fillna("").astype(str)
    changed = da_col != da_col.shift(1)
    changed.iloc[0] = False
    total_changes = changed.sum()
    n_years = len(records) / 252
    return total_changes / n_years if n_years > 0 else 0.0


# ---- 预计算 trend_strength 序列 ----

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


def _compute_zero_crossings_all(prices):
    """计算所有防御 ETF 的零轴穿越次数总和（用于 sma 参数扫描）。"""
    pre = _precompute_ts(prices, window=40)
    return {name: _count_zero_crossings(ts) for name, ts in pre.items()}


def _run_smooth_backtest(prices, sma_window=1):
    """运行带 SMA 平滑的回测。"""
    import src.signal_generator as sg
    from src.backtest_engine import run_backtest
    from src.signal_generator import DEFAULT_PARAMS, DEFENSE_NAMES

    precomputed_ts = _precompute_ts(prices, window=40)

    smoothed = {}
    for name, ts_series in precomputed_ts.items():
        if sma_window <= 1:
            smoothed[name] = ts_series > 0
        else:
            s = ts_series.rolling(sma_window, min_periods=1).mean()
            smoothed[name] = s > 0

    close_cache = {
        name: prices[name]["close"]
        for name in DEFENSE_NAMES
        if name in prices
    }

    def _smoothed_trend_confirmation(close_series, method="trend_strength", window=40):
        if method != "trend_strength":
            from src.trend_strength import trend_confirmation as _orig
            return _orig(close_series, method=method, window=window)

        last_date = close_series.index[-1]
        last_val = close_series.iloc[-1]

        for etf_name, full_close in close_cache.items():
            if last_date in full_close.index:
                if abs(full_close.loc[last_date] - last_val) / max(abs(last_val), 1e-8) < 1e-6:
                    sig = smoothed.get(etf_name)
                    if sig is not None and last_date in sig.index:
                        return bool(sig.loc[last_date])
                    break

        from src.trend_strength import trend_strength as _ts
        return _ts(close_series, window=window) > 0

    params = {**DEFAULT_PARAMS, "trend_confirmation_method": "trend_strength"}

    with patch.object(sg, "trend_confirmation", side_effect=_smoothed_trend_confirmation):
        result = run_backtest(prices=prices, initial_capital=1_000_000,
                              params=params, min_days=120)
    return result["records_df"]


# ---- 测试 ----

class TestSmaParamScan:
    """SMA 参数细化扫描"""

    @pytest.fixture(scope="class")
    def prices(self):
        return _clean_prices(load_all_prices())

    def test_sma_param_scan_table(self, prices):
        """输出 sma 参数细化扫描对比表"""
        sma_values = [1, 2, 3, 4, 5, 7, 10]
        rows = []

        for sma in sma_values:
            records = _run_smooth_backtest(prices, sma_window=sma)
            nav = records["nav"]
            sharpe = _compute_sharpe(nav)
            mdd = _max_drawdown(nav)
            whip = _count_whipsaws_records(records)

            # 零轴穿越：所有 defense ETF 的零轴穿越次数总和（使用 precomputed_ts）
            pre = _precompute_ts(prices, window=40)
            total_zc = 0
            if sma <= 1:
                for ts in pre.values():
                    total_zc += _count_zero_crossings(ts > 0)
            else:
                for ts in pre.values():
                    smoothed_ts = ts.rolling(sma, min_periods=1).mean()
                    total_zc += _count_zero_crossings(smoothed_ts > 0)

            annual_to = _estimate_annual_turnover(records)

            rows.append((sma, sharpe, mdd, whip, total_zc, annual_to))

        print(f"\n{'=' * 90}")
        print(f"  SMA 参数细化扫描对比（真实数据全量回测 2014-2026）")
        print(f"{'=' * 90}")
        print(f"{'sma':>5} {'Sharpe':>9} {'最大回撤':>10} {'Whipsaw':>8} {'零轴穿越':>10} {'年化换手':>10}")
        print("-" * 55)
        for sma, sharpe, mdd, whip, zc, to in rows:
            print(f"{sma:>5} {sharpe:>9.3f} {mdd:>9.1%} {whip:>8} {zc:>10} {to:>10.1f}")

        # 边际换率分析
        print(f"\n{'─' * 55}")
        print(f"  边际换率分析（每增加 1 sma 的变化）")
        print(f"{'─' * 55}")
        for i in range(1, len(rows)):
            prev = rows[i - 1]
            curr = rows[i]
            ds = curr[1] - prev[1]  # Sharpe 变化
            dw = prev[3] - curr[3]  # Whipsaw 减少
            step = f"sma={prev[0]}→{curr[0]}"
            print(f"  {step:>12}: ΔSharpe={ds:+.3f}, Whipsaw-{dw}")

    def test_sma_3_sharpe_not_collapsed(self, prices):
        """sma=3 的 Sharpe 不低于 sma=1 的 70%"""
        r1 = _run_smooth_backtest(prices, sma_window=1)
        r3 = _run_smooth_backtest(prices, sma_window=3)
        s1 = _compute_sharpe(r1["nav"])
        s3 = _compute_sharpe(r3["nav"])
        if s1 > 0:
            ratio = s3 / s1
            assert ratio >= 0.7, f"sma=3/sma=1={ratio:.2%} < 70%"
