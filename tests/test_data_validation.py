# [2026-07-15] 新增：时间门禁 + 拉取不入库测试

import os
import sys

import pandas as pd
import pytest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _mock_ohlc(close_values, start_date="2026-07-14"):
    """构造模拟 OHLCV DataFrame。"""
    dates = pd.date_range(start_date, periods=len(close_values), freq="D")
    data = {
        "open": [c * 0.998 for c in close_values],
        "high": [c * 1.005 for c in close_values],
        "low": [c * 0.995 for c in close_values],
        "close": close_values,
        "volume": [1_000_000] * len(close_values),
    }
    df = pd.DataFrame(data, index=dates)
    df.index.name = "date"
    return df


def _seed_parquet(tmpdir, code="513100", last_close=2.168, last_date="2026-07-10"):
    """在 tmpdir 下创建含已有数据的 parquet。"""
    df = _mock_ohlc([last_close], last_date)
    path = os.path.join(str(tmpdir), f"{code}.parquet")
    df.to_parquet(path)
    return path


class TestTimeGate:
    """时间门禁：15:00 前不拉当日"""

    @patch("scripts.update_data.fetch_etf_daily_tx")
    @patch("scripts.update_data.fetch_etf_daily")
    @patch("scripts.update_data.datetime")
    def test_before_15_skip_when_already_today(self, mock_dt, mock_em, mock_tx, tmpdir):
        """15:00 前，parquet 已有今天数据（last_date=今天），start>end → up_to_date"""
        _seed_parquet(tmpdir, last_date="2026-07-15", last_close=2.170)

        mock_now = pd.Timestamp("2026-07-15 10:00:00")
        mock_dt.now.return_value = mock_now
        mock_dt.side_effect = lambda *a, **kw: pd.Timestamp(*a, **kw)

        from scripts.update_data import update_single_etf

        result = update_single_etf("513100", str(tmpdir))
        # 时间门禁：end = 7/14，start = 7/16 > end → up_to_date
        assert result["ok"] is True
        assert result.get("needs_verify") is False
        assert result.get("reason") == "up_to_date"

    @patch("scripts.update_data.fetch_etf_daily_tx")
    @patch("scripts.update_data.fetch_etf_daily")
    @patch("scripts.update_data.datetime")
    def test_after_15_fetch_today(self, mock_dt, mock_em, mock_tx, tmpdir):
        """15:00 后 → end_date=今天。last_date=7/14, 今天=7/15, start=7/15, end=7/15"""
        _seed_parquet(tmpdir, last_date="2026-07-14", last_close=2.168)

        mock_now = pd.Timestamp("2026-07-15 15:30:00")
        mock_dt.now.return_value = mock_now
        mock_dt.side_effect = lambda *a, **kw: pd.Timestamp(*a, **kw)

        mock_tx.return_value = _mock_ohlc([2.170], "2026-07-15")
        mock_em.return_value = _mock_ohlc([2.170], "2026-07-15")

        from scripts.update_data import update_single_etf

        result = update_single_etf("513100", str(tmpdir))
        assert result.get("needs_verify") is True


class TestFetchAndVerify:
    """拉取逻辑 + 返回结构"""

    @patch("scripts.update_data.fetch_etf_daily_tx")
    @patch("scripts.update_data.fetch_etf_daily")
    @patch("scripts.update_data.datetime")
    def test_fetch_ok_returns_needs_verify(self, mock_dt, mock_em, mock_tx, tmpdir):
        """拉到数据 → needs_verify=True，含 latest_close 和 new_data"""
        _seed_parquet(tmpdir, last_date="2026-07-14", last_close=2.168)

        mock_now = pd.Timestamp("2026-07-15 15:30:00")
        mock_dt.now.return_value = mock_now
        mock_dt.side_effect = lambda *a, **kw: pd.Timestamp(*a, **kw)

        mock_tx.return_value = _mock_ohlc([2.170], "2026-07-15")
        mock_em.return_value = pd.DataFrame()

        from scripts.update_data import update_single_etf

        result = update_single_etf("513100", str(tmpdir))
        assert result["ok"] is True
        assert result["needs_verify"] is True
        assert result["code"] == "513100"
        assert result["source"] == "tx"
        assert result["latest_close"] == 2.170
        assert result["latest_date"] == "2026-07-15"
        assert "new_data" in result
        assert isinstance(result["new_data"], pd.DataFrame)

    @patch("scripts.update_data.fetch_etf_daily_tx")
    @patch("scripts.update_data.fetch_etf_daily")
    @patch("scripts.update_data.datetime")
    def test_tx_fallback_to_em(self, mock_dt, mock_em, mock_tx, tmpdir):
        """腾讯空 → 切东方财富，source='em'"""
        _seed_parquet(tmpdir, last_date="2026-07-14", last_close=2.168)

        mock_now = pd.Timestamp("2026-07-15 15:30:00")
        mock_dt.now.return_value = mock_now
        mock_dt.side_effect = lambda *a, **kw: pd.Timestamp(*a, **kw)

        mock_tx.return_value = pd.DataFrame()
        mock_em.return_value = _mock_ohlc([2.170], "2026-07-15")

        from scripts.update_data import update_single_etf

        result = update_single_etf("513100", str(tmpdir))
        assert result["ok"] is True
        assert result["needs_verify"] is True
        assert result["source"] == "em"
        assert result["latest_close"] == 2.170

    @patch("scripts.update_data.fetch_etf_daily_tx")
    @patch("scripts.update_data.fetch_etf_daily")
    @patch("scripts.update_data.datetime")
    def test_both_empty(self, mock_dt, mock_em, mock_tx, tmpdir):
        """两源均空 → ok=False reason=no_data"""
        _seed_parquet(tmpdir, last_date="2026-07-14", last_close=2.168)

        mock_now = pd.Timestamp("2026-07-15 15:30:00")
        mock_dt.now.return_value = mock_now
        mock_dt.side_effect = lambda *a, **kw: pd.Timestamp(*a, **kw)

        mock_tx.return_value = pd.DataFrame()
        mock_em.return_value = pd.DataFrame()

        from scripts.update_data import update_single_etf

        result = update_single_etf("513100", str(tmpdir))
        assert result["ok"] is False
        assert result["reason"] == "no_data"

    @patch("scripts.update_data.fetch_etf_daily_tx")
    @patch("scripts.update_data.fetch_etf_daily")
    @patch("scripts.update_data.datetime")
    def test_up_to_date(self, mock_dt, mock_em, mock_tx, tmpdir):
        """已是最新 → ok=True needs_verify=False"""
        _seed_parquet(tmpdir, last_date="2026-07-15", last_close=2.170)

        mock_now = pd.Timestamp("2026-07-15 15:30:00")
        mock_dt.now.return_value = mock_now
        mock_dt.side_effect = lambda *a, **kw: pd.Timestamp(*a, **kw)

        from scripts.update_data import update_single_etf

        result = update_single_etf("513100", str(tmpdir))
        assert result["ok"] is True
        assert result.get("needs_verify") is False
        assert result.get("reason") == "up_to_date"
