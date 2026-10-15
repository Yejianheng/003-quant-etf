# [2026-10-15] 重写：适配 raw/adjusted 双层布局 + 新增门禁日期对齐、基准漂移两类用例
#             （旧版仍在调用 v214 已删除的 lookback_days 参数与 fetch_etf_daily，长期僵尸失败）
# [2026-06-18] 新增：test_single_day_fetch_when_need_one_day 检测 fence-post bug
# [2026-05-30] 新增：每日数据更新脚本测试 — 3 场景
"""测试 scripts/update_data.py — 原始行情层增量写入 + 研究行情层重算"""
import os
from datetime import date
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pytest


# ---- helpers ----

def _ohlcv(pairs):
    """pairs: [(日期字符串, 收盘价)] → 全列 OHLCV DataFrame（open=high=low=close）"""
    idx = pd.to_datetime([d for d, _ in pairs])
    c = [float(v) for _, v in pairs]
    return pd.DataFrame({"open": c, "high": c, "low": c, "close": c,
                         "volume": [1e6] * len(c)}, index=idx)


def _seed_raw(data_dir, code, pairs):
    """在原始行情层预置数据，返回其路径。"""
    raw_dir = os.path.join(data_dir, "raw")
    os.makedirs(raw_dir, exist_ok=True)
    path = os.path.join(raw_dir, f"{code}.parquet")
    _ohlcv(pairs).to_parquet(path)
    return path


def _run(data_dir, code="510300", tx=None, em=None, sina=None, today=(2026, 6, 18),
         write=True):
    """在固定时间门禁 + 屏蔽 sleep 的条件下跑完整入库流程。

    与 scripts/check_position.py 一致：update_single_etf 只负责拉取+校验，
    真正落盘由调用方调用 _write_parquet_incremental 完成。
    """
    empty = pd.DataFrame()
    from scripts.update_data import update_single_etf, _write_parquet_incremental
    with patch("scripts.update_data.time.sleep"), \
         patch("scripts.update_data.date") as md, \
         patch("scripts.update_data.datetime") as mdt:
        md.today.return_value = date(*today)
        mdt.now.return_value.hour = 20          # 过 15:00 时间门禁，end = today
        with patch("scripts.update_data.fetch_etf_daily_tx", MagicMock(return_value=empty if tx is None else tx)), \
             patch("scripts.update_data.fetch_etf_daily_em", MagicMock(return_value=empty if em is None else em)), \
             patch("scripts.update_data.fetch_etf_daily_sina", MagicMock(return_value=empty if sina is None else sina)):
            result = update_single_etf(code, data_dir)
        if write and result["ok"] and not result.get("needs_verify") and "new_data" in result:
            _write_parquet_incremental(code, result["new_data"], data_dir)
    return result


# ---- 基础路径 ----

def test_missing_parquet_returns_no_parquet(tmp_path):
    """原始行情层缺文件 → 不崩溃，返回 no_parquet"""
    data_dir = str(tmp_path / "data")
    os.makedirs(data_dir)
    assert _run(data_dir)["reason"] == "no_parquet"


def test_three_sources_agree_appends_to_raw(tmp_path):
    """三源一致 → 新数据落入原始行情层，且研究行情层被同步生成"""
    data_dir = str(tmp_path / "data")
    _seed_raw(data_dir, "510300", [("2026-06-15", 1.00), ("2026-06-16", 1.00)])
    fresh = _ohlcv([("2026-06-17", 1.10), ("2026-06-18", 1.20)])

    r = _run(data_dir, tx=fresh, em=fresh, sina=fresh)

    assert r["ok"] and not r["needs_verify"]
    raw = pd.read_parquet(os.path.join(data_dir, "raw", "510300.parquet"))
    assert len(raw) == 4
    assert raw.index.is_unique
    assert os.path.exists(os.path.join(data_dir, "510300.parquet")), "研究行情层应被派生"


def test_up_to_date_when_no_new_rows(tmp_path):
    """库内末日已是最新 → up_to_date，不发起入库"""
    data_dir = str(tmp_path / "data")
    _seed_raw(data_dir, "510300", [("2026-06-17", 1.00), ("2026-06-18", 1.00)])
    r = _run(data_dir)
    assert r["reason"] == "up_to_date"


# ---- 修复点 1：门禁比对按「共同最新日」对齐 ----

