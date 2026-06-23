# [2026-06-11] 新增：check_position 脚本测试 — 3 场景
"""测试 scripts/check_position.py — 仓位三合一脚本"""

import os
import re
import numpy as np
import pandas as pd
import pytest
from unittest.mock import patch, MagicMock, call


def _make_ohlcv_df(start_date="2025-06-01", days=260):
    dates = pd.date_range(start_date, periods=days, freq="B")
    n = len(dates)
    rng = np.random.RandomState(42)
    prices = 1.0 * np.exp(np.cumsum(rng.normal(0.0002, 0.008, n)))
    return pd.DataFrame({
        "open": prices * 0.99,
        "high": prices * 1.02,
        "low": prices * 0.98,
        "close": prices,
        "volume": np.full(n, 1e6),
    }, index=dates)


def _make_fake_parquets(data_dir, start_date="2025-06-01", days=260):
    """在 data_dir 创建 5 只防御 ETF 的模拟 parquet 文件。"""
    from src.etf_universe import ETF_UNIVERSE
    from src.signal_generator import DEFENSE_NAMES
    os.makedirs(data_dir, exist_ok=True)
    for name in DEFENSE_NAMES:
        code = ETF_UNIVERSE[name]
        df = _make_ohlcv_df(start_date, days)
        path = os.path.join(data_dir, f"{code}.parquet")
        df.to_parquet(path)


class TestCheckPosition:
    """scripts/check_position.py 的单元测试"""

    def test_basic_execution(self, tmp_path, capsys):
        """5 只 parquet 存在 → 脚本正常执行，输出含仓位报告、当前持仓、操作指令、风控状态"""
        data_dir = str(tmp_path / "data")
        output_path = str(tmp_path / "nav_2026.html")
        _make_fake_parquets(data_dir, start_date="2025-06-01", days=260)

        mock_update = MagicMock()
        from scripts import check_position
        with (
            patch("scripts.check_position.check_freshness", return_value=[]),
            patch("scripts.check_position.update_single_etf", mock_update),
            patch("scripts.check_position.DATA_DIR", data_dir),
            patch("scripts.check_position.OUTPUT_PATH", output_path),
            patch("scripts.nav_chart.check_freshness", return_value=[]),
            patch("scripts.nav_chart.update_single_etf", mock_update),
        ):
            check_position.main()

        captured = capsys.readouterr().out
        assert "仓位报告" in captured, f"输出应包含「仓位报告」，实际：{captured[:200]}"
        assert "当前持仓" in captured, "输出应包含「当前持仓」"
        assert "操作指令" in captured, "输出应包含「操作指令」"
        assert "风控状态" in captured, "输出应包含「风控状态」"
        assert os.path.exists(output_path), f"nav_2026.html 未生成: {output_path}"

    def test_output_contains_5_etf_names(self, tmp_path, capsys):
        """输出内容含 5 只 ETF 的中文名称"""
        data_dir = str(tmp_path / "data")
        output_path = str(tmp_path / "nav_2026.html")
        _make_fake_parquets(data_dir, start_date="2025-06-01", days=260)

        mock_update = MagicMock()
        from scripts import check_position
        with (
            patch("scripts.check_position.check_freshness", return_value=[]),
            patch("scripts.check_position.update_single_etf", mock_update),
            patch("scripts.check_position.DATA_DIR", data_dir),
            patch("scripts.check_position.OUTPUT_PATH", output_path),
            patch("scripts.nav_chart.check_freshness", return_value=[]),
            patch("scripts.nav_chart.update_single_etf", mock_update),
        ):
            check_position.main()

        captured = capsys.readouterr().out
        for name in ["沪深300", "创业板", "纳指", "黄金", "国债ETF"]:
            assert name in captured, f"输出应包含 ETF 名称「{name}」"

    def test_chart_generates_with_6_datasets(self, tmp_path, capsys):
        """确认根目录 nav_2026.html 被生成且包含 6 条 dataset"""
        data_dir = str(tmp_path / "data")
        output_path = str(tmp_path / "nav_2026.html")
        _make_fake_parquets(data_dir, start_date="2025-06-01", days=260)

        mock_update_check = MagicMock()
        mock_update_nav = MagicMock()
        from scripts import check_position
        with (
            patch("scripts.check_position.check_freshness", return_value=[]),
            patch("scripts.check_position.update_single_etf", mock_update_check),
            patch("scripts.check_position.DATA_DIR", data_dir),
            patch("scripts.check_position.OUTPUT_PATH", output_path),
            patch("scripts.nav_chart.check_freshness", return_value=[]),
            patch("scripts.nav_chart.update_single_etf", mock_update_nav),
        ):
            check_position.main()

        assert os.path.exists(output_path), f"nav_2026.html 未生成: {output_path}"
        html = open(output_path, encoding="utf-8").read()
        dataset_count = len(re.findall(r'"label":\s*"', html))
        assert dataset_count >= 6, f"应有 ≥6 个 label（dataset），实际 {dataset_count}"

    def test_updates_all_5_etfs(self, tmp_path, capsys):
        """验证调用了 5 次 update_single_etf（5 只防御 ETF 全部更新）"""
        data_dir = str(tmp_path / "data")
        output_path = str(tmp_path / "nav_2026.html")
        _make_fake_parquets(data_dir, start_date="2025-06-01", days=260)

        mock_update_check = MagicMock()
        mock_update_nav = MagicMock()
        from scripts import check_position
        with (
            patch("scripts.check_position.check_freshness", return_value=[]),
            patch("scripts.check_position.update_single_etf", mock_update_check),
            patch("scripts.check_position.DATA_DIR", data_dir),
            patch("scripts.check_position.OUTPUT_PATH", output_path),
            patch("scripts.nav_chart.check_freshness", return_value=[]),
            patch("scripts.nav_chart.update_single_etf", mock_update_nav),
        ):
            check_position.main()

        assert mock_update_check.call_count == 5, f"应调用 5 次 update_single_etf，实际 {mock_update_check.call_count}"
