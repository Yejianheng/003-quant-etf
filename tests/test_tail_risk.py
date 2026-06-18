# [2026-06-18] 新增：尾部审计模块测试
import pytest
import numpy as np
import pandas as pd
from attribution.tail_risk import tail_risk_audit


def _make_returns(seed, n, crash_day=None):
    """构造日收益序列，可选 crash_day 插入暴跌"""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2020-01-02", periods=n, freq="B")
    rets = rng.normal(0.0005, 0.012, n)

    if crash_day is not None and crash_day < n:
        rets[crash_day] = -0.08

    return pd.Series(rets, index=dates)


class TestTailRiskAudit:
    def test_normal_distribution_skew_near_zero(self):
        """正态分布 → 偏度接近零"""
        rets = _make_returns(42, 500)
        result = tail_risk_audit(rets)
        assert abs(result["skewness"]) < 0.5

    def test_crash_creates_negative_skew(self):
        """单日暴跌 → 负偏度"""
        rets = _make_returns(42, 500, crash_day=200)
        result = tail_risk_audit(rets)
        assert result["skewness"] < -0.3

    def test_worst_months_count(self):
        """最差月列表恰好 5 个"""
        rets = _make_returns(42, 500)
        result = tail_risk_audit(rets)
        assert len(result["worst_5_months"]) == 5

    def test_max_drawdown_duration_positive(self):
        """最大回撤持续天数为正"""
        rets = _make_returns(42, 500, crash_day=200)
        result = tail_risk_audit(rets)
        assert result["max_dd_duration_days"] > 0

    def test_insurance_sell_detection(self):
        """小赚大赔 → 卖保险警告"""
        rng = np.random.default_rng(1)
        dates = pd.date_range("2020-01-02", periods=500, freq="B")
        rets = rng.normal(0.001, 0.005, 500)
        rets[300] = -0.15
        rets = pd.Series(rets, index=dates)

        result = tail_risk_audit(rets)
        assert result["skewness"] < 0
        assert result["insurance_sell_warning"] is True


class TestBoundary:
    def test_empty_returns(self):
        rets = pd.Series([], dtype=float)
        result = tail_risk_audit(rets)
        assert np.isnan(result["skewness"])

    def test_always_positive(self):
        """全程正收益 → 偏度可算"""
        dates = pd.date_range("2020-01-02", periods=200, freq="B")
        rets = pd.Series(np.full(200, 0.001), index=dates)
        result = tail_risk_audit(rets)
        assert result["max_drawdown"] == pytest.approx(0.0, abs=1e-9)
