# [2026-05-30] 新增：样本外验证 — 开发期 2014-2020 调参，验证期 2021-2026 验证

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
    "ewma_lambda": 0.94,
    "target_vol_beta": 0.10,
    "target_vol_alpha": 0.20,
    "defense_ratio": 1.00,
}


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


def filter_prices_by_dates(
    prices: dict[str, pd.DataFrame],
    start_date: str,
    end_date: str,
) -> dict[str, pd.DataFrame]:
    """按日期范围截取 prices，返回截取后的副本。"""
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    result = {}
    for name, df in prices.items():
        mask = (df.index >= start) & (df.index <= end)
        filtered = df.loc[mask].copy()
        if len(filtered) > 0:
            result[name] = filtered
    return result


def compute_metrics(nav_series: pd.Series) -> dict:
    """从净值序列计算绩效指标。"""
    if len(nav_series) < 2:
        return {}
    returns = nav_series.pct_change().dropna()
    annual_factor = 252
    total_return = (nav_series.iloc[-1] / nav_series.iloc[0]) - 1
    years = len(nav_series) / annual_factor
    annual_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0
    annual_vol = returns.std() * np.sqrt(annual_factor)
    sharpe = annual_return / annual_vol if annual_vol > 0 else 0
    peak = nav_series.expanding().max()
    dd = (nav_series - peak) / peak
    max_dd = dd.min()
    return {
        "总收益": total_return, "年化": annual_return,
        "波动率": annual_vol, "Sharpe": sharpe, "最大回撤": max_dd,
    }


def find_best_params(results: list[dict]) -> dict:
    """从参数扫描结果中选出 Sharpe 最高的那组。"""
    return max(results, key=lambda r: r.get("sharpe_ratio", -999))


def fmt_metrics(m: dict) -> dict:
    """格式化指标为字符串。"""
    return {
        "总收益": f"{m['总收益']:.1%}",
        "年化": f"{m['年化']:.1%}",
        "波动率": f"{m['波动率']:.1%}",
        "Sharpe": f"{m['Sharpe']:.2f}",
        "最大回撤": f"{m['最大回撤']:.1%}",
    }


