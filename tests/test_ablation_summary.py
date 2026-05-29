# [2026-05-30] 新增：Ablation 汇总测试

import os
import sys
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.ablation_summary import extract_mixed_row


class TestExtractMixedRow:
    def test_extracts_both_states(self):
        """提取混合配置的有/无模块两行。"""
        row_on, row_off = extract_mixed_row("ablation_1.2_trend_filter.csv")
        assert len(row_on) > 0, "应有'有趋势过滤'行"
        assert len(row_off) > 0, "应有'无趋势过滤'行"
        assert "Sharpe" in row_on
        assert "最大回撤" in row_on

    def test_all_four_ablations(self):
        """四个 ablation CSV 都能正常提取混合配置。"""
        files = [
            "ablation_1.2_trend_filter.csv",
            "ablation_1.3_vol_target.csv",
            "ablation_1.4_ewma.csv",
            "ablation_1.5_corr_cb.csv",
        ]
        for f in files:
            row_on, row_off = extract_mixed_row(f)
            assert row_on["Sharpe"] is not None, f"{f}: 有模块 Sharpe 缺失"
            assert row_off["Sharpe"] is not None, f"{f}: 无模块 Sharpe 缺失"
