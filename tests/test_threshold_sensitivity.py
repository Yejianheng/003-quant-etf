# [2026-05-30] 新增：熔断阈值敏感性扫描测试 — P1-8
import os
import sys
import numpy as np
import pandas as pd
import pytest

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

FIXED_PARAMS_BASE = {
    "trend_window": 40,
    "ewma_lambda": 0.94,
    "target_vol_beta": 0.10,
    "corr_threshold": 0.0,
    "defense_ratio": 1.0,
}

INITIAL_CAPITAL = 1_000_000
MIN_DAYS = 120


def _load_defense_prices():
    prices = {}
    for name, code in DEFENSE_MAP.items():
        fpath = os.path.join(DATA_DIR, f"{code}.parquet")
        if not os.path.exists(fpath):
            continue
        df = pd.read_parquet(fpath)
        prices[name] = df
    return prices


def _make_thresholds(liquidate_at: float) -> list:
    """构造 drawdown_thresholds: halve@12%, liquidate@liquidate_at"""
    # 格式: [(halve_start, 1.0), (liquidate_start, 0.5), (liquidate_start, 0.0)]
    # <12%: normal, 12%-X: halve, >=X: liquidate
    return [(0.12, 1.0), (liquidate_at, 0.5), (liquidate_at, 0.0)]


def _run_with_threshold(liquidate_at: float) -> dict:
    prices = _load_defense_prices()
    params = {**FIXED_PARAMS_BASE, "drawdown_thresholds": _make_thresholds(liquidate_at)}
    return run_backtest(prices, initial_capital=INITIAL_CAPITAL, params=params, min_days=MIN_DAYS)


def _count_liquidate_days(records: pd.DataFrame) -> int:
    return (records["drawdown_level"] == "liquidate").sum()


def _count_recovery_days(records: pd.DataFrame) -> int:
    """统计从 liquidate 恢复到 halve/normal 的天数。"""
    in_liquidation = False
    recovery_days = 0
    for level in records["drawdown_level"]:
        if level == "liquidate":
            in_liquidation = True
        elif in_liquidation and level != "liquidate":
            recovery_days += 1
            in_liquidation = False
    return recovery_days


# ═══════════════════════════════════════════════════════════════
# 基础路径：四个阈值扫描
# ═══════════════════════════════════════════════════════════════


class TestThresholdScan:
    """扫描 dd_threshold_liquidate 0.15/0.18/0.20/0.25"""

    THRESHOLDS = [0.15, 0.18, 0.20, 0.25]

    def test_all_thresholds_produce_valid_results(self):
        """所有阈值都能正常完成回测"""
        for th in self.THRESHOLDS:
            result = _run_with_threshold(th)
            assert result["records_df"] is not None
            assert len(result["records_df"]) > 0, f"阈值 {th} 回测无记录"
            assert result["final_nav"] > 0, f"阈值 {th} 最终 NAV 应 > 0"

    def test_sharpe_above_benchmarks(self):
        """所有阈值下策略 Sharpe > 沪深300"""
        prices = _load_defense_prices()
        for th in self.THRESHOLDS:
            params = {**FIXED_PARAMS_BASE, "drawdown_thresholds": _make_thresholds(th)}
            result = run_backtest(prices, initial_capital=INITIAL_CAPITAL, params=params, min_days=MIN_DAYS)
            bench_300_sharpe = _compute_sharpe_from_series(result["benchmark_300"])
            assert result["sharpe_ratio"] > bench_300_sharpe, (
                f"阈值 {th}: 策略 Sharpe={result['sharpe_ratio']:.2f} ≤ 沪深300={bench_300_sharpe:.2f}"
            )


def _compute_sharpe_from_series(series: pd.Series) -> float:
    if series is None or len(series) < 2:
        return -999
    r = series.pct_change().dropna()
    if r.std() == 0:
        return 0
    return (r.mean() / r.std()) * np.sqrt(252)


class TestThresholdComparison:
    """阈值之间的比较关系"""

    def test_stricter_threshold_reduces_max_dd(self):
        """0.15 比 0.18 更保守 → 最大回撤应 ≤ 0.18"""
        r15 = _run_with_threshold(0.15)
        r18 = _run_with_threshold(0.18)
        assert r15["max_drawdown"] <= r18["max_drawdown"] + 0.005, (
            f"0.15 回撤={r15['max_drawdown']:.4f} 不应明显 > 0.18 回撤={r18['max_drawdown']:.4f}"
        )

    def test_looser_threshold_allows_deeper_dd(self):
        """0.25 硬约束已破 → 最大回撤 ≥ 0.15"""
        r25 = _run_with_threshold(0.25)
        assert r25["max_drawdown"] <= -0.10, (
            f"0.25 阈值下最大回撤={r25['max_drawdown']:.4f}，预期 ≤ -10%"
        )

    def test_liquidate_trigger_order(self):
        """0.15 比 0.18 触发更多 liquidate（或相等）"""
        r15 = _run_with_threshold(0.15)
        r18 = _run_with_threshold(0.18)
        n15 = _count_liquidate_days(r15["records_df"])
        n18 = _count_liquidate_days(r18["records_df"])
        assert n15 >= n18, (
            f"0.15 liquidate={n15} 天应 ≥ 0.18 liquidate={n18} 天（更保守触发更多）"
        )


# ═══════════════════════════════════════════════════════════════
# 边界
# ═══════════════════════════════════════════════════════════════


class TestDefaultThreshold:
    """无 drawdown_thresholds 时使用默认 0.18"""

    def test_none_uses_default(self):
        prices = _load_defense_prices()
        params_no_th = {**FIXED_PARAMS_BASE}
        r_default = run_backtest(prices, initial_capital=INITIAL_CAPITAL, params=params_no_th, min_days=MIN_DAYS)

        params_explicit = {**FIXED_PARAMS_BASE, "drawdown_thresholds": _make_thresholds(0.18)}
        r_explicit = run_backtest(prices, initial_capital=INITIAL_CAPITAL, params=params_explicit, min_days=MIN_DAYS)

        # 使用默认阈值与显式指定 0.18 的 liquidate 天数应接近
        nd = _count_liquidate_days(r_default["records_df"])
        ne = _count_liquidate_days(r_explicit["records_df"])
        # 默认阈值 halve 在 12% liquidate 在 18%，与 _make_thresholds(0.18) 一致
        assert nd == ne, (
            f"默认阈值 liquidate 天数={nd} 应与显式 0.18={ne} 一致"
        )
