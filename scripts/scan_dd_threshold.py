# [2026-05-30] 新增：熔断阈值敏感性扫描 — P1-8
"""
扫描 dd_threshold_liquidate 0.15/0.18/0.20/0.25，输出对比表。
用法: python scripts/scan_dd_threshold.py
"""
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.backtest_engine import run_backtest

BASE = os.path.join(os.path.dirname(__file__), "..")
DATA_DIR = os.path.join(BASE, "data")
OUTPUT_DIR = os.path.join(BASE, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

DEFENSE_MAP = {
    "沪深300": "510300",
    "创业板": "159915",
    "纳指": "513100",
    "黄金": "518880",
    "国债ETF": "511010",
}

FIXED_PARAMS_BASE = {
    "trend_window": 40,
    "ewma_lambda": 0.94,
    "target_vol_beta": 0.10,
    "corr_threshold": 0.0,
    "defense_ratio": 1.0,
}

INITIAL_CAPITAL = 1_000_000
MIN_DAYS = 120


def make_thresholds(liquidate_at: float) -> list:
    """halve@12%, liquidate@liquidate_at"""
    return [(0.12, 1.0), (liquidate_at, 0.5), (liquidate_at, 0.0)]


def count_liquidate_days(records: pd.DataFrame) -> int:
    return (records["drawdown_level"] == "liquidate").sum()


def count_liquidate_episodes(records: pd.DataFrame) -> int:
    episodes = 0
    in_episode = False
    for level in records["drawdown_level"]:
        if level == "liquidate" and not in_episode:
            episodes += 1
            in_episode = True
        elif level != "liquidate":
            in_episode = False
    return episodes


def compute_recovery_days(records: pd.DataFrame) -> int:
    liquidate_dates = records[records["drawdown_level"] == "liquidate"].index
    if len(liquidate_dates) == 0:
        return 0
    last_liquidate = liquidate_dates[-1]
    after = records[records.index > last_liquidate]
    return len(after)


def main():
    print("=== 熔断阈值敏感性扫描 ===\n")
    print("固定参数:", FIXED_PARAMS_BASE)

    print("\n[1/3] 加载防御层数据...")
    prices = {}
    for name, code in DEFENSE_MAP.items():
        fpath = os.path.join(DATA_DIR, f"{code}.parquet")
        if not os.path.exists(fpath):
            print(f"  MISSING: {code} {name}")
            continue
        df = pd.read_parquet(fpath)
        prices[name] = df
        print(f"  {name} ({code}): {df.index[0].date()} ~ {df.index[-1].date()} ({len(df)} 行)")

    thresholds_to_scan = [0.15, 0.18, 0.20, 0.25]
    results = []

    print(f"\n[2/3] 扫描 {len(thresholds_to_scan)} 个阈值...")
    for th in thresholds_to_scan:
        params = {**FIXED_PARAMS_BASE, "drawdown_thresholds": make_thresholds(th)}
        result = run_backtest(prices, initial_capital=INITIAL_CAPITAL, params=params, min_days=MIN_DAYS)
        records = result["records_df"]

        row = {
            "liquidate阈值": th,
            "Sharpe": round(result["sharpe_ratio"], 2),
            "年化收益": f"{result['annual_return']:.1%}",
            "年化波动率": f"{result['annual_volatility']:.1%}",
            "最大回撤": f"{result['max_drawdown']:.1%}",
            "liquidate触发天数": count_liquidate_days(records),
            "liquidate触发段数": count_liquidate_episodes(records),
            "恢复天数": compute_recovery_days(records),
            "最终NAV": f"{result['final_nav']:,.0f}",
        }
        results.append(row)
        print(f"  阈值={th}: Sharpe={row['Sharpe']}, 年化={row['年化收益']}, "
              f"最大回撤={row['最大回撤']}, liquidate={row['liquidate触发天数']}天")

    print(f"\n[3/3] 对比表\n")
    headers = ["liquidate阈值", "Sharpe", "年化收益", "年化波动率", "最大回撤",
               "liquidate触发天数", "liquidate触发段数", "恢复天数", "最终NAV"]
    col_widths = [14, 8, 10, 10, 10, 16, 14, 10, 12]

    sep = "+" + "+".join("-" * w for w in col_widths) + "+"
    print(sep)
    print("|" + "|".join(h.center(w) for h, w in zip(headers, col_widths)) + "|")
    print(sep)
    for r in results:
        vals = [str(r[h]) for h in headers]
        print("|" + "|".join(v.center(w) for v, w in zip(vals, col_widths)) + "|")
    print(sep)

    df = pd.DataFrame(results)
    csv_path = os.path.join(OUTPUT_DIR, "threshold_sensitivity.csv")
    df.to_csv(csv_path, index=False)
    print(f"\n结果已保存至 {csv_path}")

    print("\n=== 判定 ===")
    current = results[1]
    print(f"当前阈值 0.18: Sharpe={current['Sharpe']}, 最大回撤={current['最大回撤']}, "
          f"liquidate={current['liquidate触发天数']}天/{current['liquidate触发段数']}段")

    dd018 = float(results[1]["最大回撤"].rstrip("%")) / 100
    dd015 = float(results[0]["最大回撤"].rstrip("%")) / 100
    dd020 = float(results[2]["最大回撤"].rstrip("%")) / 100
    dd025 = float(results[3]["最大回撤"].rstrip("%")) / 100

    if abs(dd018) <= abs(dd020) + 0.005 and abs(dd018) >= abs(dd015) - 0.005:
        print("判定: 0.18 在合理区间内 [PASS]")
    else:
        print("判定: 0.18 可能需要调整 [REVIEW]")

    dd_range = max(abs(dd015), abs(dd018), abs(dd020), abs(dd025)) - min(abs(dd015), abs(dd018), abs(dd020), abs(dd025))
    if dd_range < 0.03:
        print(f"判定: 策略对阈值不敏感（回撤极差 {dd_range:.1%} < 3%）[PASS]")
    else:
        print(f"判定: 策略对阈值敏感（回撤极差 {dd_range:.1%} ≥ 3%）[REVIEW]")


if __name__ == "__main__":
    main()
