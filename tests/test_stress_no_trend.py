# [2026-05-30] 修改：新增 seed 独立性、target_dates、同组相关性测试
# [2026-05-30] 新增：stress_no_trend.py 测试
import os
import sys
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.stress_no_trend import generate_synthetic_sideways


def _make_real_prices(n_days: int = 504) -> pd.DataFrame:
    """构造类真实价格的 OHLC DataFrame。"""
    np.random.seed(42)
    dates = pd.date_range("2022-01-01", periods=n_days, freq="B")
    close = 100 * (1 + np.random.randn(n_days).cumsum() * 0.012).reshape(-1)
    # 确保全为正
    close = close - close.min() + 50
    df = pd.DataFrame({
        "open": close * 0.99,
        "high": close * 1.02,
        "low": close * 0.98,
        "close": close,
    }, index=dates)
    return df


class TestGenerateSyntheticSideways:
    """合成零趋势价格路径。"""

    def test_returns_dataframe_with_ohlc(self):
        """返回 DataFrame 含 OHLC 列。"""
        real = _make_real_prices(504)
        synth = generate_synthetic_sideways(real, seed=42)
        assert isinstance(synth, pd.DataFrame)
        for col in ["open", "high", "low", "close"]:
            assert col in synth.columns, f"缺少列 {col}"

    def test_same_number_of_rows(self):
        """合成数据行数与输入一致。"""
        real = _make_real_prices(504)
        synth = generate_synthetic_sideways(real, seed=42)
        assert len(synth) == len(real)

    def test_near_zero_cumulative_return(self):
        """合成路径累计收益接近零。"""
        real = _make_real_prices(504)
        synth = generate_synthetic_sideways(real, seed=42)
        total_return = synth["close"].iloc[-1] / synth["close"].iloc[0] - 1
        assert abs(total_return) < 0.05, f"累计收益 {total_return:.2%} 超出 ±5%"

    def test_prices_all_positive(self):
        """合成价格全部为正。"""
        real = _make_real_prices(504)
        synth = generate_synthetic_sideways(real, seed=42)
        assert (synth["close"] > 0).all()

    def test_short_input_does_not_crash(self):
        """输入仅 20 行不崩溃。"""
        real = _make_real_prices(20)
        synth = generate_synthetic_sideways(real, seed=42)
        assert len(synth) == 20

    def test_nan_input_raises(self):
        """输入含 NaN 抛出 ValueError。"""
        real = _make_real_prices(100)
        real.iloc[50, 3] = np.nan  # close 列含 NaN
        with pytest.raises(ValueError, match="NaN"):
            generate_synthetic_sideways(real, seed=42)

    # ---- 新增：seed 独立性与 target_dates ----

    def test_different_seeds_low_correlation(self):
        """不同 seed 生成的路径相关性应显著低于同 seed。"""
        real = _make_real_prices(504)
        s1 = generate_synthetic_sideways(real, seed=42)
        s2 = generate_synthetic_sideways(real, seed=99)
        r1 = s1["close"].pct_change().dropna()
        r2 = s2["close"].pct_change().dropna()
        corr_diff = np.corrcoef(r1, r2)[0, 1]
        # 不同 seed 应产生低相关路径
        assert abs(corr_diff) < 0.5, f"不同 seed 相关性 {corr_diff:.3f} 应 < 0.5"

    def test_same_seed_reproducible(self):
        """同 seed 同输入产生完全相同的路径。"""
        real = _make_real_prices(504)
        s1 = generate_synthetic_sideways(real, seed=42)
        s2 = generate_synthetic_sideways(real, seed=42)
        pd.testing.assert_frame_equal(s1, s2)

    def test_target_dates_controls_index(self):
        """传入 target_dates 时，输出 index 与之匹配。"""
        real = _make_real_prices(504)
        target = pd.bdate_range("2025-01-02", periods=504)
        synth = generate_synthetic_sideways(real, seed=42, target_dates=target)
        assert len(synth) == 504
        assert synth.index[0] == target[0]
        assert synth.index[-1] == target[-1]
