# [2026-06-12] 新增：sf 生效后的影响量化（v181 漏洞验证 3）
"""验证 sf（波动率缩放）生效后的绩效影响。

独立脚本，通过 monkey-patch allocate_capital 注入修复逻辑，
不修改任何 src/ 下的生产代码。

修复：allocate_capital 中 defense_pool *= signal["execution"]["final_multiplier"]
替代原有的 defense_pool *= signal["drawdown_stop"]["position_multiplier"]
"""
import os
import sys
from copy import deepcopy

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.portfolio_manager import allocate_capital as _original_allocate
from src.backtest_engine import run_backtest

BASE = os.path.join(os.path.dirname(__file__), "..")
DATA_DIR = os.path.join(BASE, "data")

ETF_CODE_MAP = {
    "沪深300": "510300", "创业板": "159915", "纳指": "513100",
    "黄金": "518880", "国债ETF": "511010",
}


def allocate_capital_fixed(
    signal: dict,
    total_capital: float,
    defense_ratio: float = 0.70,
) -> dict:
    """allocate_capital 修复版：使用 signal["execution"]["final_multiplier"]

    与原始版本的唯一差异：line 14-16。
    原始: dd_mult = signal["drawdown_stop"]["position_multiplier"]
          defense_pool *= dd_mult
    修复: 使用 final_multiplier（已包含 min(sf, dd_mult)），sf 生效。
    """
    defense_pool = total_capital * defense_ratio
    offense_pool = total_capital * (1 - defense_ratio)

    # === 修复点：使用 final_multiplier 替代 raw dd_mult ===
    final_mult = signal["execution"]["final_multiplier"]
    defense_pool *= final_mult
    offense_pool *= final_mult

    if signal["circuit_breaker"]["triggered"]:
        return {
            "date": signal["date"],
            "total_capital": total_capital,
            "positions": {},
            "defense_total": 0.0,
            "offense_total": 0.0,
            "repo_amount": total_capital,
            "exposure": 0.0,
            "exposure_ratio": 0.0,
        }

    positions: dict[str, float] = {}
    repo_amount = 0.0

    for name, weight in signal["defense"]["target_weights"].items():
        positions[name] = defense_pool * weight

    offense_weights = signal["offense"]["target_weights"]
    if offense_weights:
        for name, weight in offense_weights.items():
            positions[name] = offense_pool * weight
    else:
        repo_amount += offense_pool

    exposure = sum(positions.values())
    repo_amount += total_capital - exposure - repo_amount

    return {
        "date": signal["date"],
        "total_capital": total_capital,
        "positions": positions,
        "defense_total": defense_pool,
        "offense_total": offense_pool if offense_weights else 0.0,
        "repo_amount": repo_amount,
        "exposure": exposure,
        "exposure_ratio": exposure / total_capital,
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


def patch_allocate_capital(prices, fixed=False):
    """Monkey-patch backtest_engine 的 allocate_capital 引用。"""
    import src.backtest_engine as be
    if fixed:
        be.allocate_capital = allocate_capital_fixed
    else:
        be.allocate_capital = _original_allocate


def run_with_sf(prices, sf_enabled=False):
    """运行回测，sf_enabled=True 时使用修复版 allocate_capital。"""
    patch_allocate_capital(prices, fixed=sf_enabled)
    result = run_backtest(
        prices,
        initial_capital=1_000_000,
        params={"defense_ratio": 1.00},
        execution_lag=1,
    )
    # 恢复原版
    patch_allocate_capital(prices, fixed=False)
    return result


def slice_prices_by_year(prices, year):
    """截取 prices 到指定年份的数据。"""
    year_start = pd.Timestamp(f"{year}-01-01")
    year_end = pd.Timestamp(f"{year}-12-31")
    sliced = {}
    for name, df in prices.items():
        df_year = df[(df.index >= year_start) & (df.index <= year_end)]
        if len(df_year) > 0:
            sliced[name] = df_year
    return sliced


def print_metrics(label, bt):
    """打印回测绩效指标。"""
    print(f"\n  {label}:")
    print(f"    总收益: {bt['total_return'] * 100:.1f}%")
    print(f"    年化:   {bt['annual_return'] * 100:.2f}%")
    print(f"    波动率: {bt['annual_volatility'] * 100:.2f}%")
    print(f"    Sharpe: {bt['sharpe_ratio']:.3f}")
    print(f"    最大回撤: {bt['max_drawdown'] * 100:.2f}%")


def run_comparison():
    """主分析：逐段对比 sf 开启/关闭的绩效差异。"""
    print("=" * 60)
    print("验证 3：sf 生效后的影响量化")
    print("=" * 60)
    print("(T+1 执行，execution_lag=1)")

    prices = load_defense_prices()
    if len(prices) < 5:
        print("ERROR: 防御 ETF 数据不完整")
        return None

    results = {}

    # --- 全量 2014-2026 ---
    print("\n--- 全量 2014-2026 ---")
    try:
        bt_no_sf = run_with_sf(prices, sf_enabled=False)
        bt_sf = run_with_sf(prices, sf_enabled=True)
        print_metrics("当前 (sf 未生效)", bt_no_sf)
        print_metrics("修复后 (sf 生效)", bt_sf)

        delta_sharpe = bt_sf["sharpe_ratio"] - bt_no_sf["sharpe_ratio"]
        delta_return = bt_sf["total_return"] - bt_no_sf["total_return"]
        delta_dd = bt_sf["max_drawdown"] - bt_no_sf["max_drawdown"]
        print(f"\n  差异 Δ:")
        print(f"    ΔSharpe:   {delta_sharpe:+.3f}")
        print(f"    Δ总收益:   {delta_return * 100:+.1f}%")
        print(f"    Δ最大回撤: {delta_dd * 100:+.2f}%")
        results["full"] = {
            "no_sf": {k: bt_no_sf[k] for k in ["total_return", "annual_return", "annual_volatility",
                                                  "sharpe_ratio", "max_drawdown"]},
            "sf": {k: bt_sf[k] for k in ["total_return", "annual_return", "annual_volatility",
                                           "sharpe_ratio", "max_drawdown"]},
            "delta_sharpe": delta_sharpe,
            "delta_return": delta_return,
            "delta_dd": delta_dd,
        }
    except Exception as e:
        print(f"  全量回测失败: {e}")
        import traceback
        traceback.print_exc()

    # --- 逐年份 (2018, 2019, 2020) ---
    for year in [2018, 2019, 2020]:
        print(f"\n--- {year} 年 ---")
        try:
            prices_year = slice_prices_by_year(prices, year)
            if len(prices_year) < 5:
                print(f"  {year} 年数据不足，跳过")
                continue
            bt_no = run_with_sf(prices_year, sf_enabled=False)
            bt_yes = run_with_sf(prices_year, sf_enabled=True)
            print_metrics(f"当前 (sf 未生效)", bt_no)
            print_metrics(f"修复后 (sf 生效)", bt_yes)

            d_sharpe = bt_yes["sharpe_ratio"] - bt_no["sharpe_ratio"]
            d_return = bt_yes["total_return"] - bt_no["total_return"]
            d_dd = bt_yes["max_drawdown"] - bt_no["max_drawdown"]
            print(f"  ΔSharpe: {d_sharpe:+.3f}  Δ收益: {d_return * 100:+.1f}%  Δ回撤: {d_dd * 100:+.2f}%")
            results[str(year)] = {
                "no_sf": {k: bt_no[k] for k in ["total_return", "annual_return", "annual_volatility",
                                                   "sharpe_ratio", "max_drawdown"]},
                "sf": {k: bt_yes[k] for k in ["total_return", "annual_return", "annual_volatility",
                                                "sharpe_ratio", "max_drawdown"]},
            }
        except Exception as e:
            print(f"  {year} 年回测失败: {e}")

    # --- 汇总表 ---
    print("\n" + "=" * 60)
    print("汇总：sf 生效 vs 未生效 — 绩效对比")
    print("=" * 60)
    print(f"{'期间':<15} {'版本':<12} {'Sharpe':>8} {'总收益':>8} {'年化':>8} {'波动率':>8} {'回撤':>8}")
    print("-" * 70)
    for period_label, period_data in results.items():
        period_name = {"full": "2014-2026", "2018": "2018", "2019": "2019", "2020": "2020"}[period_label]
        for ver, key in [("sf 未生效", "no_sf"), ("sf 生效", "sf")]:
            if ver == "sf 未生效" and period_label != "2018":
                continue  # 只显示 2018 双版本 + 其他期间 sf 生效版本
            d = period_data[key]
            print(f"{period_name:<15} {ver:<12} {d['sharpe_ratio']:>8.3f} {d['total_return']:>7.1%} "
                  f"{d['annual_return']:>7.2%} {d['annual_volatility']:>7.2%} {d['max_drawdown']:>7.2%}")

    # 全量对比
    for ver, key in [("sf 未生效", "no_sf"), ("sf 生效", "sf")]:
        d = results["full"][key]
        print(f"{'2014-2026':<15} {ver:<12} {d['sharpe_ratio']:>8.3f} {d['total_return']:>7.1%} "
              f"{d['annual_return']:>7.2%} {d['annual_volatility']:>7.2%} {d['max_drawdown']:>7.2%}")

    print("\n结论:")
    if "full" in results:
        fd = results["full"]
        print(f"  sf 生效后: Sharpe {fd['delta_sharpe']:+.3f}, "
              f"收益 {fd['delta_return'] * 100:+.1f}%, 回撤 {fd['delta_dd'] * 100:+.2f}%")

    # 恢复原版（确保不污染后续测试）
    patch_allocate_capital(prices, fixed=False)
    return results


if __name__ == "__main__":
    results = run_comparison()
