# [2026-06-18] 新增：test_single_day_fetch_when_need_one_day 检测 fence-post bug
# [2026-05-30] 新增：每日数据更新脚本测试 — 3 场景
"""测试 scripts/update_data.py — 增量更新 ETF parquet"""

import os
from datetime import date
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pytest


# ---- helpers ----

def _make_ohlcv_df(start_date="2024-01-02", days=130):
    """创建模拟 OHLCV DataFrame，日期索引。"""
    dates = pd.date_range(start_date, periods=days, freq="B")
    n = len(dates)
    rng = np.random.RandomState(42)
    prices = 1.0 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, n)))
    df = pd.DataFrame({
        "open": prices * 0.99,
        "high": prices * 1.02,
        "low": prices * 0.98,
        "close": prices,
        "volume": np.full(n, 1e6),
    }, index=dates)
    return df


# ---- tests ----

class TestUpdateData:
    """scripts/update_data.py 的单元测试"""

    def test_existing_parquet_appends_new_data(self, tmp_path):
        """parquet 存在 → 追加新数据 → 行数增加、无重复日期"""
        data_dir = str(tmp_path / "data")
        os.makedirs(data_dir)

        # 写入旧数据（模拟已有 120 天）
        old_df = _make_ohlcv_df("2024-01-02", days=120)
        old_path = os.path.join(data_dir, "510300.parquet")
        old_df.to_parquet(old_path)

        # 模拟 AKShare 返回最近 10 天新数据
        new_df = _make_ohlcv_df("2024-06-17", days=10)
        mock_fetch = MagicMock(return_value=new_df)

        from scripts.update_data import update_single_etf
        with patch("scripts.update_data.fetch_etf_daily", mock_fetch):
            updated = update_single_etf("510300", data_dir, lookback_days=10)

        assert updated is True
        result = pd.read_parquet(old_path)
        assert len(result) > 120, f"应增加行数，实际 {len(result)}"
        assert result.index.is_unique, "日期不应重复"

    def test_missing_parquet_skipped_no_crash(self, tmp_path):
        """parquet 不存在 → 跳过，返回 False，不崩溃"""
        data_dir = str(tmp_path / "data")
        os.makedirs(data_dir)

        mock_fetch = MagicMock()
        from scripts.update_data import update_single_etf
        with patch("scripts.update_data.fetch_etf_daily", mock_fetch):
            updated = update_single_etf("999999", data_dir, lookback_days=10)

        assert updated is False
        mock_fetch.assert_not_called()

    def test_fetch_returns_empty_skipped_no_crash(self, tmp_path):
        """AKShare 返回空 DataFrame → 跳过，返回 False，不崩溃"""
        data_dir = str(tmp_path / "data")
        os.makedirs(data_dir)

        old_df = _make_ohlcv_df("2024-01-02", days=120)
        old_path = os.path.join(data_dir, "510300.parquet")
        old_df.to_parquet(old_path)

        mock_fetch = MagicMock(return_value=pd.DataFrame())
        from scripts.update_data import update_single_etf
        with patch("scripts.update_data.fetch_etf_daily", mock_fetch):
            updated = update_single_etf("510300", data_dir, lookback_days=10)

        assert updated is False
        # 原文件未被破坏
        result = pd.read_parquet(old_path)
        assert len(result) == 120, f"原文件应保持 120 行，实际 {len(result)}"

    def test_single_day_fetch_when_need_one_day(self, tmp_path):
        """start_date == end_date 时不应跳过，应发起拉取"""
        data_dir = str(tmp_path / "data")
        os.makedirs(data_dir)

        # 旧数据截止 T-1（昨天）
        dates = pd.date_range("2026-06-10", "2026-06-17", freq="B")
        old_df = pd.DataFrame({
            "open": [1.0] * len(dates), "high": [1.0] * len(dates),
            "low": [1.0] * len(dates), "close": [1.0] * len(dates),
            "volume": [1e6] * len(dates),
        }, index=dates)
        old_path = os.path.join(data_dir, "510300.parquet")
        old_df.to_parquet(old_path)

        # 模拟 AKShare 返回今天 (T) 这一天
        new_df = pd.DataFrame({
            "open": [1.01], "high": [1.01],
            "low": [1.01], "close": [1.01], "volume": [1e6],
        }, index=[pd.Timestamp("2026-06-18")])
        mock_fetch = MagicMock(return_value=new_df)

        from scripts.update_data import update_single_etf
        # 固定 "today" 为 2026-06-18，old_data last_date=6/17, start=6/18, end=6/18
        with patch("scripts.update_data.date") as mock_date:
            mock_date.today.return_value = date(2026, 6, 18)
            with patch("scripts.update_data.fetch_etf_daily", mock_fetch):
                updated = update_single_etf("510300", data_dir)

        assert updated is True, "单日增量应触发拉取，不应跳过"
        mock_fetch.assert_called_once()
        result = pd.read_parquet(old_path)
        assert len(result) == len(dates) + 1, "应有 len(dates)+1 行"
