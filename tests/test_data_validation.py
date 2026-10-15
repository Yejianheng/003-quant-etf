# [2026-10-15] 重写：适配 raw/adjusted 双层布局；同时 mock date 与 datetime 消除时间依赖
#             （旧版只 mock datetime，date.today() 取真实当天，用例随日期推移必然失效；
#               且预置到 data/{code}.parquet、patch 已废弃的 fetch_etf_daily）
# [2026-07-15] 新增：时间门禁 + 拉取不入库测试
"""测试 scripts/update_data.py — 时间门禁（15:00）与数据源降级链"""

import os
import sys
from datetime import date
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _mock_ohlc(close_values, start_date):
    """构造模拟 OHLCV DataFrame。"""
    dates = pd.date_range(start_date, periods=len(close_values), freq="D")
    df = pd.DataFrame({
        "open": [c * 0.998 for c in close_values],
        "high": [c * 1.005 for c in close_values],
        "low": [c * 0.995 for c in close_values],
        "close": close_values,
        "volume": [1_000_000] * len(close_values),
    }, index=dates)
    df.index.name = "date"
    return df


def _seed_raw(tmpdir, code="513100", last_close=2.168, last_date="2026-07-10"):
    """在原始行情层 data/raw/{code}.parquet 预置数据。"""
    raw_dir = os.path.join(str(tmpdir), "raw")
    os.makedirs(raw_dir, exist_ok=True)
    path = os.path.join(raw_dir, f"{code}.parquet")
    _mock_ohlc([last_close], last_date).to_parquet(path)
    return path


def _run(tmpdir, code="513100", today=(2026, 7, 15), hour=15, tx=None, em=None, sina=None):
    """固定 date/datetime + 屏蔽 sleep + 屏蔽三源网络调用，跑一次 update_single_etf。"""
    empty = pd.DataFrame()
    from scripts.update_data import update_single_etf
    with patch("scripts.update_data.time.sleep"), \
         patch("scripts.update_data.date") as md, \
         patch("scripts.update_data.datetime") as mdt, \
         patch("scripts.update_data.fetch_etf_daily_tx", MagicMock(return_value=empty if tx is None else tx)), \
         patch("scripts.update_data.fetch_etf_daily_em", MagicMock(return_value=empty if em is None else em)), \
         patch("scripts.update_data.fetch_etf_daily_sina", MagicMock(return_value=empty if sina is None else sina)):
        md.today.return_value = date(*today)
        mdt.now.return_value.hour = hour
        return update_single_etf(code, str(tmpdir))


class TestTimeGate:
    """时间门禁：15:00 前不拉当日"""

    def test_before_15_treats_today_as_unavailable(self, tmp_path):
        """10:00 运行 → end_date 退到昨天；库内已有昨天数据 → up_to_date"""
        _seed_raw(tmp_path, last_date="2026-07-14", last_close=2.168)
        r = _run(tmp_path, today=(2026, 7, 15), hour=10)
        assert r["ok"] is True
        assert r.get("needs_verify") is False
        assert r.get("reason") == "up_to_date"

    def test_before_15_still_fetches_missing_prior_day(self, tmp_path):
        """10:00 运行但库内只到前天 → 仍应拉取到昨天，不得整体跳过"""
        _seed_raw(tmp_path, last_date="2026-07-13", last_close=2.160)
        new = _mock_ohlc([2.168], "2026-07-14")
        r = _run(tmp_path, today=(2026, 7, 15), hour=10, tx=new, em=new, sina=new)
        assert r.get("needs_verify") is False
        assert r["latest_date"] == "2026-07-14", "15:00 前只能拉到昨天"

    def test_after_15_includes_today(self, tmp_path):
        """15:30 运行 → end_date = 今天"""
        _seed_raw(tmp_path, last_date="2026-07-14", last_close=2.168)
        new = _mock_ohlc([2.170], "2026-07-15")
        r = _run(tmp_path, today=(2026, 7, 15), hour=15, tx=new, em=new, sina=new)
        assert r.get("needs_verify") is False
        assert r["latest_date"] == "2026-07-15", "15:00 后当日数据应纳入"


class TestFetchAndVerify:
    """数据源降级链 + 返回结构"""

    def test_single_source_needs_verify(self, tmp_path):
        """仅腾讯有数据 → needs_verify=True，并带上 new_data"""
        _seed_raw(tmp_path, last_date="2026-07-14", last_close=2.168)
        r = _run(tmp_path, hour=15, tx=_mock_ohlc([2.170], "2026-07-15"))
        assert r["ok"] is True
        assert r["needs_verify"] is True
        assert r["code"] == "513100"
        assert r["source"] == "tx"
        assert r["latest_close"] == 2.170
        assert isinstance(r["new_data"], pd.DataFrame)

    def test_tx_empty_falls_back_to_em(self, tmp_path):
        """腾讯空 → 东方财富顶上，source='em'"""
        _seed_raw(tmp_path, last_date="2026-07-14", last_close=2.168)
        r = _run(tmp_path, hour=15, tx=pd.DataFrame(), em=_mock_ohlc([2.170], "2026-07-15"))
        assert r["ok"] is True
        assert r["needs_verify"] is True
        assert r["source"] == "em"
        assert r["latest_close"] == 2.170

    def test_two_sources_agree_passes(self, tmp_path):
        """两源同值 → 自动通过（无需核验）"""
        _seed_raw(tmp_path, last_date="2026-07-14", last_close=2.168)
        same = _mock_ohlc([2.170], "2026-07-15")
        r = _run(tmp_path, hour=15, tx=same, em=same)
        assert r["ok"] is True
        assert r.get("needs_verify") is False
        assert r["agreed_sources"] == 2

    def test_both_empty_no_data(self, tmp_path):
        """三源均空 → ok=False reason=no_data"""
        _seed_raw(tmp_path, last_date="2026-07-14", last_close=2.168)
        r = _run(tmp_path, hour=15)
        assert r["ok"] is False
        assert r["reason"] == "no_data"

    def test_missing_parquet(self, tmp_path):
        """原始行情层缺文件 → no_parquet"""
        os.makedirs(str(tmp_path), exist_ok=True)
        assert _run(tmp_path, hour=15)["reason"] == "no_parquet"

    def test_up_to_date_when_last_is_today(self, tmp_path):
        """库内已是今天 → up_to_date，不发起拉取"""
        _seed_raw(tmp_path, last_date="2026-07-15", last_close=2.170)
        r = _run(tmp_path, hour=15)
        assert r["ok"] is True
        assert r.get("needs_verify") is False
        assert r.get("reason") == "up_to_date"
