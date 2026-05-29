# [2026-05-29] 新增：步骤4 — 条件性激活回测验证

import os
import sys
import json
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE = os.path.join(os.path.dirname(__file__), "..")
OUTPUT_DIR = os.path.join(BASE, "output")
DATA_DIR = os.path.join(BASE, "data")


def load_nav(label: str) -> pd.Series:
    path = os.path.join(OUTPUT_DIR, f"nav_{label}.csv")
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    return df.iloc[:, 0].rename(label)


def load_records(label: str) -> pd.DataFrame:
    path = os.path.join(OUTPUT_DIR, f"records_{label}.csv")
    return pd.read_csv(path, index_col=0, parse_dates=True)


def load_activation_rules() -> dict:
    path = os.path.join(OUTPUT_DIR, "activation_rules.json")
    with open(path) as f:
        return json.load(f)


def extract_offense_count(records: pd.DataFrame) -> pd.Series:
    def parse(val):
        if pd.isna(val) or str(val).strip() == "":
            return 0
        return len(str(val).split(";"))
    return records["offense_top"].apply(parse).rename("offense_count")


def compute_rolling_volatility(prices: pd.DataFrame, window: int = 60) -> pd.Series:
    returns = prices["close"].pct_change()
    vol = returns.rolling(window).std() * np.sqrt(252)
    return vol.rename("volatility")


def generate_activation_signal(
    offense_count: pd.Series,
    volatility: pd.Series,
    max_offense: int = 2,
    max_vol: float = 0.18,
) -> pd.Series:
    # [2026-05-29] 修改：允许通过参数自定义阈值（测试用）
    signal = (offense_count <= max_offense) & (volatility < max_vol)
    # forward-fill NaN in volatility (early days before rolling window fills)
    signal = signal.fillna(False)
    return signal.rename("activation_signal")


def build_conditional_nav(
    nav_defense: pd.Series,
    nav_mixed: pd.Series,
    signal: pd.Series,
) -> pd.Series:
    """用信号在 defense 和 mixed 的日收益率之间切换，构建条件 NAV"""
    common = nav_defense.index.intersection(nav_mixed.index).intersection(signal.index)
    d = nav_defense.loc[common]
    m = nav_mixed.loc[common]
    s = signal.loc[common]

    d_ret = d.pct_change()
    m_ret = m.pct_change()

    nav = pd.Series(np.nan, index=common, name="conditional_nav")
    nav.iloc[0] = d.iloc[0]

    for i in range(1, len(common)):
        if s.iloc[i]:
            nav.iloc[i] = nav.iloc[i - 1] * (1 + m_ret.iloc[i])
        else:
            nav.iloc[i] = nav.iloc[i - 1] * (1 + d_ret.iloc[i])

    return nav


def compute_metrics_from_nav(nav: pd.Series) -> dict:
    if len(nav) < 2:
        return {}
    returns = nav.pct_change().dropna()
    total_return = (nav.iloc[-1] / nav.iloc[0]) - 1
    years = len(nav) / 252
    annual_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0
    annual_vol = returns.std() * np.sqrt(252)
    sharpe = annual_return / annual_vol if annual_vol > 0 else 0
    peak = nav.expanding().max()
    drawdown = (nav - peak) / peak
    max_dd = drawdown.min()
    return {
        "总收益": total_return,
        "年化": annual_return,
        "波动率": annual_vol,
        "Sharpe": sharpe,
        "最大回撤": max_dd,
    }


