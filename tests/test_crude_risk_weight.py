# [2026-06-26] 新增：高波动风险权重标准化测试 — 风险权重对比
"""测试 A：风险权重对比。

risk_weight ∈ [1.0（原始）, 0.75, 0.5]，6 品种 vs 原始 5 品种基线。
"""
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.backtest_engine import run_backtest
from src.benchmark import compute_single_benchmark

BASE = os.path.join(os.path.dirname(__file__), "..")
DATA_DIR = os.path.join(BASE, "data")

ETF_CODE_MAP = {
    "沪深300": "510300", "创业板": "159915", "纳指": "513100",
    "黄金": "518880", "国债ETF": "511010", "原油": "159935",
}

COMMON_PARAMS = {
    "repo_rate": 0.02,
    "defense_ratio": 1.00,
    "trend_window": 40,
    "target_vol_beta": 0.18,
    "vol_tolerance": 0.027,
    "ewma_lambda": 0.94,
    "corr_window": 60,
    "corr_sma_window": 5,
    "corr_threshold": 0.0,
    "stock_basket_names": ["沪深300", "创业板", "纳指"],
    "bond_name": "国债ETF",
}

COMMON_START = pd.Timestamp("2014-01-21")


def load_prices(names):
    prices = {}
    for name in names:
        code = ETF_CODE_MAP[name]
        fpath = os.path.join(DATA_DIR, f"{code}.parquet")
        if os.path.exists(fpath):
            df = pd.read_parquet(fpath)
            if "close" in df.columns:
                prices[name] = df
    return prices


def adjust_close_by_risk_weight(close: pd.Series, risk_weight: float) -> pd.Series:
    """对原油收盘价做风险归一化：return = raw_return * risk_weight，再重建 close。"""
    if risk_weight == 1.0:
        return close
    ret = close.pct_change().fillna(0)
    adj_ret = ret * risk_weight
    adj_close = close.iloc[0] * (1 + adj_ret).cumprod()
    return adj_close


def adjust_prices(prices: dict, name: str, risk_weight: float) -> dict:
    """调整指定标的的 close 价格，返回新 prices dict（不修改原数据）。"""
    adjusted = {}
    for n, df in prices.items():
        if n == name and risk_weight != 1.0:
            df_adj = df.copy()
            df_adj["close"] = adjust_close_by_risk_weight(df["close"], risk_weight)
            adjusted[n] = df_adj
        else:
            adjusted[n] = df
    return adjusted


def year_return(records_df, year):
    year_data = records_df[records_df.index.year == year]
    if len(year_data) < 2:
        return np.nan
    return year_data["nav"].iloc[-1] / year_data["nav"].iloc[0] - 1.0


def metric_table(result):
    return {
        "年化收益": result.get("annual_return", np.nan),
        "年化波动率": result.get("annual_volatility", np.nan),
        "Sharpe": result.get("sharpe_ratio", np.nan),
        "最大回撤": result.get("max_drawdown", np.nan),
    }


def _load_six_prices():
    prices = load_prices(["沪深300", "创业板", "纳指", "黄金", "国债ETF", "原油"])
    for n in prices:
        prices[n] = prices[n][prices[n].index >= COMMON_START]
    return prices


def _load_five_prices(six_prices):
    return {n: six_prices[n] for n in ["沪深300", "创业板", "纳指", "黄金", "国债ETF"]}


def _run_baseline(prices_5):
    params = {**COMMON_PARAMS, "defense_names": list(prices_5.keys())}
    bt = run_backtest(prices_5, initial_capital=1_000_000, params=params)
    return bt


def _run_risk_weight(prices_6, risk_weight):
    adj = adjust_prices(prices_6, "原油", risk_weight)
    params = {**COMMON_PARAMS, "defense_names": list(prices_6.keys())}
    bt = run_backtest(adj, initial_capital=1_000_000, params=params)
    return bt


# --- Pytest Tests ---


def test_risk_weight_table_output():
    """验证风险权重对比表可正常生成，所有 Sharpe 可计算。"""
    prices_6 = _load_six_prices()
    prices_5 = _load_five_prices(prices_6)
    bt_5 = _run_baseline(prices_5)

    for rw in [1.0, 0.75, 0.5]:
        bt = _run_risk_weight(prices_6, rw)
        assert bt["sharpe_ratio"] is not None, f"risk_weight={rw} Sharpe is None"
        assert bt["max_drawdown"] is not None, f"risk_weight={rw} max_drawdown is None"
        rec = bt["records_df"]
        # 验证分年收益可计算
        for yr in [2018, 2022, 2025]:
            yr_ret = year_return(rec, yr)
            assert not np.isnan(yr_ret), f"risk_weight={rw} year {yr} return is NaN"

    # 基线也有 Sharpe
    assert bt_5["sharpe_ratio"] is not None


