# [2026-05-29] 新增：步骤1 — 纯进攻 vs 纯防御 滚动相对收益分析

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

ROLLING_WINDOWS = [60, 120, 250]
WINDOW_LABELS = {60: "Quarterly(60d)", 120: "Semi-annual(120d)", 250: "Annual(250d)"}


def load_nav(label: str) -> pd.Series:
    path = os.path.join(OUTPUT_DIR, f"nav_{label}.csv")
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    return df.iloc[:, 0].rename(label)


def plot_relative_returns(
    offense: pd.Series,
    defense: pd.Series,
    output_path: str,
):
    fig, axes = plt.subplots(len(ROLLING_WINDOWS), 1, figsize=(16, 12), sharex=True)

    dates = offense.index

    for i, w in enumerate(ROLLING_WINDOWS):
        ax = axes[i]
        rolling_o = offense.pct_change().rolling(w).sum()
        rolling_d = defense.pct_change().rolling(w).sum()
        relative = rolling_o - rolling_d

        ax.fill_between(dates, relative.values, 0,
                        where=(relative.values >= 0), color="green", alpha=0.15, label="Offense > Defense")
        ax.fill_between(dates, relative.values, 0,
                        where=(relative.values < 0), color="red", alpha=0.15, label="Offense < Defense")
        ax.plot(dates, relative.values, color="black", linewidth=0.8)
        ax.axhline(y=0, color="gray", linestyle="--", linewidth=0.5)
        ax.set_ylabel(f"Rolling {w}d Excess Return")
        ax.set_title(f"{WINDOW_LABELS[w]} — Offense - Defense Rolling Return Spread", fontsize=11)
        ax.legend(loc="upper left", fontsize=8)
        ax.grid(True, alpha=0.3)

    axes[-1].set_xlabel("Date")
    fig.suptitle("Pure Offense vs Pure Defense — Rolling Relative Return", fontsize=14, y=1.01)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  相对收益曲线图已保存至 {output_path}")


def compute_relative_stats(offense: pd.Series, defense: pd.Series) -> pd.DataFrame:
    rows = []
    for w in ROLLING_WINDOWS:
        rolling_o = offense.pct_change().rolling(w).sum()
        rolling_d = defense.pct_change().rolling(w).sum()
        relative = rolling_o - rolling_d
        valid = relative.dropna()

        if len(valid) == 0:
            rows.append({
                "窗口": f"{w}日",
                "总交易日": 0,
                "进攻跑赢天数": 0,
                "进攻跑输天数": 0,
                "跑赢占比": 0.0,
                "跑赢时均值超额": 0.0,
                "跑输时均值超额": 0.0,
                "当前窗口超额": np.nan,
            })
            continue

        outperform_days = (valid > 0).sum()
        underperform_days = (valid < 0).sum()
        total = len(valid)
        outperform_pct = outperform_days / total
        mean_outperform = float(valid[valid > 0].mean()) if outperform_days > 0 else 0.0
        mean_underperform = float(valid[valid < 0].mean()) if underperform_days > 0 else 0.0

        rows.append({
            "窗口": f"{w}日",
            "总交易日": total,
            "进攻跑赢天数": outperform_days,
            "进攻跑输天数": underperform_days,
            "跑赢占比": outperform_pct,
            "跑赢时均值超额": mean_outperform,
            "跑输时均值超额": mean_underperform,
            "当前窗口超额": float(valid.iloc[-1]),
        })

    return pd.DataFrame(rows)


def list_regime_periods(offense: pd.Series, defense: pd.Series, window: int = 120):
    rolling_o = offense.pct_change().rolling(window).sum()
    rolling_d = defense.pct_change().rolling(window).sum()
    relative = rolling_o - rolling_d
    valid = relative.dropna()

    if len(valid) == 0:
        return []

    regimes = []
    current_sign = None
    current_start = None

    for date, val in valid.items():
        sign = "outperform" if val > 0 else "underperform"
        if sign != current_sign:
            if current_start is not None:
                regimes.append({
                    "start": current_start,
                    "end": date,
                    "regime": current_sign,
                    "mean_excess": float(valid[current_start:date].mean()),
                })
            current_start = date
            current_sign = sign

    if current_start is not None:
        regimes.append({
            "start": current_start,
            "end": valid.index[-1],
            "regime": current_sign,
            "mean_excess": float(valid[current_start:valid.index[-1]].mean()),
        })

    return regimes


