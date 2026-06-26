# [2026-06-26] 新增：SMA 跨 target_vol_beta 稳定性测试
"""测试 sma=3 的效果是否在不同 beta 下一致（真实数据全量 2014-2026）"""

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


def _run_backtest_with_sma(prices, sma_window=1, beta=0.18):
    """运行带 SMA 平滑 + 指定 beta 的回测。"""
    import src.signal_generator as sg
    from src.backtest_engine import run_backtest
    from src.signal_generator import DEFAULT_PARAMS, DEFENSE_NAMES

    # 预计算 trend_strength 序列
    from src.trend_strength import trend_strength as _ts
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

    # 应用 SMA 平滑
    signals = {}
    for name, ts_series in precomputed_ts.items():
        if sma_window <= 1:
            signals[name] = ts_series > 0
        else:
            s = ts_series.rolling(sma_window, min_periods=1).mean()
            signals[name] = s > 0

    close_cache = {
        name: prices[name]["close"]
        for name in DEFENSE_NAMES
        if name in prices
    }

    def _custom_tc(close_series, method="trend_strength", window=40):
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

    params = {
        **DEFAULT_PARAMS,
        "trend_confirmation_method": "trend_strength",
        "target_vol_beta": beta,
    }

    with patch.object(sg, "trend_confirmation", side_effect=_custom_tc):
        result = run_backtest(prices=prices, initial_capital=1_000_000,
                              params=params, min_days=120)
    return result["records_df"]


# ---- 测试 ----

class TestSmaBetaStability:
    """SMA 跨 beta 稳定性测试"""

    @pytest.fixture(scope="class")
    def prices(self):
        return _clean_prices(load_all_prices())

    def test_beta_stability_table(self, prices):
        """输出不同 beta 下 sma=1 vs sma=3 对比表"""
        betas = [0.10, 0.15, 0.18]
        rows = []

        for beta in betas:
            r_orig = _run_backtest_with_sma(prices, sma_window=1, beta=beta)
            r_sma3 = _run_backtest_with_sma(prices, sma_window=3, beta=beta)

            s_orig = _compute_sharpe(r_orig["nav"])
            s_sma3 = _compute_sharpe(r_sma3["nav"])
            w_orig = _count_whipsaws_records(r_orig)
            w_sma3 = _count_whipsaws_records(r_sma3)

            s_change = (s_sma3 / s_orig - 1) if s_orig > 0 else 0
            w_change = (w_sma3 / w_orig - 1) if w_orig > 0 else 0

            rows.append((beta, s_orig, s_sma3, s_change, w_orig, w_sma3, w_change))

        print(f"\n{'=' * 100}")
        print(f"  SMA 跨 beta 稳定性测试（真实数据全量回测）")
        print(f"{'=' * 100}")
        header = (f"{'beta':>5} {'原 Sharpe':>10} {'sma=3 Sharpe':>13} "
                  f"{'Sharpe变化%':>12} {'原 Whipsaw':>10} {'sma=3 Whipsaw':>14} "
                  f"{'Whipsaw变化%':>14}")
        print(header)
        print("-" * 80)
        for beta, s_orig, s_sma3, s_chg, w_orig, w_sma3, w_chg in rows:
            print(f"{beta:>5.2f} {s_orig:>10.3f} {s_sma3:>13.3f} "
                  f"{s_chg:>11.1%} {w_orig:>10} {w_sma3:>14} "
                  f"{w_chg:>13.1%}")

        print(f"\n  判断：sma=3 效果是否跨 beta 一致？")
        s_drops = [r[3] for r in rows]
        if min(s_drops) >= -0.15:
            print(f"  >> sma=3 各 beta Sharpe 跌幅均 < 15%，效果稳定")
        else:
            print(f"  >> sma=3 在部分 beta 下 Sharpe 跌幅较大")

    def test_sma3_no_severe_degradation(self, prices):
        """sma=3 在任何 beta 下 Sharpe 不低于原版 70%"""
        for beta in [0.10, 0.15, 0.18]:
            r_orig = _run_backtest_with_sma(prices, sma_window=1, beta=beta)
            r_sma3 = _run_backtest_with_sma(prices, sma_window=3, beta=beta)
            s_orig = _compute_sharpe(r_orig["nav"])
            s_sma3 = _compute_sharpe(r_sma3["nav"])
            if s_orig > 0:
                ratio = s_sma3 / s_orig
                assert ratio >= 0.7, (
                    f"beta={beta}: sma=3/sma=1={ratio:.2%} < 70%"
                )
