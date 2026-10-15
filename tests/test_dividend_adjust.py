# [2026-10-15] 新增：分红再投复权模块测试
"""tests/test_dividend_adjust.py — 分红再投复权（后复权式）单元测试。

需求：给定原始 OHLCV 与除息表，产出「分红再投」等效价格序列，
使该序列的收益率等于含分红的真实收益率，且不回溯改写历史（后复权）。
"""
import numpy as np
import pandas as pd
import pytest

from src.dividend_adjust import adjust_prices_for_dividends


def _make_df(closes, start="2020-01-01"):
    idx = pd.bdate_range(start, periods=len(closes))
    return pd.DataFrame(
        {"open": closes, "high": closes, "low": closes, "close": closes,
         "volume": [1000.0] * len(closes)},
        index=idx,
    )


def _div_table(pairs):
    """pairs: [(日期字符串, 每股分红)]"""
    s = pd.Series({pd.Timestamp(d): float(v) for d, v in pairs}, name="dividend")
    s.index.name = "date"
    return s.to_frame()


# --- 基础路径 ---

def test_single_dividend_restores_true_return():
    """单次分红：复权后收益率 == (除息日收盘 + 分红)/前收 - 1"""
    df = _make_df([10.0, 10.0, 9.5, 9.5])          # 第 3 天除息跌 0.5
    div = _div_table([(df.index[2], 0.5)])
    out = adjust_prices_for_dividends(df, div)

    ret_adj = out["close"].iloc[2] / out["close"].iloc[1] - 1
    ret_true = (df["close"].iloc[2] + 0.5) / df["close"].iloc[1] - 1
    assert ret_adj == pytest.approx(ret_true, rel=1e-12)
    assert ret_adj == pytest.approx(0.0, abs=1e-12)   # 真实收益为 0


def test_factor_applies_forward_only():
    """后复权：除息日之前的价格不被改写"""
    df = _make_df([10.0, 10.0, 9.5, 9.5])
    div = _div_table([(df.index[2], 0.5)])
    out = adjust_prices_for_dividends(df, div)

    assert out["close"].iloc[0] == pytest.approx(10.0)
    assert out["close"].iloc[1] == pytest.approx(10.0)
    assert out["close"].iloc[2] > df["close"].iloc[2]  # 除息日起被上调


def test_multiple_dividends_compound():
    """多次分红：因子累乘"""
    df = _make_df([10.0, 9.0, 8.0, 7.0])
    div = _div_table([(df.index[1], 1.0), (df.index[2], 1.0)])
    out = adjust_prices_for_dividends(df, div)
    f1 = (9.0 + 1.0) / 9.0
    f2 = (8.0 + 1.0) / 8.0
    assert out["close"].iloc[3] == pytest.approx(7.0 * f1 * f2, rel=1e-12)


# --- 边界 ---

def test_empty_dividend_table_returns_identical():
    """空除息表：价格原样返回"""
    df = _make_df([10.0, 11.0, 12.0])
    out = adjust_prices_for_dividends(df, pd.DataFrame(columns=["dividend"]))
    pd.testing.assert_frame_equal(out, df)


def test_dividend_date_not_in_index_is_skipped():
    """除息日不在交易日 index 中：跳过，不抛异常"""
    df = _make_df([10.0, 10.0, 10.0])
    div = _div_table([("2019-06-01", 1.0)])   # 早于 index，不存在
    out = adjust_prices_for_dividends(df, div)
    pd.testing.assert_frame_equal(out, df)


def test_zero_dividend_is_noop():
    """分红为 0：因子为 1，价格不变"""
    df = _make_df([10.0, 10.0, 10.0])
    div = _div_table([(df.index[1], 0.0)])
    out = adjust_prices_for_dividends(df, div)
    pd.testing.assert_frame_equal(out, df)


# --- 异常 / 不变式 ---

def test_all_ohlc_columns_scaled_volume_untouched():
    """OHLC 同乘因子；volume 不参与复权"""
    df = _make_df([10.0, 10.0, 9.0])
    div = _div_table([(df.index[2], 1.0)])
    out = adjust_prices_for_dividends(df, div)
    for col in ["open", "high", "low", "close"]:
        assert out[col].iloc[2] == pytest.approx(df[col].iloc[2] * (9.0 + 1.0) / 9.0, rel=1e-12)
    pd.testing.assert_series_equal(out["volume"], df["volume"])


def test_shape_index_dtype_preserved():
    """长度 / index / 列 不变"""
    df = _make_df([10.0, 10.0, 9.0])
    div = _div_table([(df.index[2], 1.0)])
    out = adjust_prices_for_dividends(df, div)
    assert len(out) == len(df)
    assert out.index.equals(df.index)
    assert list(out.columns) == list(df.columns)
    assert not out.isna().any().any()
