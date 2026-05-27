# [2026-05-27] 新增：数据管线测试 — 3 场景

import pandas as pd
import pytest
import tempfile
import os

from src.data_pipeline import fetch_etf_daily, save_to_parquet, load_from_parquet


class TestFetchEtfDaily:
    """场景 1：正常拉取"""

    def test_fetch_returns_dataframe_with_required_columns(self):
        df = fetch_etf_daily("510300", "2024-01-01", "2024-01-31")
        assert isinstance(df, pd.DataFrame)
        assert not df.empty
        required_cols = {"open", "high", "low", "close", "volume"}
        assert required_cols.issubset(set(df.columns))
        assert isinstance(df.index, pd.DatetimeIndex)
        assert df.index.name == "date"


class TestFetchEtfDailyEmpty:
    """场景 2：空参数处理 — 非交易日区间"""

    def test_fetch_weekend_dates_returns_empty(self):
        df = fetch_etf_daily("510300", "2024-01-06", "2024-01-07")
        assert isinstance(df, pd.DataFrame)
        assert df.empty


class TestParquetRoundtrip:
    """场景 3：存储读取往返"""

    def test_roundtrip_preserves_data(self):
        df = fetch_etf_daily("510300", "2024-01-01", "2024-01-31")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.parquet")
            save_to_parquet(df, path)
            loaded = load_from_parquet(path)
            pd.testing.assert_frame_equal(df, loaded)
