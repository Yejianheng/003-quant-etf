# [2026-05-29] 新增：动态回测结果分析 — K 值收益曲线 + 稳定性排名 + 推荐

import os
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE = os.path.join(os.path.dirname(__file__), "..")
OUTPUT_DIR = os.path.join(BASE, "output")

CONFIG_LABELS = ["纯防御", "K=2", "K=3", "K=4", "K=5", "K=6"]


def load_navs() -> dict[str, pd.Series]:
    navs = {}
    for label in CONFIG_LABELS:
        path = os.path.join(OUTPUT_DIR, f"nav_{label}.csv")
        if os.path.exists(path):
            s = pd.read_csv(path, index_col=0, parse_dates=True).squeeze("columns")
            navs[label] = s
    return navs


def load_records() -> dict[str, pd.DataFrame]:
    records = {}
    for label in CONFIG_LABELS:
        path = os.path.join(OUTPUT_DIR, f"records_{label}.csv")
        if os.path.exists(path):
            df = pd.read_csv(path, index_col=0, parse_dates=True)
            records[label] = df
    return records


def load_summary() -> pd.DataFrame:
    path = os.path.join(OUTPUT_DIR, "dynamic_backtest_results.csv")
    return pd.read_csv(path)


def compute_offense_stats(records: pd.DataFrame) -> dict:
    total_days = len(records)
    if total_days == 0:
        return {}
    offense_col = "offense_top" if "offense_top" in records.columns else None
    if offense_col is None:
        return {}
    empty_days = (records[offense_col].isna() | (records[offense_col] == "")).sum()
    offense_empty_rate = empty_days / total_days
    offense_participation_rate = 1 - offense_empty_rate
    non_empty = records[offense_col][records[offense_col] != ""].dropna()
    avg_offense_count = non_empty.apply(lambda x: len(x.split(";"))).mean() if len(non_empty) > 0 else 0
    return {
        "offense_empty_rate": offense_empty_rate,
        "offense_participation_rate": offense_participation_rate,
        "avg_offense_positions": avg_offense_count,
    }


def plot_k_comparison(navs: dict[str, pd.Series], output_path: str | None = None):
    if output_path is None:
        output_path = os.path.join(OUTPUT_DIR, "k_value_comparison.png")
    fig, ax = plt.subplots(figsize=(14, 7))
    colors = ["gray", "red", "orange", "green", "blue", "purple"]
    for label, color in zip(CONFIG_LABELS, colors):
        if label in navs:
            s = navs[label]
            norm = s / s.iloc[0]
            ax.plot(norm.index, norm.values, label=label, color=color, linewidth=1.2, alpha=0.9)
    ax.set_title("K Value NAV Comparison (2013-2026)", fontsize=14)
    ax.set_xlabel("Date")
    ax.set_ylabel("NAV (normalized to 1.0)")
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    print(f"  K 值收益对比图已保存至 {output_path}")


def compute_metrics_from_nav(nav: pd.Series) -> dict:
    if len(nav) < 2:
        return {}
    returns = nav.pct_change().dropna()
    total_return = (nav.iloc[-1] / nav.iloc[0]) - 1
    years = len(nav) / 252
    annual_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0
    annual_vol = returns.std() * np.sqrt(252)
    sharpe = annual_return / annual_vol if annual_vol > 0 else 0
    peak = nav.expanding().max()
    drawdown = (nav - peak) / peak
    max_dd = drawdown.min()
    return {"总收益": total_return, "年化": annual_return, "Sharpe": sharpe, "最大回撤": max_dd}


