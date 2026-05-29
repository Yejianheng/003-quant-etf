# [2026-05-29] 新增：2022 股债双杀专项分析

import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE = os.path.join(os.path.dirname(__file__), "..")
OUTPUT_DIR = os.path.join(BASE, "output")
DATA_DIR = os.path.join(BASE, "data")

DEFENSE_ETFS = ["沪深300", "创业板", "纳指", "黄金", "国债ETF"]
YEAR_START = "2022-01-01"
YEAR_END = "2022-12-31"


def parse_defense_etfs(s) -> list:
    if s is None or (isinstance(s, float) and np.isnan(s)):
        return []
    s = str(s).strip()
    if not s or s.lower() == "nan":
        return []
    return [x.strip() for x in s.split(";") if x.strip()]


def track_etf_transitions(defense_series: pd.Series, etf_name: str) -> pd.DataFrame:
    mask = defense_series.apply(lambda s: etf_name in parse_defense_etfs(s))
    changed = mask != mask.shift(1)
    changed.iloc[0] = False
    flip_idx = changed[changed].index

    events = []
    for dt in flip_idx:
        is_active = mask.loc[dt]
        events.append({
            "date": dt,
            "etf": etf_name,
            "event": "active" if is_active else "inactive",
        })
    return pd.DataFrame(events)


def classify_migration_stage(defense_active_str: str) -> str:
    etfs = parse_defense_etfs(defense_active_str)
    if not etfs:
        return "空仓/repo"
    has_stock = any(e in etfs for e in ["沪深300", "创业板", "纳指"])
    has_bond = "国债ETF" in etfs
    has_gold = "黄金" in etfs

    if has_stock and not has_bond and not has_gold:
        return "权益重仓"
    if has_stock and has_bond:
        return "股债混合"
    if has_stock and has_gold and not has_bond:
        return "权益+黄金"
    if not has_stock and has_bond and not has_gold:
        return "纯债"
    if not has_stock and (has_bond or has_gold):
        return "避险资产"
    if has_stock:
        return "权益重仓"
    return "其他"


def compute_6040_nav(stock_prices: pd.Series, bond_prices: pd.Series,
                     rebalance_freq: int = 21) -> pd.Series:
    common_idx = stock_prices.index.intersection(bond_prices.index)
    s = stock_prices.loc[common_idx].astype(float)
    b = bond_prices.loc[common_idx].astype(float)

    nav = pd.Series(1.0, index=common_idx)
    s_units = 0.6 / s.iloc[0]
    b_units = 0.4 / b.iloc[0]

    for i in range(1, len(common_idx)):
        s_val = s_units * s.iloc[i]
        b_val = b_units * b.iloc[i]
        total = s_val + b_val
        nav.iloc[i] = total

        if i % rebalance_freq == 0:
            s_units = 0.6 * total / s.iloc[i]
            b_units = 0.4 * total / b.iloc[i]

    return nav


def find_circuit_breaker_periods(exposure: pd.Series) -> list:
    in_repo = (exposure == 0.0)
    changed = in_repo != in_repo.shift(1)
    changed.iloc[0] = False

    periods = []
    start = None
    for dt in changed[changed].index:
        if in_repo.loc[dt] and start is None:
            start = dt
        elif not in_repo.loc[dt] and start is not None:
            periods.append({"start": start, "end": dt})
            start = None
    if start is not None:
        periods.append({"start": start, "end": in_repo.index[-1]})

    return periods


