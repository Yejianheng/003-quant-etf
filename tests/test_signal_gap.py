# [2026-06-25] 新增：信号间隔回放测试 — 5 场景
"""测试 _replay_gap — 信号间隔自动补全"""

import json
import os
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pytest


# ---- helpers ----

def _make_ohlcv(n=130, trend=0.001, volatility=0.01, seed=42):
    """合成 OHLCV 数据，含 DatetimeIndex。"""
    rng = np.random.RandomState(seed)
    returns = np.full(n, trend / 252) + rng.normal(0, volatility / np.sqrt(252), n)
    prices = 1.0 * np.exp(np.cumsum(returns))
    dates = pd.date_range("2024-01-02", periods=n, freq="B")
    df = pd.DataFrame({
        "open": prices * 0.99,
        "high": prices * 1.02,
        "low": prices * 0.98,
        "close": prices,
        "volume": np.full(n, 1e6),
    }, index=dates)
    return df


def _make_state(last_date="2025-06-01", active_names=None):
    """构造模拟 state dict。"""
    if active_names is None:
        active_names = ["沪深300", "创业板", "纳指", "黄金", "国债ETF"]
    return {
        "last_date": last_date,
        "last_active": list(active_names),
        "last_cb_triggered": False,
        "last_offense_weights": {},
        "portfolio_values": [{"date": "2025-05-01", "value": 1.0}],
    }


ETF_ORDER = ["沪深300", "创业板", "纳指", "黄金", "国债ETF"]


def _make_prices_uptrend(n=150, trend=0.15):
    """5 只 ETF 全部强上升趋势。"""
    prices = {}
    for i, name in enumerate(ETF_ORDER):
        prices[name] = _make_ohlcv(n=n, trend=trend, seed=i + 100)
    return prices


def _make_prices_gold_downtrend(n=150):
    """4 只 ETF 上升，黄金先升后降。"""
    prices = {}
    for i, name in enumerate(["沪深300", "创业板", "纳指", "国债ETF"]):
        prices[name] = _make_ohlcv(n=n, trend=0.15, seed=i + 100)

    rng = np.random.RandomState(104)
    half = n // 2
    up = np.full(half, 0.15 / 252) + rng.normal(0, 0.005 / np.sqrt(252), half)
    down = np.full(n - half, -0.50 / 252) + rng.normal(0, 0.005 / np.sqrt(252), n - half)
    all_ret = np.concatenate([up, down])
    gold_prices = 1.0 * np.exp(np.cumsum(all_ret))
    dates = pd.date_range("2024-01-02", periods=n, freq="B")
    prices["黄金"] = pd.DataFrame({
        "open": gold_prices * 0.99,
        "high": gold_prices * 1.02,
        "low": gold_prices * 0.98,
        "close": gold_prices,
        "volume": np.full(n, 1e6),
    }, index=dates)
    return prices


