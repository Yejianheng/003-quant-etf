# [2026-11-06] 新增：断层回放必须消费回测引擎熔断/乘数状态 — 回归「熔断持续期误报持仓 + 幽灵买卖」
# [2026-09-11] 新增：操作指令基线测试 — 回归 v221「永远无需调仓」bug
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
            patch("scripts.check_position.update_single_etf",
                  MagicMock(return_value={"ok": True, "needs_verify": False})),
            patch("scripts.check_position.DATA_DIR", data_dir),
            patch("scripts.check_position.OUTPUT_PATH", str(tmp_path / "nav_2026.html")),
            patch("scripts.check_position.update_chart", MagicMock()),
        ):
            check_position.main()

        captured = capsys.readouterr().out
        assert "期间回顾" in captured, (
            f"state 14天前应输出'期间回顾'，实际输出：\n{captured}"
        )


# ---- v221 回归：操作指令对比基线 ----

def _baseline_signal(active):
    """构造 _compare_signals 可用的信号摘要。"""
    return {
        "defense": {"active": list(active)},
        "offense": {"target_weights": {}},
        "circuit_breaker": {"triggered": False},
    }


class TestPrevActiveSignal:
    """_prev_active_signal(): 对比基线 = 上一交易日收盘信号（= T 日实际持仓）

    图表口径：T 日持仓 = T-1 日收盘信号。回放 daily_active 最后一项是 T 日信号
    （= 次日目标），故 T 日持仓应取 daily_active[-2]。
    """

    def test_replay_covers_prev_day_uses_second_to_last(self):
        """回放覆盖 T-1（gap≥2）→ 基线取 daily_active[-2]"""
        from scripts.daily_signal import _prev_active_signal

        replay = {
            "daily_active": [
                {"date": "2025-06-23", "active": ["沪深300", "纳指"]},
                {"date": "2025-06-24", "active": ["纳指"]},
            ]
        }

        got = _prev_active_signal(replay, _baseline_signal(["纳指"]))

        assert got["defense"]["active"] == ["沪深300", "纳指"], (
            f"基线应为 T-1 持仓，实际 {got['defense']['active']}"
        )

    def test_replay_single_day_uses_fallback(self):
        """回放只覆盖 T（gap==1）→ T-1 不在回放内，基线取 fallback"""
        from scripts.daily_signal import _prev_active_signal

        replay = {"daily_active": [{"date": "2025-06-24", "active": ["纳指"]}]}
        fallback = _baseline_signal(["沪深300", "纳指"])

        assert _prev_active_signal(replay, fallback) is fallback, (
            "gap==1 时应原样返回 fallback（state 中上一交易日信号）"
        )

    def test_no_replay_uses_fallback(self):
        """无回放 / 回放为空 → 基线取 fallback"""
        from scripts.daily_signal import _prev_active_signal

        fallback = _baseline_signal(["纳指"])

        assert _prev_active_signal(None, fallback) is fallback
        assert _prev_active_signal({"daily_active": []}, fallback) is fallback

    def test_first_run_returns_none(self):
        """首次运行（无回放、无 fallback）→ None，报告应输出'首次建仓'"""
        from scripts.daily_signal import _prev_active_signal

        assert _prev_active_signal(None, None) is None
        assert _prev_active_signal({"daily_active": []}, None) is None

    def test_fallback_ignored_when_replay_covers_prev_day(self):
        """回放覆盖 T-1 时，fallback 不再参与——避免 state 陈旧值干扰"""
        from scripts.daily_signal import _prev_active_signal

        replay = {
            "daily_active": [
                {"date": "2025-06-23", "active": ["纳指"]},
                {"date": "2025-06-24", "active": ["纳指", "黄金"]},
            ]
        }
        stale = _baseline_signal(["沪深300", "创业板", "纳指", "黄金", "国债ETF"])

        got = _prev_active_signal(replay, stale)

        assert got["defense"]["active"] == ["纳指"], (
            f"应取回放 T-1，不应取陈旧 fallback，实际 {got['defense']['active']}"
        )


