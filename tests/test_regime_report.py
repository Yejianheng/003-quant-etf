# [2026-05-29] 新增：汇总报告输出验证

import os
import sys
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from regime_report import build_final_report

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")


class TestBuildFinalReport:
    """build_final_report 合并前三步数据输出最终报告。"""

    def test_returns_dataframe_with_required_columns(self):
        df = build_final_report(OUTPUT_DIR)
        required = ["Regime", "纯防御收益", "纯防御Sharpe", "最大回撤",
                     "空仓率", "Whipsaw", "是否存活"]
        for col in required:
            assert col in df.columns, f"缺少列: {col}"

    def test_all_regimes_survive(self):
        df = build_final_report(OUTPUT_DIR)
        assert (df["是否存活"] == "存活").all()

    def test_all_regimes_present(self):
        df = build_final_report(OUTPUT_DIR)
        regimes = set(df["Regime"])
        expected = {"单边牛市", "长期熊市", "高频震荡市", "利率regime_shift"}
        assert regimes == expected
