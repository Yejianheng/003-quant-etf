# [2026-05-29] 新增：震荡市 Whipsaw 专项分析 — 单元测试

import os
import sys
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from analyze_whipsaw import (
    parse_defense_etfs,
    detect_etf_flips,
    classify_whipsaws,
    build_whipsaw_detail,
)


class TestParseDefenseEtfs:
    """parse_defense_etfs 从分号分隔字符串中提取 ETF 名称列表。"""

    def test_multiple_etfs(self):
        result = parse_defense_etfs("沪深300;创业板;纳指;国债ETF")
        assert result == ["沪深300", "创业板", "纳指", "国债ETF"]

    def test_single_etf(self):
        result = parse_defense_etfs("国债ETF")
        assert result == ["国债ETF"]

    def test_empty_string(self):
        assert parse_defense_etfs("") == []
        assert parse_defense_etfs(float("nan")) == []

    def test_none_value(self):
        assert parse_defense_etfs(None) == []


class TestDetectEtfFlips:
    """detect_etf_flips 检测单个 ETF 在 defense_active 列中的进出事件。"""

    def test_single_entry_exit(self):
        dates = pd.date_range("2020-01-02", periods=10, freq="B")
        da = pd.Series(
            ["创业板", "创业板;纳指", "创业板;纳指", "纳指", "纳指",
             "创业板;纳指", "创业板;纳指", "创业板", "创业板", ""],
            index=dates,
        )
        flips = detect_etf_flips(da, "创业板")
        # 创业板: present d0-d2, absent d3-d4, present d5-d7, absent d8-d9
        assert len(flips) >= 2
        assert flips.iloc[0]["event"] == "exit"
        assert flips.iloc[-1]["event"] == "exit"

    def test_no_flips(self):
        dates = pd.date_range("2020-01-02", periods=5, freq="B")
        da = pd.Series(["创业板;纳指"] * 5, index=dates)
        flips = detect_etf_flips(da, "创业板")
        assert len(flips) == 0


class TestClassifyWhipsaws:
    """classify_whipsaws 识别窗口内的快速进出对。"""

    def test_single_whipsaw_pair(self):
        dates = pd.date_range("2020-01-02", periods=30, freq="B")
        da = pd.Series(
            [""] * 5 + ["创业板"] * 5 + [""] * 20,
            index=dates,
        )
        flips = detect_etf_flips(da, "创业板")
        # entry at index 5, exit at index 10 → within 20-day window
        pairs = classify_whipsaws(flips, window=20)
        assert len(pairs) == 1
        assert pairs[0]["type"] == "whipsaw"

    def test_no_whipsaw_when_stable(self):
        dates = pd.date_range("2020-01-02", periods=100, freq="B")
        da = pd.Series(
            [""] * 10 + ["创业板"] * 80 + [""] * 10,
            index=dates,
        )
        flips = detect_etf_flips(da, "创业板")
        pairs = classify_whipsaws(flips, window=20)
        # entry then exit after 80 days → not within 20-day window
        assert len(pairs) == 0


class TestBuildWhipsawDetail:
    """build_whipsaw_detail 构建 whipsaw 明细表。"""

    def test_returns_dataframe(self):
        dates = pd.date_range("2020-01-02", periods=60, freq="B")
        nav = pd.Series(1.0 + np.cumsum(np.random.randn(60) * 0.005), index=dates)
        rec = pd.DataFrame({
            "defense_active": [""] * 10 + ["沪深300;创业板"] * 20
                            + ["沪深300"] * 15 + ["沪深300;创业板"] * 15,
            "nav": nav.values,
        }, index=dates)
        rec["defense_active"] = rec["defense_active"].astype(str)
        detail = build_whipsaw_detail(rec, nav, "2020-01-02", "2020-03-31", window=20)
        assert isinstance(detail, pd.DataFrame)