class TestReportActionBaseline:
    """format_signal_report: 当日趋势变化时必须报出买卖，而非'无需调仓'"""

    @staticmethod
    def _signal(active):
        return {
            "date": "2025-06-24",
            "defense": {
                "trend_strengths": {n: 0.5 for n in active},
                "active": list(active),
                "target_weights": {n: 1.0 / len(active) for n in active},
                "scaling_factor": 1.0,
                "predicted_vol": 0.08,
            },
            "offense": {"rankings": [], "target_weights": {}},
            "circuit_breaker": {"triggered": False, "smoothed_corr": -0.1},
            "drawdown_stop": {"level": "normal", "position_multiplier": 1.0,
                              "drawdown": -0.02},
            "execution": {"final_multiplier": 1.0, "funds_to_repo": False},
        }

    def test_last_day_flip_negative_reports_sell(self):
        """最后一交易日趋势转负 → 报'卖出'（旧逻辑误报'无需调仓'）"""
        from scripts.daily_signal import format_signal_report

        signal = self._signal(["纳指", "黄金", "国债ETF"])
        replay_result = {
            "gap_trading_days": 2,
            "last_date": "2025-06-20",
            "today": "2025-06-24",
            "daily_active": [
                {"date": "2025-06-23",
                 "active": ["纳指", "黄金", "国债ETF", "沪深300"]},
                {"date": "2025-06-24", "active": ["纳指", "黄金", "国债ETF"]},
            ],
            "changes": [{"date": "2025-06-24", "event": "removed", "etf": "沪深300"}],
        }

        report = format_signal_report(signal, previous_signal=None,
                                      replay_result=replay_result)

        assert "卖出 沪深300" in report, f"应报卖出沪深300，实际：\n{report}"
        assert "无需调仓" not in report, f"不应报无需调仓，实际：\n{report}"

    def test_last_day_flip_positive_reports_buy(self):
        """最后一交易日趋势转正 → 报'买入'"""
        from scripts.daily_signal import format_signal_report

        signal = self._signal(["纳指", "沪深300"])
        replay_result = {
            "gap_trading_days": 2,
            "last_date": "2025-06-20",
            "today": "2025-06-24",
            "daily_active": [
                {"date": "2025-06-23", "active": ["纳指"]},
                {"date": "2025-06-24", "active": ["纳指", "沪深300"]},
            ],
            "changes": [{"date": "2025-06-24", "event": "added", "etf": "沪深300"}],
        }

        report = format_signal_report(signal, previous_signal=None,
                                      replay_result=replay_result)

        assert "买入 沪深300" in report, f"应报买入沪深300，实际：\n{report}"
        assert "无需调仓" not in report, f"不应报无需调仓，实际：\n{report}"

    def test_no_change_still_reports_no_action(self):
        """回放覆盖 T-1 且与今日一致 → 仍应报'无需调仓'（不能矫枉过正）"""
        from scripts.daily_signal import format_signal_report

        signal = self._signal(["纳指", "黄金"])
        replay_result = {
            "gap_trading_days": 2,
            "last_date": "2025-06-20",
            "today": "2025-06-24",
            "daily_active": [
                {"date": "2025-06-23", "active": ["纳指", "黄金"]},
                {"date": "2025-06-24", "active": ["纳指", "黄金"]},
            ],
            "changes": [],
        }

        report = format_signal_report(signal, previous_signal=None,
                                      replay_result=replay_result)

        assert "无需调仓" in report, f"持仓未变应报无需调仓，实际：\n{report}"