def main():
    print("=== 动态回测结果分析 ===\n")

    # 1. 加载数据
    navs = load_navs()
    records = load_records()
    summary = load_summary()
    print(f"[1/4] 加载 {len(navs)} 条净值序列, {len(records)} 条日记录, {len(summary)} 条汇总")

    # 2. K 值收益对比图
    print("\n[2/4] 生成 K 值收益对比图...")
    plot_k_comparison(navs)

    # 3. 进攻层演进 + 稳定性排名
    print("\n[3/4] 进攻层演进分析...")
    rows = []
    for label in CONFIG_LABELS:
        if label not in navs or label not in records:
            continue
        m = compute_metrics_from_nav(navs[label])
        os_ = compute_offense_stats(records[label])
        n_benchmarks_beaten = sum([
            1 for bcol in ["strategy_总收益", "strategy_Sharpe"]
            if bcol in summary.columns
        ])
        # 从 summary 读取已算好的指标
        sr = summary[summary["label"] == label]
        strategy_sharpe = float(sr["strategy_Sharpe"].iloc[0]) if len(sr) > 0 and "strategy_Sharpe" in sr.columns else m.get("Sharpe", 0)
        strategy_return = float(sr["strategy_总收益"].iloc[0]) if len(sr) > 0 and "strategy_总收益" in sr.columns else m.get("总收益", 0)
        strategy_dd = float(sr["strategy_最大回撤"].iloc[0]) if len(sr) > 0 and "strategy_最大回撤" in sr.columns else m.get("最大回撤", 0)

        rows.append({
            "label": label,
            "总收益": strategy_return,
            "年化": m.get("年化", 0),
            "Sharpe": strategy_sharpe,
            "最大回撤": strategy_dd,
            "进攻空仓率": os_.get("offense_empty_rate", 0),
            "进攻参与率": os_.get("offense_participation_rate", 0),
            "平均进攻持仓数": os_.get("avg_offense_positions", 0),
        })

    df_rank = pd.DataFrame(rows)
    df_rank = df_rank.sort_values("Sharpe", ascending=False)

    print(f"\n{'配置':<10} {'总收益':>8} {'年化':>8} {'Sharpe':>8} {'最大回撤':>8} {'空仓率':>8} {'进攻参与率':>8} {'均持仓':>8}")
    print("-" * 80)
    for _, r in df_rank.iterrows():
        print(f"{r['label']:<10} {r['总收益']:>8.1%} {r['年化']:>8.1%} {r['Sharpe']:>8.2f} "
              f"{r['最大回撤']:>8.1%} {r['进攻空仓率']:>8.1%} {r['进攻参与率']:>8.1%} {r['平均进攻持仓数']:>8.2f}")

    # 保存排名
    rank_path = os.path.join(OUTPUT_DIR, "stability_ranking.csv")
    df_rank.to_csv(rank_path, index=False)
    print(f"\n  稳定性排名已保存至 {rank_path}")

    # 4. 推荐 K 值
    print("\n[4/4] 推荐 K 值...")
    best = df_rank.iloc[0]
    print(f"\n  推荐 K 值: {best['label']}")
    print(f"  理由: Sharpe {best['Sharpe']:.2f}（最高）, 总收益 {best['总收益']:.1%}, "
          f"最大回撤 {best['最大回撤']:.1%}, 进攻参与率 {best['进攻参与率']:.1%}")

    # 进攻层 0→6 演进过程
    print("\n  进攻层 ETF 演进过程:")
    print("  ┌─────────────┬──────────────────────────────────────┐")
    print("  │ 时间段        │ 可用进攻 ETF                           │")
    print("  ├─────────────┼──────────────────────────────────────┤")
    print("  │ 2013-07~2016-08 │ 0 只（仅防御层）                       │")
    print("  │ 2016-08~2017-09 │ 2 只（证券+军工）                       │")
    print("  │ 2017-09~2019-05 │ 3 只（+有色）                          │")
    print("  │ 2019-05~2019-06 │ 4 只（+酒）                            │")
    print("  │ 2019-06~2020-04 │ 5 只（+半导体）                         │")
    print("  │ 2020-04~2026-05 │ 6 只（+创新药）                         │")
    print("  └─────────────┴──────────────────────────────────────┘")


if __name__ == "__main__":
    main()
