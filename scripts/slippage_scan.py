# [2026-05-30] 新增：滑点与手续费扫描 — 4 档摩擦纯防御全量 2014-2026

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

SCENARIOS = [
    {"label": "理想", "slippage_bps": 0,  "commission_rate": 0.0,     "总摩擦(bp)": 0},
    {"label": "乐观", "slippage_bps": 5,  "commission_rate": 0.00025,  "总摩擦(bp)": 12.5},
    {"label": "中性", "slippage_bps": 10, "commission_rate": 0.00025,  "总摩擦(bp)": 22.5},
    {"label": "悲观", "slippage_bps": 20, "commission_rate": 0.0005,   "总摩擦(bp)": 45},
]


def load_all_prices():
    prices = {}
    for name, code in {**DEFENSE_MAP, **OFFENSE_MAP}.items():
        fpath = os.path.join(DATA_DIR, f"{code}.parquet")
        if os.path.exists(fpath):
            df = pd.read_parquet(fpath)
            if all(c in df.columns for c in ["open", "high", "low", "close"]):
                prices[name] = df
    return prices


def compute_metrics(nav_series: pd.Series) -> dict:
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


def fmt_metrics(m: dict) -> dict:
    return {
        "总收益": f"{m['总收益']:.1%}",
        "年化": f"{m['年化']:.1%}",
        "波动率": f"{m['波动率']:.1%}",
        "Sharpe": f"{m['Sharpe']:.2f}",
        "最大回撤": f"{m['最大回撤']:.1%}",
    }


def main():
    print("=" * 70)
    print("步骤 3: 滑点与手续费扫描 — 纯防御全量 2014-2026")
    print("=" * 70)

    prices = load_all_prices()
    print(f"\n加载 ETF: {list(prices.keys())}")

    all_rows = []
    bench_sharpe = None

    for sc in SCENARIOS:
        label = sc["label"]
        print(f"\n{'─' * 50}")
        print(f"  [{label}] slippage={sc['slippage_bps']}bp, "
              f"commission={sc['commission_rate']:.5f} (万{sc['commission_rate']*10000:.1f})")

        result = run_backtest(
            prices=prices,
            initial_capital=1_000_000,
            params=FIXED_PARAMS,
            min_days=120,
            slippage_bps=sc["slippage_bps"],
            commission_rate=sc["commission_rate"],
        )
        records = result["records_df"]
        nav = records["nav"]
        m = compute_metrics(nav)
        m_fmt = fmt_metrics(m)
        print(f"  年化={m_fmt['年化']}, Sharpe={m_fmt['Sharpe']}, "
              f"最大回撤={m_fmt['最大回撤']}")

        nav.to_csv(os.path.join(OUTPUT_DIR, f"nav_slippage_{label}.csv"), header=True)
        records.to_csv(os.path.join(OUTPUT_DIR, f"records_slippage_{label}.csv"), header=True)

        row = {
            "场景": label,
            "双边滑点(bp)": sc["slippage_bps"],
            "佣金": f"万{sc['commission_rate']*10000:.1f}",
            "总摩擦(bp)": sc["总摩擦(bp)"],
        }
        row.update(m)
        all_rows.append(row)

        if bench_sharpe is None:
            # 基准沪深300 Sharpe（从 result 提取）
            b300 = result.get("benchmark_300")
            if b300 is not None and len(b300) > 1:
                bm = compute_metrics(b300.loc[nav.index.intersection(b300.index)])
                bench_sharpe = bm.get("Sharpe", 0)

    # 对比表
    print(f"\n{'=' * 70}")
    print("  滑点与手续费对比表（纯防御，2014-2026）")
    print(f"{'=' * 70}")

    print(f"{'场景':<8} {'双边滑点':>8} {'佣金':>8} {'总摩擦':>8} "
          f"{'Sharpe':>8} {'年化':>10} {'最大回撤':>10}")
    print("─" * 70)
    for r in all_rows:
        print(f"{r['场景']:<8} {r['双边滑点(bp)']:>6}bp {r['佣金']:>8} "
              f"{r['总摩擦(bp)']:>6}bp {r['Sharpe']:>8.2f} "
              f"{r['年化']:>9.1%} {r['最大回撤']:>9.1%}")

    # 验收
    neutral = [r for r in all_rows if r["场景"] == "中性"][0]
    print(f"\n  验收: 中性假设下策略 Sharpe={neutral['Sharpe']:.2f}")
    if bench_sharpe is not None:
        print(f"  基准沪深300 Sharpe={bench_sharpe:.2f}")
        if neutral["Sharpe"] > bench_sharpe:
            print("  [PASS] 中性摩擦下策略 Sharpe > 基准")
        else:
            print("  [FAIL] 中性摩擦下策略 Sharpe <= 基准")

    # 策略开始不划算的档位
    print(f"\n  Sharpe 随摩擦衰减:")
    for r in all_rows:
        print(f"    {r['场景']}: Sharpe {r['Sharpe']:.2f}")

    df_all = pd.DataFrame(all_rows)
    csv_path = os.path.join(OUTPUT_DIR, "slippage_scan_results.csv")
    df_all.to_csv(csv_path, index=False)
    print(f"\n汇总 → {csv_path}")

    print("\n=== 步骤 3 完成 ===")
    return df_all


if __name__ == "__main__":
    main()
