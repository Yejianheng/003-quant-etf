# [2026-06-26] 新增：加入原油 6 品种对比测试
"""测试 B：加入原油（6 品种）。

组合 A（当前 5）：沪深300 + 创业板 + 纳指 + 黄金 + 国债ETF
组合 B（6 品种）：沪深300 + 创业板 + 纳指 + 黄金 + 国债ETF + 原油
"""
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.backtest_engine import run_backtest
from src.benchmark import compute_benchmark, compute_single_benchmark

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


def compute_benchmark_navs(prices, combo_a_names, combo_b_names):
    """计算三基准净值."""
    # 沪深300、创业板、纳指买入持有
    bm_300 = compute_single_benchmark(prices, "沪深300")
    bm_chinext = compute_single_benchmark(prices, "创业板")
    bm_nasdaq = compute_single_benchmark(prices, "纳指")

    def metric(nav_series):
        if nav_series is None or len(nav_series) < 2:
            return {"总收益": np.nan, "年化": np.nan, "波动率": np.nan, "Sharpe": np.nan, "最大回撤": np.nan}
        total = nav_series.iloc[-1] - 1.0
        n = len(nav_series)
        annual_ret = nav_series.iloc[-1] ** (252 / n) - 1.0 if n >= 2 else np.nan
        daily_ret = nav_series.pct_change().dropna()
        vol = daily_ret.std() * np.sqrt(252) if len(daily_ret) > 0 else np.nan
        sharpe = annual_ret / vol if vol and vol > 0 else np.nan
        running_max = nav_series.cummax()
        dd = (nav_series - running_max) / running_max
        mdd = dd.min() if len(dd) > 0 else np.nan
        return {"总收益": total, "年化": annual_ret, "波动率": vol, "Sharpe": sharpe, "最大回撤": mdd}

    return {
        "沪深300": metric(bm_300),
        "创业板": metric(bm_chinext),
        "纳指": metric(bm_nasdaq),
    }


def active_excluded_pct(records_df, name):
    """计算某 ETF 被趋势过滤剔除的天数占比。"""
    if len(records_df) < 2:
        return np.nan
    excluded = 0
    total = 0
    for _, row in records_df.iterrows():
        active_str = row.get("defense_active", "")
        if not active_str:
            continue
        active_set = set(active_str.split(";"))
        total += 1
        if name not in active_set:
            excluded += 1
    return excluded / total if total > 0 else np.nan


def run_comparison():
    print("=" * 70)
    print("测试 B：加入原油（6 品种）对比 (2014-01-21 ~ 2026-06-25)")
    print("=" * 70)

    combo_a_names = ["沪深300", "创业板", "纳指", "黄金", "国债ETF"]
    combo_b_names = ["沪深300", "创业板", "纳指", "黄金", "国债ETF", "原油"]

    prices_a = load_prices(combo_a_names)
    prices_b = load_prices(combo_b_names)

    # 统一起始日期
    common_start = pd.Timestamp("2014-01-21")
    for name in combo_a_names:
        prices_a[name] = prices_a[name][prices_a[name].index >= common_start]
    for name in combo_b_names:
        prices_b[name] = prices_b[name][prices_b[name].index >= common_start]

    # 组合 A（5 品种）
    params_a = {**COMMON_PARAMS, "defense_names": combo_a_names}
    bt_a = run_backtest(prices_a, initial_capital=1_000_000, params=params_a)
    records_a = bt_a["records_df"]

    # 组合 B（6 品种）
    params_b = {**COMMON_PARAMS, "defense_names": combo_b_names}
    bt_b = run_backtest(prices_b, initial_capital=1_000_000, params=params_b)
    records_b = bt_b["records_df"]

    # 基准指标
    benchmarks = compute_benchmark_navs(prices_a, combo_a_names, combo_b_names)

    # --- 输出表格 ---
    print(f"\n{'指标':<15} {'组合A(5品种)':>14} {'组合B(6品种)':>14} {'沪深300':>12} {'创业板':>12} {'纳指':>12}")
    print("-" * 81)

    def fmt_benchmark(bm_dict, label):
        m = {"年化收益": "年化", "Sharpe": "Sharpe", "最大回撤": "最大回撤", "年化波动率": "波动率"}
        bm_label = m.get(label, label)
        return bm_dict.get(bm_label, np.nan)

    rows = [
        ("年化收益", bt_a["annual_return"], bt_b["annual_return"]),
        ("年化波动率", bt_a["annual_volatility"], bt_b["annual_volatility"]),
        ("Sharpe", bt_a["sharpe_ratio"], bt_b["sharpe_ratio"]),
        ("最大回撤", bt_a["max_drawdown"], bt_b["max_drawdown"]),
    ]
    for label, va, vb in rows:
        bm300 = fmt_benchmark(benchmarks["沪深300"], label)
        bm_cx = fmt_benchmark(benchmarks["创业板"], label)
        bm_nq = fmt_benchmark(benchmarks["纳指"], label)
        print(f"{label:<15} {va:>14.4f} {vb:>14.4f} {bm300:>12.4f} {bm_cx:>12.4f} {bm_nq:>12.4f}")

    # 分年收益
    print(f"\n{'年份':<10} {'组合A(5)':>14} {'组合B(6)':>14}")
    print("-" * 40)
    for yr in [2015, 2018, 2020, 2022, 2025]:
        # 如果 2015, 用 H2
        ra = year_return(records_a, yr)
        rb = year_return(records_b, yr)
        print(f"{yr:<10} {ra:>14.2%} {rb:>14.2%}")

    # 熔断触发天数
    cb_a = count_cb_triggers(records_a)
    cb_b = count_cb_triggers(records_b)
    print(f"\n{'熔断触发天数':<15} {cb_a:>14} {cb_b:>14}")

    # 原油被趋势过滤剔除天数占比
    oil_excluded_pct = active_excluded_pct(records_b, "原油")
    print(f"\n原油被趋势过滤剔除天数占比: {oil_excluded_pct:.2%}")
    print(f"  （占比越高，说明趋势过滤对原油越有效剔除弱市期）")

    # --- 重点判断 ---
    print("\n--- 重点判断 ---")

    # 是否有年份 5 品种全负而原油正收益
    print(f"各年份收益对比——缺口填补分析：")
    for yr in [2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]:
        ra = year_return(records_a, yr)
        rb = year_return(records_b, yr)
        combo_5_neg = ra < 0 if not np.isnan(ra) else False
        combo_6_pos = rb > 0 if not np.isnan(rb) else False
        gap = combo_5_neg and combo_6_pos
        marker = " *** 缺口填补！" if gap else ""
        if not np.isnan(ra) and not np.isnan(rb):
            print(f"  {yr}: 5品种={ra:.2%}  6品种={rb:.2%}{marker}")

    # 最大回撤
    print(f"\n全量最大回撤：")
    print(f"  5 品种: {bt_a['max_drawdown']:.2%}")
    print(f"  6 品种: {bt_b['max_drawdown']:.2%}")
    dd_change = bt_b["max_drawdown"] - bt_a["max_drawdown"]
    if dd_change >= 0:
        print(f"  加入原油后回撤改善: {dd_change:+.2%}")
    else:
        print(f"  加入原油后回撤恶化: {dd_change:+.2%}")

    return {"bt_a": bt_a, "bt_b": bt_b}


if __name__ == "__main__":
    run_comparison()
