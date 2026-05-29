# [2026-05-30] 新增：Look-Ahead Bias 验证 — 信号 T 日收盘 vs 成交 T+1 日收盘对比

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

# 数据加载（与 run_dynamic_backtest.py 一致）
DEFENSE_MAP = {
    "沪深300": "510300",
    "创业板": "159915",
    "纳指": "513100",
    "黄金": "518880",
    "国债ETF": "511010",
}

OFFENSE_MAP = {
    "消费ETF": "159928",
    "医药ETF": "512010",
    "证券ETF": "512880",
    "有色ETF": "512400",
    "科技ETF": "515000",
    "军工ETF": "512660",
}

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
    annual_vol = float(returns.std() * np.sqrt(annual_factor))
    sharpe = annual_return / annual_vol if annual_vol > 0 else 0
    peak = nav_series.expanding().max()
    drawdown = (nav_series - peak) / peak
    max_dd = float(drawdown.min())
    return {
        "总收益": total_return,
        "年化": annual_return,
        "波动率": annual_vol,
        "Sharpe": sharpe,
        "最大回撤": max_dd,
    }


def main():
    print("=" * 70)
    print("Look-Ahead Bias 验证：信号 T 日 → 成交 T 日 vs T+1 日")
    print("=" * 70)

    # 加载数据
    print("\n[1/3] 加载数据...")
    all_prices = {}
    for name, code in {**DEFENSE_MAP, **OFFENSE_MAP}.items():
        df = load_prices(code)
        if df is not None:
            all_prices[name] = df
            print("  {0} ({1}): {2} ~ {3} ({4} 行)".format(
                name, code, df.index[0].date(), df.index[-1].date(), len(df)
            ))

    configs = [
        ("纯防御", 1.0),
        ("纯进攻", 0.0),
        ("混合", 0.70),
    ]

    print("\n[2/3] 运行双版回测...")

    comparison_rows = []
    for label, defense_ratio in configs:
        params = {**FIXED_PARAMS_BASE, "defense_ratio": defense_ratio}

        # 原版：当日成交
        print("\n  [{0}] 原版（当日成交）...".format(label))
        result_orig = run_backtest(
            prices=all_prices,
            initial_capital=1_000_000,
            params=params,
            min_days=120,
            execution_lag=0,
        )
        nav_orig = result_orig["records_df"]["nav"]
        m_orig = compute_metrics(nav_orig)
        print("    Sharpe={0:.3f}, 回撤={1:.1%}".format(m_orig["Sharpe"], m_orig["最大回撤"]))

        # 修正版：T+1 成交
        print("  [{0}] 修正版（T+1 成交）...".format(label))
        result_fixed = run_backtest(
            prices=all_prices,
            initial_capital=1_000_000,
            params=params,
            min_days=120,
            execution_lag=1,
        )
        nav_fixed = result_fixed["records_df"]["nav"]
        m_fixed = compute_metrics(nav_fixed)
        print("    Sharpe={0:.3f}, 回撤={1:.1%}".format(m_fixed["Sharpe"], m_fixed["最大回撤"]))

        delta_sharpe = m_orig["Sharpe"] - m_fixed["Sharpe"]
        delta_return = m_orig["总收益"] - m_fixed["总收益"]
        delta_dd = m_orig["最大回撤"] - m_fixed["最大回撤"]

        comparison_rows.append({
            "配置": label,
            "原版Sharpe": m_orig["Sharpe"],
            "修正版Sharpe": m_fixed["Sharpe"],
            "ΔSharpe": delta_sharpe,
            "原版总收益": m_orig["总收益"],
            "修正版总收益": m_fixed["总收益"],
            "原版回撤": m_orig["最大回撤"],
            "修正版回撤": m_fixed["最大回撤"],
        })

    # 输出对比表
    print("\n" + "[3/3] 对比结果")
    print("=" * 70)
    print("\n{0:>10}  {1:>10}  {2:>10}  {3:>10}  {4:>10}  {5:>10}  {6:>10}".format(
        "配置", "原版Sharpe", "修正Sharpe", "ΔSharpe", "原版收益", "修正收益", "原版回撤"
    ))
    print("-" * 70)
    for r in comparison_rows:
        print("{0:>10}  {1:>10.3f}  {2:>10.3f}  {3:>+10.3f}  {4:>9.1%}  {5:>9.1%}  {6:>9.1%}".format(
            r["配置"], r["原版Sharpe"], r["修正版Sharpe"], r["ΔSharpe"],
            r["原版总收益"], r["修正版总收益"], r["原版回撤"]
        ))

    # 决策
    print("\n" + "=" * 70)
    print("决策判断（以纯防御 ΔSharpe 为准）：")
    pure_defense_row = [r for r in comparison_rows if r["配置"] == "纯防御"][0]
    pure_defense_delta = pure_defense_row["ΔSharpe"]
    print("  纯防御 ΔSharpe（原版 - 修正版）= {0:+.3f}".format(pure_defense_delta))
    if abs(pure_defense_delta) < 0.05:
        print("  → ΔSharpe < 0.05，记录结论，不修改引擎。")
    else:
        print("  → ΔSharpe ≥ 0.05，需修复引擎为 T+1 执行。")
    print("=" * 70)

    # 保存 CSV
    df = pd.DataFrame(comparison_rows)
    csv_path = os.path.join(OUTPUT_DIR, "lookahead_bias_check.csv")
    df.to_csv(csv_path, index=False)
    print("\n结果已保存至 {0}".format(csv_path))


if __name__ == "__main__":
    main()
