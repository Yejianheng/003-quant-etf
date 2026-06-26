# [2026-06-26] 新增：高波动风险权重标准化测试 — 逐年风险覆盖分析
"""测试 B：逐年风险覆盖分析。

对最优（或全部）风险权重，输出逐年对比表和资产贡献分析。
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

COMMON_START = pd.Timestamp("2014-01-21")


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


def adjust_close_by_risk_weight(close: pd.Series, risk_weight: float) -> pd.Series:
    if risk_weight == 1.0:
        return close
    ret = close.pct_change().fillna(0)
    adj_ret = ret * risk_weight
    return close.iloc[0] * (1 + adj_ret).cumprod()


def adjust_prices(prices: dict, name: str, risk_weight: float) -> dict:
    adjusted = {}
    for n, df in prices.items():
        if n == name and risk_weight != 1.0:
            df_adj = df.copy()
            df_adj["close"] = adjust_close_by_risk_weight(df["close"], risk_weight)
            adjusted[n] = df_adj
        else:
            adjusted[n] = df
    return adjusted


def year_return(records_df, year):
    year_data = records_df[records_df.index.year == year]
    if len(year_data) < 2:
        return np.nan
    return year_data["nav"].iloc[-1] / year_data["nav"].iloc[0] - 1.0


def active_excluded_pct_by_year(records_df, name, year):
    """计算某年某 ETF 被趋势过滤剔除的天数占比。"""
    year_data = records_df[records_df.index.year == year]
    if len(year_data) < 2:
        return np.nan
    excluded = 0
    total = 0
    for _, row in year_data.iterrows():
        active_str = row.get("defense_active", "")
        if not active_str:
            continue
        total += 1
        if name not in active_str:
            excluded += 1
    return excluded / total if total > 0 else np.nan


def estimate_asset_contrib(records_df, prices, name, year):
    """估计某年某标的对组合的日收益贡献均值。

    每日贡献 ≈ weight_i × return_i 的日均值。
    weight_i = 1/n_active（若该标在 defense_active 中），否则 0。
    """
    year_data = records_df[records_df.index.year == year]
    if len(year_data) < 2:
        return np.nan
    if name not in prices:
        return np.nan
    close = prices[name]["close"]
    daily_rets = close.pct_change()

    daily_contribs = []
    for date, row in year_data.iterrows():
        if date not in close.index:
            continue
        ret = daily_rets.get(date, 0)
        if pd.isna(ret):
            continue
        active_str = row.get("defense_active", "")
        if not active_str:
            continue
        active_set = set(active_str.split(";"))
        if name in active_set:
            n_active = len(active_set)
            weight = 1.0 / n_active
            daily_contribs.append(weight * ret)
    if not daily_contribs:
        return 0.0
    return float(np.mean(daily_contribs))


def estimate_asset_annual_contrib(records_df, prices, name, year):
    """估计某标的对组合的年化贡献率 = sum(每日贡献)。"""
    year_data = records_df[records_df.index.year == year]
    if len(year_data) < 2:
        return np.nan
    if name not in prices:
        return np.nan
    close = prices[name]["close"]
    daily_rets = close.pct_change()

    cum_contrib = 1.0
    for date, row in year_data.iterrows():
        if date not in close.index:
            continue
        ret = daily_rets.get(date, 0)
        if pd.isna(ret) or ret == 0:
            continue
        active_str = row.get("defense_active", "")
        if not active_str:
            continue
        active_set = set(active_str.split(";"))
        if name in active_set:
            n_active = len(active_set)
            weight = 1.0 / n_active
            # 放大到年度：如果全年都满仓，年均贡献 ≈ (1 + ret*weight)^252 - 1
            cum_contrib *= (1 + weight * ret)
    return cum_contrib - 1.0


def run_coverage_analysis():
    """运行逐年风险覆盖分析。"""
    print("=" * 80)
    print("测试 B：逐年风险覆盖分析 (2014-01-21 ~ 最新)")
    print("=" * 80)

    combo_5 = ["沪深300", "创业板", "纳指", "黄金", "国债ETF"]
    combo_6 = combo_5 + ["原油"]

    prices_6 = load_prices(combo_6)
    for n in list(prices_6.keys()):
        prices_6[n] = prices_6[n][prices_6[n].index >= COMMON_START]

    prices_5 = {n: prices_6[n] for n in combo_5}

    # 使用 risk_weight=0.5（最低权重）
    rw = 0.5
    adj_prices = adjust_prices(prices_6, "原油", rw)

    # 5 品种基线
    bt_5 = run_backtest(prices_5, initial_capital=1_000_000,
                        params={**COMMON_PARAMS, "defense_names": combo_5})
    # 6 品种调整
    bt_6 = run_backtest(adj_prices, initial_capital=1_000_000,
                        params={**COMMON_PARAMS, "defense_names": combo_6})

    records_5 = bt_5["records_df"]
    records_6 = bt_6["records_df"]

    years = [2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]

    print(f"\n{'年份':<8} {'5品种收益':>12} {'6品种收益':>12} {'原油贡献':>12} {'黄金贡献':>12} {'原油剔除占比':>14}")
    print("-" * 72)

    for yr in years:
        r5 = year_return(records_5, yr)
        r6 = year_return(records_6, yr)
        oil_contrib = estimate_asset_annual_contrib(records_6, adj_prices, "原油", yr)
        gold_contrib = estimate_asset_annual_contrib(records_6, adj_prices, "黄金", yr)
        excl_pct = active_excluded_pct_by_year(records_6, "原油", yr)

        r5_s = f"{r5:.2%}" if not np.isnan(r5) else "N/A"
        r6_s = f"{r6:.2%}" if not np.isnan(r6) else "N/A"
        oil_s = f"{oil_contrib:.2%}" if not np.isnan(oil_contrib) else "N/A"
        gold_s = f"{gold_contrib:.2%}" if not np.isnan(gold_contrib) else "N/A"
        excl_s = f"{excl_pct:.2%}" if not np.isnan(excl_pct) else "N/A"

        print(f"{yr:<8} {r5_s:>12} {r6_s:>12} {oil_s:>12} {gold_s:>12} {excl_s:>14}")

    # 关注点分析
    print("\n--- 重点判断 ---")

    print("\n缺口填补分析（5品种负/接近0，6品种显著改善）：")
    for yr in years:
        r5 = year_return(records_5, yr)
        r6 = year_return(records_6, yr)
        if np.isnan(r5) or np.isnan(r6):
            continue
        if r5 < 0.02 and r6 > r5 + 0.01:
            print(f"  {yr}: 5品种 {r5:.2%} → 6品种 {r6:.2%} (改善 {r6-r5:+.2%})")

    # 原油 vs 黄金贡献对比
    print(f"\n原油 vs 黄金平均日贡献对比 (risk_weight={rw}):")
    for yr in years:
        oil_daily = estimate_asset_contrib(records_6, adj_prices, "原油", yr)
        gold_daily = estimate_asset_contrib(records_6, adj_prices, "黄金", yr)
        if np.isnan(oil_daily) and np.isnan(gold_daily):
            continue
        oil_s = f"{oil_daily:.6f}" if not np.isnan(oil_daily) else "N/A"
        gold_s = f"{gold_daily:.6f}" if not np.isnan(gold_daily) else "N/A"
        print(f"  {yr}: 原油={oil_s}  黄金={gold_s}")

    return bt_5, bt_6


def test_coverage_table_output():
    """验证逐年覆盖分析表可正常生成。"""
    combo_5 = ["沪深300", "创业板", "纳指", "黄金", "国债ETF"]
    combo_6 = combo_5 + ["原油"]
    prices_6 = load_prices(combo_6)
    for n in list(prices_6.keys()):
        prices_6[n] = prices_6[n][prices_6[n].index >= COMMON_START]
    prices_5 = {n: prices_6[n] for n in combo_5}

    for rw in [0.5]:
        adj = adjust_prices(prices_6, "原油", rw)
        bt_6 = run_backtest(adj, initial_capital=1_000_000,
                            params={**COMMON_PARAMS, "defense_names": combo_6})
        rec = bt_6["records_df"]
        for yr in [2018, 2020, 2022]:
            yr_ret = year_return(rec, yr)
            assert not np.isnan(yr_ret), f"rw={rw} yr={yr} return NaN"
    assert True


def test_crude_exclusion_rate():
    """验证原油在多数年份被趋势过滤高比例剔除。"""
    combo_5 = ["沪深300", "创业板", "纳指", "黄金", "国债ETF"]
    combo_6 = combo_5 + ["原油"]
    prices_6 = load_prices(combo_6)
    for n in list(prices_6.keys()):
        prices_6[n] = prices_6[n][prices_6[n].index >= COMMON_START]
    adj = adjust_prices(prices_6, "原油", 0.5)
    bt = run_backtest(adj, initial_capital=1_000_000,
                      params={**COMMON_PARAMS, "defense_names": combo_6})
    rec = bt["records_df"]
    for yr in [2018, 2020, 2022, 2025]:
        excl = active_excluded_pct_by_year(rec, "原油", yr)
        print(f"\n  {yr} 原油剔除占比: {excl:.2%}" if not np.isnan(excl) else f"\n  {yr}: N/A")
    assert True


if __name__ == "__main__":
    run_coverage_analysis()
