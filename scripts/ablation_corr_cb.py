# [2026-05-30] 新增：相关性熔断 ablation — 有熔断 vs 无熔断对比

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


def count_cb_triggers(records: pd.DataFrame) -> int:
    """统计熔断触发总天数。"""
    if "circuit_breaker_triggered" not in records.columns:
        return 0
    return int(records["circuit_breaker_triggered"].sum())


def run_config(prices, defense_ratio, corr_threshold):
    params = {
        **FIXED_PARAMS,
        "defense_ratio": defense_ratio,
        "corr_threshold": corr_threshold,
    }
    result = run_backtest(prices=prices, initial_capital=1_000_000, params=params, min_days=120)
    records = result["records_df"]
    nav = records["nav"]
    m = compute_metrics(nav)
    m["2022收益"] = year_return(nav, 2022)
    m["2018收益"] = year_return(nav, 2018)
    m["熔断触发次数"] = count_cb_triggers(records)
    return nav, records, m


def main():
    print("=" * 70)
    print("Step 1.5: 相关性熔断 Ablation — 有熔断 vs 无熔断")
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

        nav_on, rec_on, m_on = run_config(prices, defense_ratio, 0.0)
        nav_off, rec_off, m_off = run_config(prices, defense_ratio, 2.0)

        print(f"  有熔断:   总收益={m_on['总收益']:.1%}, Sharpe={m_on['Sharpe']:.2f}, "
              f"最大回撤={m_on['最大回撤']:.1%}, 2022={m_on['2022收益']:.1%}, "
              f"熔断={m_on['熔断触发次数']}天")
        print(f"  无熔断:   总收益={m_off['总收益']:.1%}, Sharpe={m_off['Sharpe']:.2f}, "
              f"最大回撤={m_off['最大回撤']:.1%}, 2022={m_off['2022收益']:.1%}, "
              f"熔断={m_off['熔断触发次数']}天")

        nav_on.to_csv(os.path.join(OUTPUT_DIR, f"nav_ablation_1.5_{label}_on.csv"), header=True)
        nav_off.to_csv(os.path.join(OUTPUT_DIR, f"nav_ablation_1.5_{label}_off.csv"), header=True)
        rec_on.to_csv(os.path.join(OUTPUT_DIR, f"records_ablation_1.5_{label}_on.csv"), header=True)
        rec_off.to_csv(os.path.join(OUTPUT_DIR, f"records_ablation_1.5_{label}_off.csv"), header=True)

        all_rows.append({"配置": label, "状态": "有熔断", **{k: v for k, v in m_on.items()}})
        all_rows.append({"配置": label, "状态": "无熔断", **{k: v for k, v in m_off.items()}})

    print(f"\n{'=' * 70}")
    print("  相关性熔断 Ablation 对比表（混合配置）")
    print(f"{'=' * 70}")
    mixed = [r for r in all_rows if r["配置"] == "混合"]
    if len(mixed) == 2:
        m_on = mixed[0] if mixed[0]["状态"] == "有熔断" else mixed[1]
        m_off = mixed[1] if mixed[0]["状态"] == "有熔断" else mixed[0]

        print(f"{'指标':<14} {'有熔断':>14} {'无熔断':>14} {'差异':>14}")
        print(f"{'─' * 58}")
        for mk in ["总收益", "最大回撤", "Sharpe", "2022收益", "2018收益"]:
            v_on = m_on.get(mk, np.nan)
            v_off = m_off.get(mk, np.nan)
            if isinstance(v_on, (int, float)) and not np.isnan(v_on):
                diff = v_on - v_off
                if mk == "Sharpe":
                    print(f"{mk:<14} {v_on:>14.2f} {v_off:>14.2f} {diff:>+14.2f}")
                else:
                    print(f"{mk:<14} {v_on:>13.1%} {v_off:>13.1%} {diff:>+13.1%}")
        print(f"{'熔断触发次数':<14} {m_on['熔断触发次数']:>14.0f} "
              f"{m_off['熔断触发次数']:>14.0f} "
              f"{m_on['熔断触发次数'] - m_off['熔断触发次数']:>+14.0f}")

    df_all = pd.DataFrame(all_rows)
    csv_path = os.path.join(OUTPUT_DIR, "ablation_1.5_corr_cb.csv")
    df_all.to_csv(csv_path, index=False)
    print(f"\n汇总 → {csv_path}")

    print("\n=== 步骤 1.5 完成 ===")
    return df_all


if __name__ == "__main__":
    main()