# [2026-10-15] 新增：熔断持续期不得每天重复报「全部清仓」；持仓不得用趋势名单冒充
class TestCircuitBreakerContinuation:
    """_compare_signals 的熔断分支此前只读 current，基线完全失效 →
    熔断一旦触发就每天都报「全部清仓」。与 v221 修的「恒输出无需调仓」是同一族单边判断 bug。"""

    @staticmethod
    def _signal(active, triggered, multiplier=0.0):
        return {
            "date": "2026-10-15",
            "defense": {"trend_strengths": {n: 0.5 for n in active},
                        "active": list(active),
                        "target_weights": {n: 1.0 / len(active) for n in active} if active else {},
                        "scaling_factor": 1.0, "predicted_vol": 0.1},
            "offense": {"rankings": [], "target_weights": {}},
            "circuit_breaker": {"triggered": triggered, "smoothed_corr": 0.12},
            "drawdown_stop": {"level": "warning", "position_multiplier": 1.0,
                              "drawdown": -0.11},
            "execution": {"final_multiplier": multiplier, "funds_to_repo": triggered},
        }

    def test_first_cb_day_reports_liquidate(self):
        """昨日未熔断、今日熔断 → 必须报「全部清仓」"""
        from scripts.daily_signal import _compare_signals

        actions = _compare_signals(self._signal(["纳指"], True, 0.0),
                                   self._signal(["纳指"], False, 1.0))
        assert actions == ["全部清仓（熔断触发）"], actions

    def test_cb_continuation_reports_no_action(self):
        """昨日已熔断、今日仍熔断 → 早已是空仓，不得再报清仓"""
        from scripts.daily_signal import _compare_signals

        actions = _compare_signals(self._signal(["纳指"], True, 0.0),
                                   self._signal(["纳指"], True, 0.0))
        assert "全部清仓（熔断触发）" not in actions, actions
        assert any("无需调仓" in a for a in actions), actions

    def test_cb_release_reports_rebuild(self):
        """昨日熔断、今日解除 → 应报建仓而非清仓"""
        from scripts.daily_signal import _compare_signals

        actions = _compare_signals(self._signal(["纳指"], False, 1.0),
                                   self._signal(["纳指"], True, 0.0))
        assert not any("清仓" in a for a in actions), actions


class TestHeldNames:
    """「当前持有」不得直接用 defense.active —— 熔断或乘数归零时 active 依然非空。
    这是 CLAUDE.md 已记载的 final_multiplier 语义陷阱的另一张脸。"""

    def test_uses_active_when_fully_invested(self):
        from scripts.daily_signal import held_names

        prev = {"defense": {"active": ["纳指", "黄金"]},
                "circuit_breaker": {"triggered": False},
                "execution": {"final_multiplier": 1.0}}
        assert held_names(prev) == ["纳指", "黄金"]

    def test_empty_when_circuit_breaker_triggered(self):
        from scripts.daily_signal import held_names

        prev = {"defense": {"active": ["纳指", "国债ETF"]},
                "circuit_breaker": {"triggered": True},
                "execution": {"final_multiplier": 0.0}}
        assert held_names(prev) == [], "熔断触发时应为空仓，不得用趋势名单冒充"

    def test_empty_when_multiplier_zero(self):
        """回撤止损清仓（multiplier=0）但熔断未触发 → 同样应为空仓"""
        from scripts.daily_signal import held_names

        prev = {"defense": {"active": ["纳指"]},
                "circuit_breaker": {"triggered": False},
                "execution": {"final_multiplier": 0.0}}
        assert held_names(prev) == []

    def test_missing_execution_field_defaults_to_active(self):
        """旧 state 无 execution 字段 → 退回 active，不得崩溃"""
        from scripts.daily_signal import held_names

        prev = {"defense": {"active": ["纳指"]},
                "circuit_breaker": {"triggered": False}}
        assert held_names(prev) == ["纳指"]

    def test_none_previous_returns_empty(self):
        from scripts.daily_signal import held_names

        assert held_names(None) == []


# [2026-11-06] 新增：熔断持续期的断层回放回归
# 回归 #2026-11-06 报告事故：10-23 → 11-06 断层回放把趋势翻转当买卖，
# 报「持有国债ETF、纳指」并输出「全部清仓（熔断触发）」——实际自 7-03 起已 100% 逆回购。

def _make_records(prices, cb=True, multiplier=0.0, active=None):
    """构造回测引擎 records_df 的最小快照（索引与 prices 对齐）。"""
    idx = prices["沪深300"].index
    if active is None:
        active = ETF_ORDER
    return pd.DataFrame({
        "nav": np.linspace(1.0, 1.2, len(idx)),
        "circuit_breaker_triggered": cb,
        "final_multiplier": multiplier,
        "defense_active": ";".join(active),
        "defense_count": len(active),
    }, index=idx)


