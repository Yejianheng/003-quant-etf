# [2026-05-30] 修改：extract_mixed_row → extract_defense_row，切换为纯防御配置
# [2026-05-30] 新增：Ablation 汇总 — 四个模块独立贡献对比

import os
import sys
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE = os.path.join(os.path.dirname(__file__), "..")
OUTPUT_DIR = os.path.join(BASE, "output")


def extract_defense_row(csv_path: str) -> tuple:
    """从 ablation CSV 提取纯防御配置的(有模块行, 无模块行)。"""
    df = pd.read_csv(os.path.join(OUTPUT_DIR, csv_path))
    defense = df[df["配置"] == "纯防御"]
    row_on = defense[defense["状态"].isin(["有趋势过滤", "有vol target", "EWMA λ=0.94", "有熔断"])]
    row_off = defense[defense["状态"].isin(["无趋势过滤", "固定等权", "历史协方差", "无熔断"])]
    return (
        row_on.iloc[0].to_dict() if len(row_on) > 0 else {},
        row_off.iloc[0].to_dict() if len(row_off) > 0 else {},
    )


def main():
    print("=" * 70)
    print("Step 5: Ablation 汇总 — 四个模块独立贡献")
    print("=" * 70)

    ablations = [
        ("1.2 趋势过滤", "ablation_1.2_trend_filter.csv"),
        ("1.3 波动率目标", "ablation_1.3_vol_target.csv"),
        ("1.4 EWMA 协方差", "ablation_1.4_ewma.csv"),
        ("1.5 相关性熔断", "ablation_1.5_corr_cb.csv"),
    ]

    summary_rows = []
    for name, fpath in ablations:
        row_on, row_off = extract_defense_row(fpath)
        if not row_on or not row_off:
            print("  {0}: 数据缺失，跳过".format(name))
            continue

        sharpe_on = row_on.get("Sharpe", float("nan"))
        sharpe_off = row_off.get("Sharpe", float("nan"))
        dd_on = row_on.get("最大回撤", float("nan"))
        dd_off = row_off.get("最大回撤", float("nan"))

        delta_sharpe = sharpe_on - sharpe_off
        delta_dd = dd_on - dd_off  # 正值 = 改善

        if delta_sharpe > 0.05 and delta_dd > 0.01:
            conclusion = "强正面：Sharpe 和回撤双重改善"
        elif delta_sharpe > 0.02:
            conclusion = "正面：Sharpe 提升，回撤变化小"
        elif abs(delta_sharpe) < 0.03 and abs(delta_dd) < 0.02:
            conclusion = "中性：差异在噪声范围内"
        elif delta_sharpe < -0.03:
            conclusion = "意外：模块移除后反而改善"
        else:
            conclusion = "待分析"

        summary_rows.append({
            "模块": name,
            "有模块 Sharpe": "{0:.2f}".format(sharpe_on),
            "无模块 Sharpe": "{0:.2f}".format(sharpe_off),
            "ΔSharpe": "{0:+.2f}".format(delta_sharpe),
            "有模块回撤": "{0:.1%}".format(dd_on),
            "无模块回撤": "{0:.1%}".format(dd_off),
            "Δ回撤(改善为正)": "{0:+.1%}".format(delta_dd),
            "结论": conclusion,
        })

        print("\n  [{0}]".format(name))
        print("    Sharpe: {0:.2f} → {1:.2f} (Δ={2:+.2f})".format(sharpe_on, sharpe_off, delta_sharpe))
        print("    回撤:   {0:.1%} → {1:.1%} (改善={2:+.1%})".format(dd_on, dd_off, delta_dd))
        print("    结论:   {0}".format(conclusion))

    df = pd.DataFrame(summary_rows)
    csv_path = os.path.join(OUTPUT_DIR, "ablation_summary.csv")
    df.to_csv(csv_path, index=False)

    print("\n" + "=" * 70)
    print("  汇总表")
    print("=" * 70)
    print(df.to_string(index=False))
    print("\n保存至 {0}".format(csv_path))

    # 边际贡献排名
    print("\n" + "=" * 70)
    print("  边际贡献排名（按 ΔSharpe）")
    print("=" * 70)
    ranked = sorted(summary_rows, key=lambda r: float(r["ΔSharpe"]), reverse=True)
    for i, r in enumerate(ranked, 1):
        print("  {0}. {1}: ΔSharpe={2}, {3}".format(i, r["模块"], r["ΔSharpe"], r["结论"]))

    print("\n=== 步骤 5 完成 ===")
    return df


if __name__ == "__main__":
    main()
