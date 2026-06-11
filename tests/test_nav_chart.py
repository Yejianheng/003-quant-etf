# [2026-06-11] 修改：适配 output_path 参数 + 表格/翻页/搜索框元素验证
# [2026-06-11] 新增：nav_chart 脚本测试 — 3 场景
"""测试 scripts/nav_chart.py — 2026 净值对比图表生成"""

import os
import re
import numpy as np
import pandas as pd
import pytest
from unittest.mock import patch, MagicMock


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


class TestNavChart:
    """scripts/nav_chart.py 的单元测试"""

    def test_basic_generates_html_with_6_datasets(self, tmp_path):
        """5 只 parquet 存在 → 生成 HTML，含 6 条 dataset + 表格 + 翻页 + 搜索框"""
        data_dir = str(tmp_path / "data")
        output_path = str(tmp_path / "nav_2026.html")
        _make_fake_parquets(data_dir, start_date="2025-06-01", days=260)
        mock_update = MagicMock()

        from scripts.nav_chart import main
        with patch("scripts.nav_chart.update_single_etf", mock_update):
            main(data_dir=data_dir, output_path=output_path)

        assert os.path.exists(output_path), f"HTML 未生成: {output_path}"

        html = open(output_path, encoding="utf-8").read()
        # 验证 6 组数据（策略 + 5 ETF）：Chart.js datasets 数组含 6 个对象
        dataset_count = len(re.findall(r'"label":\s*"', html))
        assert dataset_count >= 6, f"应有 ≥6 个 label（dataset），实际 {dataset_count}"
        # 验证 canvas 元素
        canvas_count = len(re.findall(r'<canvas\b', html, re.IGNORECASE))
        assert canvas_count >= 1, f"应有 ≥1 个 <canvas>，实际 {canvas_count}"
        # 验证颜色
        for color in ["#dc3912", "#3366cc", "#ff9900", "#109618", "#ffd700", "#990099"]:
            assert color in html, f"HTML 中应包含颜色 {color}"
        # 验证标题
        assert "2026 净值对比" in html
        # 验证盈亏线（灰色虚线）
        assert "borderDash" in html or "'afterDraw'" in html
        # 验证表格元素
        assert "<table" in html, "HTML 应包含 <table>"
        # 验证翻页按钮
        assert "上一页" in html, "HTML 应包含 上一页 按钮"
        assert "下一页" in html, "HTML 应包含 下一页 按钮"
        # 验证日期搜索框
        assert 'type="date"' in html, "HTML 应包含日期选择器"
        assert "跳转" in html, "HTML 应包含跳转按钮"

    def test_truncates_to_2026(self, tmp_path):
        """数据起点早于 2026-01-01 → 图表标签仅显示 2026-01-01 之后"""
        data_dir = str(tmp_path / "data")
        output_path = str(tmp_path / "nav_2026.html")
        _make_fake_parquets(data_dir, start_date="2025-06-01", days=260)
        mock_update = MagicMock()

        from scripts.nav_chart import main
        with patch("scripts.nav_chart.update_single_etf", mock_update):
            main(data_dir=data_dir, output_path=output_path)

        html = open(output_path, encoding="utf-8").read()
        # 提取 Chart.js labels 中的第一个日期
        match = re.search(r'"2026-01-0[2-9]"', html)
        assert match, f"HTML 中应包含 2026-01-02 之后的标签，实际未找到"
        # 不应包含 2025 年的日期标签
        assert not re.search(r'"2025-\d{2}-\d{2}"', html), (
            "HTML 标签不应包含 2025 年日期"
        )

    def test_missing_parquet_raises(self, tmp_path):
        """parquet 缺失 → FileNotFoundError，错误消息含缺失文件名"""
        data_dir = str(tmp_path / "data")
        output_path = str(tmp_path / "nav_2026.html")
        # 仅创建 4 只 parquet，缺 510300（沪深300）
        from src.signal_generator import DEFENSE_NAMES
        from src.etf_universe import ETF_UNIVERSE
        os.makedirs(data_dir, exist_ok=True)
        missing_code = ETF_UNIVERSE["沪深300"]
        for name in ["创业板", "纳指", "黄金", "国债ETF"]:
            code = ETF_UNIVERSE[name]
            df = _make_ohlcv_df("2025-06-01", 260)
            df.to_parquet(os.path.join(data_dir, f"{code}.parquet"))
        mock_update = MagicMock()

        from scripts.nav_chart import main
        with patch("scripts.nav_chart.update_single_etf", mock_update):
            with pytest.raises(FileNotFoundError, match=missing_code):
                main(data_dir=data_dir, output_path=output_path)