def main():
    print("=" * 70)
    print("步骤 1: 样本外验证 — 开发期 2014-2020 / 验证期 2021-2026")
    print("=" * 70)

    all_prices = load_all_prices()
    print(f"\n加载 ETF: {list(all_prices.keys())}")
    for name, df in all_prices.items():
        print(f"  {name}: {df.index[0].date()} ~ {df.index[-1].date()} ({len(df)} 行)")

    # 按时期划分
    dev_prices = filter_prices_by_dates(all_prices, "2014-01-01", "2020-12-31")
    val_prices = filter_prices_by_dates(all_prices, "2021-01-01", "2026-12-31")

    print(f"\n开发期 ETF 数: {len(dev_prices)}")
    for name, df in dev_prices.items():
        print(f"  {name}: {df.index[0].date()} ~ {df.index[-1].date()} ({len(df)} 行)")
    print(f"验证期 ETF 数: {len(val_prices)}")

    # 全量（用于对比）
    full_prices = all_prices

    # ── 开发期参数扫描 ──
    print("\n" + "=" * 70)
    print("  [A] 开发期 2014-2020: 扫描 trend_window")
    print("=" * 70)

    trend_windows = [20, 40, 60, 80, 120]
    dev_results = []
    for tw in trend_windows:
        params = {**FIXED_PARAMS, "trend_window": tw}
        try:
            bt = run_backtest(
                prices=dev_prices,
                initial_capital=1_000_000,
                params=params,
                min_days=120,
            )
        except Exception as e:
            print(f"  trend_window={tw}: ERROR {e}")
            continue

        records = bt["records_df"]
        nav = records["nav"]
        m = compute_metrics(nav)
        m_fmt = fmt_metrics(m)
        dev_results.append({**params, **m, **bt})
        print(f"  trend_window={tw:>3}: 年化={m_fmt['年化']}, Sharpe={m_fmt['Sharpe']}, "
              f"最大回撤={m_fmt['最大回撤']}")

    if not dev_results:
        print("ERROR: 开发期扫描无有效结果")
        return

    best = find_best_params(dev_results)
    best_tw = int(best["trend_window"])
    print(f"\n  >> 开发期最优: trend_window={best_tw}, Sharpe={best['sharpe_ratio']:.2f}")

    # ── 验证期 ──
    print("\n" + "=" * 70)
    print(f"  [B] 验证期 2021-2026: trend_window={best_tw}（不调参）")
    print("=" * 70)

    best_params = {**FIXED_PARAMS, "trend_window": best_tw}
    bt_val = run_backtest(
        prices=val_prices,
        initial_capital=1_000_000,
        params=best_params,
        min_days=120,
    )
    val_nav = bt_val["records_df"]["nav"]
    val_m = compute_metrics(val_nav)
    val_fmt = fmt_metrics(val_m)
    print(f"  年化={val_fmt['年化']}, Sharpe={val_fmt['Sharpe']}, "
          f"最大回撤={val_fmt['最大回撤']}")

    # ── 全量 ──
    print("\n" + "=" * 70)
    print(f"  [C] 全量 2014-2026: trend_window={best_tw}")
    print("=" * 70)

    bt_full = run_backtest(
        prices=full_prices,
        initial_capital=1_000_000,
        params=best_params,
        min_days=120,
    )
    full_nav = bt_full["records_df"]["nav"]
    full_m = compute_metrics(full_nav)
    full_fmt = fmt_metrics(full_m)
    print(f"  年化={full_fmt['年化']}, Sharpe={full_fmt['Sharpe']}, "
          f"最大回撤={full_fmt['最大回撤']}")

    # ── 三基准（验证期） ──
    val_bench = {}
    for bname, bkey in [("沪深300", "benchmark_300"), ("创业板", "benchmark_chinext"), ("纳指", "benchmark_nasdaq")]:
        bseries = bt_val.get(bkey)
        if bseries is not None and len(bseries) > 1:
            common = val_nav.index.intersection(bseries.index)
            if len(common) > 1:
                bm = compute_metrics(bseries.loc[common])
                val_bench[bname] = bm

    # ── 对比表 ──
    print("\n" + "=" * 70)
    print("  样本外验证对比表")
    print("=" * 70)

    print(f"\n{'指标':<10} {'开发期14-20':>14} {'验证期21-26':>14} {'全量14-26':>14}")
    print(f"{'─' * 54}")
    for mk in ["总收益", "年化", "波动率", "Sharpe", "最大回撤"]:
        dv = best.get(mk, None)
        vv = val_m.get(mk, None)
        fv = full_m.get(mk, None)
        if mk == "Sharpe":
            print(f"{mk:<10} {dv:>14.2f} {vv:>14.2f} {fv:>14.2f}")
        elif isinstance(dv, (int, float)):
            print(f"{mk:<10} {dv:>13.1%} {vv:>13.1%} {fv:>13.1%}")

    # 验证期策略 vs 基准
    print(f"\n{'指标':<10} {'策略(验证期)':>14} {'沪深300':>14} {'创业板':>14} {'纳指':>14}")
    print(f"{'─' * 68}")
    for mk in ["总收益", "年化", "波动率", "Sharpe", "最大回撤"]:
        sv = val_m.get(mk)
        h3 = val_bench.get("沪深300", {}).get(mk)
        cy = val_bench.get("创业板", {}).get(mk)
        nd = val_bench.get("纳指", {}).get(mk)
        if mk == "Sharpe":
            print(f"{mk:<10} {sv:>14.2f} {h3:>14.2f} {cy:>14.2f} {nd:>14.2f}")
        elif isinstance(sv, (int, float)):
            print(f"{mk:<10} {sv:>13.1%} {h3:>13.1%} {cy:>13.1%} {nd:>13.1%}")

    # 验收
    val_sharpe = val_m.get("Sharpe", 0)
    hs300_sharpe = val_bench.get("沪深300", {}).get("Sharpe", 0)
    print(f"\n  验收: 验证期策略 Sharpe={val_sharpe:.2f} vs 沪深300 Sharpe={hs300_sharpe:.2f}")
    if val_sharpe > hs300_sharpe:
        print("  [PASS] 验证期策略 Sharpe > 沪深300 Sharpe")
    else:
        print("  [FAIL] 验证期策略 Sharpe <= 沪深300 Sharpe")

    # 保存净值
    best_nav = bt_full["records_df"]["nav"]
    best_nav.to_csv(os.path.join(OUTPUT_DIR, "nav_oos_best.csv"), header=True)
    val_nav.to_csv(os.path.join(OUTPUT_DIR, "nav_oos_validation.csv"), header=True)
    bt_full["records_df"].to_csv(os.path.join(OUTPUT_DIR, "records_oos_full.csv"), header=True)
    bt_val["records_df"].to_csv(os.path.join(OUTPUT_DIR, "records_oos_validation.csv"), header=True)

    # 保存参数扫描结果
    scan_rows = []
    for r in dev_results:
        row = {"trend_window": int(r["trend_window"])}
        for mk in ["总收益", "年化", "波动率", "Sharpe", "最大回撤"]:
            row[mk] = r.get(mk)
        scan_rows.append(row)
    pd.DataFrame(scan_rows).to_csv(
        os.path.join(OUTPUT_DIR, "oos_param_scan.csv"), index=False
    )

    print(f"\n=== 步骤 1 完成 ===")
    return {
        "best_trend_window": best_tw,
        "dev_sharpe": best.get("sharpe_ratio"),
        "val_sharpe": val_sharpe,
        "full_sharpe": full_m.get("Sharpe"),
    }


if __name__ == "__main__":
    main()
