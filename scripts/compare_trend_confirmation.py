# [2026-05-30] 新增：趋势确认机制对比 — 5 种方法纯防御全量 2014-2026

import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.backtest_engine import run_backtest
from src.signal_generator import DEFENSE_NAMES

BASE = os.path.join(os.path.dirname(__file__), "..")
DATA_DIR = os.path.join(BASE, "data")
OUTPUT_DIR = os.path.join(BASE, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

DEFENSE_MAP = {
    "沪深300": "510300", "创业板": "159915", "纳指": "513100",
    "黄金": "518880", "国债ETF": "511010",
}
OFFENSE_MAP = {
    "消费ETF": "159928", "医药ETF": "512010", "证券ETF": "512880",
    "有色ETF": "512400", "科技ETF": "515000", "军工ETF": "512660",
}

FIXED_PARAMS = {
    "trend_window": 40,
    "ewma_lambda": 0.94,
    "target_vol_beta": 0.10,
    "target_vol_alpha": 0.20,
    "defense_ratio": 1.00,
}

WHIPSAW_WINDOW = 20

METHOD_LABELS = {
    "trend_strength": "Trend Strength（当前）",
    "price_ma": "Price > MA",
    "dual_ma": "Dual MA",
    "ma_slope": "MA Slope",
    "breakout": "Breakout",
}


def load_all_prices():
    """加载所有 ETF 的 OHLCV 数据。"""
    prices = {}
    for name, code in {**DEFENSE_MAP, **OFFENSE_MAP}.items():
        fpath = os.path.join(DATA_DIR, f"{code}.parquet")
        if os.path.exists(fpath):
            df = pd.read_parquet(fpath)
            if all(c in df.columns for c in ["open", "high", "low", "close"]):
                prices[name] = df
    return prices


def compute_metrics(nav_series: pd.Series) -> dict:
    """从净值序列计算绩效指标。"""
    if len(nav_series) < 2:
        return {}
    returns = nav_series.pct_change().dropna()
    annual_factor = 252
    total_return = (nav_series.iloc[-1] / nav_series.iloc[0]) - 1
    years = len(nav_series) / annual_factor
    annual_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0
    annual_vol = returns.std() * np.sqrt(annual_factor)
    sharpe = annual_return / annual_vol if annual_vol > 0 else 0
    peak = nav_series.expanding().max()
    dd = (nav_series - peak) / peak
    max_dd = dd.min()
    return {
        "总收益": total_return, "年化": annual_return,
        "波动率": annual_vol, "Sharpe": sharpe, "最大回撤": max_dd,
    }


def year_return(nav_series: pd.Series, year: int) -> float:
    """提取指定年份收益。"""
    mask = (nav_series.index >= f"{year}-01-01") & (nav_series.index <= f"{year}-12-31")
    yr = nav_series.loc[mask]
    if len(yr) < 2:
        return np.nan
    return yr.iloc[-1] / yr.iloc[0] - 1


def parse_etf_list(s):
    """解析分号分隔的 ETF 列表字符串。"""
    if s is None or (isinstance(s, float) and np.isnan(s)):
        return []
    s = str(s).strip()
    if not s or s.lower() == "nan":
        return []
    return [x.strip() for x in s.split(";") if x.strip()]


def count_whipsaws(records: pd.DataFrame) -> int:
    """统计防御层 ETF 的 whipsaw 次数（20 日内先进后出）。"""
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


def run_config(prices, method):
    """运行纯防御指定趋势确认机制，返回 (nav, records, metrics)。"""
    params = {
        **FIXED_PARAMS,
        "trend_confirmation_method": method,
    }
    result = run_backtest(prices=prices, initial_capital=1_000_000, params=params, min_days=120)
    records = result["records_df"]
    nav = records["nav"]
    m = compute_metrics(nav)
    m["2018收益"] = year_return(nav, 2018)
    m["2022收益"] = year_return(nav, 2022)
    m["whipsaw_count"] = count_whipsaws(records)
    return nav, records, m


def main():
    print("=" * 70)
    print("步骤 2: 趋势确认机制对比 — 纯防御全量 2014-2026")
    print("=" * 70)

    prices = load_all_prices()
    print(f"\n加载 ETF: {list(prices.keys())}")

    methods = ["trend_strength", "price_ma", "dual_ma", "ma_slope", "breakout"]

    all_rows = []
    for method in methods:
        label = METHOD_LABELS[method]
        print(f"\n{'─' * 50}")
        print(f"  [{label}]")

        nav, records, m = run_config(prices, method)

        yr18 = f"{m['2018收益']:.1%}" if not np.isnan(m['2018收益']) else "N/A"
        yr22 = f"{m['2022收益']:.1%}" if not np.isnan(m['2022收益']) else "N/A"
        print(f"  Sharpe={m['Sharpe']:.2f}, 最大回撤={m['最大回撤']:.1%}, "
              f"whipsaw={m['whipsaw_count']}, 2018={yr18}, 2022={yr22}")

        nav.to_csv(os.path.join(OUTPUT_DIR, f"nav_trend_confirm_{method}.csv"), header=True)
        records.to_csv(os.path.join(OUTPUT_DIR, f"records_trend_confirm_{method}.csv"), header=True)

        all_rows.append({"机制": label, "method": method, **m})

    # 对比表
    print(f"\n{'=' * 70}")
    print("  趋势确认机制对比表（纯防御，2014-2026）")
    print(f"{'=' * 70}")

    header = f"{'机制':<24} {'Sharpe':>8} {'最大回撤':>10} {'Whipsaw':>8} {'2018收益':>10} {'2022收益':>10}"
    print(header)
    print("─" * 75)
    for r in all_rows:
        yr18 = f"{r['2018收益']:.1%}" if not np.isnan(r['2018收益']) else "N/A"
        yr22 = f"{r['2022收益']:.1%}" if not np.isnan(r['2022收益']) else "N/A"
        print(f"{r['机制']:<24} {r['Sharpe']:>8.2f} {r['最大回撤']:>9.1%} "
              f"{r['whipsaw_count']:>8} {yr18:>10} {yr22:>10}")

    # 最优判定
    best = max(all_rows, key=lambda r: r["Sharpe"])
    print(f"\n  >> 最优机制: {best['机制']} (Sharpe={best['Sharpe']:.2f})")

    # 保存汇总
    df_all = pd.DataFrame(all_rows)
    csv_path = os.path.join(OUTPUT_DIR, "trend_confirmation_comparison.csv")
    df_all.to_csv(csv_path, index=False)
    print(f"\n汇总 → {csv_path}")

    print("\n=== 步骤 2 完成 ===")
    return df_all


if __name__ == "__main__":
    main()
