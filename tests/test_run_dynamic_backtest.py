# [2026-05-29] 新增：run_dynamic_backtest 脚本测试

import os
import sys
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.run_dynamic_backtest import (
    load_prices,
    compute_metrics,
    fmt_metrics,
    DEFENSE_MAP,
    OFFENSE_MAP,
    FIXED_PARAMS_BASE,
)


class TestLoadPrices:
    """数据加载"""

    def test_load_existing_etf(self):
        """加载存在的 ETF 数据 → 返回 DataFrame"""
        df = load_prices("510300")
        assert df is not None
        assert "close" in df.columns
        assert len(df) > 0

    def test_load_missing_etf(self):
        """加载不存在的 ETF → 返回 None"""
        df = load_prices("999999")
        assert df is None


class TestComputeMetrics:
    """绩效指标计算"""

    def test_uptrend_metrics(self):
        """上涨净值 → 正收益正 Sharpe"""
        dates = pd.date_range("2024-01-01", periods=252, freq="B")
        nav = pd.Series(1.0 * np.exp(np.cumsum(np.full(252, 0.001))), index=dates)
        m = compute_metrics(nav)
        assert m["总收益"] > 0
        assert m["Sharpe"] > 0
        assert m["最大回撤"] <= 0

    def test_short_series(self):
        """不足 2 天 → 返回空 dict"""
        nav = pd.Series([1.0], index=[pd.Timestamp("2024-01-01")])
        m = compute_metrics(nav)
        assert m == {}


class TestFmtMetrics:
    def test_formats_as_percentages(self):
        m = {"总收益": 0.1234, "年化": 0.0567, "波动率": 0.15, "Sharpe": 0.89, "最大回撤": -0.15}
        f = fmt_metrics(m)
        assert "%" in f["总收益"]
        assert "%" in f["年化"]
        assert "0.89" in f["Sharpe"]


class TestConfigs:
    """配置完整性"""

    def test_defense_map_has_5_entries(self):
        assert len(DEFENSE_MAP) == 5

    def test_offense_map_has_6_entries(self):
        assert len(OFFENSE_MAP) == 6

    def test_fixed_params_has_required_keys(self):
        for key in ["trend_window", "ewma_lambda", "target_vol_beta", "target_vol_alpha"]:
            assert key in FIXED_PARAMS_BASE


class TestMainImport:
    """验证脚本可导入且 main 函数存在"""

    def test_main_function_exists(self):
        """main 函数可导入"""
        from scripts.run_dynamic_backtest import main
        assert callable(main)


class TestMainIntegration:
    """集成测试：完整回测运行（慢，需 --run-slow 标记）"""

    @pytest.mark.slow
    def test_main_runs_without_error(self):
        """main() 不抛异常，产生 CSV 输出"""
        from scripts.run_dynamic_backtest import main
        main()
        out = os.path.join(os.path.dirname(__file__), "..", "output", "dynamic_backtest_results.csv")
        assert os.path.exists(out), f"输出文件应存在: {out}"
