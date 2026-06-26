# [2026-06-26] 新增：SMA 慢熊专项测试（2018 + 2022）
"""测试 sma=3 在慢熊年份的表现（真实数据）"""

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

def _compute_sharpe_from_returns(returns: pd.Series) -> float:
    """从收益率序列计算 Sharpe。"""
    if len(returns) < 2:
        return 0.0
    ann_ret = returns.mean() * 252
    ann_vol = returns.std() * np.sqrt(252)
    return ann_ret / ann_vol if ann_vol > 0 else 0.0


def _year_metrics(nav: pd.Series, year: int) -> dict:
    """计算指定年份的绩效指标。"""
    mask = (nav.index >= f"{year}-01-01") & (nav.index <= f"{year}-12-31")
    yr_nav = nav.loc[mask]
    if len(yr_nav) < 2:
        return {"收益": np.nan, "Sharpe": np.nan, "最大回撤": np.nan}

    ret = yr_nav.iloc[-1] / yr_nav.iloc[0] - 1

    returns = yr_nav.pct_change().dropna()
    sharpe = _compute_sharpe_from_returns(returns)

    peak = yr_nav.expanding().max()
    dd = (yr_nav - peak) / peak
    max_dd = dd.min()

    return {"收益": ret, "Sharpe": sharpe, "最大回撤": max_dd}


def _year_zero_crossings(prices, year: int, sma_window=1) -> int:
    """计算指定年份内所有防御 ETF 的零轴穿越总和。"""
    from src.trend_strength import trend_strength as _ts
    from src.signal_generator import DEFENSE_NAMES

    total = 0
    for name in DEFENSE_NAMES:
        if name not in prices:
            continue
        close = prices[name]["close"]
        # 截取到指定年份末尾
        mask = close.index <= f"{year}-12-31"
        seg = close.loc[mask]
        if len(seg) < 41:
            continue

        ts_vals = {}
        for i in range(40, len(seg) + 1):
            ts_vals[seg.index[i - 1]] = _ts(seg.iloc[:i], window=40)

        ts_series = pd.Series(ts_vals)

        # 只保留该年份
        yr_mask = (ts_series.index >= f"{year}-01-01") & (ts_series.index <= f"{year}-12-31")
        yr_ts = ts_series.loc[yr_mask]

        if len(yr_ts) < 2:
            continue

        if sma_window > 1:
            yr_ts = yr_ts.rolling(sma_window, min_periods=1).mean()

        pos = yr_ts > 0
        changed = pos != pos.shift(1)
        changed.iloc[0] = False
        total += changed.sum()
    return int(total)


# ---- 回测运行器 ----

def _run_smooth_backtest(prices, sma_window=1):
    """运行带 SMA 平滑的回测。"""
    import src.signal_generator as sg
    from src.backtest_engine import run_backtest
    from src.signal_generator import DEFAULT_PARAMS, DEFENSE_NAMES
    from src.trend_strength import trend_strength as _ts

    # 预计算
    precomputed_ts = {}
    for name in DEFENSE_NAMES:
        if name not in prices:
            continue
        close = prices[name]["close"]
        ts_vals = {}
        for i in range(40, len(close) + 1):
            seg = close.iloc[:i]
            ts_vals[close.index[i - 1]] = _ts(seg, window=40)
        precomputed_ts[name] = pd.Series(ts_vals)

    signals = {}
    for name, ts_series in precomputed_ts.items():
        if sma_window <= 1:
            signals[name] = ts_series > 0
        else:
            s = ts_series.rolling(sma_window, min_periods=1).mean()
            signals[name] = s > 0

    close_cache = {
        name: prices[name]["close"]
        for name in DEFENSE_NAMES if name in prices
    }

    def _smoothed_tc(close_series, method="trend_strength", window=40):
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
        return _ts(close_series, window=window) > 0

    params = {**DEFAULT_PARAMS, "trend_confirmation_method": "trend_strength"}

    with patch.object(sg, "trend_confirmation", side_effect=_smoothed_tc):
        result = run_backtest(prices=prices, initial_capital=1_000_000,
                              params=params, min_days=120)
    return result["records_df"]["nav"]


# ---- 测试 ----

class TestSmaSlowBear:
    """SMA 慢熊专项测试"""

    @pytest.fixture(scope="class")
    def prices(self):
        return _clean_prices(load_all_prices())

    def test_slow_bear_table(self, prices):
        """输出 2018 和 2022 年对比表"""
        years = [2018, 2022]
        sma_values = [1, 3]

        all_data = {}
        for sma in sma_values:
            nav = _run_smooth_backtest(prices, sma_window=sma)
            all_data[sma] = nav

        print(f"\n{'=' * 75}")
        print(f"  慢熊专项：SMA 平滑对熊市年份的影响")
        print(f"{'=' * 75}")

        for year in years:
            print(f"\n  --- {year} 年 ---")
            print(f"  {'指标':<10} {'原版(sma=1)':<16} {'sma=3':<16}")
            print("  " + "-" * 42)

            metrics_sma1 = _year_metrics(all_data[1], year)
            metrics_sma3 = _year_metrics(all_data[3], year)

            for key in ["收益", "Sharpe", "最大回撤"]:
                v1 = metrics_sma1.get(key, np.nan)
                v3 = metrics_sma3.get(key, np.nan)
                if key == "Sharpe":
                    print(f"  {key:<10} {v1:<16.3f} {v3:<.3f}")
                else:
                    v1_str = f"{v1:.1%}" if not np.isnan(v1) else "N/A"
                    v3_str = f"{v3:.1%}" if not np.isnan(v3) else "N/A"
                    print(f"  {key:<10} {v1_str:<16} {v3_str:<16}")

            # 零轴穿越
            zc1 = _year_zero_crossings(prices, year, sma_window=1)
            zc3 = _year_zero_crossings(prices, year, sma_window=3)
            print(f"  {'零轴穿越':<10} {zc1:<16} {zc3:<16}")

        # 判断：sma=3 是否会因平滑导致回撤加深
        print(f"\n  {'=' * 55}")
        print(f"  专项判断")
        for year in years:
            m1 = _year_metrics(all_data[1], year)
            m3 = _year_metrics(all_data[3], year)
            dd_diff = m3["最大回撤"] - m1["最大回撤"] if not (np.isnan(m1["最大回撤"]) or np.isnan(m3["最大回撤"])) else 0
            if dd_diff < 0:
                print(f"  {year}年: sma=3 回撤加深 {abs(dd_diff):.1%} — 平滑导致信号延迟")
            else:
                print(f"  {year}年: sma=3 回撤未加深 (Δ={dd_diff:+.1%})")

    def test_sma3_2018_not_catastrophic(self, prices):
        """2018 年 sma=3 的最大回撤不比 sma=1 差太多（<5%）"""
        nav1 = _run_smooth_backtest(prices, sma_window=1)
        nav3 = _run_smooth_backtest(prices, sma_window=3)

        m1 = _year_metrics(nav1, 2018)
        m3 = _year_metrics(nav3, 2018)

        dd1 = m1["最大回撤"]
        dd3 = m3["最大回撤"]
        if not (np.isnan(dd1) or np.isnan(dd3)):
            # sma=3 的回撤不应比 sma=1 深超过 5%
            assert dd3 >= dd1 - 0.05, (
                f"2018 sma=3 回撤 {dd3:.1%} 比 sma=1 {dd1:.1%} 深超 5%"
            )
