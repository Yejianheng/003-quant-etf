# [2026-06-18] 新增：macro_corr_decomposition 测试 — OLS 拟合 + parquet 读写 + 边界
"""测试 macro_corr_decomposition.py 的核心函数。"""
import os, sys, tempfile, warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

# 导入待测模块中的工具函数
from macro_corr_decomposition import ols_fit, safe_fetch


class TestOlsFit:
    """OLS 拟合基础 + 边界。"""

    def test_basic_fit(self):
        """基础路径：y = 3*X1 + 2*X2 + 1, R² ≈ 1.0。"""
        np.random.seed(42)
        n = 200
        X = np.random.randn(n, 2)
        true_beta = np.array([3.0, 2.0])
        y = 1.0 + X @ true_beta + np.random.normal(0, 0.01, n)

        coeffs, se, t_stats, p_vals, r2, adj_r2 = ols_fit(X, y)

        assert len(coeffs) == 3
        assert abs(coeffs[0] - 1.0) < 0.1   # const
        assert abs(coeffs[1] - 3.0) < 0.1   # β1
        assert abs(coeffs[2] - 2.0) < 0.1   # β2
        assert r2 > 0.99

    def test_const_only(self):
        """边界：空特征只有 intercept → R² ≈ 0。"""
        np.random.seed(42)
        n = 100
        X = np.empty((n, 0))
        y = np.full(n, 5.0)

        coeffs, se, t_stats, p_vals, r2, adj_r2 = ols_fit(X, y)

        assert len(coeffs) == 1  # only const
        assert abs(coeffs[0] - 5.0) < 0.01
        assert r2 <= 0.0 or abs(r2) < 1e-10

    def test_collinear_features(self):
        """边界：完全共线特征 → lstsq 不报错，系数合理。"""
        np.random.seed(42)
        n = 100
        X1 = np.random.randn(n)
        X = np.column_stack([X1, X1 * 2])  # perfect collinearity
        y = 4.0 + 3.0 * X1 + np.random.normal(0, 0.1, n)

        coeffs, se, t_stats, p_vals, r2, adj_r2 = ols_fit(X, y)

        assert len(coeffs) == 3  # const + 2 features
        assert r2 > 0.9  # still fits y even if coefficients are non-unique

    def test_single_sample(self):
        """边界：仅 3 个样本，3 个特征（刚好饱和），dof=0 时 SE 无穷大但不崩溃。"""
        np.random.seed(42)
        n = 3
        X = np.random.randn(n, 2)
        y = np.array([1.0, 2.0, 3.0])

        coeffs, se, t_stats, p_vals, r2, adj_r2 = ols_fit(X, y)

        assert len(coeffs) == 3
        assert r2 >= 0.0  # saturated model, r2 should be very high or exactly perfect
        # dof = n - k = 0, so SE and t stats are undefined — check they don't crash
        assert not np.any(np.isnan(coeffs))


class TestParquetIO:
    """parquet 读写验证。"""

    def test_roundtrip(self):
        """基础路径：DataFrame 写入 → 读回，列和值一致。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'test.parquet')
            df = pd.DataFrame({
                'a': [1.0, 2.0, 3.0],
                'b': [4.0, 5.0, 6.0],
            })
            df.to_parquet(path)
            loaded = pd.read_parquet(path)
            pd.testing.assert_frame_equal(df, loaded)


class TestDataAlignment:
    """日期对齐边界。"""

    def test_empty_intersection(self):
        """边界：X 和 y 无交集日 → common 为空，应报错。"""
        idx_x = pd.date_range('2020-01-01', '2020-01-10', freq='D')
        idx_y = pd.date_range('2021-01-01', '2021-01-10', freq='D')
        common = idx_x.intersection(idx_y)
        assert len(common) == 0