def main():
    print("=" * 70)
    print("2022 股债双杀专项分析")
    print("=" * 70)

    nav_path = os.path.join(OUTPUT_DIR, "nav_纯防御.csv")
    rec_path = os.path.join(OUTPUT_DIR, "records_纯防御.csv")
    nav = pd.read_csv(nav_path, index_col=0, parse_dates=True).iloc[:, 0]
    records = pd.read_csv(rec_path, index_col=0, parse_dates=True)

    r2022 = records[(records.index >= YEAR_START) & (records.index <= YEAR_END)]
    n2022 = nav[(nav.index >= YEAR_START) & (nav.index <= YEAR_END)]

    da_col = r2022["defense_active"].fillna("").astype(str)

    # ── 1. 每只 ETF 的 active→inactive 时间点 ─────────────────
    print("\n[1/5] 防御 5 只 ETF 状态转变时间点\n")
    for etf in DEFENSE_ETFS:
        events = track_etf_transitions(da_col, etf)
        active_days = da_col.apply(lambda s: etf in parse_defense_etfs(s)).sum()
        total_days = len(da_col)
        pct = active_days / total_days * 100
        print(f"  {etf}: active {active_days}/{total_days} 天 ({pct:.0f}%), "
              f"{len(events)} 次转换")
        if len(events) > 0:
            for _, ev in events.iterrows():
                direction = "→ 激活" if ev["event"] == "active" else "→ 退出"
                print(f"    {ev['date'].strftime('%Y-%m-%d')} {direction}")

    # ── 2. 资金逐级撤退路径 ─────────────────────────────────
    print("\n[2/5] 资金逐级撤退路径\n")
    stage_series = da_col.apply(classify_migration_stage)
    stage_changes = stage_series != stage_series.shift(1)
    stage_changes.iloc[0] = False
    change_idx = stage_changes[stage_changes].index

    with pd.option_context("display.max_colwidth", 60):
        for dt in change_idx:
            nav_val = n2022.loc[dt] if dt in n2022.index else np.nan
            exp = r2022.loc[dt, "exposure"]
            print(f"  {dt.strftime('%Y-%m-%d')} : {stage_series.loc[dt]:<10} "
                  f"| NAV={nav_val:>12.0f} | exposure={exp:>12.0f}")

    # ── 3. 熔断 repo 期 ──────────────────────────────────────
    print("\n[3/5] 熔断/空仓期 (exposure=0)\n")
    cb_periods = find_circuit_breaker_periods(r2022["exposure"])
    for p in cb_periods:
        duration = (p["end"] - p["start"]).days
        start_nav = n2022.loc[p["start"]] if p["start"] in n2022.index else np.nan
        end_nav = n2022.loc[p["end"]] if p["end"] in n2022.index else np.nan
        print(f"  {p['start'].strftime('%Y-%m-%d')} → {p['end'].strftime('%Y-%m-%d')} "
              f"({duration} 天) | NAV: {start_nav:>12.0f} → {end_nav:>12.0f}")

    # ── 4. vs 60/40 组合 ─────────────────────────────────────
    print("\n[4/5] 纯防御 vs 60/40 组合\n")

    # Load benchmark prices
    hs300 = pd.read_parquet(os.path.join(DATA_DIR, "510300.parquet"))["close"]
    bond = pd.read_parquet(os.path.join(DATA_DIR, "511010.parquet"))["close"]

    nav_6040 = compute_6040_nav(hs300, bond)

    # 对齐到 2022
    def_nav_2022 = n2022.copy()
    def_nav_norm = def_nav_2022 / def_nav_2022.iloc[0]

    nav_6040_2022 = nav_6040[(nav_6040.index >= YEAR_START) & (nav_6040.index <= YEAR_END)]
    nav_6040_norm = nav_6040_2022 / nav_6040_2022.iloc[0]

    common = def_nav_norm.index.intersection(nav_6040_norm.index)
    def_ret = def_nav_norm.loc[common].iloc[-1] - 1
    ret_6040 = nav_6040_norm.loc[common].iloc[-1] - 1

    def_vol = def_nav_norm.pct_change().std() * np.sqrt(252)
    vol_6040 = nav_6040_norm.pct_change().std() * np.sqrt(252)

    def_sharpe = (def_ret - 0.02) / def_vol if def_vol > 0 else 0
    sharpe_6040 = (ret_6040 - 0.02) / vol_6040 if vol_6040 > 0 else 0

    def_dd = (def_nav_norm / def_nav_norm.cummax() - 1).min()
    dd_6040 = (nav_6040_norm / nav_6040_norm.cummax() - 1).min()

    print(f"  {'':<16} {'纯防御':>10} {'60/40':>10}")
    print(f"  {'年收益':<16} {def_ret:>9.1%} {ret_6040:>9.1%}")
    print(f"  {'波动率':<16} {def_vol:>9.1%} {vol_6040:>9.1%}")
    print(f"  {'Sharpe':<16} {def_sharpe:>9.2f} {sharpe_6040:>9.2f}")
    print(f"  {'最大回撤':<16} {def_dd:>9.1%} {dd_6040:>9.1%}")

    # ── 5. 资金迁移阶段统计 ─────────────────────────────────
    print("\n[5/5] 资金所处阶段天数统计\n")
    stage_counts = stage_series.value_counts()
    total = len(stage_series)
    for stage, count in stage_counts.items():
        pct_count = count / total * 100
        segment = n2022[stage_series == stage]
        seg_ret = segment.iloc[-1] / segment.iloc[0] - 1 if len(segment) > 1 else 0
        print(f"  {stage:<10}: {count:>4} 天 ({pct_count:>5.1f}%) | 段内收益 {seg_ret:>7.2%}")

    # 保存明细
    events_all = []
    for etf in DEFENSE_ETFS:
        ev = track_etf_transitions(da_col, etf)
        events_all.append(ev)
    all_events = pd.concat(events_all, ignore_index=True)
    events_path = os.path.join(OUTPUT_DIR, "regime_2022_etf_transitions.csv")
    all_events.to_csv(events_path, index=False)
    print(f"\n  ETF 转换事件 → {events_path}")

    print("\n=== 步骤 3 完成 ===")


if __name__ == "__main__":
    main()
