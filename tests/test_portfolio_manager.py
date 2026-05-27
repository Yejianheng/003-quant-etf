# [2026-05-27] 新增：组合管理器测试 — 5 场景

import pytest
from src.portfolio_manager import allocate_capital


def _make_all_green_signal():
    """构造全绿信号：5 标的 active，无熔断，normal 止损，进攻层空。"""
    return {
        "date": "2024-06-01",
        "defense": {
            "trend_strengths": {
                "沪深300": 0.15,
                "创业板": 0.12,
                "纳指": 0.18,
                "黄金": 0.08,
                "国债ETF": 0.05,
            },
            "active": ["沪深300", "创业板", "纳指", "黄金", "国债ETF"],
            "target_weights": {
                "沪深300": 0.2,
                "创业板": 0.2,
                "纳指": 0.2,
                "黄金": 0.2,
                "国债ETF": 0.2,
            },
            "scaling_factor": 1.0,
        },
        "offense": {
            "rankings": [],
            "target_weights": {},
        },
        "circuit_breaker": {
            "triggered": False,
            "smoothed_corr": -0.35,
        },
        "drawdown_stop": {
            "level": "normal",
            "position_multiplier": 1.0,
            "drawdown": -0.02,
        },
        "execution": {
            "final_multiplier": 1.0,
            "funds_to_repo": False,
        },
    }


def _make_offense_signal():
    """进攻层持仓信号：5 防御标的 + 3 进攻标的等权。"""
    signal = _make_all_green_signal()
    signal["offense"] = {
        "rankings": [
            {"name": "半导体", "score": 2.5},
            {"name": "新能源", "score": 2.1},
            {"name": "医药", "score": 1.8},
        ],
        "target_weights": {
            "半导体": 1 / 3,
            "新能源": 1 / 3,
            "医药": 1 / 3,
        },
    }
    return signal


def _make_circuit_breaker_signal():
    """熔断信号。"""
    signal = _make_all_green_signal()
    signal["circuit_breaker"]["triggered"] = True
    signal["circuit_breaker"]["smoothed_corr"] = 0.25
    signal["execution"]["funds_to_repo"] = True
    signal["execution"]["final_multiplier"] = 0.0
    return signal


def _make_halve_signal():
    """回撤减半信号：level=halve, multiplier=0.5。"""
    signal = _make_all_green_signal()
    signal["drawdown_stop"]["level"] = "halve"
    signal["drawdown_stop"]["position_multiplier"] = 0.5
    signal["drawdown_stop"]["drawdown"] = -0.15
    signal["execution"]["final_multiplier"] = 0.5
    return signal


class TestAllGreenNormal:
    """场景 1：全绿正常分配 — defense 全 active，offense 空 → repo=30%"""

    def test_all_green_normal(self):
        signal = _make_all_green_signal()
        result = allocate_capital(signal, 1_000_000)

        assert result["total_capital"] == 1_000_000
        assert result["defense_total"] == pytest.approx(700_000, rel=1e-6)
        assert result["offense_total"] == 0.0
        assert result["repo_amount"] == pytest.approx(300_000, rel=1e-6)
        assert result["exposure"] == pytest.approx(700_000, rel=1e-6)
        assert result["exposure_ratio"] == pytest.approx(0.70, rel=1e-6)
        for name in ["沪深300", "创业板", "纳指", "黄金", "国债ETF"]:
            assert result["positions"][name] == pytest.approx(140_000, rel=1e-6), (
                f"{name} 应分配 140,000，实际 {result['positions'][name]}"
            )


class TestOffenseActive:
    """场景 2：进攻层持仓 — 3 标的等权，defense/offense 各 70/30"""

    def test_offense_active(self):
        signal = _make_offense_signal()
        result = allocate_capital(signal, 1_000_000)

        assert result["defense_total"] == pytest.approx(700_000, rel=1e-6)
        assert result["offense_total"] == pytest.approx(300_000, rel=1e-6)
        assert result["positions"]["半导体"] == pytest.approx(100_000, rel=1e-6)
        assert result["positions"]["新能源"] == pytest.approx(100_000, rel=1e-6)
        assert result["positions"]["医药"] == pytest.approx(100_000, rel=1e-6)
        for name in ["沪深300", "创业板", "纳指", "黄金", "国债ETF"]:
            assert result["positions"][name] == pytest.approx(140_000, rel=1e-6)
        assert result["repo_amount"] == pytest.approx(0.0, abs=1e-6)
        assert result["exposure"] == pytest.approx(1_000_000, rel=1e-6)
        assert result["exposure_ratio"] == pytest.approx(1.0, rel=1e-6)


class TestCircuitBreaker:
    """场景 3：熔断全进逆回购 — positions 空，repo = 全部资金"""

    def test_circuit_breaker(self):
        signal = _make_circuit_breaker_signal()
        result = allocate_capital(signal, 1_000_000)

        assert result["positions"] == {}
        assert result["repo_amount"] == pytest.approx(1_000_000, rel=1e-6)
        assert result["exposure"] == 0.0
        assert result["exposure_ratio"] == 0.0
        assert result["defense_total"] == 0.0
        assert result["offense_total"] == 0.0


class TestDrawdownHalve:
    """场景 4：回撤减半 — multiplier=0.5，defense 砍半 + offense 空 → repo=65%"""

    def test_drawdown_halve(self):
        signal = _make_halve_signal()
        result = allocate_capital(signal, 1_000_000)

        assert result["defense_total"] == pytest.approx(350_000, rel=1e-6)
        assert result["offense_total"] == 0.0
        assert result["repo_amount"] == pytest.approx(650_000, rel=1e-6)
        for name in ["沪深300", "创业板", "纳指", "黄金", "国债ETF"]:
            assert result["positions"][name] == pytest.approx(70_000, rel=1e-6)
        assert result["exposure"] == pytest.approx(350_000, rel=1e-6)
        assert result["exposure_ratio"] == pytest.approx(0.35, rel=1e-6)


class TestOffenseEmptyNoReflow:
    """场景 5：进攻层空仓不回流 — 最关键测试"""

    def test_offense_empty_no_reflow(self):
        signal = _make_all_green_signal()
        result = allocate_capital(signal, 1_000_000)

        assert result["offense_total"] == 0.0
        assert result["defense_total"] == pytest.approx(700_000, rel=1e-6)
        # defense_total 不得回流为 1,000,000
        assert result["defense_total"] != pytest.approx(1_000_000, rel=1e-6), (
            "进攻层空仓时 defense_total 不应回流为 1,000,000"
        )
        assert result["repo_amount"] == pytest.approx(300_000, rel=1e-6)
        assert result["exposure_ratio"] == pytest.approx(0.70, rel=1e-6)
