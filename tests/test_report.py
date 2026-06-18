# [2026-06-18] 新增：报表模块测试
import pytest
import numpy as np
import pandas as pd
import os
import tempfile
from attribution.report import generate_four_tables_report
from attribution.factor_return import factor_attribution
from attribution.timing import timing_decomposition
from attribution.tail_risk import tail_risk_audit
from attribution.stability import stability_matrix


def _make_fake_results():
    rng = np.random.default_rng(42)
    dates = pd.date_range("2018-01-02", "2025-12-31", freq="B")
    n = len(dates)
    factor = pd.DataFrame({
        "沪深300": rng.normal(0.0003, 0.015, n),
        "创业板": rng.normal(0.0004, 0.020, n),
        "纳指": rng.normal(0.0005, 0.014, n),
        "黄金": rng.normal(0.0001, 0.010, n),
        "国债ETF": rng.normal(0.0001, 0.004, n),
    }, index=dates)
    strategy = 0.4 * factor["沪深300"] + 0.2 * factor["创业板"] + 0.15 * factor["纳指"] \
        + 0.1 * factor["黄金"] + 0.15 * factor["国债ETF"] + rng.normal(0, 0.002, n)
    strategy = pd.Series(strategy, index=dates, name="strategy")
    bench = factor.mean(axis=1)
    fa = factor_attribution(strategy, factor)
    td = timing_decomposition(strategy, bench)
    tr = tail_risk_audit(strategy, bench)
    sm = stability_matrix(daily_returns=strategy)
    return {"factor_return": fa, "timing": td, "tail_risk": tr, "stability": sm}


class TestReport:
    def test_generates_html_file(self):
        results = _make_fake_results()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "report.html")
            generate_four_tables_report(results, path)
            assert os.path.exists(path)
            content = open(path, encoding="utf-8").read()
            assert "因子归因" in content
            assert "择时分解" in content
            assert "尾部审计" in content
            assert "稳定性矩阵" in content

    def test_handles_nan_values(self):
        results = _make_fake_results()
        results["tail_risk"]["skewness"] = np.nan
        results["stability"]["parameter_sensitivity"] = []
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "report.html")
            generate_four_tables_report(results, path)
            assert os.path.exists(path)
