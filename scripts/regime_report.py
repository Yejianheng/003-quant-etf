# [2026-05-29] 新增：汇总报告 — 合并四 regime 最终输出

import os
import sys
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE = os.path.join(os.path.dirname(__file__), "..")
OUTPUT_DIR = os.path.join(BASE, "output")

MAX_DD_LIMIT = -0.20

REGIME_FILE_MAP = {
    "单边牛市": "regime_单边牛市.csv",
    "长期熊市": "regime_长期熊市.csv",
    "高频震荡市": "regime_高频震荡市.csv",
    "利率regime_shift": "regime_利率regime_shift.csv",
}


def build_final_report(output_dir: str = OUTPUT_DIR) -> pd.DataFrame:
    rows = []
    whipsaw_df = _load_whipsaw_detail(output_dir)

    for regime_name, filename in REGIME_FILE_MAP.items():
        path = os.path.join(output_dir, filename)
        if not os.path.exists(path):
            continue

        df = pd.read_csv(path, index_col=0)
        if "纯防御" not in df.index:
            continue

        row = df.loc["纯防御"]

        # 匹配 whipsaw 数量
        if len(whipsaw_df) > 0:
            # whipsaw detail 中 regime 列为 "2016-02→2016-12" 格式
            w_count = _count_whipsaws_for_regime(whipsaw_df, regime_name)
        else:
            w_count = 0

        survived = "存活" if row["最大回撤"] > MAX_DD_LIMIT else "突破20%回撤"

        rows.append({
            "Regime": regime_name,
            "纯防御收益": row["区间收益"],
            "纯防御Sharpe": row["Sharpe"],
            "最大回撤": row["最大回撤"],
            "空仓率": row["空仓天数占比"],
            "Whipsaw": w_count,
            "是否存活": survived,
        })

    return pd.DataFrame(rows)


def _load_whipsaw_detail(output_dir: str) -> pd.DataFrame:
    path = os.path.join(output_dir, "regime_whipsaw_detail.csv")
    if os.path.exists(path):
        return pd.read_csv(path)
    return pd.DataFrame()


def _count_whipsaws_for_regime(whipsaw_df: pd.DataFrame, regime_name: str) -> int:
    zone_map = {
        "高频震荡市": ["2016-02", "2021-07"],
        "单边牛市": [],
        "长期熊市": [],
        "利率regime_shift": [],
    }
    prefixes = zone_map.get(regime_name, [])
    if not prefixes:
        return 0

    count = 0
    for prefix in prefixes:
        count += whipsaw_df["regime"].str.startswith(prefix).sum()
    return int(count)


def main():
    print("=" * 70)
    print("汇总报告 — Regime 压力测试最终输出")
    print("=" * 70)

    df = build_final_report()

    print(f"\n{'Regime':<18} {'收益':>8} {'Sharpe':>8} {'最大回撤':>8} "
          f"{'空仓率':>8} {'Whipsaw':>8} {'存活':>6}")
    print("-" * 70)
    for _, r in df.iterrows():
        print(f"{r['Regime']:<18} {r['纯防御收益']:>7.1%} {r['纯防御Sharpe']:>7.2f} "
              f"{r['最大回撤']:>7.1%} {r['空仓率']:>7.1%} {r['Whipsaw']:>8d} "
              f"{r['是否存活']:>6}")

    out_path = os.path.join(OUTPUT_DIR, "regime_stress_report.csv")
    df.to_csv(out_path, index=False)
    print(f"\n  最终报告 → {out_path}")

    print("\n=== 最强/最弱判定 ===")
    best = df.loc[df["纯防御Sharpe"].idxmax()]
    worst = df.loc[df["纯防御Sharpe"].idxmin()]
    print(f"  最强: {best['Regime']} — Sharpe {best['纯防御Sharpe']:.2f}, "
          f"收益 {best['纯防御收益']:.1%}, 空仓率 {best['空仓率']:.0%}")
    print(f"  最弱: {worst['Regime']} — Sharpe {worst['纯防御Sharpe']:.2f}, "
          f"收益 {worst['纯防御收益']:.1%}, 空仓率 {worst['空仓率']:.0%}")

    print("\n=== 步骤 4 完成 ===")
    return df


if __name__ == "__main__":
    main()
