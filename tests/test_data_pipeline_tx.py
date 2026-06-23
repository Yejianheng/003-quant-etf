# [2026-06-23] 新增：腾讯财经数据源测试 — 3 场景
"""测试 src/data_pipeline.py 的腾讯财经数据源函数"""

import pandas as pd
import pytest

from src.data_pipeline import fetch_etf_daily_tx


def _tx_or_skip(code, start, end):
    """调 fetch_etf_daily_tx，不可达时 skip 测试。"""
    df = fetch_etf_daily_tx(code, start, end)
    if df.empty:
        pytest.skip("腾讯财经返回空数据（网络不可达或非交易日区间）")
    return df


class TestFetchEtfDailyTx:
    """场景 1：正常拉取 — 返回标准格式 DataFrame"""

    def test_returns_dataframe_with_required_columns(self):
        df = _tx_or_skip("510300", "2026-06-01", "2026-06-15")
        assert isinstance(df, pd.DataFrame)
        assert not df.empty
        required_cols = {"open", "high", "low", "close", "volume"}
        assert required_cols.issubset(set(df.columns)), f"缺失列: {required_cols - set(df.columns)}"
        assert isinstance(df.index, pd.DatetimeIndex)
        assert df.index.name == "date"

    def test_volume_is_positive_integers(self):
        """腾讯 amount 是成交量（手）×100 → volume 列应为正整数"""
        df = _tx_or_skip("510300", "2026-06-01", "2026-06-15")
        assert (df["volume"] > 0).all(), "volume 应全为正数"
        # volume 应为 100 的倍数（手 × 100 = 股）
        assert (df["volume"] % 100 == 0).all(), "volume 应为 100 的倍数"

    def test_shenzhen_code_prefix(self):
        """1xxxxx/0xxxxx → sz 前缀"""
        df = _tx_or_skip("159915", "2026-06-01", "2026-06-15")
        assert isinstance(df, pd.DataFrame)
        assert not df.empty

    def test_shanghai_code_prefix(self):
        """5xxxxx → sh 前缀"""
        df = _tx_or_skip("511010", "2026-06-01", "2026-06-15")
        assert isinstance(df, pd.DataFrame)
        assert not df.empty


class TestFetchEtfDailyTxEmpty:
    """场景 2：空参数处理"""

    def test_no_trade_dates_returns_empty(self):
        df = fetch_etf_daily_tx("510300", "2099-01-01", "2099-01-31")
        assert isinstance(df, pd.DataFrame)
        assert df.empty


class TestFetchEtfDailyTxInvalidCode:
    """场景 3：无效代码"""

    def test_invalid_code_returns_empty(self):
        df = fetch_etf_daily_tx("999999", "2026-06-01", "2026-06-15")
        assert isinstance(df, pd.DataFrame)
        assert df.empty
