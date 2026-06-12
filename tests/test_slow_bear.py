# [2026-06-12] 新增：慢熊场景 trend_strength 表现分析（v181 漏洞验证 2）
"""验证 trend_strength 在 2018 年慢熊场景的表现。

独立脚本，不修改任何生产代码。
分析内容：
  1. 2018 年每日各 ETF 的 trend_strength 分布
  2. 2018 年信号变化频率（与全期对比）
  3. 纳指 trend_strength 在 0 上下穿越次数
  4. 可选：trend_confirmation(method="price_ma") vs trend_strength 对比
"""
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.trend_strength import trend_strength, trend_confirmation
from src.signal_generator import DEFENSE_NAMES, generate_signal

BASE = os.path.join(os.path.dirname(__file__), "..")
DATA_DIR = os.path.join(BASE, "data")

ETF_CODE_MAP = {
    "沪深300": "510300", "创业板": "159915", "纳指": "513100",
    "黄金": "518880", "国债ETF": "511010",
}


def load_defense_prices():
    """加载 5 只防御 ETF 的 parquet 数据。"""
    prices = {}
    for name, code in ETF_CODE_MAP.items():
        fpath = os.path.join(DATA_DIR, f"{code}.parquet")
        if os.path.exists(fpath):
            df = pd.read_parquet(fpath)
            if "close" in df.columns:
                prices[name] = df
    return prices


def compute_trend_strength_series(prices_series, window=40):
    """计算滚动 trend_strength 时间序列。"""
    ts_series = pd.Series(np.nan, index=prices_series.index, dtype=float)
    for i in range(window, len(prices_series) + 1):
        window_data = prices_series.iloc[:i]
        ts_series.iloc[i - 1] = trend_strength(window_data, window=window)
    return ts_series


def count_zero_crossings(series):
    """计算时间序列穿越 0 的次数。"""
    signs = np.sign(series.dropna())
    crossings = 0
    for i in range(1, len(signs)):
        if signs.iloc[i] != 0 and signs.iloc[i - 1] != 0 and signs.iloc[i] != signs.iloc[i - 1]:
            crossings += 1
    return crossings


def compute_signal_change_frequency(signals_df):
    """计算信号变化频率：相邻日 active ETF 集合不同的天数占比。"""
    if len(signals_df) < 2:
        return 0.0, 0
    changes = 0
    for i in range(1, len(signals_df)):
        prev_active = set(signals_df.iloc[i - 1]["active"])
        curr_active = set(signals_df.iloc[i]["active"])
        if prev_active != curr_active:
            changes += 1
    return changes / (len(signals_df) - 1), changes


