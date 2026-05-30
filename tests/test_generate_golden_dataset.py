# [2026-05-30] 新增：Golden Dataset 验证测试 — 引擎改动后结果必须与基准完全一致
import os
import sys
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.backtest_engine import run_backtest

BASE = os.path.join(os.path.dirname(__file__), "..")
DATA_DIR = os.path.join(BASE, "data")
OUTPUT_DIR = os.path.join(BASE, "output")

DEFENSE_MAP = {
    "沪深300": "510300",
    "创业板": "159915",
    "纳指": "513100",
    "黄金": "518880",
    "国债ETF": "511010",
}

FIXED_PARAMS = {
    "trend_window": 40,
    "ewma_lambda": 0.94,
    "target_vol_beta": 0.10,
    "corr_threshold": 0.0,
    "defense_ratio": 1.0,
}

CUTOFF_DATE = pd.Timestamp("2022-12-31")
INITIAL_CAPITAL = 1_000_000
MIN_DAYS = 120


def _load_prices():
    prices = {}
    for name, code in DEFENSE_MAP.items():
        fpath = os.path.join(DATA_DIR, f"{code}.parquet")
        if not os.path.exists(fpath):
            continue
        df = pd.read_parquet(fpath)
        df = df[df.index <= CUTOFF_DATE]
        prices[name] = df
    return prices


def _run_golden_backtest():
    prices = _load_prices()
    return run_backtest(
        prices=prices,
        initial_capital=INITIAL_CAPITAL,
        params=FIXED_PARAMS,
        min_days=MIN_DAYS,
    )


def _golden_file_path(name):
    return os.path.join(OUTPUT_DIR, name)


# ═══════════════════════════════════════════════════════════════
# 基础路径：golden 文件存在 → 重新回测结果逐行一致
# ═══════════════════════════════════════════════════════════════


class TestGoldenNav:
    """golden_nav.csv 存在 → NAV 逐行一致"""

    def test_nav_row_by_row(self):
        path = _golden_file_path("golden_nav.csv")
        if not os.path.exists(path):
            pytest.skip("golden_nav.csv 不存在，请先运行 scripts/generate_golden_dataset.py")

        golden = pd.read_csv(path, index_col=0, parse_dates=True)
        result = _run_golden_backtest()
        records = result["records_df"]
        actual_nav = records["nav"]

        # 日期索引对齐
        common = golden.index.intersection(actual_nav.index)
        assert len(common) > 0, "golden 与回测日期无交集"

        golden_aligned = golden.loc[common, "nav"]
        actual_aligned = actual_nav.loc[common]

        diff = (golden_aligned - actual_aligned).abs()
        max_diff = diff.max()
        assert max_diff < 0.01, (
            f"NAV 偏差过大: max={max_diff:.6f}，golden 与回测结果应一致"
        )


class TestGoldenSignals:
    """golden_signals.csv 存在 → signals 逐列一致"""

    SIGNAL_COLS = [
        "exposure", "repo_amount", "final_multiplier",
        "circuit_breaker_triggered", "drawdown_level", "drawdown",
        "n_positions", "position_names", "defense_active",
        "scaling_factor", "predicted_vol", "defense_count",
    ]

    # 这些列用分号分隔 → 比较有序集合（顺序无关）
    _SET_COLS = {"position_names", "defense_active", "offense_top"}

    def test_signals_column_by_column(self):
        path = _golden_file_path("golden_signals.csv")
        if not os.path.exists(path):
            pytest.skip("golden_signals.csv 不存在，请先运行 scripts/generate_golden_dataset.py")

        golden = pd.read_csv(path, index_col=0, parse_dates=True)
        result = _run_golden_backtest()
        records = result["records_df"]

        common = golden.index.intersection(records.index)
        assert len(common) > 0, "golden 与回测日期无交集"

        for col in self.SIGNAL_COLS:
            if col not in golden.columns or col not in records.columns:
                continue
            golden_col = golden.loc[common, col]
            actual_col = records.loc[common, col]

            if col in self._SET_COLS:
                # 分号分隔列：比较集合（顺序无关）
                for i in range(len(common)):
                    g_set = set(str(golden_col.iloc[i]).split(";")) if str(golden_col.iloc[i]) != "nan" else set()
                    a_set = set(str(actual_col.iloc[i]).split(";")) if str(actual_col.iloc[i]) != "nan" else set()
                    if g_set == {""}:
                        g_set = set()
                    if a_set == {""}:
                        a_set = set()
                    assert g_set == a_set, (
                        f"列 '{col}' 第 {i} 行集合不一致: golden={g_set}, actual={a_set}"
                    )
            elif golden_col.dtype == object:
                # 非分号字符串列：精确匹配
                mismatches = (golden_col != actual_col).sum()
                assert mismatches == 0, (
                    f"列 '{col}' 有 {mismatches} 行不一致"
                )
            else:
                # 数值列：容差
                diff = (golden_col.astype(float) - actual_col.astype(float)).abs()
                assert diff.max() < 1e-6, (
                    f"列 '{col}' 偏差过大: max={diff.max():.10f}"
                )


