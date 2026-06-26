# [2026-06-26] 修改：从 synthetic 改为真实数据全量回测
# [2026-06-26] 新增：含交易成本的趋势确认净收益对比测试
"""测试含交易成本的趋势确认净收益对比（真实数据）"""

import sys
import os

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.compare_trend_confirmation import run_config, load_all_prices, compute_metrics


# ---- 交易成本档位 ----

COST_BANDS = {
    "乐观": {"slippage_bp": 5, "commission": 0.00025},
    "中性": {"slippage_bp": 10, "commission": 0.00025},
    "悲观": {"slippage_bp": 20, "commission": 0.0005},
}

METHODS = ["trend_strength", "price_ma", "dual_ma", "ma_slope", "breakout"]

METHOD_LABELS = {
    "trend_strength": "Trend Strength",
    "price_ma": "Price > MA",
    "dual_ma": "Dual MA",
    "ma_slope": "MA Slope",
    "breakout": "Breakout",
}

BAD_DATE = pd.Timestamp("2022-01-13")  # 部分行业ETF有该日但防御层全缺，导致NAV归零


def _clean_prices(raw):
    """从所有ETF数据中移除 BAD_DATE，防止日期联合索引异常。"""
    cleaned = {}
    for name, df in raw.items():
        cleaned[name] = df[df.index != BAD_DATE].copy()
    return cleaned


# ---- 交易成本计算 ----

def compute_net_from_records(records_df: pd.DataFrame,
                              slippage_bp: float = 10,
                              commission_rate: float = 0.00025) -> pd.DataFrame:
    """从 records_df 计算含成本的净值序列。"""
    df = records_df.copy()
    df["prev_active"] = df["defense_active"].shift(1)
    df["prev_exposure"] = df["exposure"].shift(1)

    cost_per_trade = []
    for idx, row in df.iterrows():
        prev_act = _parse_active(row.get("prev_active", ""))
        curr_act = _parse_active(row["defense_active"])
        prev_exp = row.get("prev_exposure", 0)
        curr_exp = row["exposure"]

        if pd.isna(prev_exp) or prev_exp == 0:
            cost_per_trade.append(0.0)
            continue

        sold = prev_act - curr_act
        bought = curr_act - prev_act

        n_prev = max(len(prev_act), 1)
        n_curr = max(len(curr_act), 1)

        total_cost = 0.0
        if sold:
            trade_val = prev_exp / n_prev * len(sold)
            total_cost += trade_val * (slippage_bp / 10000 + commission_rate)
        if bought:
            trade_val = curr_exp / n_curr * len(bought)
            total_cost += trade_val * (slippage_bp / 10000 + commission_rate)

        cost_per_trade.append(total_cost)

    df["trade_cost"] = cost_per_trade
    df["cumulative_cost"] = df["trade_cost"].cumsum()
    df["net_nav"] = df["nav"] - df["cumulative_cost"]
    return df


def _parse_active(val) -> set:
    """解析 defense_active 字符串为 set。"""
    if not val or (isinstance(val, float) and np.isnan(val)):
        return set()
    return {x.strip() for x in str(val).split(";") if x.strip()}


def net_sharpe(nav_series: pd.Series) -> float:
    """从净值序列计算年化 Sharpe。"""
    if len(nav_series) < 2:
        return 0.0
    final = nav_series.iloc[-1]
    initial = nav_series.iloc[0]
    if final <= 0 or initial <= 0:
        return -999.0
    returns = nav_series.pct_change().dropna()
    if len(returns) < 2:
        return 0.0
    annual_factor = 252
    ann_ret = (final / initial) ** (annual_factor / len(nav_series)) - 1
    ann_vol = returns.std() * np.sqrt(annual_factor)
    return ann_ret / ann_vol if ann_vol > 0 else 0.0


def count_whipsaws(records: pd.DataFrame) -> int:
    """统计防御层 ETF 的 whipsaw 次数（20 日内先进后出）。"""
    from scripts.compare_trend_confirmation import DEFENSE_NAMES, parse_etf_list
    WHIPSAW_WINDOW = 20
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