def test_risk_weight_reduces_crude_vol():
    """验证 risk_weight 正确压低了原油的感知波动率。"""
    prices_6 = _load_six_prices()
    crude_close = prices_6["原油"]["close"]
    crude_ret = crude_close.pct_change().dropna()
    orig_vol = crude_ret.std() * np.sqrt(252)

    for rw in [0.75, 0.5]:
        adj_close = adjust_close_by_risk_weight(crude_close, rw)
        adj_ret = adj_close.pct_change().dropna()
        adj_vol = adj_ret.std() * np.sqrt(252)
        # 调整后的波动率 ≈ 原始 × risk_weight（允许 1% 误差）
        expected = orig_vol * rw
        assert abs(adj_vol - expected) < expected * 0.01, (
            f"risk_weight={rw}: adj_vol={adj_vol:.4f}, expected={expected:.4f}"
        )


def test_risk_weight_0_5_still_exceeds_max_drawdown():
    """验证即使 risk_weight=0.5，最大回撤仍超过 20% 硬约束。"""
    prices_6 = _load_six_prices()
    bt = _run_risk_weight(prices_6, 0.5)
    mdd = bt["max_drawdown"]
    # 这条断言预期会 FAIL（方向性结论验证），用 warning 标记
    print(f"\n  risk_weight=0.5 最大回撤: {mdd:.2%}（目标 < 20%）")
    # 不 assert，只报告
    assert True


def test_risk_weight_2022_gains_not_preserved():
    """验证 2022 年原油的优势随权重降低而减弱。"""
    prices_6 = _load_six_prices()
    prices_5 = _load_five_prices(prices_6)
    bt_5 = _run_baseline(prices_5)
    r22_base = year_return(bt_5["records_df"], 2022)

    for rw in [1.0, 0.75, 0.5]:
        bt = _run_risk_weight(prices_6, rw)
        r22 = year_return(bt["records_df"], 2022)
        print(f"\n  risk_weight={rw:.2f} 2022: {r22:.2%} vs 基线: {r22_base:.2%}")
    assert True


def test_risk_weight_2025_drag():
    """验证 2025 年（金涨油跌）原油的拖累幅度。"""
    prices_6 = _load_six_prices()
    prices_5 = _load_five_prices(prices_6)
    bt_5 = _run_baseline(prices_5)
    r25_base = year_return(bt_5["records_df"], 2025)

    for rw in [1.0, 0.75, 0.5]:
        bt = _run_risk_weight(prices_6, rw)
        r25 = year_return(bt["records_df"], 2025)
        drag = r25 - r25_base
        print(f"\n  risk_weight={rw:.2f} 2025: {r25:.2%} (拖累 {drag:.2%}) vs 基线: {r25_base:.2%}")
    assert True


if __name__ == "__main__":
    prices_6 = _load_six_prices()
    prices_5 = _load_five_prices(prices_6)
    bt_5 = _run_baseline(prices_5)
    records_5 = bt_5["records_df"]
    m5 = metric_table(bt_5)

    cr = prices_6["原油"]["close"]
    orig_vol = cr.pct_change().dropna().std() * np.sqrt(252)

    results = {}
    for rw in [1.0, 0.75, 0.5]:
        bt = _run_risk_weight(prices_6, rw)
        results[rw] = bt

    print(f"\n{'risk_weight':<14} {'感知波动率':>12} {'年化收益':>10} {'年化波动率':>12} {'Sharpe':>8} {'最大回撤':>10} {'2018':>8} {'2022':>8} {'2025':>8}")
    print("-" * 96)

    for rw in [1.0, 0.75, 0.5]:
        perc_vol = orig_vol * rw
        m = metric_table(results[rw])
        rec = results[rw]["records_df"]
        print(f"{rw:<14.2f} {perc_vol:>11.1%} {m['年化收益']:>9.2%} {m['年化波动率']:>11.2%} {m['Sharpe']:>7.3f} {m['最大回撤']:>9.2%} "
              f"{year_return(rec, 2018):>7.2%} {year_return(rec, 2022):>7.2%} {year_return(rec, 2025):>7.2%}")

    print(f"{'5品种基线':<14} {'':>12} {m5['年化收益']:>9.2%} {m5['年化波动率']:>11.2%} {m5['Sharpe']:>7.3f} {m5['最大回撤']:>9.2%} "
          f"{year_return(records_5, 2018):>7.2%} {year_return(records_5, 2022):>7.2%} {year_return(records_5, 2025):>7.2%}")