def main():
    print("=== Step 4: Conditional Activation Backtest ===\n")

    # 1. 加载数据和规则
    print("[1/4] Loading data...")
    nav_defense = load_nav("纯防御")
    nav_mixed = load_nav("混合")
    nav_offense = load_nav("纯进攻")
    records = load_records("纯进攻")
    hs300 = pd.read_parquet(os.path.join(DATA_DIR, "510300.parquet"))
    rules = load_activation_rules()
    print(f"  Defense NAV: {len(nav_defense)} days, Mixed NAV: {len(nav_mixed)} days")
    print(f"  Rule: {rules['rule']}")

    # 2. 生成多个规则的激活信号
    print("\n[2/4] Generating activation signals...")
    offense_count = extract_offense_count(records)
    volatility = compute_rolling_volatility(hs300)

    # Rule variants
    rule_variants = {
        "offense<=2 & vol<0.18": generate_activation_signal(offense_count, volatility, max_offense=2, max_vol=0.18),
        "offense<=2 only": generate_activation_signal(offense_count, volatility, max_offense=2, max_vol=999),
        "offense<=3 only": generate_activation_signal(offense_count, volatility, max_offense=3, max_vol=999),
    }

    for name, sig in rule_variants.items():
        common_idx = nav_defense.index.intersection(sig.dropna().index)
        active_days = sig.loc[common_idx].sum()
        total_days = len(common_idx)
        print(f"  {name}: active {active_days}/{total_days} ({active_days/total_days:.1%})")

    # 3. 构建并对比所有条件 NAV
    print("\n[3/4] Building conditional NAVs...")
    all_cond_navs = {}
    for name, sig in rule_variants.items():
        all_cond_navs[name] = build_conditional_nav(nav_defense, nav_mixed, sig)

    # 4. 对比
    print("\n[4/4] Results:")
    configs = {
        "纯防御(baseline)": nav_defense,
        "纯进攻": nav_offense,
        "固定70:30": nav_mixed,
        **all_cond_navs,
    }

    all_metrics = {}
    ref_idx = nav_defense.index
    for label, nav in configs.items():
        common = ref_idx.intersection(nav.index)
        n = nav.loc[common]
        m = compute_metrics_from_nav(n)
        all_metrics[label] = m

    print(f"\n{'配置':<24} {'总收益':>8} {'年化':>8} {'Sharpe':>8} {'最大回撤':>8}")
    print("-" * 60)
    for label in configs:
        m = all_metrics[label]
        marker = " <<<" if "offense" in label else ""
        print(f"{label:<24} {m['总收益']:>7.1%} {m['年化']:>7.1%} {m['Sharpe']:>7.2f} {m['最大回撤']:>7.1%}{marker}")

    defense_sharpe = all_metrics["纯防御(baseline)"]["Sharpe"]
    best_cond = max(all_cond_navs.keys(), key=lambda k: all_metrics[k]["Sharpe"])
    print(f"\n  Best conditional: {best_cond} (Sharpe {all_metrics[best_cond]['Sharpe']:.2f})")
    print(f"  Target: > defense Sharpe ({defense_sharpe:.2f})")
    print(f"  Result: {'PASS' if all_metrics[best_cond]['Sharpe'] > defense_sharpe else 'FAIL'}")

    # 保存最佳条件信号
    best_signal = rule_variants[best_cond]
    signal_stats = pd.DataFrame({
        "date": ref_idx,
        "activation": [best_signal.get(d, False) for d in ref_idx],
    })
    signal_stats.to_csv(os.path.join(OUTPUT_DIR, "conditional_signal.csv"), index=False)
    print(f"  Signal data saved")

    # 保存最佳条件 NAV
    best_nav = all_cond_navs[best_cond]
    cond_nav_df = pd.DataFrame({"date": best_nav.index, "nav": best_nav.values})
    cond_nav_df.to_csv(os.path.join(OUTPUT_DIR, "nav_条件性激活.csv"), index=False)
    print(f"  Conditional NAV saved")

    # 保存所有对比指标
    metrics_rows = []
    for label, m in all_metrics.items():
        metrics_rows.append({"label": label, **m})
    metrics_df = pd.DataFrame(metrics_rows)
    metrics_df.to_csv(os.path.join(OUTPUT_DIR, "conditional_backtest_metrics.csv"), index=False)
    print(f"  Metrics saved")

    print("\n=== Step 4 Complete ===")


if __name__ == "__main__":
    main()