def test_gate_aligns_on_common_date(tmp_path):
    """某源当日数据未出（新浪滞后一天）时，应在共同最新日比对，不得误报分歧。

    旧逻辑取各源自己的最后一行：tx=06-18 的新浪 06-17 比，必然判为分歧。
    """
    data_dir = str(tmp_path / "data")
    _seed_raw(data_dir, "510300", [("2026-06-16", 1.00)])

    tx_em = _ohlcv([("2026-06-17", 1.10), ("2026-06-18", 1.20)])
    sina_lagging = _ohlcv([("2026-06-17", 1.10)])       # 缺 06-18

    r = _run(data_dir, tx=tx_em, em=tx_em, sina=sina_lagging)

    assert not r["needs_verify"], "共同日 06-17 三源一致，不应判为分歧"
    assert r["latest_date"] == "2026-06-18", "应采用有最新数据的源，写满到 06-18"


# ---- 修复点 2：基准漂移复检 ----

def test_basis_drift_blocks_write(tmp_path):
    """库内末日在某源上取值不同 → 判定价格基准已变，阻断写入"""
    data_dir = str(tmp_path / "data")
    _seed_raw(data_dir, "510300", [("2026-06-16", 1.00)])

    # 三个源都把 06-16 报成 1.02（与库内 1.00 不一致）= 复权口径变了
    drifted = _ohlcv([("2026-06-16", 1.02), ("2026-06-17", 1.05)])

    r = _run(data_dir, tx=drifted, em=drifted, sina=drifted)

    assert r["ok"] is False
    assert r["reason"] == "basis_drift"
    raw = pd.read_parquet(os.path.join(data_dir, "raw", "510300.parquet"))
    assert len(raw) == 1, "阻断时原始行情层不得被改动"


def test_basis_match_allows_write(tmp_path):
    """库内末日在各源上取值一致 → 不触发漂移告警（与上一条对照）"""
    data_dir = str(tmp_path / "data")
    _seed_raw(data_dir, "510300", [("2026-06-16", 1.00)])
    fresh = _ohlcv([("2026-06-16", 1.00), ("2026-06-17", 1.05)])

    r = _run(data_dir, tx=fresh, em=fresh, sina=fresh)

    assert r["ok"] and not r["needs_verify"]
    assert r["reason"] if "reason" in r else True
    raw = pd.read_parquet(os.path.join(data_dir, "raw", "510300.parquet"))
    assert len(raw) == 2


# ---- 研究行情层由分红再投派生 ----

def test_adjusted_layer_applies_dividends(tmp_path):
    """研究行情层 = 原始行情 × 分红因子；原始层保持不复权不动"""
    data_dir = str(tmp_path / "data")
    _seed_raw(data_dir, "510300", [("2026-06-15", 10.0), ("2026-06-16", 10.0)])
    div_dir = os.path.join(data_dir, "dividends")
    os.makedirs(div_dir, exist_ok=True)
    pd.DataFrame({"dividend": [1.0]}, index=pd.to_datetime(["2026-06-17"])).to_parquet(
        os.path.join(div_dir, "510300.parquet"))

    fresh = _ohlcv([("2026-06-17", 10.0), ("2026-06-18", 10.0)])
    _run(data_dir, tx=fresh, em=fresh, sina=fresh)

    raw = pd.read_parquet(os.path.join(data_dir, "raw", "510300.parquet"))
    adj = pd.read_parquet(os.path.join(data_dir, "510300.parquet"))

    assert raw["close"].iloc[-1] == pytest.approx(10.0), "原始层必须保持不复权"
    # 除息日 06-17 因子 = (10+1)/10 = 1.1，其后的 06-18 同样 ×1.1
    assert adj["close"].iloc[-1] == pytest.approx(11.0)
    assert adj["close"].iloc[0] == pytest.approx(10.0), "除息日之前不得被改写"


def test_no_dividend_table_keeps_layers_identical(tmp_path):
    """无除息表 → 研究行情层与原始行情层逐位相同"""
    data_dir = str(tmp_path / "data")
    _seed_raw(data_dir, "510300", [("2026-06-16", 1.00)])
    fresh = _ohlcv([("2026-06-17", 1.10)])
    _run(data_dir, tx=fresh, em=fresh, sina=fresh)

    raw = pd.read_parquet(os.path.join(data_dir, "raw", "510300.parquet"))
    adj = pd.read_parquet(os.path.join(data_dir, "510300.parquet"))
    pd.testing.assert_frame_equal(raw, adj)
