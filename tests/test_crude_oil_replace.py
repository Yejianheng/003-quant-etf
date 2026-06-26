# [2026-06-26] 新增：原油替换黄金 5 品种对比测试
"""测试 A：原油替换黄金。

组合 A（当前）：沪深300 + 创业板 + 纳指 + 黄金 + 国债ETF
组合 B（替换）：沪深300 + 创业板 + 纳指 + 原油 + 国债ETF
"""
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.backtest_engine import run_backtest

BASE = os.path.join(os.path.dirname(__file__), "..")
DATA_DIR = os.path.join(BASE, "data")

ETF_CODE_MAP = {
    "沪深300": "510300", "创业板": "159915", "纳指": "513100",
    "黄金": "518880", "国债ETF": "511010", "原油": "159935",
}

COMMON_PARAMS = {
    "repo_rate": 0.02,
    "defense_ratio": 1.00,
    "trend_window": 40,
    "target_vol_beta": 0.18,
    "vol_tolerance": 0.027,
    "ewma_lambda": 0.94,
    "corr_window": 60,
    "corr_sma_window": 5,
    "corr_threshold": 0.0,
    "stock_basket_names": ["沪深300", "创业板", "纳指"],
    "bond_name": "国债ETF",
}


def load_prices(names):
    prices = {}
    for name in names:
        code = ETF_CODE_MAP[name]
        fpath = os.path.join(DATA_DIR, f"{code}.parquet")
        if os.path.exists(fpath):
            df = pd.read_parquet(fpath)
            if "close" in df.columns:
                prices[name] = df
    return prices


def year_return(records_df, year):
    year_data = records_df[records_df.index.year == year]
    if len(year_data) < 2:
        return np.nan
    return year_data["nav"].iloc[-1] / year_data["nav"].iloc[0] - 1.0


def count_cb_triggers(records_df):
    return records_df["circuit_breaker_triggered"].sum()


def run_comparison():
    print("=" * 70)
    print("测试 A：原油替换黄金 — 5 品种对比 (2014-01-21 ~ 2026-06-25)")
    print("=" * 70)

    combo_a_names = ["沪深300", "创业板", "纳指", "黄金", "国债ETF"]
    combo_b_names = ["沪深300", "创业板", "纳指", "原油", "国债ETF"]

    prices_a = load_prices(combo_a_names)
    prices_b = load_prices(combo_b_names)

    # 统一起始日期：原油有数据日（2014-01-21）
    common_start = pd.Timestamp("2014-01-21")
    for name in combo_a_names:
        prices_a[name] = prices_a[name][prices_a[name].index >= common_start]
    for name in combo_b_names:
        prices_b[name] = prices_b[name][prices_b[name].index >= common_start]

    # 组合 A
    params_a = {**COMMON_PARAMS, "defense_names": combo_a_names}
    bt_a = run_backtest(prices_a, initial_capital=1_000_000, params=params_a)
    records_a = bt_a["records_df"]

    # 组合 B
    params_b = {**COMMON_PARAMS, "defense_names": combo_b_names}
    bt_b = run_backtest(prices_b, initial_capital=1_000_000, params=params_b)
    records_b = bt_b["records_df"]

    # --- 输出表格 ---
    print(f"\n{'指标':<15} {'组合A(黄金)':>15} {'组合B(原油)':>15}")
    print("-" * 47)
    rows = [
        ("年化收益", bt_a["annual_return"], bt_b["annual_return"]),
        ("年化波动率", bt_a["annual_volatility"], bt_b["annual_volatility"]),
        ("Sharpe", bt_a["sharpe_ratio"], bt_b["sharpe_ratio"]),
        ("最大回撤", bt_a["max_drawdown"], bt_b["max_drawdown"]),
    ]
    for label, va, vb in rows:
        print(f"{label:<15} {va:>15.4f} {vb:>15.4f}")

    # 分年收益
    print(f"\n{'年份':<8} {'组合A(黄金)':>15} {'组合B(原油)':>15}")
    print("-" * 41)
    for yr in [2018, 2020, 2022, 2025]:
        ra = year_return(records_a, yr)
        rb = year_return(records_b, yr)
        print(f"{yr:<8} {ra:>15.2%} {rb:>15.2%}")

    # 熔断触发天数
    cb_a = count_cb_triggers(records_a)
    cb_b = count_cb_triggers(records_b)
    print(f"\n{'熔断触发天数':<15} {cb_a:>15} {cb_b:>15}")

    # --- 重点判断 ---
    print("\n--- 重点判断 ---")

    r2022_a = year_return(records_a, 2022)
    r2022_b = year_return(records_b, 2022)
    print(f"2022 年（股债双杀）：")
    print(f"  组合 A（黄金）: {r2022_a:.2%}")
    print(f"  组合 B（原油）: {r2022_b:.2%}")
    delta_2022 = r2022_b - r2022_a
    if delta_2022 > 0:
        print(f"  结论：原油提供额外正收益（+{delta_2022:.2%} vs 黄金）")
    else:
        print(f"  结论：原油未提供额外保护（{delta_2022:+.2%} vs 黄金）")

    r2025_a = year_return(records_a, 2025)
    r2025_b = year_return(records_b, 2025)
    print(f"\n2025 年（金涨油跌）：")
    print(f"  组合 A（黄金）: {r2025_a:.2%}")
    print(f"  组合 B（原油）: {r2025_b:.2%}")
    print(f"  替换原油后收益变化: {r2025_b-r2025_a:+.2%}")

    dd_a = bt_a["max_drawdown"]
    dd_b = bt_b["max_drawdown"]
    print(f"\n全量最大回撤：")
    print(f"  组合 A: {dd_a:.2%}")
    print(f"  组合 B: {dd_b:.2%}")
    if dd_b >= dd_a:
        print(f"  替换后回撤改善（回撤更小）: {dd_b-dd_a:+.2%}")
    else:
        print(f"  替换后回撤恶化（回撤更大）: {dd_b-dd_a:+.2%}")

    return {"bt_a": bt_a, "bt_b": bt_b}


if __name__ == "__main__":
    run_comparison()