class TestReplayGap:
    """_replay_gap(): 逐日回放趋势变化"""

    def test_replay_gap_no_change(self):
        """间隔 14 天空白，趋势全程不变 → 回放确认 0 changes"""
        from scripts.daily_signal import _replay_gap

        prices = _make_prices_uptrend(n=150)
        latest = prices["沪深300"].index[-1]
        # last_date = 14 trading days before latest
        gap_start = latest - pd.Timedelta(days=20)
        state = _make_state(last_date=str(gap_start.date()))

        result = _replay_gap(prices, state)

        assert result["gap_trading_days"] > 0
        assert result["today"] == str(latest.date())
        assert len(result["changes"]) == 0, (
            f"全上升趋势不应有变化，实际：{result['changes']}"
        )

    def test_replay_gap_one_change(self):
        """间隔内某 ETF 趋势转负 → changes 含 1 条 removed 事件"""
        from scripts.daily_signal import _replay_gap
        from src.trend_strength import trend_strength

        prices = _make_prices_gold_downtrend(n=150)
        dates = prices["沪深300"].index
        half = 150 // 2  # 黄金在此转跌

        # State last_date 设在 half - 10（黄金仍为正时）
        state_dt = dates[half - 11]
        state = _make_state(last_date=str(state_dt.date()))

        # 找出黄金趋势首次转负的日期
        first_neg_dt = None
        for i in range(half - 11 + 1, len(dates)):
            ts = trend_strength(prices["黄金"]["close"].iloc[:i + 1], window=40)
            if ts <= 0:
                first_neg_dt = dates[i]
                break

        assert first_neg_dt is not None, (
            "黄金应先升后降，应出现趋势转负日期"
        )

        result = _replay_gap(prices, state)

        assert len(result["changes"]) >= 1, (
            f"黄金趋势转负应有变化事件，实际：{result['changes']}"
        )
        change = result["changes"][0]
        assert change["etf"] == "黄金"
        assert change["event"] == "removed"
        assert change["date"] == str(first_neg_dt.date()), (
            f"变化日期应为 {first_neg_dt.date()}，实际 {change['date']}"
        )

    def test_replay_gap_multi_change(self):
        """间隔内先剔除再恢复 → changes 含 2 条事件"""
        import scripts.daily_signal as ds
        from scripts.daily_signal import _replay_gap

        prices = _make_prices_uptrend(n=150)
        dates = sorted(set.intersection(*[set(df.index) for df in prices.values()]))
        gap_start = dates[99]
        gap_dates = [d for d in dates if d > gap_start][:60]
        assert len(gap_dates) >= 16, f"至少需要 16 个 gap 日，实际 {len(gap_dates)}"

        state = _make_state(last_date=str(gap_start.date()))

        # 黄金：前 9 日正（day_idx 0-8）→ 第 10 日起负 6 日（9-14）→ 第 16 日起正（15+）
        removed_dt = gap_dates[9]
        added_dt = gap_dates[15]

        call_seq = []
        for day_idx in range(len(gap_dates)):
            for name in ETF_ORDER:
                if name == "黄金":
                    if day_idx < 9:
                        call_seq.append(0.5)
                    elif day_idx < 15:
                        call_seq.append(-0.1)
                    else:
                        call_seq.append(0.5)
                else:
                    call_seq.append(0.5)

        with patch.object(ds, "trend_strength", side_effect=call_seq):
            result = _replay_gap(prices, state)

        assert len(result["changes"]) >= 2, (
            f"应有 ≥2 变化事件，实际：{result['changes']}"
        )

        assert result["changes"][0]["event"] == "removed"
        assert result["changes"][0]["etf"] == "黄金"
        assert result["changes"][0]["date"] == str(removed_dt.date())

        added_events = [c for c in result["changes"] if c["event"] == "added"]
        assert len(added_events) >= 1, (
            f"黄金应恢复 active，找到 {len(added_events)} 条 added"
        )
        assert added_events[0]["etf"] == "黄金"
        assert added_events[0]["date"] == str(added_dt.date())

    def test_replay_gap_first_run(self):
        """state=None → 跳过回放，不崩"""
        from scripts.daily_signal import _replay_gap

        prices = _make_prices_uptrend(n=150)
        result = _replay_gap(prices, None)

        assert result["gap_trading_days"] == 0
        assert result["changes"] == []

    def test_replay_gap_no_gap(self):
        """state.last_date == today → gap=0，不崩"""
        from scripts.daily_signal import _replay_gap

        prices = _make_prices_uptrend(n=150)
        latest = prices["沪深300"].index[-1]
        state = _make_state(last_date=str(latest.date()))

        result = _replay_gap(prices, state)

        assert result["gap_trading_days"] == 0


