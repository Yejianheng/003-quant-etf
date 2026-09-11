# [2026-09-11] 新增：操作指令基线集成测试 — 回归 v221「永远无需调仓」bug
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


# update_single_etf 的桩返回值：ok 且无需核验，使脚本走正常入库路径。
# 裸 MagicMock 的 needs_verify 为真值，会误触发「待核验」分支导致脚本提前 sys.exit。
_UPDATE_STUB = {"ok": True, "needs_verify": False}


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

        mock_update = MagicMock(return_value=_UPDATE_STUB)
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
        assert "当前持有" in captured, "输出应包含「当前持有」（T-1 信号，实际持仓）"
        assert "次日目标仓位" in captured, "输出应包含「次日目标仓位」（T 信号）"
        assert "操作指令" in captured, "输出应包含「操作指令」"
        assert "风控状态" in captured, "输出应包含「风控状态」"
        assert os.path.exists(output_path), f"nav_2026.html 未生成: {output_path}"

    def test_output_contains_5_etf_names(self, tmp_path, capsys):
        """输出内容含 5 只 ETF 的中文名称"""
        data_dir = str(tmp_path / "data")
        output_path = str(tmp_path / "nav_2026.html")
        _make_fake_parquets(data_dir, start_date="2025-06-01", days=260)

        mock_update = MagicMock(return_value=_UPDATE_STUB)
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

        mock_update_check = MagicMock(return_value=_UPDATE_STUB)
        mock_update_nav = MagicMock(return_value=_UPDATE_STUB)
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

        mock_update_check = MagicMock(return_value=_UPDATE_STUB)
        mock_update_nav = MagicMock(return_value=_UPDATE_STUB)
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


class TestActionBaselineIntegration:
    """check_position.main(): 最后一日趋势翻转 → 必须报出买卖，而非'无需调仓'

    回归 v221：旧逻辑拿「今日信号」与「回放的今日信号」比较（自己跟自己比），
    恒等于'无需调仓'，且只在当日发生趋势变化时发作——恰是最需要指令的日子。
    """

    @staticmethod
    def _build_flip_prices(n=200, seed=7, drop_last=0.0):
        """构造 5 只 ETF 日线。

        国债 ETF 收益与股票篮子反相关 → 60 日相关性为负，规避熔断干扰。
        黄金最后一日暴跌 → 其 trend_strength 在最后一日由正转负。
        """
        rng = np.random.RandomState(seed)
        dates = pd.date_range("2024-06-03", periods=n, freq="B")
        stocks = [rng.normal(0.0006, 0.002, n) for _ in range(3)]
        rets = {
            "沪深300": stocks[0],
            "创业板": stocks[1],
            "纳指": stocks[2],
            "黄金": rng.normal(0.0006, 0.002, n),
            "国债ETF": -0.6 * np.mean(stocks, axis=0) + rng.normal(0, 0.0002, n),
        }

        prices = {}
        for name, ret in rets.items():
            ret = ret.copy()
            if name == "黄金" and drop_last:
                ret[-1] = drop_last
            close = 1.0 * np.exp(np.cumsum(ret))
            prices[name] = pd.DataFrame({
                "open": close * 0.999,
                "high": close * 1.002,
                "low": close * 0.998,
                "close": close,
                "volume": np.full(n, 1e6),
            }, index=dates)
        return prices

    @staticmethod
    def _write_parquets(data_dir, prices):
        from src.etf_universe import ETF_UNIVERSE
        os.makedirs(data_dir, exist_ok=True)
        for name, df in prices.items():
            df.to_parquet(os.path.join(data_dir, f"{ETF_UNIVERSE[name]}.parquet"))

    def _run(self, tmp_path, state, prices):
        """写入数据与 state 后执行 check_position.main()，返回 stdout。"""
        data_dir = str(tmp_path / "data")
        self._write_parquets(data_dir, prices)

        from scripts.daily_signal import _save_state
        _save_state(data_dir, state)

        from scripts import check_position
        with (
            patch("scripts.check_position.check_freshness", return_value=[]),
            patch("scripts.check_position.update_single_etf",
                  MagicMock(return_value=_UPDATE_STUB)),
            patch("scripts.check_position.DATA_DIR", data_dir),
            patch("scripts.check_position.OUTPUT_PATH",
                  str(tmp_path / "nav_2026.html")),
            patch("scripts.check_position.update_chart", MagicMock()),
        ):
            check_position.main()

        return data_dir

    def test_last_day_flip_reports_sell(self, tmp_path, capsys):
        """黄金最后一日趋势由正转负 → 报告应报'卖出 黄金'"""
        prices = self._build_flip_prices(drop_last=-0.06)
        idx = prices["沪深300"].index
        state = {
            "last_date": str(idx[-3].date()),
            "last_active": ["沪深300", "创业板", "纳指", "黄金", "国债ETF"],
            "last_offense_weights": {},
            "last_cb_triggered": False,
            "portfolio_values": [],
        }

        self._run(tmp_path, state, prices)
        captured = capsys.readouterr().out

        assert "卖出 黄金" in captured, (
            f"最后一日黄金趋势转负应报卖出，实际输出：\n{captured}"
        )
        assert "无需调仓" not in captured, (
            f"趋势已变化不应报无需调仓，实际输出：\n{captured}"
        )

    def test_hold_membership_is_daily_active_minus_2(self, tmp_path, capsys):
        """『当前持有』应为 T-1 信号（含黄金），而非今日目标（不含黄金）"""
        prices = self._build_flip_prices(drop_last=-0.06)
        idx = prices["沪深300"].index
        state = {
            "last_date": str(idx[-3].date()),
            "last_active": ["沪深300", "创业板", "纳指", "黄金", "国债ETF"],
            "last_offense_weights": {},
            "last_cb_triggered": False,
            "portfolio_values": [],
        }

        self._run(tmp_path, state, prices)
        captured = capsys.readouterr().out

        hold_line = next(
            (ln for ln in captured.splitlines() if ln.startswith("  持有：")), None
        )
        assert hold_line is not None, f"'当前持有'段应含『持有：』行，实际：\n{captured}"
        assert "黄金" in hold_line, (
            f"T-1 持仓应含黄金，实际：{hold_line}"
        )
