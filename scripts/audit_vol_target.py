# [2026-05-30] 新增：Vol Target 触发审计 — 扫描纯防御全量回测中 scaling_factor != 1.0 的交易日
"""
扫描纯防御 2014-2026 回测记录，提取 vol target 实际触发的交易日，
回答：12 年纯防御中 vol target 是否触发过、触发几次、效果如何。
"""
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


def load_all_prices():
    prices = {}
    for name, code in {**DEFENSE_MAP, **OFFENSE_MAP}.items():
        fpath = os.path.join(DATA_DIR, f"{code}.parquet")
        if os.path.exists(fpath):
            df = pd.read_parquet(fpath)
            if all(c in df.columns for c in ["open", "high", "low", "close"]):
                prices[name] = df
    return prices


def compute_sharpe_from_records(records: pd.DataFrame) -> float:
    """从 records 的 nav 列计算年化 Sharpe。"""
    nav = records["nav"].values
    if len(nav) < 2:
        return 0.0
    daily_returns = np.diff(nav) / nav[:-1]
    n = len(records)
    annual_return = (nav[-1] / nav[0]) ** (252 / n) - 1
    annual_vol = float(np.std(daily_returns, ddof=1) * np.sqrt(252))
    return annual_return / annual_vol if annual_vol > 0 else 0.0


def main():
    print("=" * 80)
    print("Vol Target 触发审计 — 纯防御 全量 2014-2026")
    print("=" * 80)

    prices = load_all_prices()
    print(f"\n加载 ETF: {list(prices.keys())}")

    params = {
        "trend_window": 40,
        "ewma_lambda": 0.94,
        "target_vol_beta": 0.10,
        "defense_ratio": 1.0,
        "vol_scaling_enabled": True,
    }
    print("\n运行纯防御回测（vol target ON）...")
    result = run_backtest(
        prices=prices,
        initial_capital=1_000_000,
        params=params,
        min_days=120,
    )
    records = result["records_df"]
    print(f"回测完成：{len(records)} 个交易日，{records.index[0].date()} ~ {records.index[-1].date()}")

    sf_col = "scaling_factor"
    triggered = records[records[sf_col] != 1.0].copy()

    if len(triggered) == 0:
        print("\n>>> 结论：纯防御 12 年 vol target 从未触发（scaling_factor 始终 = 1.0）<<<")
        return

    print(f"\n触发明细：{len(triggered)} 个交易日（占 {len(records)} 的 {len(triggered)/len(records):.1%}）\n")

    output_rows = []
    for idx, row in triggered.iterrows():
        output_rows.append({
            "触发日期": str(idx.date()),
            "scaling_factor": round(row["scaling_factor"], 4),
            "predicted_vol": round(row.get("predicted_vol", 0), 4),
            "active_count": int(row.get("defense_count", 0)),
            "熔断触发": bool(row.get("circuit_breaker_triggered", False)),
        })

    df_detail = pd.DataFrame(output_rows)
    print(df_detail.to_string(index=False))

    total_days = len(records)
    triggered_days = len(triggered)
    sf_mean = triggered["scaling_factor"].mean()
    sf_min = triggered["scaling_factor"].min()
    sf_max = triggered["scaling_factor"].max()

    sharpe_full = compute_sharpe_from_records(records)

    triggered_indices = [records.index.get_loc(i) for i in triggered.index]
    window_indices = set()
    for ti in triggered_indices:
        for offset in range(-20, 21):
            wi = ti + offset
            if 0 <= wi < len(records):
                window_indices.add(wi)
    triggered_window = records.iloc[sorted(window_indices)]
    sharpe_triggered_window = compute_sharpe_from_records(triggered_window)
    sharpe_triggered_only = compute_sharpe_from_records(triggered)

    print(f"\n{'─' * 50}")
    print("统计汇总")
    print(f"{'─' * 50}")
    stats = [
        ("总交易日", total_days),
        ("sf != 1.0 的天数", triggered_days),
        ("占比", f"{triggered_days / total_days:.2%}"),
        ("sf 均值（触发时）", f"{sf_mean:.4f}"),
        ("sf 最小值", f"{sf_min:.4f}"),
        ("sf 最大值", f"{sf_max:.4f}"),
        ("sf < 0.5 的天数", int((triggered["scaling_factor"] < 0.5).sum())),
        ("sf < 0.8 的天数", int((triggered["scaling_factor"] < 0.8).sum())),
        ("熔断同时触发的天数", int(triggered["circuit_breaker_triggered"].sum())),
        ("触发期间 Sharpe（仅触发日）", f"{sharpe_triggered_only:.2f}"),
        ("触发期间 ±20d 窗口 Sharpe", f"{sharpe_triggered_window:.2f}"),
        ("全区间 Sharpe", f"{sharpe_full:.2f}"),
    ]
    for label, val in stats:
        print(f"  {label:<32} {val}")

    df_detail.to_csv(os.path.join(OUTPUT_DIR, "audit_vol_target_detail.csv"), index=False)
    records.to_csv(os.path.join(OUTPUT_DIR, "records_audit_vol_target.csv"))
    print(f"\n明细 → {OUTPUT_DIR}/audit_vol_target_detail.csv")
    print(f"全量 records → {OUTPUT_DIR}/records_audit_vol_target.csv")
    print("\n=== Vol Target 触发审计完成 ===")


if __name__ == "__main__":
    main()
