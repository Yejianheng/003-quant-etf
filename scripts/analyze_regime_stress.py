# [2026-05-29] 新增：市场状态压力测试 — 四个 regime 独立绩效分析

import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE = os.path.join(os.path.dirname(__file__), "..")
OUTPUT_DIR = os.path.join(BASE, "output")
DATA_DIR = os.path.join(BASE, "data")

RISK_FREE = 0.02
TRADING_DAYS_PER_YEAR = 252

REGIME_DEFS = {
    "单边牛市": [
        ("2014-07-01", "2015-06-12"),
        ("2019-01-01", "2020-12-31"),
    ],
    "长期熊市": [
        ("2018-01-01", "2018-12-31"),
        ("2022-01-01", "2022-10-31"),
    ],
    "高频震荡市": [
        ("2016-02-01", "2016-12-31"),
        ("2021-07-01", "2021-12-31"),
    ],
    "利率regime_shift": [
        ("2022-01-01", "2022-12-31"),
    ],
}

BENCHMARK_ETFS = {
    "沪深300": "510300",
    "创业板": "159915",
}


def load_defense_nav():
    path = os.path.join(OUTPUT_DIR, "nav_纯防御.csv")
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    return df.iloc[:, 0].rename("纯防御")


def load_defense_records():
    path = os.path.join(OUTPUT_DIR, "records_纯防御.csv")
    return pd.read_csv(path, index_col=0, parse_dates=True)


def load_benchmark_prices():
    result = {}
    for label, code in BENCHMARK_ETFS.items():
        path = os.path.join(DATA_DIR, f"{code}.parquet")
        df = pd.read_parquet(path)
        result[label] = df["close"].rename(label)
    return result


def compute_metrics(nav: pd.Series) -> dict:
    daily_ret = nav.pct_change().dropna()
    if len(daily_ret) == 0:
        return {}

    total_ret = nav.iloc[-1] / nav.iloc[0] - 1
    n_days = len(daily_ret)
    ann_ret = (1 + total_ret) ** (TRADING_DAYS_PER_YEAR / n_days) - 1
    ann_vol = daily_ret.std() * np.sqrt(TRADING_DAYS_PER_YEAR)
    sharpe = (ann_ret - RISK_FREE) / ann_vol if ann_vol > 0 else 0.0

    cummax = nav.cummax()
    drawdowns = (nav - cummax) / cummax
    max_dd = drawdowns.min()

    return {
        "区间收益": total_ret,
        "年化": ann_ret,
        "波动率": ann_vol,
        "Sharpe": sharpe,
        "最大回撤": max_dd,
        "交易日": n_days,
    }


def slice_nav(nav: pd.Series, start: str, end: str) -> pd.Series:
    idx = nav.index
    mask = (idx >= pd.Timestamp(start)) & (idx <= pd.Timestamp(end))
    return nav.loc[mask]


def align_to_nav(bench: pd.Series, nav_index: pd.DatetimeIndex) -> pd.Series:
    aligned = bench.reindex(nav_index, method="ffill").dropna()
    return aligned


def _count_whipsaws(status: pd.Series, window: int = 20) -> int:
    if len(status) < 2:
        return 0
    changes = status != status.shift(1)
    flip_dates = changes[changes].index
    if len(flip_dates) < 2:
        return 0

    count = 0
    for i in range(len(flip_dates) - 1):
        delta = (flip_dates[i + 1] - flip_dates[i]).days
        if delta <= window:
            count += 1
    return count


def compute_regime_table(nav: pd.Series, benchmarks: dict, records: pd.DataFrame,
                         regime_name: str, sub_periods: list) -> pd.DataFrame:
    rows = []

    all_nav_parts = []
    for start, end in sub_periods:
        part = slice_nav(nav, start, end)
        if len(part) > 0:
            all_nav_parts.append(part)

    if not all_nav_parts:
        return pd.DataFrame()

    regime_nav = pd.concat(all_nav_parts).sort_index()
    metrics = compute_metrics(regime_nav)
    if not metrics:
        return pd.DataFrame()
    metrics["标签"] = "纯防御"

    rec_slice = records.loc[records.index.isin(regime_nav.index)]
    if len(rec_slice) > 0:
        cash_days = (rec_slice["exposure"] == 0) | (rec_slice["final_multiplier"] < 0.1)
        metrics["空仓天数占比"] = cash_days.mean()

        pos_names = rec_slice["position_names"].fillna("").astype(str)
        turnover_days = (pos_names != pos_names.shift(1)).sum()
        metrics["换手次数"] = int(turnover_days)

        defense_col = "defense_active" if "defense_active" in rec_slice.columns else None
        if defense_col and defense_col in rec_slice.columns:
            def_status = rec_slice[defense_col].fillna("").astype(str)
            metrics["whipsaw_次数"] = _count_whipsaws(def_status, window=20)
        else:
            metrics["whipsaw_次数"] = 0
    else:
        metrics["空仓天数占比"] = 0.0
        metrics["换手次数"] = 0
        metrics["whipsaw_次数"] = 0

    rows.append(metrics)

    for label, bench_prices in benchmarks.items():
        b_aligned = align_to_nav(bench_prices, regime_nav.index)
        if len(b_aligned) < 2:
            continue
        b_nav = b_aligned / b_aligned.iloc[0]
        b_metrics = compute_metrics(b_nav)
        b_metrics["标签"] = label
        b_metrics["空仓天数占比"] = 0.0
        b_metrics["换手次数"] = 0
        b_metrics["whipsaw_次数"] = 0
        rows.append(b_metrics)

    df = pd.DataFrame(rows).set_index("标签")
    col_order = ["区间收益", "年化", "波动率", "Sharpe", "最大回撤",
                 "空仓天数占比", "换手次数", "whipsaw_次数", "交易日"]
    existing = [c for c in col_order if c in df.columns]
    return df[existing]


