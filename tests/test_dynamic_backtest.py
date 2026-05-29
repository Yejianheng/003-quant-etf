# [2026-05-29] 新增：动态 ETF 接入回测测试 — 6 场景

import numpy as np
import pandas as pd
import pytest
from src.backtest_engine import run_backtest, union_dates, get_available_etfs


def _price_series(log_returns, start_price=1.0):
    """对数收益率 → 价格 Series（带工作日 DatetimeIndex）。"""
    prices = start_price * np.exp(np.cumsum(log_returns))
    dates = pd.date_range("2024-01-01", periods=len(prices), freq="B")
    return pd.Series(prices, index=dates, name="close")


def _make_ohlcv(close_series):
    """收盘价 Series → OHLCV DataFrame。"""
    close = close_series.values
    idx = close_series.index
    return pd.DataFrame({
        "open": close * 0.99,
        "high": close * 1.02,
        "low": close * 0.98,
        "close": close,
        "volume": np.full(len(close), 1e6),
    }, index=idx)


def _make_defense_prices(n=200, seed=42):
    """5 只防御标的单边上涨。"""
    rng = np.random.RandomState(seed)
    noise = rng.normal(0, 0.001, n)
    stock_r = np.full(n, 0.001) + noise
    bond_r = np.full(n, 0.0005) - noise

    return {
        "沪深300": _make_ohlcv(_price_series(stock_r + rng.normal(0, 0.0003, n), start_price=1.0)),
        "创业板": _make_ohlcv(_price_series(stock_r + rng.normal(0, 0.0003, n), start_price=1.0)),
        "纳指": _make_ohlcv(_price_series(stock_r + rng.normal(0, 0.0003, n), start_price=1.0)),
        "黄金": _make_ohlcv(_price_series(rng.normal(0.0003, 0.001, n), start_price=1.0)),
        "国债ETF": _make_ohlcv(_price_series(bond_r, start_price=1.0)),
    }


# ═══════════════════════════════════════════════════════════════
# 引擎改动验证
# ═══════════════════════════════════════════════════════════════


class TestUnionDates:
    """union_dates(prices) → 返回日期并集，非交集"""

    def test_union_dates_returns_all_dates(self):
        """两个 ETF 日期范围不同 → 并集包含两者的所有日期"""
        idx_a = pd.date_range("2024-01-01", "2024-01-10", freq="B")
        idx_b = pd.date_range("2024-01-05", "2024-01-15", freq="B")
        prices = {
            "A": pd.DataFrame({"close": np.ones(len(idx_a))}, index=idx_a),
            "B": pd.DataFrame({"close": np.ones(len(idx_b))}, index=idx_b),
        }
        result = union_dates(prices)
        assert len(result) > max(len(idx_a), len(idx_b)), (
            f"并集应大于各自长度，实际 {len(result)} vs A={len(idx_a)} B={len(idx_b)}"
        )
        # 验证包含两端的日期
        assert pd.Timestamp("2024-01-01") in result
        assert pd.Timestamp("2024-01-15") in result

    def test_union_dates_same_range(self):
        """相同日期范围 → 并集等于交集"""
        idx = pd.date_range("2024-01-01", "2024-01-10", freq="B")
        prices = {
            "A": pd.DataFrame({"close": np.ones(len(idx))}, index=idx),
            "B": pd.DataFrame({"close": np.ones(len(idx))}, index=idx),
        }
        result = union_dates(prices)
        assert len(result) == len(idx), (
            f"同日期范围并集=交集，实际 {len(result)} vs {len(idx)}"
        )


class TestGetAvailableETFs:
    """get_available_etfs(prices, date) → 返回该日期有数据且 ≥min_history 的 ETF"""

    def test_returns_only_etfs_with_data_on_date(self):
        """某 ETF 在该日期之前才开始 → 不包含该 ETF"""
        idx_a = pd.date_range("2024-01-01", "2024-03-31", freq="B")
        idx_b = pd.date_range("2024-03-01", "2024-03-31", freq="B")
        prices = {
            "A": pd.DataFrame({"close": np.ones(len(idx_a))}, index=idx_a),
            "B": pd.DataFrame({"close": np.ones(len(idx_b))}, index=idx_b),
        }
        # 2024-01-15: 只有 A 有数据
        available = get_available_etfs(prices, pd.Timestamp("2024-01-15"), min_history=10)
        assert "A" in available
        assert "B" not in available, "B 在 1 月 15 日还没上市，不应出现"

    def test_min_history_filter(self):
        """ETF 有数据但历史不足 min_history → 不包含"""
        idx = pd.date_range("2024-01-01", "2024-03-31", freq="B")
        prices = {
            "A": pd.DataFrame({"close": np.ones(len(idx))}, index=idx),
        }
        # 第 5 天：数据不够 min_history=20
        date = idx[5]
        available = get_available_etfs(prices, date, min_history=20)
        assert "A" not in available, f"第 5 天历史不足 20，不应出现"

        # 第 30 天：数据够了
        date = idx[30]
        available = get_available_etfs(prices, date, min_history=20)
        assert "A" in available, f"第 30 天历史 ≥20，应出现"


