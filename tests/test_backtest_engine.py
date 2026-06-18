# [2026-06-18] 新增：跨市场参数化测试 — repo_rate / defense_names 参数化
# [2026-05-28] 新增：test_three_benchmarks — 验证 run_backtest 返回三条新基准
# [2026-05-27] 新增：回测引擎测试 — 3 场景

import numpy as np
import pandas as pd
from src.backtest_engine import run_backtest, parameter_scan


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


def _make_bull_prices(n=200, seed=42):
    """全绿场景：5 只防御标的单边上涨，股债负相关。"""
    rng = np.random.RandomState(seed)
    noise = rng.normal(0, 0.001, n)
    stock_r = np.full(n, 0.001) + noise
    bond_r = np.full(n, 0.0005) - noise

    return {
        "沪深300": _make_ohlcv(_price_series(stock_r + rng.normal(0, 0.0003, n))),
        "创业板": _make_ohlcv(_price_series(stock_r + rng.normal(0, 0.0003, n))),
        "纳指": _make_ohlcv(_price_series(stock_r + rng.normal(0, 0.0003, n))),
        "黄金": _make_ohlcv(_price_series(rng.normal(0.0003, 0.001, n))),
        "国债ETF": _make_ohlcv(_price_series(bond_r)),
    }


def _make_crash_prices(n=200, seed=42):
    """先涨后暴跌：前 145 天全线上涨，中段 10 天股票+黄金闪崩，债券独立。

    设计要点：
    - 股票+黄金崩盘（-4%/天 × 10 天），债券独立微涨（日收益率零相关）
      → 60 日滚动相关 ≈ 0 → 配合 corr_threshold=0.99 隔离 CB
    - 趋势过滤在 ~5 个崩盘日后转负排除风险资产，但前 4 天已积累 ~12% 回撤
      → drawdown_stop 在第 5 天检测到 halve 级别
    """
    rng = np.random.RandomState(seed)
    noise_level = 0.0003

    # 股票+黄金路径：大涨 → 闪崩 → 平稳
    risk_drift = np.zeros(n)
    risk_drift[:145] = 0.0012
    risk_drift[145:155] = -0.040
    risk_drift[155:] = 0.0003

    stock_r = risk_drift + rng.normal(0, noise_level, n)
    gold_r = risk_drift + rng.normal(0, noise_level, n)

    # 债券独立路径：不参与崩盘，日收益率与股票零相关
    bond_r = rng.normal(0.0003, 0.001, n)

    return {
        "沪深300": _make_ohlcv(_price_series(stock_r + rng.normal(0, 0.0002, n))),
        "创业板": _make_ohlcv(_price_series(stock_r + rng.normal(0, 0.0002, n))),
        "纳指": _make_ohlcv(_price_series(stock_r + rng.normal(0, 0.0002, n))),
        "黄金": _make_ohlcv(_price_series(gold_r)),
        "国债ETF": _make_ohlcv(_price_series(bond_r)),
    }


def _make_scan_prices(n=130, seed=77):
    """参数扫描用短数据：130 天上涨行情。"""
    rng = np.random.RandomState(seed)
    noise = rng.normal(0, 0.001, n)
    stock_r = np.full(n, 0.001) + noise
    bond_r = np.full(n, 0.0005) - noise

    return {
        "沪深300": _make_ohlcv(_price_series(stock_r + rng.normal(0, 0.0003, n))),
        "创业板": _make_ohlcv(_price_series(stock_r + rng.normal(0, 0.0003, n))),
        "纳指": _make_ohlcv(_price_series(stock_r + rng.normal(0, 0.0003, n))),
        "黄金": _make_ohlcv(_price_series(rng.normal(0.0003, 0.001, n))),
        "国债ETF": _make_ohlcv(_price_series(bond_r)),
    }


class TestBullMarket:
    """场景 1：全绿场景回测 — 单边上涨、股债负相关、无大幅回撤"""

    def test_bull_market(self):
        prices = _make_bull_prices(n=200)
        result = run_backtest(prices, initial_capital=1_000_000, min_days=120)

        assert result["final_nav"] > 1_000_000, (
            f"牛市应盈利，final_nav={result['final_nav']:.2f}"
        )
        assert result["total_return"] > 0, (
            f"牛市总收益应为正，实际 {result['total_return']:.4f}"
        )
        assert len(result["records_df"]) == 80, (
            f"200 天数据 min_days=120 应产生 80 条记录，实际 {len(result['records_df'])}"
        )
        assert result["max_drawdown"] > -0.05, (
            f"牛市回撤应 < 5%，实际 max_drawdown={result['max_drawdown']:.4f}"
        )
        # 基准也应上涨
        assert result["final_benchmark_nav"] > 1.0, (
            f"基准也应上涨，实际 benchmark_nav={result['final_benchmark_nav']:.4f}"
        )