def analyze_2018():
    """分析 2018 年慢熊场景。"""
    print("=" * 60)
    print("验证 2：trend_strength 在 2018 慢熊场景的表现")
    print("=" * 60)

    prices = load_defense_prices()
    if len(prices) < 5:
        print("ERROR: 防御 ETF 数据不完整")
        return None

    # --- 1. 2018 年纳指 trend_strength 序列 ---
    print("\n--- 纳指 2018 年 trend_strength 序列 ---")
    nasdaq_close = prices["纳指"]["close"]
    nasdaq_2018 = nasdaq_close.loc["2017-10-01":"2018-12-31"]  # 含预热窗口
    ts_nasdaq = compute_trend_strength_series(nasdaq_2018, window=40)
    ts_2018 = ts_nasdaq.loc["2018-01-01":"2018-12-31"]

    print(f"2018 年交易日数: {len(ts_2018)}")
    print(f"trend_strength > 0 天数: {(ts_2018 > 0).sum()}")
    print(f"trend_strength <= 0 天数: {(ts_2018 <= 0).sum()}")
    print(f"trend_strength > 0 占比: {(ts_2018 > 0).sum() / len(ts_2018) * 100:.1f}%")
    print(f"trend_strength 均值: {ts_2018.mean():.4f}")
    print(f"trend_strength 中位数: {ts_2018.median():.4f}")
    print(f"trend_strength 标准差: {ts_2018.std():.4f}")
    nasdaq_crossings = count_zero_crossings(ts_2018)
    print(f"\n纳指 2018 年 0 轴穿越次数: {nasdaq_crossings}")

    # 每月统计
    print("\n纳指 2018 年逐月 trend_strength 均值:")
    for month in range(1, 13):
        mask = ts_2018.index.month == month
        if mask.sum() > 0:
            monthly_mean = ts_2018[mask].mean()
            monthly_positive_pct = (ts_2018[mask] > 0).sum() / mask.sum() * 100
            print(f"  {month:02d}月: mean={monthly_mean:+.4f}, positive={monthly_positive_pct:.0f}%")

    # --- 2. 各 ETF 2018 年 trend_strength 分布 ---
    print("\n--- 各 ETF 2018 年 trend_strength 分布 ---")
    etf_2018_stats = {}
    for name in DEFENSE_NAMES:
        if name not in prices:
            continue
        close = prices[name]["close"]
        close_2018 = close.loc["2017-10-01":"2018-12-31"]
        ts_all = compute_trend_strength_series(close_2018, window=40)
        ts_year = ts_all.loc["2018-01-01":"2018-12-31"]
        crossings = count_zero_crossings(ts_year)
        etf_2018_stats[name] = {
            "mean": ts_year.mean(),
            "median": ts_year.median(),
            "std": ts_year.std(),
            "positive_pct": (ts_year > 0).sum() / len(ts_year) * 100,
            "crossings": crossings,
        }
        print(f"  {name}: mean={ts_year.mean():+.4f}, median={ts_year.median():+.4f}, "
              f"positive={etf_2018_stats[name]['positive_pct']:.0f}%, crossings={crossings}")

    # --- 3. 信号变化频率：2018 vs 全期 ---
    print("\n--- 信号变化频率对比 ---")
    min_days = 120
    # 构建全期信号
    all_dates = sorted(set.union(*[set(df.index) for df in prices.values()]))
    all_dates = pd.DatetimeIndex(all_dates)
    defense_starts = [df.index.min() for df in prices.values()]
    all_dates = all_dates[all_dates >= max(defense_starts)]

    nav_series = pd.Series(1_000_000.0, index=all_dates, dtype=float)
    all_signals = []
    for t in range(min_days, len(all_dates)):
        today = all_dates[t]
        visible = {}
        for name, df in prices.items():
            if today in df.index and (df.index <= today).sum() >= min_days:
                visible[name] = df.loc[:today]
        try:
            sig = generate_signal(visible, nav_series.iloc[:t + 1])
            all_signals.append({
                "date": str(today.date()),
                "active": tuple(sorted(sig["defense"]["active"])),
            })
        except Exception:
            continue

    sig_df = pd.DataFrame(all_signals)
    sig_df["date"] = pd.to_datetime(sig_df["date"])

    # 全期变化频率
    full_freq, full_changes = compute_signal_change_frequency(sig_df)
    print(f"全期 ({sig_df['date'].iloc[0].date()} ~ {sig_df['date'].iloc[-1].date()}):")
    print(f"  信号变化频率: {full_freq * 100:.1f}% ({full_changes}/{len(sig_df) - 1})")

    # 2018 年变化频率
    sig_2018 = sig_df[(sig_df["date"] >= "2018-01-01") & (sig_df["date"] <= "2018-12-31")]
    if len(sig_2018) > 1:
        freq_2018, changes_2018 = compute_signal_change_frequency(sig_2018)
        print(f"2018 年: 信号变化频率: {freq_2018 * 100:.1f}% ({changes_2018}/{len(sig_2018) - 1})")
    else:
        freq_2018, changes_2018 = 0, 0
        print("2018 年: 数据不足")

    # 非 2018 年份的变化频率
    sig_non_2018 = sig_df[(sig_df["date"] < "2018-01-01") | (sig_df["date"] > "2018-12-31")]
    if len(sig_non_2018) > 1:
        freq_non, changes_non = compute_signal_change_frequency(sig_non_2018)
        print(f"非 2018 年: 信号变化频率: {freq_non * 100:.1f}% ({changes_non}/{len(sig_non_2018) - 1})")

    # --- 4. price_ma vs trend_strength 对比 (2018) ---
    print("\n--- 2018 年 trend_strength vs price_ma 对比 ---")
    print("（通过 params 覆盖 trend_confirmation_method，不修改 DEFAULT_PARAMS）")

    # 使用 price_ma 重跑 2018 年信号
    price_ma_signals = []
    for t in range(min_days, len(all_dates)):
        today = all_dates[t]
        if today.year != 2018:
            continue
        visible = {}
        for name, df in prices.items():
            if today in df.index and (df.index <= today).sum() >= min_days:
                visible[name] = df.loc[:today]
        try:
            sig = generate_signal(visible, nav_series.iloc[:t + 1],
                                  params={"trend_confirmation_method": "price_ma"})
            price_ma_signals.append({
                "date": str(today.date()),
                "active": tuple(sorted(sig["defense"]["active"])),
            })
        except Exception:
            continue

    pm_df = pd.DataFrame(price_ma_signals)
    if len(pm_df) > 1:
        freq_pm, changes_pm = compute_signal_change_frequency(pm_df)
        print(f"price_ma 方法 — 2018 年信号变化频率: {freq_pm * 100:.1f}% ({changes_pm}/{len(pm_df) - 1})")
    else:
        freq_pm, changes_pm = 0, 0
        print("price_ma: 数据不足")

    # Active ETF 平均数量对比
    sig_2018_ts = sig_df[(sig_df["date"] >= "2018-01-01") & (sig_df["date"] <= "2018-12-31")]
    avg_active_ts = sig_2018_ts["active"].apply(len).mean()
    avg_active_pm = pm_df["active"].apply(len).mean() if len(pm_df) > 0 else 0
    print(f"\n2018 年平均 active ETF 数量:")
    print(f"  trend_strength: {avg_active_ts:.1f}")
    print(f"  price_ma:       {avg_active_pm:.1f}")

    # 统计不同 active 组合的数量
    ts_combos = sig_2018_ts["active"].value_counts().head(10)
    print(f"\n2018 年 trend_strength 最常出现的 active 组合:")
    for combo, count in ts_combos.items():
        print(f"  {combo}: {count} 天")

    # --- 5. 结论 ---
    print("\n" + "=" * 60)
    print("结论：慢熊 2018 trend_strength 穿越频率")
    print("=" * 60)
    print(f"  纳指 0 轴穿越: {nasdaq_crossings} 次")
    print(f"  2018 年信号变化频率: {freq_2018 * 100:.1f}%")
    print(f"  全期信号变化频率:   {full_freq * 100:.1f}%")
    print(f"  price_ma 信号变化频率: {freq_pm * 100:.1f}%")
    print(f"  trend_strength > 0 占比: {(ts_2018 > 0).sum() / len(ts_2018) * 100:.1f}%")

    return {
        "nasdaq_crossings_2018": nasdaq_crossings,
        "signal_change_freq_2018": freq_2018,
        "signal_change_freq_full": full_freq,
        "signal_change_freq_price_ma_2018": freq_pm,
        "ts_positive_pct_2018": (ts_2018 > 0).sum() / len(ts_2018) * 100,
        "avg_active_ts_2018": avg_active_ts,
        "avg_active_pm_2018": avg_active_pm,
        "etf_2018_stats": etf_2018_stats,
    }


if __name__ == "__main__":
    result = analyze_2018()
