# [2026-05-29] 新增：趋势过滤 ablation — 有/无 MA40 趋势过滤对比

import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.backtest_engine import run_backtest
from src.signal_generator import DEFENSE_NAMES

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

WHIPSAW_WINDOW = 20


def load_all_prices():
    """加载所有 ETF 的 OHLCV 数据。"""
    prices = {}
    for name, code in {**DEFENSE_MAP, **OFFENSE_MAP}.items():
        fpath = os.path.join(DATA_DIR, f"{code}.parquet")
        if os.path.exists(fpath):
            df = pd.read_parquet(fpath)
            if all(c in df.columns for c in ["open", "high", "low", "close"]):
                prices[name] = df
    return prices


def compute_metrics(nav_series: pd.Series) -> dict:
    """从净值序列计算绩效指标。"""
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
    """提取指定年份收益。"""
    mask = (nav_series.index >= f"{year}-01-01") & (nav_series.index <= f"{year}-12-31")
    yr = nav_series.loc[mask]
    if len(yr) < 2:
        return np.nan
    return yr.iloc[-1] / yr.iloc[0] - 1


def parse_etf_list(s):
    """解析分号分隔的 ETF 列表字符串。"""
    if s is None or (isinstance(s, float) and np.isnan(s)):
        return []
    s = str(s).strip()
    if not s or s.lower() == "nan":
        return []
    return [x.strip() for x in s.split(";") if x.strip()]


def count_whipsaws(records: pd.DataFrame) -> int:
    """统计防御层 ETF 的 whipsaw 次数（20 日内先进后出）。"""
    da_col = records["defense_active"].fillna("").astype(str)
    total = 0
    for etf in DEFENSE_NAMES:
        mask = da_col.apply(lambda s: etf in parse_etf_list(s))
        changed = mask != mask.shift(1)
        changed.iloc[0] = False
        flips = changed[changed]
        if len(flips) < 2:
            continue
        flip_list = [(dt, mask.loc[dt]) for dt in flips.index]
        i = 0
        while i < len(flip_list) - 1:
            dt_a, active_a = flip_list[i]
            dt_b, active_b = flip_list[i + 1]
            if active_a and not active_b:
                delta = (dt_b - dt_a).days
                if delta <= WHIPSAW_WINDOW:
                    total += 1
                    i += 2
                    continue
            i += 1
    return total


def run_config(prices, defense_ratio, trend_filter_enabled):
    """运行单个配置，返回 (nav, records, metrics)。"""
    params = {
        **FIXED_PARAMS,
        "defense_ratio": defense_ratio,
        "trend_filter_enabled": trend_filter_enabled,
    }
    result = run_backtest(prices=prices, initial_capital=1_000_000, params=params, min_days=120)
    records = result["records_df"]
    nav = records["nav"]
    m = compute_metrics(nav)
    m["2018收益"] = year_return(nav, 2018)
    m["2022收益"] = year_return(nav, 2022)
    m["whipsaw_count"] = count_whipsaws(records)
    return nav, records, m


def main():
    print("=" * 70)
    print("Step 1.2: 趋势过滤 Ablation — 有 MA40 vs 无趋势过滤（全仓等权）")
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

        print(f"  有趋势过滤: 总收益={m_on['总收益']:.1%}, Sharpe={m_on['Sharpe']:.2f}, "
              f"最大回撤={m_on['最大回撤']:.1%}, whipsaw={m_on['whipsaw_count']}")
        print(f"  无趋势过滤: 总收益={m_off['总收益']:.1%}, Sharpe={m_off['Sharpe']:.2f}, "
              f"最大回撤={m_off['最大回撤']:.1%}, whipsaw={m_off['whipsaw_count']}")

        nav_on.to_csv(os.path.join(OUTPUT_DIR, f"nav_ablation_1.2_{label}_on.csv"), header=True)
        nav_off.to_csv(os.path.join(OUTPUT_DIR, f"nav_ablation_1.2_{label}_off.csv"), header=True)
        rec_on.to_csv(os.path.join(OUTPUT_DIR, f"records_ablation_1.2_{label}_on.csv"), header=True)
        rec_off.to_csv(os.path.join(OUTPUT_DIR, f"records_ablation_1.2_{label}_off.csv"), header=True)

        all_rows.append({
            "配置": label, "状态": "有趋势过滤",
            **{k: v for k, v in m_on.items()},
        })
        all_rows.append({
            "配置": label, "状态": "无趋势过滤",
            **{k: v for k, v in m_off.items()},
        })

    # 对比表
    print(f"\n{'=' * 70}")
    print("  趋势过滤 Ablation 对比表（混合配置）")
    print(f"{'=' * 70}")
    mixed = [r for r in all_rows if r["配置"] == "混合"]
    if len(mixed) == 2:
        m_on_row = mixed[0] if mixed[0]["状态"] == "有趋势过滤" else mixed[1]
        m_off_row = mixed[1] if mixed[0]["状态"] == "有趋势过滤" else mixed[0]

        print(f"{'指标':<12} {'有趋势过滤':>14} {'无趋势过滤':>14} {'差异':>14}")
        print(f"{'─' * 56}")
        for mk in ["总收益", "最大回撤", "Sharpe", "2018收益", "2022收益"]:
            v_on = m_on_row[mk]
            v_off = m_off_row[mk]
            if isinstance(v_on, (int, float)) and not np.isnan(v_on):
                diff = v_on - v_off
                if mk == "Sharpe":
                    print(f"{mk:<12} {v_on:>14.2f} {v_off:>14.2f} {diff:>+14.2f}")
                else:
                    print(f"{mk:<12} {v_on:>13.1%} {v_off:>13.1%} {diff:>+13.1%}")
        print(f"{'whipsaw次数':<12} {m_on_row['whipsaw_count']:>14d} "
              f"{m_off_row['whipsaw_count']:>14d} "
              f"{m_on_row['whipsaw_count'] - m_off_row['whipsaw_count']:>+14d}")

    df_all = pd.DataFrame(all_rows)
    csv_path = os.path.join(OUTPUT_DIR, "ablation_1.2_trend_filter.csv")
    df_all.to_csv(csv_path, index=False)
    print(f"\n汇总 → {csv_path}")

    print("\n=== 步骤 1.2 完成 ===")
    return df_all


if __name__ == "__main__":
    main()
