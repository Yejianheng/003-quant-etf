# [2026-05-29] 新增：analyze_dynamic_results 脚本测试

import os
import sys
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.analyze_dynamic_results import (
    load_navs,
    load_records,
    compute_offense_stats,
    load_summary,
    OUTPUT_DIR,
)


@pytest.fixture
def sample_nav():
    """构造 252 天上涨净值序列。"""
    dates = pd.date_range("2024-01-01", periods=252, freq="B")
    return pd.Series(1.0 * np.exp(np.cumsum(np.full(252, 0.001))), index=dates)


@pytest.fixture
def sample_records():
    """构造含 offense_top 列的 records DataFrame。"""
    dates = pd.date_range("2024-01-01", periods=252, freq="B")
    offense_top = [""] * 100 + ["军工ETF;证券ETF"] * 100 + ["军工ETF"] * 52
    return pd.DataFrame({
        "nav": 1.0 * np.exp(np.cumsum(np.full(252, 0.001))),
        "offense_top": offense_top,
        "position_names": ["沪深300;国债ETF"] * 50 + ["沪深300;国债ETF;军工ETF"] * 202,
    }, index=dates)


class TestLoadNavs:
    def test_loads_all_configs(self):
        """加载所有 6 种配置的净值文件"""
        navs = load_navs()
        assert len(navs) >= 6, f"应有至少 6 条净值序列，实际 {len(navs)}"


class TestLoadRecords:
    def test_loads_all_configs(self):
        """加载所有 6 种配置的记录文件"""
        records = load_records()
        assert len(records) >= 6, f"应有至少 6 条记录，实际 {len(records)}"


class TestLoadSummary:
    def test_loads_summary(self):
        """加载汇总 CSV"""
        df = load_summary()
        assert len(df) >= 6
        assert "label" in df.columns
        assert "strategy_Sharpe" in df.columns or "strategy_总收益" in df.columns


class TestOffenseStats:
    def test_empty_rate(self, sample_records):
        """空仓率 = offense_top 为空的天数占比"""
        stats = compute_offense_stats(sample_records)
        assert "offense_empty_rate" in stats
        assert 0.35 < stats["offense_empty_rate"] < 0.45  # 100/252 ≈ 0.397

    def test_participation_rate(self, sample_records):
        """参与率 = offense_top 非空的天数占比"""
        stats = compute_offense_stats(sample_records)
        assert "offense_participation_rate" in stats
        assert stats["offense_participation_rate"] > 0.5  # 152/252

    def test_avg_offense_count(self, sample_records):
        """进攻持仓数的日平均值"""
        stats = compute_offense_stats(sample_records)
        assert "avg_offense_positions" in stats
        assert stats["avg_offense_positions"] > 0


class TestOutputDir:
    def test_output_dir_exists(self):
        assert os.path.isdir(OUTPUT_DIR)