# ═══════════════════════════════════════════════════════════════
# 基础路径
# ═══════════════════════════════════════════════════════════════


class TestDynamicBacktest:
    """run_backtest 含不同上市日期的 ETF → 回测从最早防御 ETF 日期开始"""

    def test_backtest_with_late_offense_etf(self):
        """防御 ETF 全量 + 进攻 ETF 从 2024-06-01 才开始 → 回测不报错"""
        prices = _make_defense_prices(n=200, seed=42)
        # 进攻 ETF：数据从 2024-06-01 开始（模拟 2020 年上市）
        offense_idx = pd.date_range("2024-06-01", "2024-10-15", freq="B")
        rng = np.random.RandomState(99)
        offense_r = rng.normal(0.0008, 0.002, len(offense_idx))
        prices["酒ETF"] = _make_ohlcv(_price_series(offense_r, start_price=2.0))
        # 重设 index 为 offense_idx
        prices["酒ETF"].index = offense_idx

        result = run_backtest(prices, initial_capital=1_000_000, min_days=120)
        assert result["records_df"] is not None
        assert len(result["records_df"]) > 0, "回测应至少产出一些日记录"

    def test_no_offense_etf_early_dates(self):
        """早期（2013 年）进攻层 ETF 全未上市 → rankings 为空，offense 资金进 repo"""
        prices = _make_defense_prices(n=200, seed=42)
        # 不添加任何进攻 ETF → offense.rankings 始终为空
        result = run_backtest(prices, initial_capital=1_000_000, min_days=120)
        records = result["records_df"]
        # 进攻层应空仓，所有进攻资金进 repo
        # 验证回测正常完成（空进攻不崩溃）
        assert result["final_nav"] > 0, "空进攻回测应正常产出净值"


# ═══════════════════════════════════════════════════════════════
# 边界
# ═══════════════════════════════════════════════════════════════


class TestEmptyETF:
    """prices 中某 ETF 的 DataFrame 为空 → 跳过该 ETF"""

    def test_empty_dataframe_skipped(self):
        """空 DataFrame 不应导致回测崩溃"""
        prices = _make_defense_prices(n=200, seed=42)
        prices["空ETF"] = pd.DataFrame()  # 空 DataFrame

        result = run_backtest(prices, initial_capital=1_000_000, min_days=120)
        assert result["records_df"] is not None
        assert len(result["records_df"]) > 0


class TestMissingDate:
    """日期并集中缺失某 ETF 的某天 → 该 ETF 当日不参与进攻排名"""

    def test_missing_date_handled(self):
        """某 ETF 在特定日期无数据 → 当日排除该 ETF"""
        idx_full = pd.date_range("2024-01-01", "2024-10-15", freq="B")
        # 故意丢一天
        idx_gap = idx_full.drop(idx_full[150])

        prices = _make_defense_prices(n=200, seed=42)
        rng = np.random.RandomState(99)
        gap_r = rng.normal(0.0008, 0.002, len(idx_gap))
        prices["酒ETF"] = pd.DataFrame({
            "open": np.ones(len(idx_gap)) * 1.98,
            "high": np.ones(len(idx_gap)) * 2.04,
            "low": np.ones(len(idx_gap)) * 1.96,
            "close": 2.0 * np.exp(np.cumsum(gap_r)),
            "volume": np.full(len(idx_gap), 1e6),
        }, index=idx_gap)

        result = run_backtest(prices, initial_capital=1_000_000, min_days=120)
        assert result["records_df"] is not None
        assert len(result["records_df"]) > 0, "缺失某天数据不应导致回测崩溃"
