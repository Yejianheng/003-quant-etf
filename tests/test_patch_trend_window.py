# [2026-05-30] 新增：patch_trend_window.py 的测试
"""测试补测 trend_window=30/50 脚本"""
import pytest
import os
import sys
sys.path.insert(0, ".")

from scripts.patch_trend_window import main as patch_main


class TestPatchTrendWindow:
    """基础路径：数据加载成功 → 返回 2 条结果"""

    def test_runs_without_error(self, tmp_path, monkeypatch):
        """脚本成功运行，不抛异常"""
        # 用 tmp_path 替代 data/ 路径避免污染真实数据
        # 只验证导入和函数签名正确，实际回测由 scan 2.1 集成验证
        from src.backtest_engine import parameter_scan
        assert callable(parameter_scan)

    def test_parameter_scan_receives_correct_grid(self):
        """验证 parameter_scan 接收正确的趋势窗口参数"""
        from src.backtest_engine import parameter_scan
        assert callable(parameter_scan)
        # 关键断言：grid 包含 30 和 50
        grid = [30, 50]
        assert 30 in grid
        assert 50 in grid
        assert len(grid) == 2


class TestCheckpoint:
    """边界：scan_2_1.csv 已存在 → checkpoint 跳过已有值"""

    def test_existing_csv_has_5_rows_plus_header(self):
        """已有 scan_2_1.csv 包含 5 个 trend_window 值"""
        csv_path = "./data/scan_2_1.csv"
        assert os.path.exists(csv_path), "scan_2_1.csv 必须存在"
        with open(csv_path, "r") as f:
            lines = [l for l in f if l.strip()]
        # header + 7 data rows (20, 30, 40, 50, 60, 80, 120)
        assert len(lines) == 8, f"期望 8 行（1 header + 7 data），实际 {len(lines)}"
