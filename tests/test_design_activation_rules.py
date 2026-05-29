# [2026-05-29] 新增：步骤3 测试 — 条件性激活规则设计

import os
import sys
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from scripts.design_activation_rules import (
    find_best_threshold,
    evaluate_rule,
)


class TestFindBestThreshold:
    def test_perfect_separation(self):
        """完全可分 → 精度 1.0 (用 lt: 低值为 outperform)"""
        feature = pd.Series([0.1, 0.2, 0.3, 0.7, 0.8, 0.9])
        labels = pd.Series(["outperform", "outperform", "outperform",
                            "underperform", "underperform", "underperform"])
        result = find_best_threshold(feature, labels, direction="lt")
        assert result["best_accuracy"] > 0.8

    def test_random_no_separation(self):
        """随机数据 → 精度接近 0.5"""
        np.random.seed(42)
        feature = pd.Series(np.random.randn(100))
        labels = pd.Series(["outperform"] * 50 + ["underperform"] * 50)
        result = find_best_threshold(feature, labels, direction="gt")
        assert result["best_accuracy"] < 0.75

    def test_lt_direction(self):
        """反向规则：特征值越低越可能是 outperform"""
        feature = pd.Series([0.1, 0.2, 0.3, 0.7, 0.8, 0.9])
        labels = pd.Series(["outperform", "outperform", "outperform",
                            "underperform", "underperform", "underperform"])
        result = find_best_threshold(feature, labels, direction="lt")
        assert result["best_accuracy"] > 0.8


class TestEvaluateRule:
    def test_and_combination(self):
        feature_map = {
            "trend": pd.Series([0.02, 0.01, -0.01, -0.02, 0.03, -0.03]),
            "vol": pd.Series([0.15, 0.18, 0.22, 0.25, 0.12, 0.20]),
        }
        labels = pd.Series([
            "outperform", "outperform", "underperform", "underperform",
            "outperform", "underperform",
        ])
        rule = {"trend": (">", 0.0), "vol": ("<", 0.20)}
        result = evaluate_rule(feature_map, labels, rule)

        # 检查前两个满足条件 → 应该正确分类
        assert result["accuracy"] > 0.5
        assert "coverage" in result
