# [2026-06-18] 新增：美股回测测试 — 数据获取/日期对齐/久期对比/对照表/2008 压力测试

import numpy as np
import pandas as pd
import pytest


# --- 辅助函数（复用项目现有模式） ---

def _price_series(log_returns, start_price=1.0):
    prices = start_price * np.exp(np.cumsum(log_returns))
    dates = pd.date_range("2020-01-01", periods=len(prices), freq="B")
    return pd.Series(prices, index=dates, name="close")


def _make_ohlcv(close_series):
    close = close_series.values
    idx = close_series.index
    return pd.DataFrame({
        "open": close * 0.99,
        "high": close * 1.02,
        "low": close * 0.98,
        "close": close,
        "volume": np.full(len(close), 1e6),
    }, index=idx)


def _make_us_prices(n=200, seed=42):
    """美股模拟价格：SPY/QQQ/GLD/SHY/BIL 上涨行情，股债负相关。"""
    rng = np.random.RandomState(seed)
    noise = rng.normal(0, 0.001, n)
    stock_r = np.full(n, 0.001) + noise
    bond_r = np.full(n, 0.0005) - noise

    return {
        "SPY": _make_ohlcv(_price_series(stock_r + rng.normal(0, 0.0003, n))),
        "QQQ": _make_ohlcv(_price_series(stock_r + rng.normal(0, 0.0004, n))),
        "GLD": _make_ohlcv(_price_series(rng.normal(0.0003, 0.001, n))),
        "SHY": _make_ohlcv(_price_series(bond_r)),
        "BIL": _make_ohlcv(_price_series(np.full(n, 0.0001))),
    }


def _make_cn_prices(n=200, seed=42):
    """A 股模拟价格（沪深300/创业板/纳指/黄金/国债ETF）。"""
    rng = np.random.RandomState(seed)
    noise = rng.normal(0, 0.001, n)
    stock_r = np.full(n, 0.001) + noise
    bond_r = np.full(n, 0.0005) - noise

    return {
        "沪深300": _make_ohlcv(_price_series(stock_r + rng.normal(0, 0.0003, n))),
        "创业板": _make_ohlcv(_price_series(stock_r + rng.normal(0, 0.0004, n))),
        "纳指": _make_ohlcv(_price_series(stock_r + rng.normal(0, 0.0003, n))),
        "黄金": _make_ohlcv(_price_series(rng.normal(0.0003, 0.001, n))),
        "国债ETF": _make_ohlcv(_price_series(bond_r)),
    }


# --- 测试：数据获取 ---

class TestFetchUSData:
    """数据获取 — yfinance → {ticker: DataFrame}"""

    def test_fetch_us_data_returns_dict(self, monkeypatch):
        """mock yfinance.download → 返回 {ticker: DataFrame} 格式"""
        # 构造 mock download 返回值（MultiIndex columns）
        dates = pd.date_range("2024-01-01", "2024-06-01", freq="B")
        n = len(dates)
        rng = np.random.RandomState(42)
        tickers = ["SPY", "QQQ", "GLD", "SHY", "BIL"]
        # yfinance MultiIndex 格式: (metric, ticker)
        arrays = {}
        for t in tickers:
            price = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.01, n)))
            arrays[("Open", t)] = price * 0.99
            arrays[("High", t)] = price * 1.02
            arrays[("Low", t)] = price * 0.98
            arrays[("Close", t)] = price
            arrays[("Volume", t)] = np.full(n, 1e6)

        mock_df = pd.DataFrame(arrays, index=dates)
        mock_df.columns = pd.MultiIndex.from_tuples(mock_df.columns)

        import yfinance as yf
        monkeypatch.setattr(yf, "download", lambda *a, **kw: mock_df)

        from scripts.backtest_us import fetch_us_data
        result = fetch_us_data(tickers, start="2024-01-01", end="2024-06-01")
        assert isinstance(result, dict)
        for t in tickers:
            assert t in result, f"返回 dict 应包含 {t}"
            assert isinstance(result[t], pd.DataFrame), f"{t} 应为 DataFrame"


# --- 测试：日期对齐 ---

