# [2026-06-26] 修改：从 synthetic 改为真实数据全量回测
# [2026-06-26] 新增：趋势信号 SMA 平滑效果验证测试
"""测试 trend_strength SMA 平滑对零轴穿越和绩效的影响（真实数据）"""

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


# ---- 预计算 trend_strength 序列 ----

def _precompute_ts(prices_dict: dict, window=40):
    """对 defense 层每只 ETF 预计算 trend_strength 日序列。"""
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


# ---- 带 SMA 平滑的回测运行器 ----

def _run_smooth_backtest(prices, sma_window=1):
    """运行带 SMA 平滑的回测。

    不 patch trend_confirmation，而是替换 signal_generator.generate_signal
    用自定义版本，在 trend 过滤步骤使用预计算+平滑的信号。
    """
    import src.signal_generator as sg
    from src.backtest_engine import run_backtest
    from src.signal_generator import DEFAULT_PARAMS, DEFENSE_NAMES

    # 1. 预计算 trend_strength 信号
    precomputed_ts = _precompute_ts(prices, window=40)

    # 2. 应用 SMA 平滑
    smoothed = {}
    for name, ts_series in precomputed_ts.items():
        if sma_window <= 1:
            smoothed[name] = ts_series > 0
        else:
            s = ts_series.rolling(sma_window, min_periods=1).mean()
            smoothed[name] = s > 0

    # 3. 缓存每个 ETF 的完整 close Series（用于查找）
    close_cache = {
        name: prices[name]["close"]
        for name in DEFENSE_NAMES
        if name in prices
    }

    def _smoothed_trend_confirmation(close_series, method="trend_strength", window=40):
        """通过数据匹配确定 ETF，查找平滑信号。"""
        if method != "trend_strength":
            from src.trend_strength import trend_confirmation as _orig
            return _orig(close_series, method=method, window=window)

        last_date = close_series.index[-1]
        last_val = close_series.iloc[-1]

        # 匹配 ETF：对比最后一日收盘价
        for etf_name, full_close in close_cache.items():
            if last_date in full_close.index:
                if abs(full_close.loc[last_date] - last_val) / max(abs(last_val), 1e-8) < 1e-6:
                    sig = smoothed.get(etf_name)
                    if sig is not None and last_date in sig.index:
                        return bool(sig.loc[last_date])
                    break

        # fallback
        from src.trend_strength import trend_strength as _ts
        return _ts(close_series, window=window) > 0

    params = {**DEFAULT_PARAMS, "trend_confirmation_method": "trend_strength"}

    with patch.object(sg, "trend_confirmation", side_effect=_smoothed_trend_confirmation):
        result = run_backtest(prices=prices, initial_capital=1_000_000,
                              params=params, min_days=120)
    return result["records_df"]


# ---- 测试 ----

class TestTrendSmoothingReal:
    """趋势信号 SMA 平滑效果验证（真实数据全量回测）"""

    @pytest.fixture(scope="class")
    def prices(self):
        return _clean_prices(load_all_prices())

    def test_sma_comparison_table(self, prices):
        """输出 SMA 平滑对比表（sma=1, 3, 5）"""
        rows = []
        for sma in [1, 3, 5]:
            records = _run_smooth_backtest(prices, sma_window=sma)
            nav = records["nav"]
            sharpe = _compute_sharpe(nav)
            mdd = _max_drawdown(nav)
            whip = _count_whipsaws_records(records)
            rows.append((sma, sharpe, mdd, whip))

        print(f"\n{'=' * 70}")
        print(f"  SMA 平滑效果对比（真实数据全量回测）")
        print(f"{'=' * 70}")
        print(f"{'sma':>5} {'Sharpe':>10} {'最大回撤':>10} {'Whipsaw':>10}")
        print("-" * 40)
        for sma, sharpe, mdd, whip in rows:
            print(f"{sma:>5} {sharpe:>10.3f} {mdd:>9.1%} {whip:>10}")

        # sma=3 Sharpe 不低于 sma=1 的 80%
        s1 = rows[0][1]
        s3 = rows[1][1]
        if s1 > 0:
            ratio = s3 / s1
            print(f"\n  比率 sma=3/sma=1: {ratio:.2%}")
            assert ratio >= 0.8, (
                f"sma=3 Sharpe {s3:.3f} < 80% × sma=1 {s1:.3f}"
            )

    def test_smoothing_does_not_collapse(self, prices):
        """sma=5 仍保持正 Sharpe"""
        records = _run_smooth_backtest(prices, sma_window=5)
        sharpe = _compute_sharpe(records["nav"])
        assert sharpe > 0, f"sma=5 Sharpe={sharpe:.3f} <= 0"
