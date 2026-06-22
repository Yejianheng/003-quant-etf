# [2026-06-18] 修改：适配换手统计行（表格底部新增换手率 + 成本行）
# [2026-06-18] 修改：适配等权基准 + 60/40 基准线（dataset 7→9, 颜色 +2, 表头 +2 列）
# [2026-06-18] 新增：repo 可视化元素测试（逆回购净值虚线 + 空仓背景带 + repo 汇总）
# [2026-06-16] 修改：去 A/B 参考线，颜色断言更新为 1 策略 + 5 ETF（6 色）
# [2026-06-16] 修复：同步表头断言"今日调仓"→"明日调仓"+颜色断言匹配当前 COLORS
# [2026-06-11] 修改：适配 T+1 前移（操作→今日调仓、建仓、权重箭头格式）
# [2026-06-11] 修改：适配净值归一化断言 + 页码跳转断言
# [2026-06-11] 修改：适配持仓权重表格 + 新增表头验证
# [2026-06-11] 修改：适配 output_path 参数 + 表格/翻页/搜索框元素验证
# [2026-06-11] 新增：nav_chart 脚本测试 — 3 场景
"""测试 scripts/nav_chart.py — 2026 净值对比图表生成"""

import json
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
        # 验证 9 组数据（策略 + 逆回购 + 等权 + 60/40 + 5 ETF）
        dataset_count = len(re.findall(r'"label":\s*"', html))
        assert dataset_count == 9, f"应有 9 个 dataset（1 策略 + 逆回购 + 等权 + 60/40 + 5 ETF），实际 {dataset_count}"
        # 验证 canvas 元素
        canvas_count = len(re.findall(r'<canvas\b', html, re.IGNORECASE))
        assert canvas_count >= 1, f"应有 ≥1 个 <canvas>，实际 {canvas_count}"
        # 验证颜色
        for color in ["#dc3912", "#3366cc", "#e06666", "#6aa84f", "#bf9000", "#674ea7", "#999999", "#888888", "#8B4513"]:
            assert color in html, f"HTML 中应包含颜色 {color}"
        # 验证标题
        assert "2026 净值对比" in html
        # 验证盈亏线（灰色虚线）
        assert "borderDash" in html or "'afterDraw'" in html
        # 验证表格元素
        assert "<table" in html, "HTML 应包含 <table>"
        # 验证新表头：持仓权重列
        assert "纯防御净值" in html, "HTML 表头应包含 纯防御净值"
        assert "等权净值" in html, "HTML 表头应包含 等权净值"
        assert "60/40净值" in html, "HTML 表头应包含 60/40净值"
        assert "现金" in html, "HTML 表头应包含 现金"
        assert "明日调仓" in html, "HTML 表头应包含 明日调仓"
        assert "Δ%" in html, "HTML 表头应包含 Δ%"
        # 验证翻页按钮
        assert "上一页" in html, "HTML 应包含 上一页 按钮"
        assert "下一页" in html, "HTML 应包含 下一页 按钮"
        assert "pageJumpInput" in html, "HTML 应包含页码跳转输入框"
        assert "jumpToPage" in html, "HTML 应包含 jumpToPage 函数"
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

    def test_table_contains_weight_and_action_columns(self, tmp_path):
        """表格列包含持仓权重 header（10 列：日期 + 净值 + 5 ETF + 现金 + 操作 + Δ%）。"""
        data_dir = str(tmp_path / "data")
        output_path = str(tmp_path / "nav_2026.html")
        _make_fake_parquets(data_dir, start_date="2025-06-01", days=260)
        mock_update = MagicMock()

        from scripts.nav_chart import main
        with patch("scripts.nav_chart.update_single_etf", mock_update):
            main(data_dir=data_dir, output_path=output_path)

        html = open(output_path, encoding="utf-8").read()
        # 新表头：10 列
        assert "纯防御净值" in html
        assert "现金" in html
        assert "明日调仓" in html
        # 不应再有旧表头
        assert "纯防御策略</th>" not in html, "旧表头「纯防御策略」应已被「纯防御净值」替代"
        # 表格数据 JSON 应含权重/现金/操作字段
        assert '"weights"' in html, "tableData JSON 应包含 weights 字段"
        assert '"cash"' in html, "tableData JSON 应包含 cash 字段"
        assert '"action"' in html, "tableData JSON 应包含 action 字段"
        # 操作列应有实际内容（建仓/权重箭头格式）
        assert "建仓" in html or "买入" in html or "卖出" in html, \
            "操作列应包含调仓描述"

    def test_repo_visualization_elements(self, tmp_path):
        """HTML 含逆回购净值虚线 + 空仓背景带 + repo 汇总统计。"""
        data_dir = str(tmp_path / "data")
        output_path = str(tmp_path / "nav_2026.html")
        _make_fake_parquets(data_dir, start_date="2025-06-01", days=260)
        mock_update = MagicMock()

        from scripts.nav_chart import main
        with patch("scripts.nav_chart.update_single_etf", mock_update):
            main(data_dir=data_dir, output_path=output_path)

        html = open(output_path, encoding="utf-8").read()
        # 逆回购净值 dataset
        assert "逆回购净值" in html, "HTML 应包含 逆回购净值 dataset"
        # 逆回购背景色带（repoBand 插件）
        assert "repoBand" in html, "HTML 应包含 repoBand 插件"
        # 现金列改为 repo 金额显示
        assert "repo_amount" in html, "tableData JSON 应包含 repo_amount 字段"
        # repo 汇总统计行
        assert "repoStats" in html, "HTML 应包含 repoStats 汇总数据"

    def test_benchmark_lines_equal_weight_and_6040(self, tmp_path):
        """HTML 含 5 ETF 等权基准线 + 60/40 股债基准线。"""
        data_dir = str(tmp_path / "data")
        output_path = str(tmp_path / "nav_2026.html")
        _make_fake_parquets(data_dir, start_date="2025-06-01", days=260)
        mock_update = MagicMock()

        from scripts.nav_chart import main
        with patch("scripts.nav_chart.update_single_etf", mock_update):
            main(data_dir=data_dir, output_path=output_path)

        html = open(output_path, encoding="utf-8").read()
        # 等权基准 dataset
        assert "5 ETF 等权" in html, "HTML 应包含 5 ETF 等权 dataset"
        # 60/40 基准 dataset
        assert "60/40 股债" in html, "HTML 应包含 60/40 股债 dataset"
        # 等权净值列
        assert "等权净值" in html, "HTML 表格应包含 等权净值 列"
        # 60/40 净值列
        assert "60/40净值" in html, "HTML 表格应包含 60/40净值 列"

    def test_turnover_stats_in_table(self, tmp_path):
        """HTML 表格底部含换手统计行（年化换手率 + 累计成本 + 成本占比）。"""
        data_dir = str(tmp_path / "data")
        output_path = str(tmp_path / "nav_2026.html")
        _make_fake_parquets(data_dir, start_date="2025-06-01", days=260)
        mock_update = MagicMock()

        from scripts.nav_chart import main
        with patch("scripts.nav_chart.update_single_etf", mock_update):
            main(data_dir=data_dir, output_path=output_path)

        html = open(output_path, encoding="utf-8").read()
        assert "年化换手率" in html, "HTML 应包含 年化换手率"
        assert "累计交易成本" in html, "HTML 应包含 累计交易成本"
        assert "成本占比" in html, "HTML 应包含 成本占比"

    def test_cash_column_binary_logic(self, tmp_path):
        """现金列：空仓(CB或无品种)=100%，有持仓=0（前端渲染为—）"""
        data_dir = str(tmp_path / "data")
        output_path = str(tmp_path / "nav_2026.html")
        _make_fake_parquets(data_dir, start_date="2025-06-01", days=260)
        mock_update = MagicMock()

        from scripts.nav_chart import main
        with patch("scripts.nav_chart.update_single_etf", mock_update):
            main(data_dir=data_dir, output_path=output_path)

        html = open(output_path, encoding="utf-8").read()
        match = re.search(r'const tableData = (\[.*?\]);\s*const PAGE_SIZE', html, re.DOTALL)
        assert match, "HTML 中应包含 tableData JSON"
        table_data = json.loads(match.group(1))
        assert len(table_data) > 0, "tableData 不应为空"
        for row in table_data:
            weights_sum = sum(row["weights"])
            repo = row.get("repo_amount", 0.0)
            if weights_sum == 0:
                assert repo == 1.0, (
                    f"{row['date']}: 空仓应 repo_amount=1.0，实际 {repo}"
                )
            else:
                assert repo == 0.0, (
                    f"{row['date']}: 有持仓应 repo_amount=0.0（前端渲染为—），实际 {repo}"
                )
