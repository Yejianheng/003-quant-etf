# [2026-07-14] 新增：execution_lag=1 隔夜跳空现金泄漏漏洞测试

import numpy as np
import pandas as pd
from src.backtest_engine import run_backtest

# 复用 test_backtest_engine 的 helper
from tests.test_backtest_engine import _make_ohlcv, _price_series


def _make_ohlcv_no_gap(close_series):
    """与 _make_ohlcv 相同但 open = close（无开收价差，用于基线对照）。"""
    close = close_series.values
    idx = close_series.index
    return pd.DataFrame({
        "open": close,
        "high": close * 1.02,
        "low": close * 0.98,
        "close": close,
        "volume": np.full(len(close), 1e6),
    }, index=idx)


def _make_gap_down_prices(n=200):
    """构造 T+1 跳空低开场景：平稳上涨行情中段出现大幅隔夜跳空。

    设计要点：
    - 股票/黄金：0.08% 日趋势，0.05% 噪声（趋势为正，策略持续持仓）
    - 国债：0.04% 日趋势，噪声与股票负相关（避免 CB 熔断干扰）
    - gap_idx=160（约回测第 40 日）：所有 ETF 开盘 = 前日收盘 × 0.90
    """
    rng = np.random.RandomState(42)
    noise_level = 0.0005
    gap_idx = 160

    stock_drift = np.full(n, 0.0008)
    stock_log_ret = stock_drift + rng.normal(0, noise_level, n)
    bond_log_ret = np.full(n, 0.0004) + rng.normal(0, noise_level, n)
    gold_log_ret = stock_drift + rng.normal(0, noise_level, n)

    stock_close = _price_series(stock_log_ret)
    bond_close = _price_series(bond_log_ret)
    gold_close = _price_series(gold_log_ret)

    prices = {}
    for name, close_series in [
        ("沪深300", stock_close), ("创业板", stock_close),
        ("纳指", stock_close), ("国债ETF", bond_close), ("黄金", gold_close),
    ]:
        close = close_series.values.copy()
        close[gap_idx:] *= 0.90  # gap 日及之后 close 打九折
        close_series_mod = pd.Series(close, index=close_series.index, name="close")
        ohlcv = _make_ohlcv(close_series_mod)
        # gap 日开盘 = 前一交易日收盘 × 0.90
        prev_close = close_series.iloc[gap_idx - 1]
        ohlcv.iloc[gap_idx, ohlcv.columns.get_loc("open")] = prev_close * 0.90
        prices[name] = ohlcv

    return prices


def _make_no_gap_prices(n=200):
    """无跳空的基准行情：open=close，去掉开收价差干扰。

    与 gap 场景的唯一区别是没有那一天的跳空开盘。
    """
    rng = np.random.RandomState(42)
    noise_level = 0.0005

    stock_drift = np.full(n, 0.0008)
    stock_log_ret = stock_drift + rng.normal(0, noise_level, n)
    bond_log_ret = np.full(n, 0.0004) + rng.normal(0, noise_level, n)
    gold_log_ret = stock_drift + rng.normal(0, noise_level, n)

    return {
        "沪深300": _make_ohlcv_no_gap(_price_series(stock_log_ret)),
        "创业板": _make_ohlcv_no_gap(_price_series(stock_log_ret)),
        "纳指": _make_ohlcv_no_gap(_price_series(stock_log_ret)),
        "国债ETF": _make_ohlcv_no_gap(_price_series(bond_log_ret)),
        "黄金": _make_ohlcv_no_gap(_price_series(gold_log_ret)),
    }


class TestExecutionLagCashLeak:
    """验证 execution_lag=1 下隔夜跳空不导致 repo_cash 为负"""

    def test_gap_down_detects_negative_repo_cash(self):
        """T+1 跳空低开 → 修复前 repo_amount 应为显著负值（bug 确认）"""
        prices = _make_gap_down_prices(n=200)
        result = run_backtest(
            prices,
            initial_capital=1_000_000,
            min_days=120,
            execution_lag=1,
            params={"defense_ratio": 1.0},
        )
        records = result["records_df"]

        min_repo = records["repo_amount"].min()
        # defense_ratio=1.0 全仓跳空导致 total_at_open < target_sum
        # 修复后 repo_cash 不应显著为负
        assert min_repo >= -10.0, (
            f"跳空场景 repo_amount 不应显著为负，实际 {min_repo:.2f}"
        )

    def test_gap_down_no_gap_no_negative(self):
        """无跳空时即使 defense_ratio=1.0 repo 也不应为负"""
        prices = _make_no_gap_prices(n=200)
        result = run_backtest(
            prices,
            initial_capital=1_000_000,
            min_days=120,
            execution_lag=1,
            params={"defense_ratio": 1.0},
        )
        records = result["records_df"]

        min_repo = records["repo_amount"].min()
        # 无跳空且 open=close 时，total_at_open == exec_alloc["total_capital"]
        # 修复前可能在佣金扣减前的舍入误差，但不应有系统性大额负值
        assert min_repo >= -1.0, (
            f"无跳空时 repo_amount 不应为负，实际 {min_repo:.2f}"
        )

    def test_gap_down_commission_free_no_negative_repo(self):
        """跳空 + 零佣金 → repo_amount 不应为负（缩放精确匹配）"""
        prices = _make_gap_down_prices(n=200)
        result = run_backtest(
            prices,
            initial_capital=1_000_000,
            min_days=120,
            execution_lag=1,
            commission_rate=0.0,
            params={"defense_ratio": 1.0},
        )
        records = result["records_df"]

        # 零佣金下 repo_amount 不应为负（缩放后买入不超可用资金）
        min_repo = records["repo_amount"].min()
        assert min_repo >= -1.0, (
            f"修复后零佣金 repo_amount 不应为负，实际最小值 {min_repo:.2f}"
        )