class TestAlignDates:
    """日期对齐 — 不同长度 DataFrame → 并集日期"""

    def test_align_dates_union(self):
        from scripts.backtest_us import align_dates_union

        dates1 = pd.date_range("2024-01-01", "2024-06-01", freq="B")
        dates2 = pd.date_range("2024-03-01", "2024-08-01", freq="B")
        df1 = pd.DataFrame({"close": np.ones(len(dates1))}, index=dates1)
        df2 = pd.DataFrame({"close": np.ones(len(dates2))}, index=dates2)

        result = align_dates_union({"A": df1, "B": df2})
        # 对齐后每个 DataFrame 应为并集日期长度
        union_len = len(result["A"])
        assert union_len > max(len(df1), len(df2)), (
            f"并集应大于单个长度，实际并集={union_len}, A={len(df1)}, B={len(df2)}"
        )
        assert len(result["B"]) == union_len, (
            f"对齐后 B 应与 A 同长度，实际 {len(result['B'])} vs {union_len}"
        )


# --- 测试：久期对比 ---

class TestCompareBondDurations:
    """久期对比 — SHY/IEF/TLT 三档对比"""

    def test_compare_bond_durations_runs(self):
        from scripts.backtest_us import compare_bond_durations

        prices = _make_us_prices(n=200)
        # 用 SHY 数据同时冒充 IEF/TLT（测试只验证结构，不等价于真实对比）
        prices["IEF"] = prices["SHY"].copy()
        prices["TLT"] = prices["SHY"].copy()
        df = compare_bond_durations(prices)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 3, f"应返回 3 行（SHY/IEF/TLT），实际 {len(df)}"
        for col in ["annual_return", "annual_volatility", "sharpe_ratio", "max_drawdown"]:
            assert col in df.columns, f"应包含列 {col}"


# --- 测试：对照表 ---

class TestComparisonTable:
    """美股对照表 — 策略 vs SPY/QQQ/60-40/等权"""

    def test_generate_us_comparison_table(self):
        from scripts.backtest_us import run_us_backtest, generate_comparison_table

        prices = _make_us_prices(n=200)
        result = run_us_backtest(prices, "SHY")
        df = generate_comparison_table(result)
        assert isinstance(df, pd.DataFrame)
        # 列应为 策略 + 基准标签
        assert "美股策略" in df.columns or len(df.columns) >= 2, (
            f"对照表应至少含策略列，实际列: {list(df.columns)}"
        )


# --- 测试：A/B 对照 ---

class TestCrossMarketTable:
    """A 股 vs 美股全期绩效对照"""

    def test_cn_vs_us_comparison(self):
        from scripts.backtest_us import generate_cross_market_table

        cn_prices = _make_cn_prices(n=200)
        us_prices = _make_us_prices(n=200)
        df = generate_cross_market_table(us_prices, cn_prices)
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0, "对照表不应为空"


# --- 测试：2008 压力测试 ---

class Test2008Stress:
    """2008 年压力测试 — 策略回撤应低于 SPY"""

    def test_2008_stress(self):
        from scripts.backtest_us import run_2008_stress_test

        # 构造 2008 年行情（暴跌 + 反弹）
        rng = np.random.RandomState(2008)
        n = 252  # 约一年
        crash_r = np.concatenate([
            np.full(126, -0.003),  # H1 暴跌
            np.full(126, 0.001),   # H2 反弹
        ]) + rng.normal(0, 0.002, n)

        prices = {
            "SPY": _make_ohlcv(_price_series(crash_r + rng.normal(0, 0.001, n))),
            "QQQ": _make_ohlcv(_price_series(crash_r + rng.normal(0, 0.0015, n))),
            "GLD": _make_ohlcv(_price_series(rng.normal(0.0005, 0.001, n))),
            "SHY": _make_ohlcv(_price_series(rng.normal(0.0003, 0.0005, n))),
            "BIL": _make_ohlcv(_price_series(np.full(n, 0.0001))),
        }
        result = run_2008_stress_test(prices)
        # 策略回撤应小于 SPY 回撤（防御起作用）
        assert result["strategy_max_dd"] > result["spy_max_dd"], (
            f"策略回撤 {result['strategy_max_dd']:.4f} 应小于 SPY {result['spy_max_dd']:.4f}"
        )
