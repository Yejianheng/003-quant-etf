# [2026-05-30] 新增：check_lookahead_bias.py 的单元测试

import os
import sys
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.check_lookahead_bias import compute_metrics, load_prices
from src.backtest_engine import run_backtest


class TestComputeMetrics:
    """场景 1：compute_metrics 计算正确性"""

    def test_uptrend_series(self):
        """上涨序列：收益正、Sharpe 正、回撤为 0（无下跌）"""
        nav = pd.Series([1.0, 1.01, 1.02, 1.03, 1.04])
        m = compute_metrics(nav)
        assert m["总收益"] > 0
        assert m["Sharpe"] > 0
        assert m["最大回撤"] == 0.0

    def test_downtrend_series(self):
        """下跌序列：收益负、Sharpe 负、回撤为负"""
        nav = pd.Series([1.0, 0.99, 0.98, 0.97, 0.96])
        m = compute_metrics(nav)
        assert m["总收益"] < 0
        assert m["Sharpe"] < 0
        assert m["最大回撤"] < 0

    def test_flat_series_sharpe_zero(self):
        """不变序列：Sharpe = 0"""
        nav = pd.Series([1.0, 1.0, 1.0, 1.0])
        m = compute_metrics(nav)
        assert m["Sharpe"] == 0.0
        assert m["最大回撤"] == 0.0

    def test_short_series_returns_empty(self):
        """长度不足 2 → 返回空 dict"""
        nav = pd.Series([1.0])
        m = compute_metrics(nav)
        assert m == {}

    def test_known_drawdown(self):
        """已知回撤：峰值 1.10, 低谷 0.90 → 回撤 ≈ -18.2%"""
        nav = pd.Series([1.0, 1.05, 1.10, 1.00, 0.90, 0.95])
        m = compute_metrics(nav)
        assert abs(m["最大回撤"] - (-0.1818)) < 0.02


class TestLoadPrices:
    """场景 2：load_prices 数据加载"""

    def test_load_existing_etf(self):
        """510300（沪深300）必须存在"""
        df = load_prices("510300")
        assert df is not None
        assert len(df) > 0
        for col in ["open", "high", "low", "close"]:
            assert col in df.columns

    def test_load_nonexistent_code(self):
        """不存在的代码 → None"""
        df = load_prices("999999")
        assert df is None


class TestBacktestLag:
    """场景 3-4：execution_lag 参数功能"""

    @pytest.fixture(scope="class")
    def prices(self):
        """加载防御层数据用于快速验证"""
        DEFENSE_MAP = {
            "沪深300": "510300",
            "创业板": "159915",
            "纳指": "513100",
            "黄金": "518880",
            "国债ETF": "511010",
        }
        DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
        result = {}
        for name, code in DEFENSE_MAP.items():
            fpath = os.path.join(DATA_DIR, f"{code}.parquet")
            if os.path.exists(fpath):
                df = pd.read_parquet(fpath)
                result[name] = df
        return result

    def test_lag0_completes(self, prices):
        """lag=0 正常完成（纯防御）"""
        result = run_backtest(
            prices=prices,
            params={"defense_ratio": 1.0},
            min_days=120,
            execution_lag=0,
        )
        assert "records_df" in result
        assert "sharpe_ratio" in result
        assert len(result["records_df"]) >= 2

    def test_lag1_completes(self, prices):
        """lag=1 正常完成（纯防御）"""
        result = run_backtest(
            prices=prices,
            params={"defense_ratio": 1.0},
            min_days=120,
            execution_lag=1,
        )
        assert "records_df" in result
        assert "sharpe_ratio" in result
        assert len(result["records_df"]) >= 2

    def test_lag0_lag1_different_nav(self, prices):
        """lag=0 和 lag=1 的 NAV 序列不同（T+1 延迟成交应产生差异）"""
        r0 = run_backtest(prices=prices, params={"defense_ratio": 1.0}, min_days=120, execution_lag=0)
        r1 = run_backtest(prices=prices, params={"defense_ratio": 1.0}, min_days=120, execution_lag=1)
        nav0 = r0["records_df"]["nav"]
        nav1 = r1["records_df"]["nav"]
        # 两版 NAV 长度应相近（lag=1 可能少 1 天的首笔成交）
        assert abs(len(nav0) - len(nav1)) <= 2
        # 存在差异（非完全一致）
        aligned = pd.concat([nav0.reset_index(drop=True), nav1.reset_index(drop=True)], axis=1).dropna()
        diff = (aligned.iloc[:, 0] - aligned.iloc[:, 1]).abs().max()
        assert diff > 0, "lag=0 和 lag=1 的 NAV 应存在差异"
