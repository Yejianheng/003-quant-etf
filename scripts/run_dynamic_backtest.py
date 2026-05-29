# [2026-05-29] 新增：动态 ETF 接入回测脚本 — 6 种配置 × 三基准对比

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

# 防御层映射
DEFENSE_MAP = {
    "沪深300": "510300",
    "创业板": "159915",
    "纳指": "513100",
    "黄金": "518880",
    "国债ETF": "511010",
}

# 进攻层：6 只代表 ETF（风险源 → 代表 ETF 代码）
# 一级风险源宽基 ETF，排除二级主题（芯片/半导体/酒/电池等）
OFFENSE_MAP = {
    "消费ETF": "159928",
    "医药ETF": "512010",
    "证券ETF": "512880",
    "有色ETF": "512400",
    "科技ETF": "515000",
    "军工ETF": "512660",
}

# 固定参数（direction.md 指定）
FIXED_PARAMS_BASE = {
    "trend_window": 40,
    "ewma_lambda": 0.94,
    "target_vol_beta": 0.10,
    "target_vol_alpha": 0.20,
}


def load_prices(code: str) -> pd.DataFrame | None:
    fpath = os.path.join(DATA_DIR, f"{code}.parquet")
    if not os.path.exists(fpath):
        return None
    df = pd.read_parquet(fpath)
    required = ["open", "high", "low", "close"]
    for col in required:
        if col not in df.columns:
            return None
    return df


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
    drawdown = (nav_series - peak) / peak
    max_dd = drawdown.min()
    return {
        "总收益": total_return,
        "年化": annual_return,
        "波动率": annual_vol,
        "Sharpe": sharpe,
        "最大回撤": max_dd,
    }


def fmt_metrics(m: dict) -> dict:
    return {
        "总收益": f"{m['总收益']:.1%}",
        "年化": f"{m['年化']:.1%}",
        "波动率": f"{m['波动率']:.1%}",
        "Sharpe": f"{m['Sharpe']:.2f}",
        "最大回撤": f"{m['最大回撤']:.1%}",
    }


def print_table(label: str, strategy_m: dict, bench_m: dict[str, dict]):
    headers = ["指标", "策略", "沪深300", "创业板", "纳指"]
    widths = [10, 12, 12, 12, 12]
    sep = "+" + "+".join("-" * w for w in widths) + "+"
    print(f"\n--- {label} ---")
    print(sep)
    print("|" + "|".join(h.center(w) for h, w in zip(headers, widths)) + "|")
    print(sep)
    for metric in ["总收益", "年化", "波动率", "Sharpe", "最大回撤"]:
        sv = strategy_m.get(metric, "-")
        h3 = bench_m.get("沪深300", {}).get(metric, "-")
        cy = bench_m.get("创业板", {}).get(metric, "-")
        nd = bench_m.get("纳指", {}).get(metric, "-")
        print("|" + "|".join(v.center(w) for v, w in zip([metric, sv, h3, cy, nd], widths)) + "|")
    print(sep)


