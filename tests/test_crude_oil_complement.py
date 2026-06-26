# [2026-06-26] 新增：原油与黄金的信号互补性分析
"""测试 C：原油与黄金的互补性。

逐年对比原油 trend_strength > 0 的天数 vs 黄金 trend_strength > 0 的天数。
判断两者能否互相补位。
"""
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.trend_strength import trend_strength

BASE = os.path.join(os.path.dirname(__file__), "..")
DATA_DIR = os.path.join(BASE, "data")

ETF_CODE_MAP = {
    "黄金": "518880", "原油": "159935",
}

TREND_WINDOW = 40

SIGNAL_START = pd.Timestamp("2014-03-20")  # 原油 + 预热窗口


def load_close(name):
    code = ETF_CODE_MAP[name]
    fpath = os.path.join(DATA_DIR, f"{code}.parquet")
    df = pd.read_parquet(fpath)
    return df["close"].dropna()


def compute_trend_signals(close_series, window=TREND_WINDOW):
    """计算每个交易日 trend_strength 是否 > 0。"""
    ts = close_series.copy()
    result = pd.Series(np.nan, index=ts.index, dtype=float)
    for i in range(window, len(ts) + 1):
        seg = ts.iloc[i - window:i]
        result.iloc[i - 1] = trend_strength(seg, window=window)
    return result


def run_analysis():
    print("=" * 70)
    print("测试 C：原油与黄金的信号互补性分析")
    print("=" * 70)

    gold_close = load_close("黄金")
    oil_close = load_close("原油")

    # 统一起始
    common_start = max(gold_close.index[0], oil_close.index[0], SIGNAL_START)
    gold_close = gold_close[gold_close.index >= common_start]
    oil_close = oil_close[oil_close.index >= common_start]

    # 共同日期交集
    common_dates = gold_close.index.intersection(oil_close.index)
    gold_close = gold_close.loc[common_dates]
    oil_close = oil_close.loc[common_dates]

    # 计算 trend_strength 信号
    gold_ts = compute_trend_signals(gold_close)
    oil_ts = compute_trend_signals(oil_close)

    # 对齐
    gold_signal = gold_ts.loc[common_dates]
    oil_signal = oil_ts.loc[common_dates]

    gold_pos = gold_signal > 0
    oil_pos = oil_signal > 0

    # --- 输出表格 ---
    print(f"\n{'年份':<8} {'金↑油↑':>10} {'金↑油↓':>10} {'金↓油↑':>10} {'金↓油↓':>10} {'互补占比':>10}")
    print("-" * 60)

    years = sorted(set(d.year for d in common_dates))
    for yr in years:
        mask = gold_signal.index.year == yr
        if mask.sum() < 20:
            continue
        g = gold_pos[mask]
        o = oil_pos[mask]
        both_up = ((g) & (o)).sum()
        gold_up_oil_down = ((g) & (~o)).sum()
        gold_down_oil_up = ((~g) & (o)).sum()
        both_down = ((~g) & (~o)).sum()
        total_obs = len(g)

        # 互补：一个 >0 一个 ≤0
        complement = gold_up_oil_down + gold_down_oil_up
        complement_pct = complement / total_obs * 100

        print(f"{yr:<8} {both_up:>10} {gold_up_oil_down:>10} {gold_down_oil_up:>10} {both_down:>10} {complement_pct:>9.1f}%")

    # 全期汇总
    total_obs = len(gold_pos)
    both_up = ((gold_pos) & (oil_pos)).sum()
    gold_up_oil_down = ((gold_pos) & (~oil_pos)).sum()
    gold_down_oil_up = ((~gold_pos) & (oil_pos)).sum()
    both_down = ((~gold_pos) & (~oil_pos)).sum()
    complement = gold_up_oil_down + gold_down_oil_up
    complement_pct = complement / total_obs * 100

    print("-" * 60)
    print(f"{'全期':<8} {both_up:>10} {gold_up_oil_down:>10} {gold_down_oil_up:>10} {both_down:>10} {complement_pct:>9.1f}%")

    # --- 重点判断 ---
    print("\n--- 重点判断 ---")
    print(f"互补占比（一个>0 一个≤0）: {complement_pct:.1f}%")
    if complement_pct > 50:
        print(f"结论：互补占比 > 50%，两者共存有价值——黄金失效时原油可补位，反之亦然。")
    elif complement_pct > 30:
        print(f"结论：存在一定互补性（{complement_pct:.1f}%），但不足以形成强对冲关系。")
    else:
        print(f"结论：互补性较弱，两者趋势方向高度一致。")
    print(f"两者同时 > 0 占比: {both_up / total_obs * 100:.1f}%")
    print(f"两者同时 ≤ 0 占比: {both_down / total_obs * 100:.1f}%")

    return {
        "gold_signal": gold_signal, "oil_signal": oil_signal,
        "complement_pct": complement_pct,
        "both_up_pct": both_up / total_obs * 100,
        "both_down_pct": both_down / total_obs * 100,
    }


if __name__ == "__main__":
    run_analysis()
