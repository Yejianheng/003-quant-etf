# [2026-06-18] 新增：美股版策略等效回测 — 跨市场验证
"""
美股版策略等效回测：用美股资产复刻 A 股 v0.18-release 策略，
验证逻辑跨市场成立。核心参数原封搬运，唯一变化 repo_rate 2%→4%。

用法：python scripts/backtest_us.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd

from src.backtest_engine import run_backtest
from src.signal_generator import generate_signal
from src.benchmark import compute_single_benchmark, compute_benchmark
from src.recorder import get_records_df

# v0.18-release 核心参数（原封搬运）
US_PARAMS = {
    "target_vol_beta": 0.18,
    "vol_tolerance": 0.027,
    "trend_window": 40,
    "ewma_lambda": 0.94,
    "corr_window": 60,
    "corr_sma_window": 5,
    "corr_threshold": 0.0,
    "defense_ratio": 1.00,
}

# 美股资产池
US_DEFENSE_NAMES = ["SPY", "QQQ", "GLD", "SHY", "BIL"]
US_STOCK_BASKET = ["SPY", "QQQ"]
US_TICKERS = ["SPY", "QQQ", "GLD", "SHY", "IEF", "TLT", "BIL"]


def fetch_us_data(tickers, start="2005-01-01", end="2026-06-18"):
    """拉取美股 ETF 历史数据（AKShare → 新浪财经美股）。

    tickers: ETF 代码列表。
    start/end: 日期范围（YYYY-MM-DD 格式）。
    返回: {ticker: DataFrame[open, high, low, close, volume]}，index=DatetimeIndex。
    """
    import time
    import akshare as ak

    result = {}
    start_int = start.replace("-", "")
    end_int = end.replace("-", "")

    for ticker in tickers:
        for attempt in range(3):
            try:
                df = ak.stock_us_daily(symbol=ticker, adjust="qfq")
                if df is not None and len(df) > 0:
                    break
            except Exception as e:
                if attempt < 2:
                    time.sleep(2 ** attempt)
                else:
                    print(f"  [{ticker}] 拉取失败: {e}")
                    df = None

        if df is None or len(df) == 0:
            continue

        # 统一处理：确保 index 为 DatetimeIndex
        if not isinstance(df.index, pd.DatetimeIndex):
            if "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date")
        # 删除可能的 date 列（AKShare 有时保留）
        if "date" in df.columns:
            df = df.drop(columns=["date"])

        # 列名归一化
        df = df.rename(columns={
            "open": "open", "high": "high", "low": "low",
            "close": "close", "volume": "volume",
        })
        cols = ["open", "high", "low", "close", "volume"]
        available = [c for c in cols if c in df.columns]
        df = df[available].sort_index()

        # 按日期范围截断
        mask = (df.index >= start) & (df.index <= end)
        df = df.loc[mask]

        # 过滤前复权异常负价（累积分红修正过度，多见于 2009 年）
        if "close" in df.columns:
            df = df[df["close"] > 0]

        if len(df) > 0:
            result[ticker] = df
            print(f"  [{ticker}] {df.index[0].date()} ~ {df.index[-1].date()} ({len(df)} 天)")

        # 频率限制：每个 ticker 间隔 2 秒
        time.sleep(2)

    # BIL 补齐：如果没有 BIL 数据，用 SPY 日期 index 生成年化 4% 合成现金曲线
    if "BIL" not in result and "SPY" in result:
        spy_idx = result["SPY"].index
        bil_close = 100 * np.exp(np.cumsum(np.full(len(spy_idx), 0.04 / 252)))
        result["BIL"] = pd.DataFrame({
            "open": bil_close, "high": bil_close,
            "low": bil_close, "close": bil_close,
            "volume": np.zeros(len(spy_idx)),
        }, index=spy_idx)
        print(f"  [BIL] 合成现金曲线 ({len(spy_idx)} 天, 年化 4%)")

    return result


def align_dates_union(prices):
    """不同长度 DataFrame → 并集日期对齐。

    对齐到所有 ETF 日期的并集，缺失日期前向填充。
    返回: 对齐后的 prices dict（各 DataFrame index 统一为并集日期）。
    """
    # 收集所有日期索引的并集
    all_dates = sorted(set().union(*[set(df.index) for df in prices.values()]))
    if not all_dates:
        return prices

    union_idx = pd.DatetimeIndex(all_dates)
    aligned = {}
    for name, df in prices.items():
        # reindex 到并集日期，前向填充缺失值
        df_aligned = df.reindex(union_idx, method="ffill")
        aligned[name] = df_aligned
    return aligned


def run_us_backtest(prices, bond_ticker, repo_rate=0.04):
    """对给定债券久期跑一次全量美股回测。

    prices: {ticker: OHLCV DataFrame}。
    bond_ticker: 债券 ETF 代号（SHY/IEF/TLT）。
    repo_rate: 现金利率（美元默认 4%）。

    返回: run_backtest 结果 dict。
    """
    params = {
        **US_PARAMS,
        "defense_names": ["SPY", "QQQ", "GLD", bond_ticker, "BIL"],
        "stock_basket_names": US_STOCK_BASKET,
        "bond_name": bond_ticker,
        "repo_rate": repo_rate,
        "benchmark_specs": {
            "SPY": None,
            "QQQ": None,
            "6040": {"SPY": 0.60, bond_ticker: 0.40},
        },
    }
    return run_backtest(prices, params=params, execution_lag=1)


def _compute_metrics_from_result(result):
    """从 run_backtest 结果提取标量绩效指标。"""
    return {
        "total_return": result.get("total_return", 0),
        "annual_return": result.get("annual_return", 0),
        "annual_volatility": result.get("annual_volatility", 0),
        "sharpe_ratio": result.get("sharpe_ratio", 0),
        "max_drawdown": result.get("max_drawdown", 0),
        "calmar_ratio": result.get("calmar_ratio", 0),
    }


def compare_bond_durations(prices):
    """久期对比：SHY/IEF/TLT 三档各自跑回测。

    返回: DataFrame，行=久期档位，列=年化/波动率/Sharpe/回撤/熔断%。
    """
    rows = []
    for bond in ["SHY", "IEF", "TLT"]:
        if bond not in prices:
            rows.append({"bond": bond, "annual_return": None, "annual_volatility": None,
                         "sharpe_ratio": None, "max_drawdown": None})
            continue
        result = run_us_backtest(prices, bond)
        metrics = _compute_metrics_from_result(result)
        # 熔断触发占比
        records = result["records_df"]
        cb_ratio = records["circuit_breaker_triggered"].mean() if len(records) > 0 else 0
        rows.append({
            "bond": bond,
            "annual_return": metrics["annual_return"],
            "annual_volatility": metrics["annual_volatility"],
            "sharpe_ratio": metrics["sharpe_ratio"],
            "max_drawdown": metrics["max_drawdown"],
            "cb_trigger_ratio": cb_ratio,
        })
    return pd.DataFrame(rows)


def generate_comparison_table(result):
    """美股对照表：策略 vs SPY/QQQ/60-40/等权。

    返回: DataFrame，列=指标名，行=各标的/策略。
    """
    metrics = _compute_metrics_from_result(result)
    records = result["records_df"]

    # 提取基准净值
    rows = [{"label": "美股策略", **metrics}]

    # SPY benchmark
    if "benchmark_SPY" in result and result["benchmark_SPY"] is not None:
        spy_nav = result["benchmark_SPY"]
        spy_metrics = _benchmark_metrics(spy_nav)
        rows.append({"label": "SPY", **spy_metrics})

    # QQQ benchmark
    if "benchmark_QQQ" in result and result["benchmark_QQQ"] is not None:
        qqq_nav = result["benchmark_QQQ"]
        qqq_metrics = _benchmark_metrics(qqq_nav)
        rows.append({"label": "QQQ", **qqq_metrics})

    # 60/40 benchmark
    if "benchmark_6040" in result and result["benchmark_6040"] is not None:
        b6040_nav = result["benchmark_6040"]
        b6040_metrics = _benchmark_metrics(b6040_nav)
        rows.append({"label": "60/40", **b6040_metrics})

    # 等权组合
    if "benchmark_nav" in result and result["benchmark_nav"] is not None:
        ew_nav = result["benchmark_nav"]
        ew_metrics = _benchmark_metrics(ew_nav)
        rows.append({"label": "等权", **ew_metrics})

    df = pd.DataFrame(rows).set_index("label")
    # 转置为 | 指标 | 策略 | SPY | QQQ | 60/40 | 等权 |
    return df.T


def _benchmark_metrics(nav_series):
    """从净值 Series 计算绩效指标。"""
    if nav_series is None or len(nav_series) < 2:
        return {"total_return": 0, "annual_return": 0, "annual_volatility": 0,
                "sharpe_ratio": 0, "max_drawdown": 0}
    returns = nav_series.pct_change().dropna()
    n = len(returns)
    total = (nav_series.iloc[-1] / nav_series.iloc[0]) - 1
    ann = (nav_series.iloc[-1] / nav_series.iloc[0]) ** (252 / n) - 1
    vol = float(np.std(returns, ddof=1) * np.sqrt(252))
    sharpe = ann / vol if vol > 0 else 0.0
    running_max = nav_series.expanding().max()
    dd = (nav_series - running_max) / running_max
    max_dd = float(dd.min())
    return {
        "total_return": total,
        "annual_return": ann,
        "annual_volatility": vol,
        "sharpe_ratio": sharpe,
        "max_drawdown": max_dd,
    }


def generate_cross_market_table(us_prices, cn_prices):
    """A 股版 vs 美股版全期绩效对照。

    us_prices: 美股价格（含 SHY）。
    cn_prices: A 股价格（沪深300/创业板/纳指/黄金/国债ETF）。

    返回: DataFrame，列=CN/US/Δ，行=绩效指标。
    """
    # CN 原始回测（默认参数）
    cn_result = run_backtest(cn_prices, params={"execution_lag": 1}, execution_lag=1)
    cn_metrics = _compute_metrics_from_result(cn_result)

    # US 回测（默认 SHY）
    us_result = run_us_backtest(us_prices, "SHY")
    us_metrics = _compute_metrics_from_result(us_result)

    rows = []
    for key in ["total_return", "annual_return", "annual_volatility", "sharpe_ratio", "max_drawdown"]:
        cn_val = cn_metrics.get(key, 0) or 0
        us_val = us_metrics.get(key, 0) or 0
        delta = us_val - cn_val
        rows.append({"metric": key, "A股(CN)": cn_val, "美股(US)": us_val, "Δ": delta})

    return pd.DataFrame(rows).set_index("metric")


def run_2008_stress_test(prices):
    """2008 年压力测试：策略回撤 vs SPY 回撤。

    返回: dict {strategy_max_dd, spy_max_dd}。
    """
    result = run_us_backtest(prices, "SHY")
    strategy_dd = result.get("max_drawdown", 0)

    # SPY 买入持有回撤
    spy_nav = None
    if "benchmark_SPY" in result:
        spy_nav = result["benchmark_SPY"]
    elif "SPY" in prices:
        close = prices["SPY"]["close"]
        spy_nav = close / close.iloc[0]

    if spy_nav is not None:
        running_max = spy_nav.expanding().max()
        spy_dd = float(((spy_nav - running_max) / running_max).min())
    else:
        spy_dd = 0.0

    return {"strategy_max_dd": strategy_dd, "spy_max_dd": spy_dd}


def main():
    """入口：拉取数据 → 久期对比 → 全期对照 → A/B 对照 → 2008 专项 → 输出 CSV。"""
    import argparse

    parser = argparse.ArgumentParser(description="美股版策略等效回测")
    parser.add_argument("--start", default="2005-01-01")
    parser.add_argument("--end", default="2026-06-18")
    parser.add_argument("--output", default="output")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    # 1. 拉取数据
    print("=" * 60)
    print("美股版策略等效回测 — 跨市场验证")
    print("=" * 60)
    print(f"\n[1/5] 拉取美股数据 ({args.start} ~ {args.end})...")
    prices = fetch_us_data(US_TICKERS, start=args.start, end=args.end)
    print(f"  获取 ETF: {list(prices.keys())}")

    # 打印各 ETF 日期范围
    for name, df in prices.items():
        print(f"  {name}: {df.index[0].date()} ~ {df.index[-1].date()} ({len(df)} 天)")

    # 2. 久期对比
    print(f"\n[2/5] 久期对比 (SHY/IEF/TLT)...")
    bond_df = compare_bond_durations(prices)
    print(bond_df.to_string())
    bond_df.to_csv(os.path.join(args.output, "us_bond_duration_comparison.csv"))

    # 选最优久期
    valid = bond_df.dropna(subset=["sharpe_ratio"])
    if len(valid) > 0:
        best_bond = valid.loc[valid["sharpe_ratio"].idxmax(), "bond"]
    else:
        best_bond = "SHY"
    print(f"  最优久期: {best_bond}")

    # 3. 全期对照表（最优久期）
    print(f"\n[3/5] 全期回测 (bond={best_bond})...")
    result = run_us_backtest(prices, best_bond)
    metrics = _compute_metrics_from_result(result)
    print(f"  年化: {metrics['annual_return']:.2%}  Sharpe: {metrics['sharpe_ratio']:.2f}  回撤: {metrics['max_drawdown']:.2%}")

    comp_df = generate_comparison_table(result)
    print("\n美股对照表:")
    print(comp_df.to_string())
    comp_df.to_csv(os.path.join(args.output, f"us_comparison_{best_bond}.csv"))

    # 4. A/B 对照表（用模拟数据占位 — 需 CN 数据时用 data_pipeline 拉取）
    print(f"\n[4/5] A/B 对照（需 CN 数据，当前仅输出 US 侧）...")
    print("  (A 股对照需运行 src/data_pipeline.py 拉取 CN 数据)")

    # 5. 2008 压力测试
    print(f"\n[5/5] 2008 压力测试...")
    stress = run_2008_stress_test(prices)
    print(f"  策略回撤: {stress['strategy_max_dd']:.2%}  SPY 回撤: {stress['spy_max_dd']:.2%}")

    print(f"\n{'=' * 60}")
    print("完成。输出文件:")
    print(f"  {args.output}/us_bond_duration_comparison.csv")
    print(f"  {args.output}/us_comparison_{best_bond}.csv")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