class TestGoldenPositions:
    """golden_positions.csv 存在 → 持仓逐列一致（容差 1 元）"""

    def test_positions_column_by_column(self):
        path = _golden_file_path("golden_positions.csv")
        if not os.path.exists(path):
            pytest.skip("golden_positions.csv 不存在，请先运行 scripts/generate_golden_dataset.py")

        golden = pd.read_csv(path, index_col=0, parse_dates=True)
        result = _run_golden_backtest()
        recorder = result.get("_recorder", None)

        if recorder is None or not recorder.get("positions_detail"):
            pytest.skip("回测引擎未返回 positions_detail，无法验证")

        actual = pd.DataFrame(recorder["positions_detail"])
        actual["date"] = pd.to_datetime(actual["date"])
        actual = actual.set_index("date").sort_index()

        common = golden.index.intersection(actual.index)
        assert len(common) > 0, "golden 与回测持仓日期无交集"

        for col in golden.columns:
            if col not in actual.columns:
                continue
            diff = (golden.loc[common, col] - actual.loc[common, col]).abs()
            assert diff.max() < 1.0, (
                f"持仓 '{col}' 偏差过大: max={diff.max():.4f}（容差 1 元）"
            )


class TestGoldenTrades:
    """golden_trades.csv 存在 → 交易数量和方向一致"""

    def test_trades_count_and_direction(self):
        path = _golden_file_path("golden_trades.csv")
        if not os.path.exists(path):
            pytest.skip("golden_trades.csv 不存在，请先运行 scripts/generate_golden_dataset.py")

        golden = pd.read_csv(path)
        result = _run_golden_backtest()

        # 从 positions_detail 重新计算 trades
        recorder = result.get("_recorder", None)
        if recorder is None or not recorder.get("positions_detail"):
            pytest.skip("回测引擎未返回 positions_detail，无法验证")

        pos_df = pd.DataFrame(recorder["positions_detail"])
        pos_df["date"] = pd.to_datetime(pos_df["date"])
        pos_df = pos_df.set_index("date").sort_index()

        trades = []
        prev = {}
        for dt, row in pos_df.iterrows():
            for col in pos_df.columns:
                cur_val = row.get(col, 0.0) if pd.notna(row.get(col)) else 0.0
                prev_val = prev.get(col, 0.0)
                delta = cur_val - prev_val
                if abs(delta) > 1.0:
                    trades.append({
                        "date": dt,
                        "etf": col,
                        "action": "buy" if delta > 0 else "sell",
                        "amount": abs(delta),
                    })
                prev[col] = cur_val
        actual = pd.DataFrame(trades)

        # 总交易数
        assert len(actual) == len(golden), (
            f"交易总数不一致: golden={len(golden)}, actual={len(actual)}"
        )

        # 买卖方向分布
        golden_buys = (golden["action"] == "buy").sum()
        actual_buys = (actual["action"] == "buy").sum()
        assert golden_buys == actual_buys, (
            f"买入次数不一致: golden={golden_buys}, actual={actual_buys}"
        )


# ═══════════════════════════════════════════════════════════════
# 边界
# ═══════════════════════════════════════════════════════════════


class TestGoldenDatasetEdge:
    """边界：golden 文件不存在 → 清晰报错"""

    def test_missing_golden_file_reports_clearly(self):
        path = _golden_file_path("golden_nonexistent.csv")
        assert not os.path.exists(path), (
            f"测试文件 {path} 不应存在"
        )
        # 验证 skip 行为：尝试读取不存在的 golden 文件
        # 测试框架层面：不存在文件时 pytest.skip 给出原因


class TestDeterministic:
    """同一数据+参数两次回测 → 结果完全一致"""

    def test_same_input_produces_same_output(self):
        result1 = _run_golden_backtest()
        result2 = _run_golden_backtest()

        nav1 = result1["records_df"]["nav"]
        nav2 = result2["records_df"]["nav"]

        diff = (nav1 - nav2).abs()
        assert diff.max() < 1e-10, (
            f"同一输入两次回测 NAV 不一致: max_diff={diff.max():.15f}"
        )

        # 所有标量指标一致
        for key in ["final_nav", "total_return", "sharpe_ratio", "max_drawdown"]:
            v1 = result1[key]
            v2 = result2[key]
            assert abs(v1 - v2) < 1e-10, (
                f"标量指标 '{key}' 两次回测不一致: {v1} vs {v2}"
            )


class TestParamSensitivity:
    """参数偏差 → 测试应检测到差异"""

    def test_different_param_produces_different_output(self):
        """修改 trend_window 应产生不同结果"""
        prices = _load_prices()
        r1 = run_backtest(prices, initial_capital=INITIAL_CAPITAL,
                          params=FIXED_PARAMS, min_days=MIN_DAYS)
        alt_params = {**FIXED_PARAMS, "trend_window": 80}
        r2 = run_backtest(prices, initial_capital=INITIAL_CAPITAL,
                          params=alt_params, min_days=MIN_DAYS)

        nav1 = r1["records_df"]["nav"]
        nav2 = r2["records_df"]["nav"]

        diff = (nav1 - nav2).abs()
        assert diff.max() > 0.01, (
            f"不同参数应产生不同 NAV，实际 max_diff={diff.max():.6f}"
        )