class TestReplayUsesBacktestStatus:
    """_replay_gap(records_df=...)：熔断/乘数状态必须来自回测引擎，不得只看趋势"""

    def _gap_state(self, prices):
        dates = prices["沪深300"].index
        return {
            "last_date": str(dates[64].date()),
            "last_active": list(ETF_ORDER),
            "last_cb_triggered": True,
            "last_final_multiplier": 0.0,
            "last_offense_weights": {},
            "portfolio_values": [],
        }

    def test_replay_marks_repo_when_cb_active(self):
        """熔断持续 + 趋势有翻转 → held 全空、changes 为空（不得产生幽灵买卖）"""
        from scripts.daily_signal import _replay_gap

        prices = _make_prices_gold_downtrend(n=150)
        state = self._gap_state(prices)
        records = _make_records(prices, cb=True, multiplier=0.0)

        result = _replay_gap(prices, state, records_df=records)

        assert result["gap_trading_days"] > 0
        assert result["changes"] == [], f"熔断持续期不应有买卖事件，实际：{result['changes']}"
        assert all(entry["held"] == [] for entry in result["daily_active"]), (
            "熔断期间实际持仓必须为空"
        )
        assert all(entry["circuit_breaker"] is True for entry in result["daily_active"])

    def test_replay_uses_records_active_list(self):
        """趋势回放与引擎信号不一致时，以回测引擎 defense_active 为准"""
        from scripts.daily_signal import _replay_gap

        prices = _make_prices_uptrend(n=150)
        state = self._gap_state(prices)
        state["last_cb_triggered"] = False
        state["last_final_multiplier"] = 1.0
        records = _make_records(prices, cb=False, multiplier=1.0, active=["国债ETF"])

        result = _replay_gap(prices, state, records_df=records)

        assert result["daily_active"], "应有回放日"
        assert all(entry["active"] == ["国债ETF"] for entry in result["daily_active"])

    def test_changes_on_cb_release_reason_break(self):
        """熔断解除当日 → 事件 reason='熔断'，其余趋势变化 reason='趋势'"""
        from scripts.daily_signal import _replay_gap

        prices = _make_prices_uptrend(n=150)
        state = self._gap_state(prices)  # 起始熔断
        dates = prices["沪深300"].index

        # 回放首日为熔断中，随后解除
        records = _make_records(prices, cb=False, multiplier=1.0)
        record_cb = records["circuit_breaker_triggered"].copy()
        gap_dates = [d for d in dates if d > pd.Timestamp(state["last_date"])]
        record_cb.loc[gap_dates[0]] = True
        records["circuit_breaker_triggered"] = record_cb

        result = _replay_gap(prices, state, records_df=records)

        add_events = [c for c in result["changes"] if c["event"] == "added"]
        assert add_events, f"熔断解除应产生买入事件，实际：{result['changes']}"
        assert all(c.get("reason") == "熔断" for c in add_events), add_events


class TestReplaySegmentsRespectCircuitBreaker:
    """_format_replay_segments：熔断持续期只能报空仓/熔断，不得出现买入/卖出"""

    def test_segments_show_repo_not_phantom_trades(self):
        from scripts.daily_signal import _replay_gap, _format_replay_segments

        prices = _make_prices_gold_downtrend(n=150)
        dates = prices["沪深300"].index
        state = {
            "last_date": str(dates[64].date()),
            "last_active": list(ETF_ORDER),
            "last_cb_triggered": True,
            "last_final_multiplier": 0.0,
            "last_offense_weights": {},
            "portfolio_values": [],
        }
        result = _replay_gap(prices, state,
                             records_df=_make_records(prices, cb=True, multiplier=0.0))

        text = "\n".join(_format_replay_segments(result))

        assert "买入" not in text and "卖出" not in text, (
            f"熔断持续期不得出现幽灵买卖，实际：\n{text}"
        )
        assert "空仓" in text and "无变化" in text, text


