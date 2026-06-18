#!/usr/bin/env python
# [2026-06-18] 修改：传递 records_df 到 generate_four_tables_report，支持逆回购统计
# [2026-06-18] 新增：四张表收益归因入口脚本
"""策略收益归因 — 四张表全量审计。输出 output/four_tables_report.html"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
import numpy as np
from src.data_pipeline import fetch_etf_daily
from src.backtest_engine import run_backtest
from attribution.factor_return import factor_attribution
from attribution.timing import timing_decomposition
from attribution.tail_risk import tail_risk_audit
from attribution.stability import stability_matrix
from attribution.report import generate_four_tables_report

BASE = os.path.join(os.path.dirname(__file__), "..")
DATA_DIR = os.path.join(BASE, "data")
OUTPUT_DIR = os.path.join(BASE, "output")

ETF_CODES = {"沪深300": "510300", "创业板": "159915", "纳指": "513100", "黄金": "518880", "国债ETF": "511010"}


def main():
    print("=" * 60)
    print("策略收益归因 — 四张表全量审计")
    print("=" * 60)

    print("\n[1/5] 加载 ETF 日线数据...")
    prices = {}
    for name, code in ETF_CODES.items():
        path = os.path.join(DATA_DIR, f"{code}.parquet")
        if os.path.exists(path):
            prices[name] = pd.read_parquet(path)
        else:
            print(f"  ⚠ {name}({code}) 数据缺失: {path}")

    if not prices:
        print("无可用数据，退出。")
        return

    print("\n[2/5] 运行回测...")
    result = run_backtest(prices, initial_capital=1_000_000)

    records_df = result["records_df"]
    nav = records_df["nav"]
    strategy_returns = nav.pct_change().dropna()

    print(f"  回测区间: {nav.index[0].date()} ~ {nav.index[-1].date()}")
    print(f"  交易日: {len(strategy_returns)}")

    factor_returns = {}
    for name in ETF_CODES:
        if name in prices:
            close = prices[name]["close"]
            ret = close.pct_change().dropna()
            factor_returns[name] = ret

    factor_df = pd.DataFrame(factor_returns)
    common_dates = strategy_returns.index.intersection(factor_df.index)
    strategy_returns = strategy_returns.loc[common_dates]
    factor_df = factor_df.loc[common_dates]

    benchmark_returns = factor_df.mean(axis=1)

    print("\n[3/5] 计算四张表...")
    print("  → 表 1: 因子归因")
    fa = factor_attribution(strategy_returns, factor_df)

    print("  → 表 2: 择时分解")
    td = timing_decomposition(strategy_returns, benchmark_returns)

    print("  → 表 3: 尾部审计")
    tr = tail_risk_audit(strategy_returns, benchmark_returns)

    print("  → 表 4: 稳定性矩阵")
    extreme_periods = {
        "2015 暴跌": (pd.Timestamp("2015-06-12"), pd.Timestamp("2015-08-26")),
        "2018 熊市": (pd.Timestamp("2018-01-24"), pd.Timestamp("2018-12-28")),
        "2020 熔断": (pd.Timestamp("2020-02-03"), pd.Timestamp("2020-03-23")),
        "2022 加息": (pd.Timestamp("2022-01-04"), pd.Timestamp("2022-10-31")),
    }
    sm = stability_matrix(daily_returns=strategy_returns, extreme_periods=extreme_periods)

    print("\n[4/5] 生成报表...")
    results = {"factor_return": fa, "timing": td, "tail_risk": tr, "stability": sm}
    report_path = os.path.join(OUTPUT_DIR, "four_tables_report.html")
    generate_four_tables_report(results, report_path, records_df=records_df)

    print(f"\n[5/5] 完成！报表: {report_path}")
    print("=" * 60)

    _print_summary(fa, td, tr, sm)


def _print_summary(fa, td, tr, sm):
    print("\n四张表摘要:")
    print(f"  因子归因: R2={_s(fa.get('r_squared'))}  alpha={_s(fa.get('alpha'))}")
    print(f"  择时分解: 择时系数={_s(td.get('timing_coefficient'))}  月胜率={_s(td.get('monthly_win_rate'))}")
    print(f"  尾部审计: 偏度={_s(tr.get('skewness'))}  卖保险={'是' if tr.get('insurance_sell_warning') else '否'}")
    rs = sm.get("rolling_sharpe", {})
    print(f"  稳定性:  滚动Sharpe min={_s(rs.get('min'))}  mean={_s(rs.get('mean'))}")


def _s(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    if isinstance(v, float):
        return f"{v:.4f}"
    return str(v)


if __name__ == "__main__":
    main()
