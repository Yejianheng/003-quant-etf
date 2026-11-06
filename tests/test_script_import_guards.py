# [2026-11-07] 新增：脚本 import 无副作用门禁 — 禁止 import 即跑全量扫描/写数据
"""测试 scripts/ 下的研究脚本：被 import 时不得执行重活或写文件。

回归 #2026-11-07：test_corr_robustness_scan 在 skip 前 import 脚本，
脚本模块顶层直接跑全量参数扫描 → 整套测试卡死；
test_macro_corr_decomposition import 时自动拉取宏观数据并覆盖
data/macro_indicators.parquet → 测试污染工作区。
"""

import sys
import types
from unittest.mock import patch

import pandas as pd
import pytest


def test_corr_scan_import_does_not_run_backtest():
    """import corr_robustness_scan 不得触发 run_backtest。"""
    sys.modules.pop("scripts.corr_robustness_scan", None)

    with patch("src.backtest_engine.run_backtest",
               side_effect=AssertionError("import 时不得跑回测")):
        import scripts.corr_robustness_scan  # noqa: F401


def test_macro_script_import_does_not_write_parquet():
    """import macro_corr_decomposition 不得拉数据、不得写 data/。"""
    sys.modules.pop("scripts.macro_corr_decomposition", None)

    fake_ak = types.ModuleType("akshare")

    def _bond_rates():
        dates = pd.date_range("2020-01-01", periods=100, freq="D")
        return pd.DataFrame({
            "日期": dates,
            "中国国债收益率10年": [2.5] * 100,
            "中国国债收益率2年": [2.0] * 100,
            "美国国债收益率10年": [1.5] * 100,
        })

    def _cpi():
        return pd.DataFrame({
            "日期": pd.date_range("2020-01-31", periods=12, freq="ME"),
            "今值": [1.0] * 12,
        })

    fake_ak.bond_zh_us_rate = _bond_rates
    fake_ak.macro_china_cpi_monthly = _cpi

    with (
        patch.dict(sys.modules, {"akshare": fake_ak}),
        patch("pandas.DataFrame.to_parquet",
              side_effect=AssertionError("import 时不得写 parquet")),
    ):
        import scripts.macro_corr_decomposition  # noqa: F401