class TestReportFormatReplay:
    """format_signal_report 集成 period review 段"""

    def test_report_without_state_no_replay_section(self):
        """无上一信号 → 报告不含'期间回顾'"""
        from scripts.daily_signal import format_signal_report

        signal = {
            "date": "2025-06-25",
            "defense": {
                "trend_strengths": {"沪深300": 0.5},
                "active": ["沪深300"],
                "target_weights": {"沪深300": 1.0},
                "scaling_factor": 1.0,
                "predicted_vol": 0.08,
            },
            "offense": {"rankings": [], "target_weights": {}},
            "circuit_breaker": {"triggered": False, "smoothed_corr": -0.1},
            "drawdown_stop": {"level": "normal", "position_multiplier": 1.0, "drawdown": -0.02},
            "execution": {"final_multiplier": 1.0, "funds_to_repo": False},
        }
        report = format_signal_report(signal, previous_signal=None, replay_result=None)

        assert "期间回顾" not in report, "无上一信号不应含'期间回顾'"

    def test_report_with_replay_no_change(self):
        """回放无变化 → 报告含'期间回顾' + '无变化'"""
        from scripts.daily_signal import format_signal_report

        signal = {
            "date": "2025-06-25",
            "defense": {
                "trend_strengths": {"沪深300": 0.5, "创业板": 0.5, "纳指": 0.5},
                "active": ["沪深300", "创业板", "纳指"],
                "target_weights": {"沪深300": 0.333, "创业板": 0.333, "纳指": 0.333},
                "scaling_factor": 1.0,
                "predicted_vol": 0.08,
            },
            "offense": {"rankings": [], "target_weights": {}},
            "circuit_breaker": {"triggered": False, "smoothed_corr": -0.1},
            "drawdown_stop": {"level": "normal", "position_multiplier": 1.0, "drawdown": -0.02},
            "execution": {"final_multiplier": 1.0, "funds_to_repo": False},
        }
        replay_result = {
            "gap_trading_days": 10,
            "last_date": "2025-06-11",
            "today": "2025-06-25",
            "daily_active": [],
            "changes": [],
        }
        report = format_signal_report(signal, previous_signal=_make_state_replay(), replay_result=replay_result)

        assert "期间回顾" in report
        assert "无变化" in report
        assert "2025-06-11" in report
        assert "2025-06-25" in report


def _make_state_replay():
    return {
        "defense": {"active": ["沪深300", "创业板", "纳指"]},
        "offense": {"target_weights": {}},
        "circuit_breaker": {"triggered": False},
    }


class TestCheckPositionReplay:
    """集成测试：check_position 含 期间回顾"""

    def _make_fake_parquets(self, data_dir, n=150):
        """写入 5 只防御 ETF 的模拟 parquet 文件。"""
        from src.etf_universe import ETF_UNIVERSE

        prices = _make_prices_uptrend(n=n)
        for name, df in prices.items():
            code = ETF_UNIVERSE[name]
            df.to_parquet(os.path.join(data_dir, f"{code}.parquet"))

    def test_check_position_output_contains_replay(self, tmp_path, capsys):
        """有 state 14 天前 + 无变化 → 报告含'期间回顾'"""
        data_dir = str(tmp_path / "data")
        os.makedirs(data_dir)
        self._make_fake_parquets(data_dir, n=150)

        # 写 state
        from scripts.daily_signal import _save_state

        prices = _make_prices_uptrend(n=150)
        latest = prices["沪深300"].index[-1]
        gap_start = latest - pd.Timedelta(days=20)
        state = {
            "last_date": str(gap_start.date()),
            "last_active": ["沪深300", "创业板", "纳指", "黄金", "国债ETF"],
            "last_cb_triggered": False,
            "last_offense_weights": {},
            "portfolio_values": [{"date": str(gap_start.date()), "value": 1.0}],
        }
        _save_state(data_dir, state)

        from scripts import check_position

        with (
            patch("scripts.check_position.check_freshness", return_value=[]),
            patch("scripts.check_position.update_single_etf", MagicMock()),
            patch("scripts.check_position.DATA_DIR", data_dir),
            patch("scripts.check_position.OUTPUT_PATH", str(tmp_path / "nav_2026.html")),
            patch("scripts.check_position.update_chart", MagicMock()),
        ):
            check_position.main()

        captured = capsys.readouterr().out
        assert "期间回顾" in captured, (
            f"state 14天前应输出'期间回顾'，实际输出：\n{captured}"
        )