class TestBaselineRespectsCircuitBreaker:
    """_prev_active_signal：断层回放基线必须保留熔断标记，否则当前持有/操作指令全错"""

    @staticmethod
    def _replay_under_cb():
        return {
            "daily_active": [
                {"date": "2025-06-23", "active": ["纳指", "国债ETF"], "held": [],
                 "circuit_breaker": True, "final_multiplier": 0.0},
                {"date": "2025-06-24", "active": ["国债ETF"], "held": [],
                 "circuit_breaker": True, "final_multiplier": 0.0},
            ]
        }

    def test_baseline_carries_cb_triggered(self):
        from scripts.daily_signal import _prev_active_signal, held_names

        baseline = _prev_active_signal(self._replay_under_cb(),
                                       _baseline_signal(["纳指", "国债ETF"]))

        assert baseline["circuit_breaker"]["triggered"] is True, (
            "断层回放基线必须保留熔断状态，不得硬编码 False"
        )
        assert baseline["defense"]["active"] == []
        assert held_names(baseline) == [], "熔断持续时当前持有必须为空仓"

    def test_compare_reports_cb_continuation_after_gap(self):
        from scripts.daily_signal import _prev_active_signal, _compare_signals

        baseline = _prev_active_signal(self._replay_under_cb(), None)
        current = {
            "defense": {"active": ["国债ETF"]},
            "offense": {"target_weights": {}},
            "circuit_breaker": {"triggered": True},
            "execution": {"final_multiplier": 0.0},
        }

        actions = _compare_signals(current, baseline)

        assert actions == ["无需调仓（熔断持续）"], actions


class TestCheckPositionCbContinuation:
    """集成：断层期间熔断持续 → 当前持有空仓 + 无需调仓，不得输出幽灵买卖"""

    @staticmethod
    def _signal(date_str, cb=True, multiplier=0.0):
        return {
            "date": date_str,
            "defense": {
                "trend_strengths": {"国债ETF": 0.2},
                "active": ["国债ETF"],
                "target_weights": {},
                "scaling_factor": 1.0,
                "predicted_vol": 0.05,
            },
            "offense": {"rankings": [], "target_weights": {}},
            "circuit_breaker": {"triggered": cb, "smoothed_corr": 0.30},
            "drawdown_stop": {"level": "normal", "position_multiplier": 1.0,
                              "drawdown": -0.03},
            "execution": {"final_multiplier": multiplier, "funds_to_repo": cb},
        }

    def test_gap_during_cb_reports_repo_and_no_action(self, tmp_path, capsys):
        from src.etf_universe import ETF_UNIVERSE
        from scripts.daily_signal import _save_state

        prices = _make_prices_gold_downtrend(n=150)
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        for name, df in prices.items():
            df.to_parquet(data_dir / f"{ETF_UNIVERSE[name]}.parquet")

        dates = prices["沪深300"].index
        _save_state(str(data_dir), {
            "last_date": str(dates[-4].date()),
            "last_active": list(ETF_ORDER),
            "last_cb_triggered": True,
            "last_final_multiplier": 0.0,
            "last_offense_weights": {},
            "portfolio_values": [],
        })

        signal = self._signal(str(dates[-1].date()))
        records = _make_records(prices, cb=True, multiplier=0.0)

        from scripts import check_position
        with (
            patch("scripts.check_position.check_freshness", return_value=[]),
            patch("scripts.check_position.update_single_etf",
                  MagicMock(return_value={"ok": True, "needs_verify": False})),
            patch("scripts.check_position.DATA_DIR", str(data_dir)),
            patch("scripts.check_position.OUTPUT_PATH", str(tmp_path / "nav.html")),
            patch("scripts.check_position.update_chart", MagicMock()),
            patch("scripts.check_position.generate_signal", return_value=signal),
            patch("scripts.daily_signal.run_backtest",
                  return_value={"records_df": records}),
        ):
            check_position.main()

        out = capsys.readouterr().out

        assert "持有：空仓（100% 逆回购）" in out, out
        assert "无需调仓（熔断持续）" in out, out
        assert "买入" not in out and "卖出" not in out, (
            f"熔断持续期不得出现幽灵买卖，实际：\n{out}"
        )
