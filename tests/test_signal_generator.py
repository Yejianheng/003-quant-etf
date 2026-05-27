# [2026-05-27] 新增：信号生成器测试 — 4 场景

import numpy as np
import pandas as pd
import pytest
from src.signal_generator import generate_signal


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


def _make_all_rising_prices(n=120, seed=42):
    """全绿场景：全部上涨，股债负相关。"""
    rng = np.random.RandomState(seed)
    noise = rng.normal(0, 0.001, n)
    # 股票篮子：正漂移 + 共享噪声
    stock_r = np.full(n, 0.001) + noise
    # 债券：正漂移 - 共享噪声 → 与股票负相关
    bond_r = np.full(n, 0.0005) - noise

    return {
        "沪深300": _make_ohlcv(_price_series(stock_r + rng.normal(0, 0.0002, n))),
        "创业板": _make_ohlcv(_price_series(stock_r + rng.normal(0, 0.0002, n))),
        "纳指": _make_ohlcv(_price_series(stock_r + rng.normal(0, 0.0002, n))),
        "黄金": _make_ohlcv(_price_series(rng.normal(0.0005, 0.001, n))),
        "国债ETF": _make_ohlcv(_price_series(bond_r)),
    }


def _make_rising_portfolio(n=120):
    """单调上涨组合净值，无回撤。"""
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    return pd.Series(np.linspace(1.0, 1.15, n), index=dates, name="nav")


class TestAllGreen:
    """场景 1：全绿正常信号 — 全部单边上涨、无回撤、股债负相关"""

    def test_all_green(self):
        prices = _make_all_rising_prices()
        pv = _make_rising_portfolio()
        signal = generate_signal(prices, pv)

        # defense.active 含全部 5 只标的
        assert len(signal["defense"]["active"]) == 5, (
            f"全部上涨时应 5 只全 active，实际 {signal['defense']['active']}"
        )
        for name in ["沪深300", "创业板", "纳指", "黄金", "国债ETF"]:
            assert name in signal["defense"]["active"], f"{name} 应在 active 中"

        # 熔断未触发
        assert signal["circuit_breaker"]["triggered"] is False, (
            f"负相关不应触发熔断，smoothed_corr={signal['circuit_breaker']['smoothed_corr']:.4f}"
        )

        # 回撤 normal
        assert signal["drawdown_stop"]["level"] == "normal", (
            f"无回撤应为 normal，实际 {signal['drawdown_stop']['level']}"
        )

        # final_multiplier > 0
        assert signal["execution"]["final_multiplier"] > 0, (
            f"全绿时 final_multiplier 应 > 0，实际 {signal['execution']['final_multiplier']}"
        )

        # 进攻层空
        assert signal["offense"]["rankings"] == []
        assert signal["offense"]["target_weights"] == {}


class TestTrendFiltering:
    """场景 2：趋势过滤排除 — 沪深300 下跌，其余上涨"""

    def test_trend_filter_excludes_falling_asset(self):
        rng = np.random.RandomState(99)
        n = 120
        # 沪深300 下跌
        hs300_r = np.full(n, -0.001) + rng.normal(0, 0.001, n)
        # 其余上涨
        stock_noise = rng.normal(0, 0.001, n)
        stock_r = np.full(n, 0.001) + stock_noise
        bond_r = np.full(n, 0.0005) - stock_noise

        prices = {
            "沪深300": _make_ohlcv(_price_series(hs300_r)),
            "创业板": _make_ohlcv(_price_series(stock_r)),
            "纳指": _make_ohlcv(_price_series(stock_r + rng.normal(0, 0.0002, n))),
            "黄金": _make_ohlcv(_price_series(rng.normal(0.0005, 0.001, n))),
            "国债ETF": _make_ohlcv(_price_series(bond_r)),
        }
        pv = _make_rising_portfolio(n)
        signal = generate_signal(prices, pv)

        assert "沪深300" not in signal["defense"]["active"], (
            f"沪深300 下跌应被排除，active={signal['defense']['active']}"
        )
        assert len(signal["defense"]["active"]) == 4, (
            f"应剩余 4 只 active，实际 {len(signal['defense']['active'])}"
        )


class TestCircuitBreakerCovers:
    """场景 3：熔断覆盖 — 股债正相关 → funds_to_repo, final_multiplier=0"""

    def test_circuit_breaker_triggered(self):
        rng = np.random.RandomState(42)
        n = 120
        noise = rng.normal(0, 0.001, n)
        # 股票和债券共享同一噪声 → 正相关
        r = np.full(n, 0.001) + noise

        prices = {
            "沪深300": _make_ohlcv(_price_series(r + rng.normal(0, 0.0002, n))),
            "创业板": _make_ohlcv(_price_series(r + rng.normal(0, 0.0002, n))),
            "纳指": _make_ohlcv(_price_series(r + rng.normal(0, 0.0002, n))),
            "黄金": _make_ohlcv(_price_series(rng.normal(0.0005, 0.001, n))),
            "国债ETF": _make_ohlcv(_price_series(r)),
        }
        pv = _make_rising_portfolio(n)
        signal = generate_signal(prices, pv)

        assert signal["circuit_breaker"]["triggered"] is True, (
            f"正相关应触发熔断，smoothed_corr={signal['circuit_breaker']['smoothed_corr']:.4f}"
        )
        assert signal["execution"]["funds_to_repo"] is True, (
            "熔断时 funds_to_repo 应为 True"
        )
        assert signal["execution"]["final_multiplier"] == 0.0, (
            f"熔断时 final_multiplier 应为 0，实际 {signal['execution']['final_multiplier']}"
        )


class TestDrawdownStopCovers:
    """场景 4：回撤止损覆盖 — 组合净值回撤 20% → liquidate, final_multiplier=0"""

    def test_drawdown_liquidate(self):
        prices = _make_all_rising_prices()
        n = 120
        dates = pd.date_range("2024-01-01", periods=n, freq="B")
        # 先涨到 1.1，再跌到 0.88（从峰值回撤 20%）
        values = np.ones(n)
        values[:60] = np.linspace(1.0, 1.1, 60)
        values[60:] = np.linspace(1.1, 0.88, 60)
        pv = pd.Series(values, index=dates, name="nav")

        signal = generate_signal(prices, pv)

        assert signal["drawdown_stop"]["level"] == "liquidate", (
            f"回撤 20% 应为 liquidate，实际 {signal['drawdown_stop']['level']}"
        )
        assert signal["drawdown_stop"]["position_multiplier"] == 0.0, (
            f"liquidate 时 position_multiplier 应为 0，实际 {signal['drawdown_stop']['position_multiplier']}"
        )
        assert signal["execution"]["final_multiplier"] == 0.0, (
            f"liquidate 时 final_multiplier 应为 0，实际 {signal['execution']['final_multiplier']}"
        )
