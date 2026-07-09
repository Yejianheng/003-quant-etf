# [2026-06-23] 新增：新鲜度门禁测试 — 3 场景
"""测试 check_freshness 函数"""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest


def _make_ohlcv_df(dates):
    """根据日期列表创建模拟 OHLCV DataFrame。"""
    n = len(dates)
    rng = np.random.RandomState(42)
    prices = 1.0 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, n)))
    return pd.DataFrame({
        "open": prices * 0.99, "high": prices * 1.02,
        "low": prices * 0.98, "close": prices, "volume": np.full(n, 1e6),
    }, index=pd.DatetimeIndex(dates))


def _bday_range_ending(anchor: date, periods: int):
    """生成结束于 anchor 的 periods 个交易日日期列表。"""
    return pd.date_range(end=str(anchor), periods=periods, freq="B")


class TestCheckFreshness:
    """check_freshness 单元测试"""

    def test_all_fresh_returns_empty(self, tmp_path):
        """全部 ETF 在容忍期内 → 返回空列表"""
        today = date.today()
        # 用最近 5 个交易日，最后一天可能是今天或最近交易日
        dates = _bday_range_ending(today, 5)
        df = _make_ohlcv_df(dates)

        for code in ["510300", "159915"]:
            df.to_parquet(str(tmp_path / f"{code}.parquet"))

        from src.data_pipeline import check_freshness
        stale = check_freshness(["510300", "159915"], str(tmp_path))
        assert stale == []

    def test_stale_returns_codes(self, tmp_path):
        """部分 ETF 超过容忍期限 → 返回对应代码列表"""
        today = date.today()
        # Fresh: 5 business days ending on today
        fresh_dates = _bday_range_ending(today, 5)
        if fresh_dates[-1].date() != today:
            pytest.skip("今天不是交易日")
        fresh_df = _make_ohlcv_df(fresh_dates)
        fresh_df.to_parquet(str(tmp_path / "510300.parquet"))

        # Stale: 5 business days ending 10 calendar days ago
        stale_end = today - timedelta(days=10)
        stale_dates = _bday_range_ending(stale_end, 5)
        stale_df = _make_ohlcv_df(stale_dates)
        stale_df.to_parquet(str(tmp_path / "159915.parquet"))

        from src.data_pipeline import check_freshness
        stale = check_freshness(["510300", "159915"], str(tmp_path))
        assert stale == ["159915"]

    def test_missing_parquet_returns_code(self, tmp_path):
        """parquet 不存在 → 返回对应代码"""
        from src.data_pipeline import check_freshness
        stale = check_freshness(["510300"], str(tmp_path))
        assert stale == ["510300"]