class TestCrashStop:
    """场景 2：下跌市防线验证 — 先涨后暴跌，防线控制回撤在可控范围

    三层防线协同：趋势过滤排除崩盘资产 → CB 或趋势过滤限制仓位 →
    回撤控制在 30% 以内。回撤止损是最后手段——在日频连续崩盘中
    趋势过滤总在回撤达 8% 前先排除资产，因此回撤止损作为兜底存在。
    """

    def test_crash_defense_controls_drawdown(self):
        prices = _make_crash_prices(n=200)
        result = run_backtest(
            prices,
            initial_capital=1_000_000,
            min_days=120,
            params={"corr_threshold": 0.99},
        )

        records = result["records_df"]
        # 验证防线起作用：回撤控制在可接受范围
        assert result["max_drawdown"] > -0.30, (
            f"防线应控制回撤 < 30%，实际 max_drawdown={result['max_drawdown']:.4f}"
        )
        # 崩盘期应有防御响应：CB 触发 或 趋势过滤排除资产（defense_active 减少）
        cb_triggered = records["circuit_breaker_triggered"].any()
        active_counts = records["defense_active"].apply(
            lambda x: len(x.split(";")) if x else 0
        )
        assets_reduced = (active_counts < 5).any()
        assert cb_triggered or assets_reduced, (
            "崩盘场景应有防御响应（CB 或趋势过滤排除资产）"
        )


class TestParameterScan:
    """场景 3：参数扫描 — 2×1 网格，按 Sharpe 降序"""

    def test_parameter_scan(self):
        prices = _make_scan_prices(n=130)
        param_grid = {"trend_window": [60, 80]}
        results = parameter_scan(prices, param_grid, initial_capital=1_000_000, min_days=120)

        assert len(results) == 2, (
            f"2×1 网格应返回 2 条结果，实际 {len(results)}"
        )
        # 参数值不同
        assert results[0]["trend_window"] != results[1]["trend_window"], (
            "两条结果的 trend_window 应不同"
        )
        # 按 Sharpe 降序
        assert results[0]["sharpe_ratio"] >= results[1]["sharpe_ratio"], (
            f"应按 Sharpe 降序排列，实际 [{results[0]['sharpe_ratio']:.4f}, {results[1]['sharpe_ratio']:.4f}]"
        )
        # 每条结果包含绩效指标
        for key in ["final_nav", "total_return", "annual_return", "max_drawdown"]:
            assert key in results[0], f"结果应包含 {key}"
            assert key in results[1], f"结果应包含 {key}"


class TestThreeBenchmarks:
    """场景 4：run_backtest 返回三基准（沪深300/创业板/纳指买入持有）。"""

    def test_three_benchmarks(self):
        prices = _make_bull_prices(n=200)
        result = run_backtest(prices, initial_capital=1_000_000, min_days=120)

        for key in ["benchmark_300", "benchmark_chinext", "benchmark_nasdaq"]:
            assert key in result, f"返回值应包含 {key}"

        # 三基准应为 Series，起始值 1.0
        b300 = result["benchmark_300"]
        assert b300 is not None
        assert b300.iloc[0] == 1.0
        assert len(b300) == 200

        b_chinext = result["benchmark_chinext"]
        assert b_chinext is not None
        assert b_chinext.iloc[0] == 1.0

        b_nasdaq = result["benchmark_nasdaq"]
        assert b_nasdaq is not None
        assert b_nasdaq.iloc[0] == 1.0

        # 现有 benchmark_nav 不应被删除
        assert "benchmark_nav" in result


class TestRepoRateParam:
    """跨市场参数化 — repo_rate 影响 repo 利息计算"""

    def test_run_backtest_with_repo_rate(self):
        """repo_rate=0.04 → repo 利息按 4% 计算，高于默认 2%"""
        prices = _make_bull_prices(n=200)
        result_04 = run_backtest(prices, initial_capital=1_000_000, min_days=120,
                                 params={"repo_rate": 0.04})
        result_02 = run_backtest(prices, initial_capital=1_000_000, min_days=120,
                                 params={"repo_rate": 0.02})
        assert result_04["final_nav"] > result_02["final_nav"], (
            f"repo_rate=0.04 终值应 > 0.02，实际 {result_04['final_nav']:.2f} vs {result_02['final_nav']:.2f}"
        )


class TestUSDefenseNames:
    """跨市场参数化 — defense_names 传入 US 资产名"""

    def test_run_backtest_with_us_defense_names(self):
        """传入 defense_names=["SPY","QQQ","GLD","SHY","BIL"] → 不抛异常"""
        rng = np.random.RandomState(42)
        n = 200
        noise = rng.normal(0, 0.001, n)
        stock_r = np.full(n, 0.001) + noise
        bond_r = np.full(n, 0.0005) - noise

        prices = {
            "SPY": _make_ohlcv(_price_series(stock_r + rng.normal(0, 0.0003, n))),
            "QQQ": _make_ohlcv(_price_series(stock_r + rng.normal(0, 0.0003, n))),
            "GLD": _make_ohlcv(_price_series(rng.normal(0.0003, 0.001, n))),
            "SHY": _make_ohlcv(_price_series(bond_r)),
            "BIL": _make_ohlcv(_price_series(np.full(n, 0.0001))),
        }
        result = run_backtest(prices, initial_capital=1_000_000, min_days=120,
                              params={"defense_names": ["SPY", "QQQ", "GLD", "SHY", "BIL"]})

        for key in ["final_nav", "total_return", "annual_return", "sharpe_ratio", "max_drawdown"]:
            assert key in result, f"返回值应包含 {key}"
