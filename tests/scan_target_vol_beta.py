# [2026-06-12] 新增：target_vol_beta 严谨扫描 — 容忍带等比 + 分半验证 + 最差滚动年
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd
from src.portfolio_manager import allocate_capital as _original_allocate

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
ETF_CODE_MAP = {
    "沪深300": "510300", "创业板": "159915", "纳指": "513100",
    "黄金": "518880", "国债ETF": "511010",
}

def allocate_fixed(signal, total_capital, defense_ratio=0.70):
    defense_pool = total_capital * defense_ratio
    offense_pool = total_capital * (1 - defense_ratio)
    final_mult = signal["execution"]["final_multiplier"]
    defense_pool *= final_mult
    offense_pool *= final_mult
    if signal["circuit_breaker"]["triggered"]:
        return {"date": signal["date"], "total_capital": total_capital,
                "positions": {}, "defense_total": 0.0, "offense_total": 0.0,
                "repo_amount": total_capital, "exposure": 0.0, "exposure_ratio": 0.0}
    positions = {}
    for name, weight in signal["defense"]["target_weights"].items():
        positions[name] = defense_pool * weight
    offense_weights = signal["offense"]["target_weights"]
    if offense_weights:
        for name, weight in offense_weights.items():
            positions[name] = offense_pool * weight
        repo_amount = 0.0
    else:
        repo_amount = offense_pool
    exposure = sum(positions.values())
    repo_amount += total_capital - exposure - repo_amount
    return {"date": signal["date"], "total_capital": total_capital,
            "positions": positions, "defense_total": defense_pool,
            "offense_total": offense_pool if offense_weights else 0.0,
            "repo_amount": repo_amount, "exposure": exposure,
            "exposure_ratio": exposure / total_capital}

def load_prices():
    prices = {}
    for name, code in ETF_CODE_MAP.items():
        fpath = os.path.join(DATA_DIR, f"{code}.parquet")
        if os.path.exists(fpath):
            df = pd.read_parquet(fpath)
            if "close" in df.columns:
                prices[name] = df
    return prices

def rolling_12m_worst(nav_series):
    daily_ret = nav_series.pct_change().dropna()
    if len(daily_ret) < 252:
        return None, None, None
    def sharpe_252(x):
        return (x.mean()*252)/(x.std()*np.sqrt(252)) if x.std()>0 else 0
    rolling = daily_ret.rolling(252).apply(sharpe_252)
    min_idx = rolling.idxmin()
    # 计算这个窗口的收益和回撤
    end_loc = nav_series.index.get_loc(min_idx)
    start_loc = max(0, end_loc - 251)
    w = nav_series.iloc[start_loc:end_loc+1]
    ret = (w.iloc[-1]/w.iloc[0]) - 1
    dd = (w - w.cummax()).min() / w.cummax().max()
    return rolling.min(), ret, dd

def run_backtest_with_beta(prices, beta, vol_tol):
    import src.backtest_engine as be
    be.allocate_capital = allocate_fixed
    from src.backtest_engine import run_backtest
    result = run_backtest(
        prices, initial_capital=1_000_000,
        params={"defense_ratio": 1.00, "target_vol_beta": beta, "vol_tolerance": vol_tol},
        execution_lag=1,
    )
    be.allocate_capital = _original_allocate
    return result

