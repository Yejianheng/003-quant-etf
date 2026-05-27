"""测试 visualization.py — HTML 报告生成。"""
import os
import tempfile
import pandas as pd
import numpy as np
import pytest

# [2026-05-27] 新增：visualization 模块测试


@pytest.fixture
def sample_result():
    """构造 run_backtest 返回值格式的样本数据。"""
    dates = pd.date_range("2020-01-02", "2020-12-31", freq="B")
    n = len(dates)
    rng = np.random.default_rng(42)
    nav = 1_000_000 * (1 + rng.normal(0.0003, 0.01, n)).cumprod()
    bench = 1.0 * (1 + rng.normal(0.0002, 0.008, n)).cumprod()

    records_df = pd.DataFrame({"nav": nav}, index=dates)
    benchmark_nav = pd.Series(bench, index=dates)

    return {
        "records_df": records_df,
        "benchmark_nav": benchmark_nav,
        "final_nav": float(nav[-1]),
        "final_benchmark_nav": float(bench[-1]),
        "total_return": float((nav[-1] - 1_000_000) / 1_000_000),
        "benchmark_return": float(bench[-1] - 1.0),
        "annual_return": 0.05,
        "annual_volatility": 0.12,
        "sharpe_ratio": 0.42,
        "max_drawdown": -0.15,
        "calmar_ratio": 0.33,
    }


class TestGenerateReport:
    def test_returns_html_path(self, sample_result):
        from src.visualization import generate_report

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "report.html")
            result_path = generate_report(sample_result, output_path=path)
            assert result_path == path
            assert os.path.exists(path)

    def test_html_contains_nav_chart(self, sample_result):
        from src.visualization import generate_report

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "report.html")
            generate_report(sample_result, output_path=path)
            html = open(path, encoding="utf-8").read()
            assert "<canvas" in html
            assert "navChart" in html or "nav" in html.lower()
            assert "Chart.js" in html or "chart.js" in html.lower()

    def test_html_contains_drawdown_chart(self, sample_result):
        from src.visualization import generate_report

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "report.html")
            generate_report(sample_result, output_path=path)
            html = open(path, encoding="utf-8").read()
            assert "ddChart" in html

    def test_html_contains_metrics(self, sample_result):
        from src.visualization import generate_report

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "report.html")
            generate_report(sample_result, output_path=path)
            html = open(path, encoding="utf-8").read()
            assert "总收益" in html or "total_return" in html.lower()
            assert "Sharpe" in html or "sharpe" in html.lower()
            assert "最大回撤" in html or "max_drawdown" in html.lower()

    def test_empty_records_does_not_crash(self):
        from src.visualization import generate_report

        empty_result = {
            "records_df": pd.DataFrame(),
            "benchmark_nav": pd.Series(dtype=float),
            "final_nav": 1_000_000.0,
            "final_benchmark_nav": 1.0,
            "total_return": 0.0,
            "benchmark_return": 0.0,
            "annual_return": 0.0,
            "annual_volatility": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown": 0.0,
            "calmar_ratio": 0.0,
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "report.html")
            result_path = generate_report(empty_result, output_path=path)
            assert os.path.exists(result_path)

    def test_creates_output_directory(self, sample_result):
        from src.visualization import generate_report

        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = os.path.join(tmpdir, "nested", "reports")
            path = os.path.join(out_dir, "report.html")
            generate_report(sample_result, output_path=path)
            assert os.path.exists(path)
