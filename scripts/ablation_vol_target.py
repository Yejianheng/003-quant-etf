# [2026-05-29] 新增：波动率目标 ablation — 有 vol target vs 固定等权对比

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
}


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
    total_return = (nav_series.iloc[-1] / nav_series.iloc[0]) - 1
    years = len(nav_series) / 252
    annual_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0
    annual_vol = returns.std() * np.sqrt(252)
    sharpe = annual_return / annual_vol if annual_vol > 0 else 0
    peak = nav_series.expanding().max()
    dd = (nav_series - peak) / peak
    max_dd = dd.min()
    return {
        "总收益": total_return, "年化": annual_return,
        "波动率": annual_vol, "Sharpe": sharpe, "最大回撤": max_dd,
    }


def compute_volatility_metrics(nav_series: pd.Series) -> dict:
    """计算波动率稳定性指标。"""
    returns = nav_series.pct_change().dropna()
    if len(returns) < 2:
        return {"年化波动率": 0.0, "日波动率方差": 0.0}
    daily_vol = returns.std()
    annual_vol = daily_vol * np.sqrt(252)
    # 日收益率方差 → 波动率不稳定性度量
    daily_var = returns.var()
    return {"年化波动率": annual_vol, "日波动率方差": daily_var}


def year_return(nav_series: pd.Series, year: int) -> float:
    mask = (nav_series.index >= f"{year}-01-01") & (nav_series.index <= f"{year}-12-31")
    yr = nav_series.loc[mask]
    if len(yr) < 2:
        return np.nan
    return yr.iloc[-1] / yr.iloc[0] - 1


def bull_participation(nav_series: pd.Series, bench_nav: pd.Series) -> float:
    """牛市参与率：策略收益 / 基准收益（仅在基准上涨时计算）。"""
    common = nav_series.index.intersection(bench_nav.index)
    if len(common) < 2:
        return np.nan
    s = nav_series.loc[common]
    b = bench_nav.loc[common]
    s_ret = s.iloc[-1] / s.iloc[0] - 1
    b_ret = b.iloc[-1] / b.iloc[0] - 1
    if b_ret > 0:
        return s_ret / b_ret
    return np.nan


def run_config(prices, defense_ratio, vol_scaling_enabled):
    params = {
        **FIXED_PARAMS,
        "defense_ratio": defense_ratio,
        "vol_scaling_enabled": vol_scaling_enabled,
    }
    result = run_backtest(prices=prices, initial_capital=1_000_000, params=params, min_days=120)
    records = result["records_df"]
    nav = records["nav"]
    m = compute_metrics(nav)
    vm = compute_volatility_metrics(nav)
    m.update(vm)
    m["2015收益"] = year_return(nav, 2015)
    m["2019收益"] = year_return(nav, 2019)
    # 牛市参与率（vs 沪深300）
    bench_300 = result.get("benchmark_300")
    if bench_300 is not None and len(bench_300) > 1:
        for yr in [2015, 2019, 2020]:
            m[f"{yr}参与率"] = bull_participation(
                nav[nav.index.year == yr] if any(nav.index.year == yr) else nav,
                bench_300[bench_300.index.year == yr] if any(bench_300.index.year == yr) else bench_300,
            )
    return nav, records, m


def main():
    print("=" * 70)
    print("Step 1.3: 波动率目标 Ablation — 有 vol target vs 固定等权")
    print("=" * 70)

    prices = load_all_prices()
    print(f"\n加载 ETF: {list(prices.keys())}")

    configs = [
        ("纯防御", 1.0),
        ("纯进攻", 0.0),
        ("混合", 0.70),
    ]

    all_rows = []
    for label, defense_ratio in configs:
        print(f"\n{'─' * 50}")
        print(f"  [{label}] defense_ratio={defense_ratio}")

        nav_on, rec_on, m_on = run_config(prices, defense_ratio, True)
        nav_off, rec_off, m_off = run_config(prices, defense_ratio, False)

        print(f"  有vol target: 总收益={m_on['总收益']:.1%}, Sharpe={m_on['Sharpe']:.2f}, "
              f"波动率={m_on['年化波动率']:.1%}, 回撤={m_on['最大回撤']:.1%}")
        print(f"  固定等权:     总收益={m_off['总收益']:.1%}, Sharpe={m_off['Sharpe']:.2f}, "
              f"波动率={m_off['年化波动率']:.1%}, 回撤={m_off['最大回撤']:.1%}")

        nav_on.to_csv(os.path.join(OUTPUT_DIR, f"nav_ablation_1.3_{label}_on.csv"), header=True)
        nav_off.to_csv(os.path.join(OUTPUT_DIR, f"nav_ablation_1.3_{label}_off.csv"), header=True)
        rec_on.to_csv(os.path.join(OUTPUT_DIR, f"records_ablation_1.3_{label}_on.csv"), header=True)
        rec_off.to_csv(os.path.join(OUTPUT_DIR, f"records_ablation_1.3_{label}_off.csv"), header=True)

        all_rows.append({"配置": label, "状态": "有vol target", **{k: v for k, v in m_on.items()}})
        all_rows.append({"配置": label, "状态": "固定等权", **{k: v for k, v in m_off.items()}})

    # 对比表
    print(f"\n{'=' * 70}")
    print("  波动率目标 Ablation 对比表（混合配置）")
    print(f"{'=' * 70}")
    mixed = [r for r in all_rows if r["配置"] == "混合"]
    if len(mixed) == 2:
        m_on_row = mixed[0] if mixed[0]["状态"] == "有vol target" else mixed[1]
        m_off_row = mixed[1] if mixed[0]["状态"] == "有vol target" else mixed[0]

        print(f"{'指标':<14} {'有vol target':>14} {'固定等权':>14} {'差异':>14}")
        print(f"{'─' * 58}")
        for mk in ["Sharpe", "年化波动率", "日波动率方差", "最大回撤", "2015收益", "2019收益"]:
            v_on = m_on_row.get(mk, np.nan)
            v_off = m_off_row.get(mk, np.nan)
            if isinstance(v_on, (int, float)) and not (isinstance(v_on, float) and np.isnan(v_on)):
                diff = v_on - v_off
                if mk == "Sharpe":
                    print(f"{mk:<14} {v_on:>14.2f} {v_off:>14.2f} {diff:>+14.2f}")
                elif "方差" in mk:
                    print(f"{mk:<14} {v_on:>14.6f} {v_off:>14.6f} {diff:>+14.6f}")
                else:
                    print(f"{mk:<14} {v_on:>13.1%} {v_off:>13.1%} {diff:>+13.1%}")

    df_all = pd.DataFrame(all_rows)
    csv_path = os.path.join(OUTPUT_DIR, "ablation_1.3_vol_target.csv")
    df_all.to_csv(csv_path, index=False)
    print(f"\n汇总 → {csv_path}")

    print("\n=== 步骤 1.3 完成 ===")
    return df_all


if __name__ == "__main__":
    main()