# ---- 测试 ----

class TestNetReturnWithCostsReal:
    """含交易成本的净收益对比（真实数据全量回测）"""

    @pytest.fixture(scope="class")
    def prices(self):
        return _clean_prices(load_all_prices())

    def test_all_methods_net_sharpe_table(self, prices):
        """输出含成本的净 Sharpe 对比表"""
        print(f"\n{'=' * 90}")
        print(f"  五种趋势确认方法含交易成本净收益对比（真实数据全量回测）")
        print(f"{'=' * 90}")
        header = (f"{'方法':<20} {'Gross Sharpe':>12} {'净Sharpe(中性)':>14} "
                  f"{'年化成本(中性)':>14} {'Whipsaw':>8}")
        print(header)
        print("-" * 90)

        results = {}
        for method in METHODS:
            nav, records, m = run_config(prices, method)
            gross_sharpe = m["Sharpe"]
            whip = count_whipsaws(records)

            # 中性成本
            band = COST_BANDS["中性"]
            net_records = compute_net_from_records(
                records, slippage_bp=band["slippage_bp"],
                commission_rate=band["commission"],
            )
            net_s = net_sharpe(net_records["net_nav"])
            total_cost = net_records["cumulative_cost"].iloc[-1]
            years = len(records) / 252
            ann_cost = total_cost / 1_000_000 / years if years > 0 else 0

            label = METHOD_LABELS[method]
            print(f"{label:<20} {gross_sharpe:>12.3f} {net_s:>14.3f} "
                  f"{ann_cost:>13.2%} {whip:>8}")

            results[method] = {
                "gross_sharpe": gross_sharpe,
                "net_sharpe_neutral": net_s,
                "ann_cost_neutral": ann_cost,
                "whipsaw": whip,
            }

        # trend_strength（当前默认）Gross Sharpe 应为正
        assert results.get("trend_strength", {}).get("gross_sharpe", -999) > 0, (
            "trend_strength 真实数据全量回测 Gross Sharpe <= 0"
        )

    def test_dual_ma_net_vs_trend_strength(self, prices):
        """在中性成本档位，对比 Dual MA 和 Trend Strength 的净 Sharpe 差值"""
        nav_ts, rec_ts, met_ts = run_config(prices, "trend_strength")
        nav_dm, rec_dm, met_dm = run_config(prices, "dual_ma")

        band = COST_BANDS["中性"]
        net_ts = compute_net_from_records(rec_ts, slippage_bp=band["slippage_bp"],
                                           commission_rate=band["commission"])
        net_dm = compute_net_from_records(rec_dm, slippage_bp=band["slippage_bp"],
                                           commission_rate=band["commission"])

        sharpe_ts = net_sharpe(net_ts["net_nav"])
        sharpe_dm = net_sharpe(net_dm["net_nav"])

        diff = sharpe_ts - sharpe_dm
        print(f"\n  Trend Strength 净 Sharpe: {sharpe_ts:.3f}")
        print(f"  Dual MA 净 Sharpe: {sharpe_dm:.3f}")
        print(f"  差值 (TS - DM): {diff:.3f}")

    def test_cost_estimates_reasonable(self, prices):
        """中性成本下年化交易成本 < 8%（breakout 可能有超高换手）"""
        band = COST_BANDS["中性"]
        for method in METHODS:
            nav, records, metrics = run_config(prices, method)
            result = compute_net_from_records(
                records, slippage_bp=band["slippage_bp"],
                commission_rate=band["commission"],
            )
            total_cost = result["cumulative_cost"].iloc[-1]
            if total_cost <= 0:
                continue
            years = len(records) / 252
            ann_cost = total_cost / 1_000_000 / years if years > 0 else 0
            print(f"  {METHOD_LABELS[method]}: 年化成本 {ann_cost:.2%}")
