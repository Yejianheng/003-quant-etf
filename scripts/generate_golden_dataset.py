# [2026-05-30] 新增：Golden Dataset 生成器 — 固定数据+参数运行回测，输出不可变基准
"""
生成永不变化的基准样本。任何引擎改动后 golden 测试必须绿灯。
用法: python scripts/generate_golden_dataset.py
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
    "沪深300": "510300",
    "创业板": "159915",
    "纳指": "513100",
    "黄金": "518880",
    "国债ETF": "511010",
}

FIXED_PARAMS = {
    "trend_window": 40,
    "ewma_lambda": 0.94,
    "target_vol_beta": 0.10,
    "corr_threshold": 0.0,
    "defense_ratio": 1.0,
}

INITIAL_CAPITAL = 1_000_000
MIN_DAYS = 120
CUTOFF_DATE = pd.Timestamp("2022-12-31")


def load_and_cutoff(code: str) -> pd.DataFrame | None:
    fpath = os.path.join(DATA_DIR, f"{code}.parquet")
    if not os.path.exists(fpath):
        return None
    df = pd.read_parquet(fpath)
    required = ["open", "high", "low", "close"]
    for col in required:
        if col not in df.columns:
            return None
    df = df[df.index <= CUTOFF_DATE]
    return df


def main():
    print("=== Golden Dataset 生成 ===\n")
    print(f"截止日期: {CUTOFF_DATE.date()}")
    print(f"固定参数: {FIXED_PARAMS}")

    print("\n[1/3] 加载防御层数据...")
    prices = {}
    for name, code in DEFENSE_MAP.items():
        df = load_and_cutoff(code)
        if df is not None:
            prices[name] = df
            print(f"  {name} ({code}): {df.index[0].date()} ~ {df.index[-1].date()} ({len(df)} 行)")

    if len(prices) != 5:
        print(f"ERROR: 预期 5 只防御 ETF，实际加载 {len(prices)} 只")
        sys.exit(1)

    print("\n[2/3] 运行纯防御回测...")
    result = run_backtest(
        prices=prices,
        initial_capital=INITIAL_CAPITAL,
        params=FIXED_PARAMS,
        min_days=MIN_DAYS,
    )

    records = result["records_df"]
    recorder = result.get("_recorder", None)
    print(f"  回测天数: {len(records)}")
    print(f"  最终 NAV: {result['final_nav']:,.2f}")
    print(f"  Sharpe: {result['sharpe_ratio']:.2f}")

    print("\n[3/3] 保存 golden 基准文件...")

    # golden_nav.csv
    nav_df = records[["nav"]].copy()
    nav_df.index.name = "date"
    nav_df.to_csv(os.path.join(OUTPUT_DIR, "golden_nav.csv"), header=True)
    print(f"  golden_nav.csv: {len(nav_df)} 行")

    # golden_signals.csv
    signal_cols = [
        "exposure", "repo_amount", "final_multiplier",
        "circuit_breaker_triggered", "drawdown_level", "drawdown",
        "n_positions", "position_names", "defense_active",
        "scaling_factor", "predicted_vol", "defense_count",
    ]
    signals_df = records[signal_cols].copy()
    signals_df.index.name = "date"
    signals_df.to_csv(os.path.join(OUTPUT_DIR, "golden_signals.csv"), header=True)
    print(f"  golden_signals.csv: {len(signals_df)} 行")

    # golden_positions.csv
    if recorder is not None and recorder.get("positions_detail"):
        pos_df = pd.DataFrame(recorder["positions_detail"])
        pos_df["date"] = pd.to_datetime(pos_df["date"])
        pos_df = pos_df.set_index("date").sort_index()
        pos_df.to_csv(os.path.join(OUTPUT_DIR, "golden_positions.csv"), header=True)
        print(f"  golden_positions.csv: {len(pos_df)} 行, {len(pos_df.columns)} 列 {list(pos_df.columns)}")
    else:
        print("  WARNING: positions_detail 为空")

    # golden_trades.csv
    if recorder is not None and recorder.get("positions_detail"):
        pos_df = pd.DataFrame(recorder["positions_detail"])
        pos_df["date"] = pd.to_datetime(pos_df["date"])
        pos_df = pos_df.set_index("date").sort_index()
        trades = []
        prev = {}
        for dt, row in pos_df.iterrows():
            for col in pos_df.columns:
                cur_val = row.get(col, 0.0) if pd.notna(row.get(col)) else 0.0
                prev_val = prev.get(col, 0.0)
                delta = cur_val - prev_val
                if abs(delta) > 1.0:
                    trades.append({
                        "date": dt,
                        "etf": col,
                        "action": "buy" if delta > 0 else "sell",
                        "amount": abs(delta),
                    })
                prev[col] = cur_val
        trades_df = pd.DataFrame(trades)
        if not trades_df.empty:
            trades_df = trades_df.sort_values(["date", "etf"]).reset_index(drop=True)
        trades_df.to_csv(os.path.join(OUTPUT_DIR, "golden_trades.csv"), index=False)
        print(f"  golden_trades.csv: {len(trades_df)} 条交易")

    print("\n=== Golden Dataset 生成完成 ===")


if __name__ == "__main__":
    main()
