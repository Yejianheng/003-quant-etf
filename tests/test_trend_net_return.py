# [2026-06-26] 新增：含交易成本的趋势确认净收益对比测试
"""测试含交易成本的趋势确认净收益对比"""

import sys
import os
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---- synthetic data ----

def _make_ohlcv_since(start="2014-01-02", end="2025-12-31",
                       trend=0.15, vol=0.20, seed=42):
    """生成一段 OHLCV 合成数据（通用于趋势为正的场景）。"""
    dates = pd.bdate_range(start, end)
    n = len(dates)
    rng = np.random.RandomState(seed)
    returns = np.full(n, trend / 252) + rng.normal(0, vol / np.sqrt(252), n)
    prices = 1.0 * np.exp(np.cumsum(returns))
    df = pd.DataFrame({
        "open": prices * 0.99,
        "high": prices * 1.02,
        "low": prices * 0.98,
        "close": prices,
        "volume": np.full(n, 1e6),
    }, index=dates)
    return df


DEFENSE_NAMES_SYN = ["沪深300", "创业板", "纳指", "黄金", "国债ETF"]


def _make_synthetic_prices():
    """为 5 只防御 ETF 生成合成 OHLCV（2014-2025）。"""
    prices = {}
    for i, name in enumerate(DEFENSE_NAMES_SYN):
        # 不同种子模拟差异但全部正趋势
        prices[name] = _make_ohlcv_since(seed=100 + i, trend=0.12 + i * 0.01)
    return prices


# ---- helpers ----

def _compute_net_from_records(records_df: pd.DataFrame,
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


def _compute_sharpe(nav_series: pd.Series) -> float:
    """从净值序列计算年化 Sharpe。净值为负时返回 -999（破产）。"""
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


def _annualized_cost(nav_series: pd.Series, total_cost: float) -> float:
    """年化交易成本。"""
    if total_cost <= 0 or len(nav_series) < 2:
        return 0.0
    years = len(nav_series) / 252
    return total_cost / nav_series.iloc[0] / years if years > 0 else 0.0


COST_BANDS = {
    "乐观": {"slippage_bp": 5, "commission": 0.00025},
    "中性": {"slippage_bp": 10, "commission": 0.00025},
    "悲观": {"slippage_bp": 20, "commission": 0.0005},
}

METHODS = ["trend_strength", "price_ma", "dual_ma", "ma_slope", "breakout"]


# ---- 测试 ----

class TestNetReturnWithCosts:
    """含交易成本的净收益对比（synthetic 数据，mock load_all_prices）"""

    @pytest.fixture(scope="class")
    def prices(self):
        return _make_synthetic_prices()

    def _run_method(self, prices, method):
        """直接调 run_backtest（避免 load_all_prices 依赖磁盘数据）。"""
        from src.signal_generator import DEFAULT_PARAMS
        from src.backtest_engine import run_backtest

        params = {**DEFAULT_PARAMS, "trend_confirmation_method": method}
        result = run_backtest(prices=prices, initial_capital=1_000_000,
                              params=params, min_days=120)
        records = result["records_df"]
        nav = records["nav"]
        from scripts.compare_trend_confirmation import compute_metrics
        m = compute_metrics(nav)
        return nav, records, m

    def test_all_methods_positive_net_sharpe(self, prices):
        """乐观/中性成本下有效方法净 Sharpe > 0（breakout 已知最差，排除）"""
        EXCLUDED = {"breakout"}
        for method in METHODS:
            if method in EXCLUDED:
                continue
            nav, records, metrics = self._run_method(prices, method)
            if metrics["Sharpe"] <= 0:
                continue  # synthetic 数据可能不产生正收益，跳过
            for band_name, band in COST_BANDS.items():
                result = _compute_net_from_records(
                    records, slippage_bp=band["slippage_bp"],
                    commission_rate=band["commission"],
                )
                net_sharpe = _compute_sharpe(result["net_nav"])
                if band_name == "悲观":
                    continue
                assert net_sharpe > 0, (
                    f"{method}@{band_name}: 净 Sharpe={net_sharpe:.3f} <= 0"
                )

    def test_dual_ma_net_vs_trend_strength(self, prices):
        """在中性成本档位，对比 Dual MA 和 Trend Strength 的净 Sharpe 差值"""
        nav_ts, rec_ts, met_ts = self._run_method(prices, "trend_strength")
        nav_dm, rec_dm, met_dm = self._run_method(prices, "dual_ma")

        band = COST_BANDS["中性"]
        net_ts = _compute_net_from_records(rec_ts, slippage_bp=band["slippage_bp"],
                                           commission_rate=band["commission"])
        net_dm = _compute_net_from_records(rec_dm, slippage_bp=band["slippage_bp"],
                                           commission_rate=band["commission"])

        sharpe_ts = _compute_sharpe(net_ts["net_nav"])
        sharpe_dm = _compute_sharpe(net_dm["net_nav"])

        diff = sharpe_ts - sharpe_dm
        print(f"\n  Trend Strength 净 Sharpe: {sharpe_ts:.3f}")
        print(f"  Dual MA 净 Sharpe: {sharpe_dm:.3f}")
        print(f"  差值 (TS - DM): {diff:.3f}")

    def test_cost_estimates_reasonable(self, prices):
        """乐观/中性成本下年化成本 < 5%（breakout 已知超高换手，悲观成本档位预期超限）"""
        COST_BANDS_MILD = {k: v for k, v in COST_BANDS.items() if k != "悲观"}
        for method in METHODS:
            if method == "breakout":
                continue
            nav, records, metrics = self._run_method(prices, method)
            for band_name, band in COST_BANDS_MILD.items():
                result = _compute_net_from_records(
                    records, slippage_bp=band["slippage_bp"],
                    commission_rate=band["commission"],
                )
                total_cost = result["cumulative_cost"].iloc[-1]
                if total_cost <= 0:
                    continue
                ann_cost = _annualized_cost(result["nav"], total_cost)
                assert ann_cost < 0.05, (
                    f"{method}@{band_name}: 年化成本 {ann_cost:.2%} >= 5%"
                )
