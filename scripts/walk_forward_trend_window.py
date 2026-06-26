# [2026-06-26] 新增：Walk-forward trend_window 滚动验证脚本
"""逐年滚动：训练窗 4 年扫描 trend_window，测试窗 1 年验证"""

import sys
import os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.backtest_engine import run_backtest
from src.signal_generator import DEFAULT_PARAMS, DEFENSE_NAMES

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
DEFENSE_MAP = {
    "沪深300": "510300", "创业板": "159915", "纳指": "513100",
    "黄金": "518880", "国债ETF": "511010",
}

TREND_WINDOWS = [20, 30, 40, 50, 60, 80, 120]
TRAIN_YEARS = 4
TEST_YEARS = 1
MIN_DAYS = 120


def load_prices() -> dict[str, pd.DataFrame]:
    """加载防御层 ETF 数据。"""
    prices = {}
    for name, code in DEFENSE_MAP.items():
        fpath = os.path.join(DATA_DIR, f"{code}.parquet")
        if os.path.exists(fpath):
            df = pd.read_parquet(fpath)
            if all(c in df.columns for c in ["open", "high", "low", "close"]):
                prices[name] = df
    return prices


def _compute_sharpe(nav: pd.Series) -> float:
    if len(nav) < 2 or nav.iloc[-1] <= 0:
        return 0.0
    returns = nav.pct_change().dropna()
    ann_ret = (nav.iloc[-1] / nav.iloc[0]) ** (252 / len(nav)) - 1
    ann_vol = returns.std() * np.sqrt(252)
    return ann_ret / ann_vol if ann_vol > 0 else 0.0


def trim_to_year(prices: dict, start_year: int, n_years: int) -> dict:
    """截取 prices 中从 start_year 起 n_years 年的数据。"""
    end_year = start_year + n_years
    trimmed = {}
    for name, df in prices.items():
        mask = (df.index >= f"{start_year}-01-01") & (df.index < f"{end_year}-01-01")
        sub = df.loc[mask].copy()
        if len(sub) > MIN_DAYS:
            trimmed[name] = sub
    return trimmed


def scan_trend_window(prices: dict, windows: list[int] = None) -> dict:
    """在给定数据上扫描 trend_window，返回 {window: sharpe}。"""
    if windows is None:
        windows = TREND_WINDOWS
    results = {}
    for w in windows:
        params = {**DEFAULT_PARAMS, "trend_window": w}
        try:
            result = run_backtest(prices=prices, initial_capital=1_000_000,
                                  params=params, min_days=60)
            nav = result["records_df"]["nav"]
            results[w] = _compute_sharpe(nav)
        except Exception:
            results[w] = 0.0
    return results


def run_walk_forward(prices: dict) -> pd.DataFrame:
    """逐年滚动 walk-forward，返回每轮结果表。

    Returns:
        DataFrame columns: [train_start, test_year, best_window,
                           test_sharpe_best, test_sharpe_40]
    """
    all_years = sorted({
        d.year
        for df in prices.values()
        for d in df.index
    })
    if len(all_years) < TRAIN_YEARS + TEST_YEARS:
        return pd.DataFrame()

    rows = []
    for i in range(len(all_years) - TRAIN_YEARS - TEST_YEARS + 1):
        train_start = all_years[i]
        test_year = all_years[i + TRAIN_YEARS]

        train_prices = trim_to_year(prices, train_start, TRAIN_YEARS)
        test_prices = trim_to_year(prices, test_year, TEST_YEARS)

        if len(train_prices) < 3 or len(test_prices) < 3:
            continue

        # 训练窗扫描
        train_results = scan_trend_window(train_prices)
        if not train_results:
            continue
        best_w = max(train_results, key=lambda w: train_results[w])
        best_sharpe = train_results[best_w]

        # 测试窗：用 best_window
        params_best = {**DEFAULT_PARAMS, "trend_window": best_w}
        try:
            r_best = run_backtest(prices=test_prices, initial_capital=1_000_000,
                                  params=params_best, min_days=60)
            test_best_sharpe = _compute_sharpe(r_best["records_df"]["nav"])
        except Exception:
            test_best_sharpe = 0.0

        # 测试窗：固定 40
        params_40 = {**DEFAULT_PARAMS, "trend_window": 40}
        try:
            r_40 = run_backtest(prices=test_prices, initial_capital=1_000_000,
                                params=params_40, min_days=60)
            test_sharpe_40 = _compute_sharpe(r_40["records_df"]["nav"])
        except Exception:
            test_sharpe_40 = 0.0

        rows.append({
            "train_start": train_start,
            "test_year": test_year,
            "best_window": best_w,
            "best_train_sharpe": best_sharpe,
            "test_sharpe_best": test_best_sharpe,
            "test_sharpe_40": test_sharpe_40,
        })

    return pd.DataFrame(rows)


def main():
    print("=" * 60)
    print("Walk-forward trend_window 滚动验证")
    print("=" * 60)

    prices = load_prices()
    print(f"\n加载 ETF: {list(prices.keys())}")

    df = run_walk_forward(prices)
    if df.empty:
        print("数据不足，无法运行 walk-forward")
        return

    print(f"\n{'=' * 60}")
    print(f"  Walk-forward 结果（{TRAIN_YEARS}年训练 → {TEST_YEARS}年测试，逐年滚动）")
    print(f"{'=' * 60}")
    print(f"{'训练起始':>8} {'测试年份':>8} {'最优window':>10} "
          f"{'测试Sharpe(最优)':>16} {'测试Sharpe(40)':>16}")
    print("-" * 60)
    for _, row in df.iterrows():
        print(f"{int(row['train_start']):>8} {int(row['test_year']):>8} "
              f"{int(row['best_window']):>10} "
              f"{row['test_sharpe_best']:>16.3f} {row['test_sharpe_40']:>16.3f}")

    narrow = df[df["best_window"].between(30, 50)]
    print(f"\n  最优 window ∈ [30,50] 比例: {len(narrow)}/{len(df)} "
          f"= {len(narrow)/len(df):.0%}")

    cum_best = (1 + df["test_sharpe_best"]).prod()
    cum_40 = (1 + df["test_sharpe_40"]).prod()
    print(f"  滚动最优累计: {cum_best:.3f}")
    print(f"  固定 40 累计: {cum_40:.3f}")
    if cum_best > 0:
        print(f"  比率: {cum_40 / cum_best:.2%}")

    return df


if __name__ == "__main__":
    main()
