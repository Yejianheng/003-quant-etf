# [2026-05-30] 新增：audit_vol_target.py 测试
import os
import sys
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.audit_vol_target import compute_sharpe_from_records


class TestComputeSharpeFromRecords:
    """compute_sharpe_from_records — 从 records DataFrame 计算 Sharpe。"""

    def test_positive_returns(self):
        """100 → 101 → 102 应返回正 Sharpe。"""
        df = pd.DataFrame({"nav": [100.0, 101.0, 102.0]})
        result = compute_sharpe_from_records(df)
        assert result > 0, f"Expected positive Sharpe, got {result}"

    def test_flat_nav(self):
        """NAV 不变 → Sharpe = 0。"""
        df = pd.DataFrame({"nav": [100.0, 100.0, 100.0]})
        result = compute_sharpe_from_records(df)
        assert result == 0.0, f"Expected 0 Sharpe for flat NAV, got {result}"

    def test_single_point(self):
        """只有 1 个数据点 → 返回 0，不崩溃。"""
        df = pd.DataFrame({"nav": [100.0]})
        result = compute_sharpe_from_records(df)
        assert result == 0.0

    def test_empty_dataframe(self):
        """空 DataFrame → 返回 0，不崩溃。"""
        df = pd.DataFrame({"nav": []})
        result = compute_sharpe_from_records(df)
        assert result == 0.0

    def test_missing_nav_column(self):
        """缺少 nav 列 → 抛出 KeyError。"""
        df = pd.DataFrame({"other": [1.0, 2.0]})
        with pytest.raises(KeyError):
            compute_sharpe_from_records(df)

    def test_large_swing(self):
        """极大波动：100 → 50 → 200。"""
        df = pd.DataFrame({"nav": [100.0, 50.0, 200.0]})
        result = compute_sharpe_from_records(df)
        assert isinstance(result, float)
        assert not np.isnan(result)
