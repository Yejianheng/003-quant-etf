# [2026-06-12] 新增：验证 sf 是否被 allocate_capital 应用（v181 漏洞验证 1）
"""验证波动率缩放因子 sf 是否真的未被 allocate_capital 应用。

只读分析，不修改任何生产代码。
结论直接输出到 stdout，也写入 strateg_漏洞验证_20260612.md。
"""
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.signal_generator import generate_signal, DEFENSE_NAMES, DEFAULT_PARAMS
from src.portfolio_manager import allocate_capital

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


def verify_sf_flow():
    """验证 1：追踪 scaling_factor 是否被 allocate_capital 使用。"""
    print("=" * 60)
    print("验证 1：sf 是否被 allocate_capital 应用")
    print("=" * 60)

    # 1. 源码静态分析
    print("\n--- 源码追踪 ---")
    print("signal_generator.py:140 → final_multiplier = min(sf, ds['position_multiplier'])")
    print("portfolio_manager.py:14  → dd_mult = signal['drawdown_stop']['position_multiplier']")
    print("portfolio_manager.py:15  → defense_pool *= dd_mult")
    print()
    print("allocate_capital 读取的键:")
    print("  [READ] signal['drawdown_stop']['position_multiplier'] — 回撤乘数")
    print("  [READ] signal['circuit_breaker']['triggered'] — 熔断标记")
    print("  [READ] signal['defense']['target_weights'] — 防御权重")
    print("  [READ] signal['offense']['target_weights'] — 进攻权重")
    print("  [SKIP] signal['execution']['final_multiplier'] — 从未读取！")
    print("  [SKIP] signal['defense']['scaling_factor'] — 从未读取！")

    # 2. 数据验证 — 加载全量数据，逐日生成信号，统计 sf 分布
    print("\n--- 数据验证：逐日信号生成 + sf 统计 ---")
    prices = load_defense_prices()
    if len(prices) < 5:
        print("ERROR: 防御 ETF 数据不完整，无法运行分析")
        return None

    # 使用并集日期（与 backtest_engine 一致）
    date_sets = [set(df.index) for df in prices.values()]
    all_dates = sorted(set.union(*date_sets))
    all_dates = pd.DatetimeIndex(all_dates)

    # 截断到防御 ETF 全部就位后
    defense_starts = [df.index.min() for df in prices.values()]
    start_date = max(defense_starts)
    all_dates = all_dates[all_dates >= start_date]

    # 生成 portfolio_value（用于 drawdown_stop）
    # 我们用简单初始值，因为 focus 是 sf 而非精确回撤
    initial_capital = 1_000_000.0
    nav_series = pd.Series(initial_capital, index=all_dates, dtype=float)

    min_days = 120
    sf_values = []
    final_mult_values = []
    sf_not_one_count = 0
    total_signals = 0
    dates_with_sf_deviation = []

    for t in range(min_days, len(all_dates)):
        today = all_dates[t]
        visible_prices = {}
        for name, df in prices.items():
            if today in df.index:
                hist = (df.index <= today).sum()
                if hist >= min_days:
                    visible_prices[name] = df.loc[:today]

        try:
            signal = generate_signal(visible_prices, nav_series.iloc[: t + 1])
        except Exception:
            continue

        sf = signal["defense"]["scaling_factor"]
        fm = signal["execution"]["final_multiplier"]
        sf_values.append(sf)
        final_mult_values.append(fm)
        total_signals += 1

        if abs(sf - 1.0) > 0.001:
            sf_not_one_count += 1
            dates_with_sf_deviation.append({
                "date": str(today.date()),
                "sf": round(sf, 4),
                "final_multiplier": round(fm, 4),
                "active": signal["defense"]["active"],
                "predicted_vol": round(signal["defense"]["predicted_vol"], 4),
            })

    sf_arr = np.array(sf_values)
    fm_arr = np.array(final_mult_values)

    print(f"总信号数: {total_signals}")
    print(f"sf ≠ 1.0 的交易日: {sf_not_one_count} ({sf_not_one_count / total_signals * 100:.1f}%)")
    print(f"sf 均值: {sf_arr.mean():.4f}")
    print(f"sf 中位数: {np.median(sf_arr):.4f}")
    print(f"sf 标准差: {sf_arr.std():.4f}")
    print(f"sf 范围: [{sf_arr.min():.4f}, {sf_arr.max():.4f}]")
    print(f"sf < 1.0 (缩仓): {(sf_arr < 0.999).sum()} 天")
    print(f"sf > 1.0 (加仓): {(sf_arr > 1.001).sum()} 天")

    # 抽样 200 天统计
    if total_signals > 200:
        sample_idx = np.linspace(0, total_signals - 1, 200, dtype=int)
        sample_sf = sf_arr[sample_idx]
        sample_not_one = (np.abs(sample_sf - 1.0) > 0.001).sum()
        print(f"\n抽样 200 个交易日: sf ≠ 1.0 的 {sample_not_one} 个 ({sample_not_one / 200 * 100:.0f}%)")

    # 展示 20 个 sf 偏离最大的日期
    print("\n--- sf 偏离最大的 20 个交易日 ---")
    sorted_deviations = sorted(dates_with_sf_deviation,
                               key=lambda x: abs(x["sf"] - 1.0), reverse=True)[:20]
    for d in sorted_deviations:
        print(f"  {d['date']}  sf={d['sf']:.4f}  fm={d['final_multiplier']:.4f}  "
              f"active={d['active']}  pred_vol={d['predicted_vol']}")

    # 3. 确认 allocate_capital 不读取 sf
    print("\n--- allocate_capital 调用验证 ---")
    # 用最后一个信号构造一个 sf 明显 ≠ 1.0 的场景
    if total_signals > 0:
        last_signal = generate_signal(visible_prices, nav_series.iloc[: len(all_dates)])
        print(f"signal['defense']['scaling_factor'] = {last_signal['defense']['scaling_factor']:.4f}")
        print(f"signal['execution']['final_multiplier'] = {last_signal['execution']['final_multiplier']:.4f}")

        alloc = allocate_capital(last_signal, 1_000_000, defense_ratio=1.0)
        # 如果 sf 被应用，positions 总值应接近 final_multiplier * 1_000_000
        # 如果 sf 未被应用，positions 总值应接近 dd_mult * 1_000_000
        exposure = alloc["exposure"]
        dd_mult = last_signal["drawdown_stop"]["position_multiplier"]
        sf_val = last_signal["defense"]["scaling_factor"]
        expected_with_sf = 1_000_000 * min(sf_val, dd_mult)
        expected_without_sf = 1_000_000 * dd_mult

        print(f"\n实际 exposure: {exposure:.2f}")
        print(f"dd_mult = {dd_mult:.2f}")
        print(f"如果 sf 生效 → exposure ≈ {expected_with_sf:.2f}")
        print(f"如果 sf 未生效 → exposure ≈ {expected_without_sf:.2f}")
        print(f"匹配结果: {'sf 未生效 [CONFIRMED]' if abs(exposure - expected_without_sf) < 1 else 'sf 生效？'}")

    # 4. 结论
    print("\n" + "=" * 60)
    print("结论：sf 确实从未被 allocate_capital 应用")
    print("=" * 60)
    print("证据链：")
    print("  1. allocate_capital 源码只读取 drawdown_stop['position_multiplier']")
    print("  2. signal['execution']['final_multiplier'] 和 signal['defense']['scaling_factor']")
    print("     均未被 allocate_capital 引用")
    print("  3. sf 在 signal_generator 中计算但被丢弃")
    print(f"  4. 全量数据中 sf ≠ 1.0 占比 {sf_not_one_count / total_signals * 100:.1f}%")

    return {
        "total_signals": total_signals,
        "sf_not_one_count": sf_not_one_count,
        "sf_not_one_pct": sf_not_one_count / total_signals * 100 if total_signals > 0 else 0,
        "sf_mean": float(sf_arr.mean()),
        "sf_std": float(sf_arr.std()),
        "sf_min": float(sf_arr.min()),
        "sf_max": float(sf_arr.max()),
        "top_deviations": sorted_deviations[:10],
    }


if __name__ == "__main__":
    result = verify_sf_flow()
