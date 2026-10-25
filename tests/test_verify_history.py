# [2026-10-25] 新增：历史行情抽检门禁测试 — 历史行入库后不再复核，靠抽检发现沉淀错误
"""测试 scripts/verify_history.py — data/raw 收盘价与第二源逐日比对"""

import os

import numpy as np
import pandas as pd
import pytest


def _make_close_series(n=300, seed=42):
    """合成收盘价序列（与 raw 层同结构）。"""
    rng = np.random.RandomState(seed)
    dates = pd.date_range("2025-06-02", periods=n, freq="B")
    prices = 10.0 * np.exp(np.cumsum(rng.normal(0.0002, 0.008, n)))
    return pd.Series(prices, index=dates, name="close")


def _write_raw(data_dir, codes, close_series):
    """为每只 ETF 写入 raw parquet（仅 close 即可满足抽检）。"""
    os.makedirs(os.path.join(data_dir, "raw"), exist_ok=True)
    for code in codes:
        df = pd.DataFrame({"close": close_series.values}, index=close_series.index)
        df.to_parquet(os.path.join(data_dir, "raw", f"{code}.parquet"))


class TestVerifyHistory:
    """verify_history.verify(): 第二源一致 → 无问题；任一不一致 → 报出"""

    def test_all_match_returns_empty(self, tmp_path):
        """两源逐日完全一致 → 无问题"""
        from scripts.verify_history import verify

        data_dir = str(tmp_path / "data")
        codes = ["510300", "159915"]
        close = _make_close_series()
        _write_raw(data_dir, codes, close)

        problems = verify(data_dir, codes=codes, fetch_fn=lambda c: close.copy())
        assert problems == []

    def test_single_mismatch_is_reported(self, tmp_path):
        """某日第二源与 raw 相差 0.01 → 报出 code + 日期 + 两值"""
        from scripts.verify_history import verify

        data_dir = str(tmp_path / "data")
        codes = ["510300"]
        close = _make_close_series()
        _write_raw(data_dir, codes, close)

        wrong = close.copy()
        target = wrong.index[100]
        wrong.iloc[100] += 0.01

        problems = verify(data_dir, codes=codes, fetch_fn=lambda c: wrong)
        assert len(problems) == 1
        msg = problems[0]
        assert "510300" in msg
        assert str(target.date()) in msg

    def test_missing_raw_parquet_is_reported(self, tmp_path):
        """raw 文件缺失 → 报出缺失，不得静默跳过"""
        from scripts.verify_history import verify

        data_dir = str(tmp_path / "data")
        os.makedirs(data_dir)
        problems = verify(data_dir, codes=["510300"], fetch_fn=lambda c: _make_close_series())
        assert len(problems) == 1
        assert "510300" in problems[0]

    def test_source_failure_is_reported(self, tmp_path):
        """第二源拉取失败 → 报出失败，退出码应为 1"""
        from scripts.verify_history import verify

        data_dir = str(tmp_path / "data")
        codes = ["510300"]
        close = _make_close_series()
        _write_raw(data_dir, codes, close)

        def _boom(code):
            raise RuntimeError("network down")

        problems = verify(data_dir, codes=codes, fetch_fn=_boom)
        assert len(problems) == 1
        assert "拉取失败" in problems[0]

    def test_main_exit_code(self, tmp_path, monkeypatch):
        """main(): 全部一致 → 0；存在不一致 → 1"""
        from scripts import verify_history

        data_dir = str(tmp_path / "data")
        close = _make_close_series()
        _write_raw(data_dir, verify_history.DEFAULT_CODES, close)

        monkeypatch.setattr(verify_history, "fetch_sina_close", lambda c: close.copy())
        assert verify_history.main(["--data-dir", data_dir]) == 0

        wrong = close.copy()
        wrong.iloc[-1] += 0.01
        monkeypatch.setattr(verify_history, "fetch_sina_close", lambda c: wrong)
        assert verify_history.main(["--data-dir", data_dir]) == 1
