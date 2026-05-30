# [2026-05-30] 新增：每日信号脚本测试 — 10 条场景
"""测试 scripts/daily_signal.py — 收盘后信号报告生成"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

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


def _write_defense_parquets(data_dir, trends=None, n=130):
    """在 data_dir 写入 5 只防御 ETF 的 parquet 文件。trends=None 则全部上涨。"""
    codes = {
        "510300": "沪深300",
        "159915": "创业板",
        "513100": "纳指",
        "518880": "黄金",
        "511010": "国债ETF",
    }
    if trends is None:
        trends = {code: 0.08 for code in codes}
    seeds = {"510300": 42, "159915": 43, "513100": 44, "518880": 45, "511010": 46}
    for code, name in codes.items():
        df = _make_ohlcv(n=n, trend=trends.get(code, 0.08), seed=seeds[code])
        df.to_parquet(os.path.join(data_dir, f"{code}.parquet"))


def _write_offense_parquet(data_dir, code, name, trend=0.10, n=130, seed=99):
    """写入一只进攻 ETF 的 parquet。"""
    df = _make_ohlcv(n=n, trend=trend, seed=seed)
    df.to_parquet(os.path.join(data_dir, f"{code}.parquet"))


def _write_defense_neg_corr(data_dir, n=130):
    """写入 5 只防御 ETF parquet，股债负相关（熔断不触发）。"""
    rng = np.random.RandomState(42)
    noise = rng.normal(0, 0.01 / np.sqrt(252), n)
    stock_r = np.full(n, 0.08 / 252) + noise
    bond_r = np.full(n, 0.04 / 252) - noise

    def _make_series(log_returns, start_price=1.0):
        prices = start_price * np.exp(np.cumsum(log_returns))
        dates = pd.date_range("2024-01-02", periods=n, freq="B")
        return pd.Series(prices, index=dates, name="close")

    def _make_df(close_series):
        c = close_series.values
        idx = close_series.index
        return pd.DataFrame({
            "open": c * 0.99, "high": c * 1.02, "low": c * 0.98,
            "close": c, "volume": np.full(n, 1e6),
        }, index=idx)

    data = {
        "510300": stock_r + rng.normal(0, 0.0002, n),
        "159915": stock_r + rng.normal(0, 0.0002, n),
        "513100": stock_r + rng.normal(0, 0.0002, n),
        "518880": rng.normal(0.0005 / 252, 0.01 / np.sqrt(252), n),
        "511010": bond_r,
    }
    for code, returns in data.items():
        df = _make_df(_make_series(returns))
        df.to_parquet(os.path.join(data_dir, f"{code}.parquet"))


def _make_signal(date_str="2024-06-28", all_active=True, cb_triggered=False,
                 dd_level="normal", dd_mult=1.0):
    """构造一个 signal dict，模拟 generate_signal 输出。"""
    if all_active:
        active = ["沪深300", "创业板", "纳指", "黄金", "国债ETF"]
        def_weights = {name: 0.2 for name in active}
    else:
        active = ["创业板", "纳指", "黄金", "国债ETF"]
        def_weights = {name: 0.25 for name in active}

    return {
        "date": date_str,
        "defense": {
            "trend_strengths": {name: 0.5 for name in active},
            "active": active,
            "target_weights": def_weights,
            "scaling_factor": 0.8,
            "predicted_vol": 0.12,
        },
        "offense": {
            "rankings": [],
            "target_weights": {},
        },
        "circuit_breaker": {
            "triggered": cb_triggered,
            "smoothed_corr": 0.85 if cb_triggered else -0.3,
        },
        "drawdown_stop": {
            "level": dd_level,
            "position_multiplier": dd_mult,
            "drawdown": -0.05 if dd_level == "normal" else -0.20,
        },
        "execution": {
            "final_multiplier": 0.0 if cb_triggered else dd_mult * 0.8,
            "funds_to_repo": cb_triggered,
        },
    }


# ---- load_prices ----

class TestLoadPrices:
    """load_prices(): 从 data/ 目录加载 ETF parquet"""

    def test_loads_all_5_defense_etfs(self, tmp_path):
        """5 只防御 ETF parquet 全部存在 → 返回 5 项 dict"""
        data_dir = str(tmp_path / "data")
        os.makedirs(data_dir)
        _write_defense_parquets(data_dir)
        from scripts.daily_signal import load_prices
        prices = load_prices(data_dir)
        assert len(prices) == 5
        for name in ["沪深300", "创业板", "纳指", "黄金", "国债ETF"]:
            assert name in prices, f"{name} 应在 prices 中"

    def test_missing_etf_skipped_others_ok(self, tmp_path):
        """某 ETF parquet 缺失 → 跳过该 ETF，其余正常加载"""
        data_dir = str(tmp_path / "data")
        os.makedirs(data_dir)
        _write_defense_parquets(data_dir)
        # 删除纳指
        os.remove(os.path.join(data_dir, "513100.parquet"))
        from scripts.daily_signal import load_prices
        prices = load_prices(data_dir)
        assert "纳指" not in prices
        assert len(prices) == 4
        for name in ["沪深300", "创业板", "黄金", "国债ETF"]:
            assert name in prices

    def test_empty_data_dir_returns_empty(self, tmp_path):
        """data/ 目录无 parquet → 返回空 dict，不崩溃"""
        data_dir = str(tmp_path / "data")
        os.makedirs(data_dir)
        from scripts.daily_signal import load_prices
        prices = load_prices(data_dir)
        assert prices == {}


# ---- format_signal_report ----

class TestFormatSignalReport:
    """format_signal_report(): 信号 dict → 中文报告文本"""

    def test_full_report_has_all_sections(self):
        """正常信号 → 报告含趋势强度、熔断、回撤、目标持仓"""
        signal = _make_signal(all_active=True)
        from scripts.daily_signal import format_signal_report
        report = format_signal_report(signal)

        assert "趋势强度" in report, f"报告应含'趋势强度'，实际：{report[:200]}"
        assert "熔断" in report, f"报告应含'熔断'"
        assert "回撤" in report, f"报告应含'回撤'"
        assert "目标持仓" in report, f"报告应含'目标持仓'"

    def test_first_run_shows_initial_position(self):
        """无上一交易日信号 → 报告含'首次建仓'"""
        signal = _make_signal()
        from scripts.daily_signal import format_signal_report
        report = format_signal_report(signal, previous_signal=None)
        assert "首次建仓" in report, f"首次运行应含'首次建仓'，实际：{report[:200]}"

    def test_no_change_shows_hold(self):
        """连续两天信号一致 → 报告含'无需调仓'"""
        signal = _make_signal()
        prev = _make_signal()
        from scripts.daily_signal import format_signal_report
        report = format_signal_report(signal, previous_signal=prev)
        assert "无需调仓" in report, f"信号不变应含'无需调仓'，实际：{report[:200]}"

    def test_signal_change_shows_sell(self):
        """某 ETF 从 active 变为 inactive → 报告含'卖出'"""
        prev = _make_signal(all_active=True)
        signal = _make_signal(all_active=False)
        from scripts.daily_signal import format_signal_report
        report = format_signal_report(signal, previous_signal=prev)
        assert "卖出" in report, (
            f"沪深300 退出 active 应含'卖出'，实际：{report[:300]}"
        )

    def test_signal_change_shows_buy(self):
        """某 ETF 从 inactive 变为 active → 报告含'买入'"""
        prev = _make_signal(all_active=False)
        signal = _make_signal(all_active=True)
        from scripts.daily_signal import format_signal_report
        report = format_signal_report(signal, previous_signal=prev)
        assert "买入" in report, (
            f"沪深300 进入 active 应含'买入'，实际：{report[:300]}"
        )

    def test_circuit_breaker_shows_liquidate(self):
        """熔断触发 → 报告含'全部清仓'"""
        signal = _make_signal(cb_triggered=True)
        from scripts.daily_signal import format_signal_report
        report = format_signal_report(signal)
        assert "全部清仓" in report, (
            f"熔断触发应含'全部清仓'，实际：{report[:200]}"
        )


# ---- main ----

class TestMain:
    """main(): 端到端集成测试"""

    def test_missing_defense_etf_exit_code_1(self, tmp_path):
        """仅 4 只防御 ETF parquet → SystemExit exit code 1"""
        data_dir = str(tmp_path / "data")
        os.makedirs(data_dir)
        _write_defense_parquets(data_dir)
        os.remove(os.path.join(data_dir, "511010.parquet"))  # 删除国债ETF

        from scripts import daily_signal
        with pytest.raises(SystemExit) as exc:
            daily_signal.main(data_dir=data_dir, state_dir=str(tmp_path))
        assert exc.value.code == 1, f"应退出 code=1，实际 {exc.value.code}"

    def test_less_than_120_days_exit_code_1(self, tmp_path):
        """交易日 < 120 → SystemExit exit code 1"""
        data_dir = str(tmp_path / "data")
        os.makedirs(data_dir)
        _write_defense_parquets(data_dir, n=100)

        from scripts import daily_signal
        with pytest.raises(SystemExit) as exc:
            daily_signal.main(data_dir=data_dir, state_dir=str(tmp_path))
        assert exc.value.code == 1

    def test_first_run_creates_state_file(self, tmp_path):
        """首次运行 → 生成状态文件，报告含'首次建仓'"""
        data_dir = str(tmp_path / "data")
        os.makedirs(data_dir)
        _write_defense_neg_corr(data_dir)
        state_dir = str(tmp_path / "state")

        from scripts import daily_signal
        report = daily_signal.main(data_dir=data_dir, state_dir=state_dir)
        assert "首次建仓" in report
        assert os.path.exists(os.path.join(state_dir, "position_state.json"))

    def test_second_run_no_change(self, tmp_path):
        """连续两天相同数据 → 报告含'无需调仓'"""
        data_dir = str(tmp_path / "data")
        os.makedirs(data_dir)
        _write_defense_neg_corr(data_dir)
        state_dir = str(tmp_path / "state")

        from scripts import daily_signal
        # 首次
        daily_signal.main(data_dir=data_dir, state_dir=state_dir)
        # 二次（相同数据）
        report2 = daily_signal.main(data_dir=data_dir, state_dir=state_dir)
        assert "无需调仓" in report2, (
            f"连续两天相同数据应含'无需调仓'，实际：{report2[:300]}"
        )

    def test_missing_parquet_for_defense_logs_warning(self, tmp_path):
        """data/ 目录无任何 parquet → 报错退出"""
        data_dir = str(tmp_path / "data")
        os.makedirs(data_dir)

        from scripts import daily_signal
        with pytest.raises(SystemExit) as exc:
            daily_signal.main(data_dir=data_dir, state_dir=str(tmp_path))
        assert exc.value.code == 1
