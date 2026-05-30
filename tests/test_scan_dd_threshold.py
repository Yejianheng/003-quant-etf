# [2026-05-30] 新增：扫描脚本输出验证 — 确保 scan_dd_threshold.py 产出正确 CSV
import os
import sys
import subprocess
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE = os.path.join(os.path.dirname(__file__), "..")
OUTPUT_DIR = os.path.join(BASE, "output")


def _run_scan():
    """运行扫描脚本，返回 True 如果成功。"""
    script = os.path.join(BASE, "scripts", "scan_dd_threshold.py")
    result = subprocess.run(
        [sys.executable, script],
        capture_output=True, text=True, timeout=600,
        cwd=BASE,
    )
    return result


class TestScanScript:
    """scan_dd_threshold.py 产出有效对比表"""

    def test_script_runs_without_error(self):
        """脚本运行不报错"""
        result = _run_scan()
        if result.returncode != 0:
            # 脚本尚未创建 → 预期红灯
            pytest.fail(f"脚本运行失败:\n{result.stderr}")

    def test_output_csv_exists(self):
        """产出 threshold_sensitivity.csv"""
        csv_path = os.path.join(OUTPUT_DIR, "threshold_sensitivity.csv")
        if not os.path.exists(csv_path):
            pytest.fail(f"输出文件不存在: {csv_path}")

    def test_csv_has_four_rows(self):
        """CSV 包含四个阈值各一行"""
        csv_path = os.path.join(OUTPUT_DIR, "threshold_sensitivity.csv")
        if not os.path.exists(csv_path):
            pytest.skip("CSV 不存在")
        df = pd.read_csv(csv_path)
        assert len(df) == 4, f"预期 4 行（0.15/0.18/0.20/0.25），实际 {len(df)}"

    def test_csv_columns(self):
        """CSV 包含所有必要列"""
        csv_path = os.path.join(OUTPUT_DIR, "threshold_sensitivity.csv")
        if not os.path.exists(csv_path):
            pytest.skip("CSV 不存在")
        df = pd.read_csv(csv_path)
        required = ["liquidate阈值", "Sharpe", "最大回撤", "liquidate触发天数"]
        for col in required:
            assert col in df.columns, f"缺少列: {col}"