def main():
    prices = load_prices()
    if len(prices) < 5:
        print("ERROR: 数据不完整"); return

    # 全量日期 → 切分前后半
    all_dates = sorted(set.union(*[set(df.index) for df in prices.values()]))
    mid = len(all_dates) // 2
    mid_date = all_dates[mid]

    prices_first = {}
    prices_second = {}
    for name, df in prices.items():
        df1 = df[df.index < mid_date]
        df2 = df[df.index >= mid_date]
        if len(df1) > 120: prices_first[name] = df1
        if len(df2) > 120: prices_second[name] = df2

    # 容忍带等比缩放：基准 0.10→0.015
    betas = [0.04, 0.06, 0.08, 0.10, 0.12, 0.15, 0.18, 0.22]

    print("=" * 90)
    print("target_vol_beta 严谨扫描（容忍带等比、前后半验证、最差滚动12月）")
    print("=" * 90)

    rows = []
    for beta in betas:
        vol_tol = beta * 0.15  # 等比容忍带（= beta × 15%）

        bt_full = run_backtest_with_beta(prices, beta, vol_tol)
        nav_full = bt_full["records_df"]["nav"]
        worst_sharpe, worst_ret, worst_dd = rolling_12m_worst(nav_full)
        # 逐年最差
        yearly = nav_full.resample("YE").apply(
            lambda s: (s.iloc[-1]/s.iloc[0]-1) if len(s)>1 else 0
        )
        worst_year_ret = yearly.min()

        bt_first = run_backtest_with_beta(prices_first, beta, vol_tol)
        bt_second = run_backtest_with_beta(prices_second, beta, vol_tol)

        rows.append({
            "beta": beta,
            "sharpe_full": bt_full["sharpe_ratio"],
            "ret_full": bt_full["total_return"],
            "ann_full": bt_full["annual_return"],
            "vol_full": bt_full["annual_volatility"],
            "dd_full": bt_full["max_drawdown"],
            "sharpe_1st": bt_first["sharpe_ratio"],
            "dd_1st": bt_first["max_drawdown"],
            "sharpe_2nd": bt_second["sharpe_ratio"],
            "dd_2nd": bt_second["max_drawdown"],
            "worst_12m_sharpe": worst_sharpe,
            "worst_12m_ret": worst_ret,
            "worst_12m_dd": worst_dd,
            "worst_year_ret": worst_year_ret,
        })

    # 表1: 全量 + 分半
    print(f"\n{'beta':<8} {'全Sharpe':>8} {'全回撤':>8} {'前半Sharpe':>8} {'前半回撤':>8} "
          f"{'后半Sharpe':>8} {'后半回撤':>8} {'最差12M Sharpe':>13} {'最差12M回撤':>10} {'最差年收益':>10}")
    print("-" * 105)
    for r in rows:
        ws = f"{r['worst_12m_sharpe']:.3f}" if r['worst_12m_sharpe'] is not None else "N/A"
        wr = f"{r['worst_12m_dd']*100:.1f}%" if r['worst_12m_dd'] is not None else "N/A"
        print(f"{r['beta']:<8.2f} {r['sharpe_full']:>8.3f} {r['dd_full']*100:>7.2f}% "
              f"{r['sharpe_1st']:>8.3f} {r['dd_1st']*100:>7.2f}% "
              f"{r['sharpe_2nd']:>8.3f} {r['dd_2nd']*100:>7.2f}% "
              f"{ws:>13} {wr:>10} {r['worst_year_ret']*100:>9.1f}%")

    # 边际换率（等比容忍带下的年化 vs 回撤）
    print(f"\n--- 边际换率（等比容忍带） ---")
    print(f"{'区间':<16} {'Δ年化':>8} {'Δ回撤':>8} {'换率':>8}")
    print("-" * 45)
    for i in range(1, len(rows)):
        da = (rows[i]["ann_full"] - rows[i-1]["ann_full"]) * 100
        dd = (rows[i]["dd_full"] - rows[i-1]["dd_full"]) * -100
        rate = da / dd if dd > 0 else 999
        print(f"{rows[i-1]['beta']:.2f}→{rows[i]['beta']:.2f}     {da:>+7.2f}%  {dd:>+7.2f}%  {rate:>7.2f}")

    # 最佳推荐：前后半 Sharpe 都 > 1.0 + 最差滚动年 > -1.5
    print(f"\n--- 稳健性过滤（前后半 Sharpe > 1.0 且 最差12月 > -1.5） ---")
    robust = [r for r in rows
              if r["sharpe_1st"] > 1.0 and r["sharpe_2nd"] > 1.0
              and (r["worst_12m_sharpe"] is not None and r["worst_12m_sharpe"] > -1.5)]
    if robust:
        best = max(robust, key=lambda r: r["sharpe_full"])
        labels = [f"{r['beta']:.2f}" for r in robust]
        print(f"  通过过滤: {labels}")
        print(f"  最优: beta={best['beta']:.2f}, 全Sharpe={best['sharpe_full']:.3f}, "
              f"回撤={best['dd_full']*100:.2f}%, 最差12M Sharpe={best['worst_12m_sharpe']:.3f}")
    else:
        print("  无通过过滤的值")

    # 2018 专项
    print(f"\n--- 2018 年各 beta 表现专项 ---")
    print(f"{'beta':<8} {'Sharpe':>8} {'收益':>8} {'回撤':>8}")
    print("-" * 35)
    import src.backtest_engine as be
    be.allocate_capital = allocate_fixed
    from src.backtest_engine import run_backtest
    prices_2018 = {}
    for name, df in prices.items():
        df18 = df[(df.index >= "2017-10-01") & (df.index <= "2018-12-31")]
        if len(df18) > 120: prices_2018[name] = df18
    for beta in [0.04, 0.06, 0.08, 0.10, 0.12, 0.15, 999]:
        vol_tol = beta * 0.15 if beta < 999 else 0.015
        bt = run_backtest(prices_2018, params={"defense_ratio": 1.00, "target_vol_beta": beta, "vol_tolerance": vol_tol}, execution_lag=1)
        label = f"{beta:.2f}" if beta < 999 else "无sf"
        print(f"{label:<8} {bt['sharpe_ratio']:>8.3f} {bt['total_return']*100:>7.1f}% {bt['max_drawdown']*100:>7.2f}%")
    be.allocate_capital = _original_allocate

if __name__ == "__main__":
    main()