def main():
    print("=== 动态 ETF 接入回测 ===\n")

    # 加载防御层
    print("[1/4] 加载防御层数据...")
    defense_prices = {}
    for name, code in DEFENSE_MAP.items():
        df = load_prices(code)
        if df is not None:
            defense_prices[name] = df
            print(f"  {name} ({code}): {df.index[0].date()} ~ {df.index[-1].date()} ({len(df)} 行)")

    # 加载进攻层
    print("\n[2/4] 加载进攻层数据...")
    offense_prices = {}
    for name, code in OFFENSE_MAP.items():
        df = load_prices(code)
        if df is not None:
            offense_prices[name] = df
            print(f"  {name} ({code}): {df.index[0].date()} ~ {df.index[-1].date()} ({len(df)} 行)")

    # 合并全部 prices（不截断日期，让引擎做并集）
    all_prices = dict(defense_prices)
    all_prices.update(offense_prices)

    # 配置列表
    configs = [
        ("纯防御", 1.0, 0),
        ("K=2", 0.70, 2),
        ("K=3", 0.70, 3),
        ("K=4", 0.70, 4),
        ("K=5", 0.70, 5),
        ("K=6", 0.70, 6),
        ("纯进攻 K=2", 0.0, 2),
        ("纯进攻 K=3", 0.0, 3),
        ("纯进攻 K=4", 0.0, 4),
        ("纯进攻 K=5", 0.0, 5),
        ("纯进攻 K=6", 0.0, 6),
    ]

    all_results = []

    print("\n[3/4] 运行回测（6 种配置）...")

    for label, defense_ratio, top_k in configs:
        print(f"\n{'='*60}")
        print(f"  {label}: defense_ratio={defense_ratio}, offense_top_k={top_k}")
        print(f"{'='*60}")

        params = {
            **FIXED_PARAMS_BASE,
            "defense_ratio": defense_ratio,
            "offense_top_k": top_k,
        }

        try:
            result = run_backtest(
                prices=all_prices,
                initial_capital=1_000_000,
                params=params,
                min_days=120,
            )
        except Exception as e:
            print(f"  ERROR: {e}")
            continue

        records = result["records_df"]
        nav = records["nav"] if "nav" in records.columns else None
        if nav is None or len(nav) < 2:
            print("  无有效净值数据")
            continue

        strategy_metrics = compute_metrics(nav)
        strategy_fmt = fmt_metrics(strategy_metrics)
        print(f"  总收益={strategy_fmt['总收益']}, 年化={strategy_fmt['年化']}, "
              f"Sharpe={strategy_fmt['Sharpe']}, 最大回撤={strategy_fmt['最大回撤']}")

        # 保存净值序列 + 完整日记录
        nav.to_csv(os.path.join(OUTPUT_DIR, f"nav_{label}.csv"), header=True)
        records.to_csv(os.path.join(OUTPUT_DIR, f"records_{label}.csv"), header=True)

        # 三基准（从 result 提取，从 engine 返回的 benchmark Series）
        bench_metrics = {}
        bench_keys = [("沪深300", "benchmark_300"), ("创业板", "benchmark_chinext"), ("纳指", "benchmark_nasdaq")]
        for bname, bkey in bench_keys:
            bseries = result.get(bkey)
            if bseries is not None and len(bseries) > 1:
                common_dates = nav.index.intersection(bseries.index)
                if len(common_dates) > 1:
                    bm = compute_metrics(bseries.loc[common_dates])
                    bench_metrics[bname] = fmt_metrics(bm)
                else:
                    bench_metrics[bname] = {}
            else:
                bench_metrics[bname] = {}

        print_table(label, strategy_fmt, bench_metrics)

        # 保存标量指标到结果列表
        row = {
            "label": label,
            "defense_ratio": defense_ratio,
            "offense_top_k": top_k,
        }
        for mk, mv in strategy_metrics.items():
            row[f"strategy_{mk}"] = mv
        for bname, bd in bench_metrics.items():
            short = bname.replace("沪深300", "hs300").replace("创业板", "cyb").replace("纳指", "ndx")
            for mk, mv in bd.items():
                row[f"bench_{short}_{mk}"] = mv
        all_results.append(row)

    # 保存结果 CSV
    if all_results:
        df_results = pd.DataFrame(all_results)
        csv_path = os.path.join(OUTPUT_DIR, "dynamic_backtest_results.csv")
        df_results.to_csv(csv_path, index=False)
        print(f"\n[4/4] 结果已保存至 {csv_path}")

        # 汇总对比
        print("\n" + "=" * 60)
        print("  汇总：6 种配置策略指标对比")
        print("=" * 60)
        print(f"{'配置':<12} {'总收益':>8} {'年化':>8} {'Sharpe':>8} {'最大回撤':>8}")
        print("-" * 50)
        for r in all_results:
            print(f"{r['label']:<12} {r['strategy_总收益']:>8.1%} {r['strategy_年化']:>8.1%} "
                  f"{r['strategy_Sharpe']:>8.2f} {r['strategy_最大回撤']:>8.1%}")


if __name__ == "__main__":
    main()
