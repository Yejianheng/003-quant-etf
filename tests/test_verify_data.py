# [2026-06-22] 新增：verify_data 测试 — 新鲜度/行数/空值三类检查

import os
import numpy as np
import pandas as pd
import pytest


def _make_ohlcv_df(days=260, end_date=None):
    """生成模拟 OHLCV DataFrame，日期为 end_date 前 days 个交易日。"""
    if end_date is None:
        end_date = pd.Timestamp.today()
    start = end_date - pd.DateOffset(days=int(days * 1.8))
    all_dates = pd.bdate_range(start, end_date)
    dates = all_dates[-days:]
    n = len(dates)
    rng = np.random.RandomState(42)
    prices = 1.0 * np.exp(np.cumsum(rng.normal(0.0002, 0.008, n)))
    return pd.DataFrame({
        "open": prices * 0.99,
        "high": prices * 1.02,
        "low": prices * 0.98,
        "close": prices,
        "volume": np.full(n, 1e6),
    }, index=dates)


def _make_defense_parquet(data_dir, code, days=260, end_date=None, inject_nan=False):
    """在 data_dir 创建单只防御 ETF 的模拟 parquet。"""
    from src.etf_universe import ETF_UNIVERSE
    os.makedirs(data_dir, exist_ok=True)
    df = _make_ohlcv_df(days=days, end_date=end_date)
    if inject_nan:
        df.iloc[0, df.columns.get_loc("close")] = np.nan
    path = os.path.join(data_dir, f"{code}.parquet")
    df.to_parquet(path)
    return df


def _make_all_fresh(data_dir, end_date=None):
    """创建 5 只全部新鲜的防御 ETF parquet。"""
    from src.signal_generator import DEFENSE_NAMES
    from src.etf_universe import ETF_UNIVERSE
    for name in DEFENSE_NAMES:
        _make_defense_parquet(data_dir, ETF_UNIVERSE[name], end_date=end_date)


class TestAllFresh:
    """5 parquets 全部最新、行数一致、无 NaN → 无告警"""

    def test_all_fresh_returns_empty(self, tmp_path):
        data_dir = str(tmp_path / "data")
        _make_all_fresh(data_dir)

        from scripts.verify_data import verify_data
        warnings = verify_data(data_dir)
        assert warnings == [], f"预期无告警，实际得到 {len(warnings)} 条: {warnings}"


class TestStaleWarning:
    """1 只 ETF 最新日期落后 4 自然日 → 告警含 [新鲜度]"""

    def test_stale_detected(self, tmp_path):
        from src.signal_generator import DEFENSE_NAMES
        from src.etf_universe import ETF_UNIVERSE
        from scripts.verify_data import verify_data

        data_dir = str(tmp_path / "data")
        today = pd.Timestamp.today()

        # 4 只新鲜，截止今天
        fresh_end = today
        stale_end = today - pd.DateOffset(days=10)

        names = list(DEFENSE_NAMES)
        for name in names[:4]:
            _make_defense_parquet(data_dir, ETF_UNIVERSE[name], end_date=fresh_end)
        # 1 只落后 4 自然日
        _make_defense_parquet(data_dir, ETF_UNIVERSE[names[4]], end_date=stale_end)

        warnings = verify_data(data_dir)
        assert any("[新鲜度]" in w for w in warnings), (
            f"预期含 [新鲜度] 告警，实际: {warnings}"
        )


class TestNullWarning:
    """1 只 ETF close 列有 NaN → 告警含 [空值]"""

    def test_null_detected(self, tmp_path):
        from src.signal_generator import DEFENSE_NAMES
        from src.etf_universe import ETF_UNIVERSE
        from scripts.verify_data import verify_data

        data_dir = str(tmp_path / "data")
        names = list(DEFENSE_NAMES)
        for name in names[:4]:
            _make_defense_parquet(data_dir, ETF_UNIVERSE[name])
        # 1 只有 NaN
        _make_defense_parquet(data_dir, ETF_UNIVERSE[names[4]], inject_nan=True)

        warnings = verify_data(data_dir)
        assert any("[空值]" in w for w in warnings), (
            f"预期含 [空值] 告警，实际: {warnings}"
        )