def compute_separate_sub_periods(nav, benchmarks, records, regime_name, sub_periods):
    """子区间分开输出，每个子区间独立一行或多行。"""
    frames = []
    for start, end in sub_periods:
        df = compute_regime_table(nav, benchmarks, records,
                                  f"{regime_name}_{start}_{end}", [(start, end)])
        if len(df) > 0:
            df = df.reset_index()
            df.insert(0, "区间", f"{start} → {end}")
            df = df.set_index(["区间", "标签"])
            frames.append(df)
    if frames:
        return pd.concat(frames)
    return pd.DataFrame()


def main():
    print("=" * 70)
    print("市场状态压力测试 — 四个 Regime 独立分析")
    print("=" * 70)

    print("\n[1/5] 加载数据...")
    nav = load_defense_nav()
    records = load_defense_records()
    benchmarks_raw = load_benchmark_prices()
    print(f"  纯防御 NAV: {nav.index[0].strftime('%Y-%m-%d')} → {nav.index[-1].strftime('%Y-%m-%d')} "
          f"({len(nav)} 日)")

    benchmarks = {}
    for label, prices in benchmarks_raw.items():
        first_val = prices.loc[prices.index >= nav.index[0]].iloc[0]
        benchmarks[label] = prices / first_val
        print(f"  {label}: ({len(prices)} 日)")

    all_summary = []

    for i, (regime_name, sub_periods) in enumerate(REGIME_DEFS.items(), 2):
        print(f"\n[{i}/5] Regime: {regime_name} ...")

        summary = compute_regime_table(nav, benchmarks, records, regime_name, sub_periods)
        if len(summary) == 0:
            print(f"  无数据，跳过")
            continue

        fmt_cols = ["区间收益", "年化", "波动率", "Sharpe", "最大回撤", "空仓天数占比"]
        header = f"{'指标':<16}" + "".join(f" {col:>10}" for col in summary.columns)
        print(header)
        print("-" * len(header))

        for label, row in summary.iterrows():
            line = f"{label:<16}"
            for col in summary.columns:
                val = row[col]
                if col in fmt_cols:
                    if col == "Sharpe":
                        line += f" {val:>10.2f}"
                    else:
                        line += f" {val:>9.1%}"
                elif col in ("换手次数", "whipsaw_次数", "交易日"):
                    line += f" {int(val):>10d}"
                else:
                    line += f" {str(val):>10}"
            print(line)

        defense_ret = summary.loc["纯防御", "区间收益"] if "纯防御" in summary.index else 0
        defense_sharpe = summary.loc["纯防御", "Sharpe"] if "纯防御" in summary.index else 0
        hs300_ret = summary.loc["沪深300", "区间收益"] if "沪深300" in summary.index else 0
        cyb_ret = summary.loc["创业板", "区间收益"] if "创业板" in summary.index else 0
        print(f"  → 纯防御: {defense_ret:.1%} (Sharpe {defense_sharpe:.2f}) | "
              f"沪深300: {hs300_ret:.1%} | 创业板: {cyb_ret:.1%}")

        all_summary.append({
            "Regime": regime_name,
            "纯防御收益": defense_ret,
            "纯防御Sharpe": defense_sharpe,
            "沪深300收益": hs300_ret,
            "创业板收益": cyb_ret,
        })

        out_path = os.path.join(OUTPUT_DIR, f"regime_{regime_name}.csv")
        summary.to_csv(out_path)
        print(f"  详细表 → {out_path}")

        if len(sub_periods) > 1:
            detail = compute_separate_sub_periods(nav, benchmarks, records,
                                                  regime_name, sub_periods)
            detail_path = os.path.join(OUTPUT_DIR, f"regime_{regime_name}_detail.csv")
            detail.to_csv(detail_path)
            print(f"  子区间明细 → {detail_path}")

    print("\n" + "=" * 70)
    print("[汇总] 四 Regime 总览")
    print("=" * 70)
    summary_df = pd.DataFrame(all_summary)
    print(f"\n{'Regime':<18} {'防御收益':>10} {'防御Sharpe':>12} {'HS300收益':>10} {'创业板收益':>10}")
    print("-" * 65)
    for _, r in summary_df.iterrows():
        print(f"{r['Regime']:<18} {r['纯防御收益']:>9.1%} {r['纯防御Sharpe']:>11.2f} "
              f"{r['沪深300收益']:>9.1%} {r['创业板收益']:>9.1%}")

    summary_path = os.path.join(OUTPUT_DIR, "regime_stress_summary.csv")
    summary_df.to_csv(summary_path, index=False)
    print(f"\n  汇总 → {summary_path}")

    valid = summary_df.dropna(subset=["纯防御Sharpe"])
    if len(valid) > 0:
        best = valid.loc[valid["纯防御Sharpe"].idxmax()]
        worst = valid.loc[valid["纯防御Sharpe"].idxmin()]
        print(f"\n  最强 regime: {best['Regime']} (Sharpe {best['纯防御Sharpe']:.2f}, "
              f"收益 {best['纯防御收益']:.1%})")
        print(f"  最弱 regime: {worst['Regime']} (Sharpe {worst['纯防御Sharpe']:.2f}, "
              f"收益 {worst['纯防御收益']:.1%})")

    print("\n=== 步骤 1 完成 ===")
    return summary_df


if __name__ == "__main__":
    main()
