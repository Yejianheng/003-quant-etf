# [2026-05-29] 新增：EWMA 协方差 ablation — EWMA λ=0.94 vs 简单历史协方差

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


def year_return(nav_series: pd.Series, year: int) -> float:
    mask = (nav_series.index >= f"{year}-01-01") & (nav_series.index <= f"{year}-12-31")
    yr = nav_series.loc[mask]
    if len(yr) < 2:
        return np.nan
    return yr.iloc[-1] / yr.iloc[0] - 1


def crisis_drawdown_speed(nav_series: pd.Series, start: str, end: str) -> dict:
    """计算危机期间回撤速度：最大回撤 / 从峰到谷的天数。"""
    mask = (nav_series.index >= start) & (nav_series.index <= end)
    crisis_nav = nav_series.loc[mask]
    if len(crisis_nav) < 2:
        return {"crisis_max_dd": np.nan, "peak_to_trough_days": np.nan, "dd_speed_per_day": np.nan}
    peak = crisis_nav.expanding().max()
    dd = (crisis_nav - peak) / peak
    max_dd = dd.min()
    trough_idx = dd.idxmin()
    peak_before = peak.loc[:trough_idx]
    peak_idx = peak_before[peak_before == peak_before.max()].index[0]
    days = (trough_idx - peak_idx).days
    speed = abs(max_dd) / days if days > 0 else np.nan
    return {"crisis_max_dd": max_dd, "peak_to_trough_days": days, "dd_speed_per_day": speed}


def run_config(prices, defense_ratio, covariance_method):
    params = {
        **FIXED_PARAMS,
        "defense_ratio": defense_ratio,
        "covariance_method": covariance_method,
    }
    result = run_backtest(prices=prices, initial_capital=1_000_000, params=params, min_days=120)
    records = result["records_df"]
    nav = records["nav"]
    m = compute_metrics(nav)
    m["2020收益"] = year_return(nav, 2020)
    m["2022收益"] = year_return(nav, 2022)
    # 危机缩仓速度
    covid = crisis_drawdown_speed(nav, "2020-02-01", "2020-04-30")
    bear22 = crisis_drawdown_speed(nav, "2022-01-01", "2022-12-31")
    m["2020回撤"] = covid["crisis_max_dd"]
    m["2020缩仓天数"] = covid["peak_to_trough_days"]
    m["2022回撤"] = bear22["crisis_max_dd"]
    m["2022缩仓天数"] = bear22["peak_to_trough_days"]
    return nav, records, m


def main():
    print("=" * 70)
    print("Step 1.4: EWMA 协方差 Ablation — EWMA λ=0.94 vs 历史协方差（等权）")
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

        nav_ewma, rec_ewma, m_ewma = run_config(prices, defense_ratio, "ewma")
        nav_hist, rec_hist, m_hist = run_config(prices, defense_ratio, "historical")

        print(f"  EWMA(λ=0.94):  总收益={m_ewma['总收益']:.1%}, Sharpe={m_ewma['Sharpe']:.2f}, "
              f"2020回撤={m_ewma['2020回撤']:.1%}, 2022回撤={m_ewma['2022回撤']:.1%}")
        print(f"  历史协方差:     总收益={m_hist['总收益']:.1%}, Sharpe={m_hist['Sharpe']:.2f}, "
              f"2020回撤={m_hist['2020回撤']:.1%}, 2022回撤={m_hist['2022回撤']:.1%}")

        nav_ewma.to_csv(os.path.join(OUTPUT_DIR, f"nav_ablation_1.4_{label}_ewma.csv"), header=True)
        nav_hist.to_csv(os.path.join(OUTPUT_DIR, f"nav_ablation_1.4_{label}_hist.csv"), header=True)
        rec_ewma.to_csv(os.path.join(OUTPUT_DIR, f"records_ablation_1.4_{label}_ewma.csv"), header=True)
        rec_hist.to_csv(os.path.join(OUTPUT_DIR, f"records_ablation_1.4_{label}_hist.csv"), header=True)

        all_rows.append({"配置": label, "状态": "EWMA λ=0.94", **{k: v for k, v in m_ewma.items()}})
        all_rows.append({"配置": label, "状态": "历史协方差", **{k: v for k, v in m_hist.items()}})

    # 对比表
    print(f"\n{'=' * 70}")
    print("  EWMA 协方差 Ablation 对比表（混合配置）")
    print(f"{'=' * 70}")
    mixed = [r for r in all_rows if r["配置"] == "混合"]
    if len(mixed) == 2:
        m_ewma = mixed[0] if mixed[0]["状态"] == "EWMA λ=0.94" else mixed[1]
        m_hist = mixed[1] if mixed[0]["状态"] == "EWMA λ=0.94" else mixed[0]

        print(f"{'指标':<14} {'EWMA λ=0.94':>14} {'历史协方差':>14} {'差异':>14}")
        print(f"{'─' * 58}")
        for mk in ["Sharpe", "最大回撤", "2020回撤", "2020缩仓天数", "2022回撤", "2022缩仓天数"]:
            v_ewma = m_ewma.get(mk, np.nan)
            v_hist = m_hist.get(mk, np.nan)
            if isinstance(v_ewma, (int, float)) and not (isinstance(v_ewma, float) and np.isnan(v_ewma)):
                diff = v_ewma - v_hist
                if mk in ("Sharpe",):
                    print(f"{mk:<14} {v_ewma:>14.2f} {v_hist:>14.2f} {diff:>+14.2f}")
                elif "天数" in mk:
                    print(f"{mk:<14} {v_ewma:>14.0f} {v_hist:>14.0f} {diff:>+14.0f}")
                else:
                    print(f"{mk:<14} {v_ewma:>13.1%} {v_hist:>13.1%} {diff:>+13.1%}")

    df_all = pd.DataFrame(all_rows)
    csv_path = os.path.join(OUTPUT_DIR, "ablation_1.4_ewma.csv")
    df_all.to_csv(csv_path, index=False)
    print(f"\n汇总 → {csv_path}")

    print("\n=== 步骤 1.4 完成 ===")
    return df_all


if __name__ == "__main__":
    main()