def main():
    print("=== 步骤1：纯进攻 vs 纯防御 滚动对比 ===\n")

    offense = load_nav("纯进攻")
    defense = load_nav("纯防御")
    print(f"[1/3] 加载数据: 纯进攻 {len(offense)} 日, 纯防御 {len(defense)} 日")

    # 对齐日期
    common = offense.index.intersection(defense.index)
    offense = offense.loc[common]
    defense = defense.loc[common]

    cum_o = offense.iloc[-1] / offense.iloc[0] - 1
    cum_d = defense.iloc[-1] / defense.iloc[0] - 1
    print(f"  累计收益: 纯进攻 {cum_o:.1%}, 纯防御 {cum_d:.1%}")
    print(f"  12年超额: {cum_o - cum_d:.1%}")

    # 绘制相对收益曲线
    print("\n[2/3] 绘制相对收益曲线...")
    plot_path = os.path.join(OUTPUT_DIR, "offense_vs_defense_relative.png")
    plot_relative_returns(offense, defense, plot_path)

    # 滚动窗口统计
    print("\n[3/3] 滚动窗口统计...")
    stats = compute_relative_stats(offense, defense)
    print(f"\n{'窗口':<12} {'总日':>6} {'跑赢日':>6} {'跑输日':>6} {'跑赢占比':>8} {'跑赢均值':>10} {'跑输均值':>10} {'当前':>10}")
    print("-" * 75)
    for _, r in stats.iterrows():
        print(f"{r['窗口']:<12} {r['总交易日']:>6} {r['进攻跑赢天数']:>6} {r['进攻跑输天数']:>6} "
              f"{r['跑赢占比']:>7.1%} {r['跑赢时均值超额']:>9.3%} {r['跑输时均值超额']:>9.3%} {r['当前窗口超额']:>9.3%}")

    stats_path = os.path.join(OUTPUT_DIR, "offense_vs_defense_stats.csv")
    stats.to_csv(stats_path, index=False)
    print(f"\n  统计表已保存至 {stats_path}")

    # 识别连续跑赢/跑输时段
    regimes = list_regime_periods(offense, defense, window=120)
    print("\n  主要时段（120日窗口，持续>60天）:")
    print(f"  {'开始':>12} {'结束':>12} {'类型':>12} {'均值超额':>10}")
    print("  " + "-" * 50)
    for r in regimes:
        days = (r["end"] - r["start"]).days
        if days > 60:
            label = "进攻跑赢" if r["regime"] == "outperform" else "进攻跑输"
            print(f"  {r['start'].strftime('%Y-%m-%d'):>12} {r['end'].strftime('%Y-%m-%d'):>12} {label:>12} {r['mean_excess']:>9.3%}")

    # 保存时段数据
    regime_df = pd.DataFrame([{
        "开始": r["start"].strftime("%Y-%m-%d"),
        "结束": r["end"].strftime("%Y-%m-%d"),
        "持续天数": (r["end"] - r["start"]).days,
        "类型": "进攻跑赢" if r["regime"] == "outperform" else "进攻跑输",
        "均值超额": r["mean_excess"],
    } for r in regimes if (r["end"] - r["start"]).days > 60])
    regime_path = os.path.join(OUTPUT_DIR, "offense_vs_defense_regimes.csv")
    regime_df.to_csv(regime_path, index=False)
    print(f"  时段数据已保存至 {regime_path}")

    print("\n=== 步骤1 完成 ===")


if __name__ == "__main__":
    main()
