# [2026-06-18] 修改：fetch_us_data 三级 fallback（东财→新浪→Stooq）+ FRED 金价条件修复
# [2026-06-18] 修改：fetch_us_data 重写 — AKShare(东方财富) + FRED 债券合成
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
import pandas_datareader.data as web

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


# FRED → 债券合成参数
BOND_SYNTH_CONFIG = {
    "SHY": {"fred_series": "DGS2",  "duration": 2.0},
    "IEF": {"fred_series": "DGS10", "duration": 8.0},
    "TLT": {"fred_series": "DGS30", "duration": 17.0},
}


def _fetch_fred_bond(start, end):
    """从 FRED 拉取国债收益率 → 合成 3 只债券 ETF 日线 OHLCV。
    返回: {ticker: DataFrame[open, high, low, close, volume]}
    """
    # 拉取所有需要的 FRED 序列（一次 API 调用支持多个 series）
    series_ids = ["DGS2", "DGS10", "DGS30", "TB3MS"]
    raw = web.DataReader(series_ids, "fred", start, end)
    # raw: DataFrame, columns=DGS2/DGS10/DGS30/TB3MS, index=DatetimeIndex
    raw = raw.ffill()  # 前向填充周末/假期

    result = {}

    # 合成债券 ETF
    for ticker, cfg in BOND_SYNTH_CONFIG.items():
        yields = raw[cfg["fred_series"]].dropna()
        if len(yields) < 2:
            continue
        dur = cfg["duration"]
        dy = yields.diff()           # Δyield (百分点)
        carry = yields / 100 / 252   # 日 carry
        price_ret = -dur * dy / 100  # 久期近似: ΔP/P ≈ -D × Δy
        daily_ret = (price_ret + carry).fillna(carry)  # 首日无 Δy，仅 carry
        nav = (1 + daily_ret).cumprod()
        nav = nav * 100 / nav.iloc[0]  # 起始价 100

        result[ticker] = pd.DataFrame({
            "open":  nav * 0.999,
            "high":  nav * 1.001,
            "low":   nav * 0.998,
            "close": nav,
            "volume": np.full(len(nav), 1e6),
        }, index=nav.index)

    # 合成 BIL（T-Bill，纯 carry）
    tbill = raw["TB3MS"].dropna()
    if len(tbill) > 1:
        daily_ret = (tbill / 100) / 252
        nav = (1 + daily_ret).cumprod()
        nav = nav * 100 / nav.iloc[0]
        result["BIL"] = pd.DataFrame({
            "open":  nav * 0.999,
            "high":  nav * 1.001,
            "low":   nav * 0.998,
            "close": nav,
            "volume": np.full(len(nav), 1e6),
        }, index=nav.index)

    return result


def _fetch_stooq(ticker, start, end):
    """Stooq 数据源（pandas_datareader），免费无 key，美股 ETF 历史可到 1990s。
    返回: DataFrame[open, high, low, close, volume] 或 None。
    """
    try:
        df = web.DataReader(f"{ticker}.US", "stooq", start=start, end=end)
        if df is None or len(df) == 0:
            return None
        df = df.rename(columns={
            "Open": "open", "High": "high", "Low": "low",
            "Close": "close", "Volume": "volume",
        })
        df.index.name = "date"
        df = df.sort_index()
        # Stooq 返回降序，转为升序
        return df
    except Exception:
        return None


def _fetch_akshare_etf(ticker, start, end):
    """拉取美股 ETF 日线。
    优先级: 东方财富 → 新浪 → Stooq（pandas_datareader）
    """
    import akshare as ak
    import time

    df = None

    # 1. 东方财富（数据最早：SPY 1993, QQQ 1999, GLD 2004）
    for attempt in range(2):
        try:
            df = ak.stock_us_hist(
                symbol=ticker, period="daily",
                start_date=start.replace("-", ""),
                end_date=end.replace("-", ""),
                adjust="qfq",
            )
            if df is not None and len(df) > 0:
                df = df.rename(columns={
                    "日期": "date", "开盘": "open", "最高": "high",
                    "最低": "low", "收盘": "close", "成交量": "volume",
                })
                break
        except Exception:
            if attempt < 1:
                time.sleep(2)
            else:
                df = None

    # 2. 东方财富失败 → 新浪
    if df is None or len(df) == 0:
        for attempt in range(3):
            try:
                df = ak.stock_us_daily(symbol=ticker, adjust="qfq")
                if df is not None and len(df) > 0:
                    break
            except Exception as e:
                if attempt < 2:
                    time.sleep(2 ** attempt)
                else:
                    df = None

    # 3. 新浪数据起始检查 → Stooq 补齐更早数据
    if df is not None and len(df) > 0:
        # 统一 index
        if not isinstance(df.index, pd.DatetimeIndex):
            if "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date")
        if "date" in df.columns:
            df = df.drop(columns=["date"])
        data_start = df.index.min()
        desired_start = pd.Timestamp(start)
        if data_start > desired_start + pd.DateOffset(years=1):
            print(f"    [{ticker}] 新浪起始 {data_start.date()}，尝试 Stooq 补齐更早数据")
            df_stooq = _fetch_stooq(ticker, start, str(data_start.date()))
            if df_stooq is not None and len(df_stooq) > 0:
                # 拼接: Stooq(早期) + Sina(近期)
                df = pd.concat([df_stooq, df]).sort_index()
    elif df is None or len(df) == 0:
        # 新浪完全失败 → Stooq 独自撑
        print(f"    [{ticker}] 新浪不可用，回退 Stooq")
        df = _fetch_stooq(ticker, start, end)

    if df is None or len(df) == 0:
        raise RuntimeError(f"{ticker} 所有数据源均失败")

    # 列标准化 + 截断 + 清洗
    cols = ["open", "high", "low", "close", "volume"]
    available = [c for c in cols if c in df.columns]
    df = df[available].sort_index()

    mask = (df.index >= start) & (df.index <= end)
    df = df.loc[mask]

    # 过滤前复权异常负价（新浪美股有 2009 年负价段）
    if "close" in df.columns:
        df = df[df["close"] > 0]
    # 异常日过滤：单日涨跌 > 50% → 剔除（新浪美股 2002-2003/2008-2009 多段异常）
    for _ in range(3):
        ret = df["close"].pct_change()
        bad = (ret.abs() > 0.50)
        if not bad.any():
            break
        df = df[~bad.reindex(df.index, fill_value=False)]
    # 绝对价格底线：前复权后不应跌破该值（新浪 qfq 累积误差导致 2002-2003 SPY 假跌至 $2-20）
    price_floors = {"SPY": 30.0, "QQQ": 15.0, "GLD": 30.0}
    floor = price_floors.get(ticker, 0)
    if floor > 0 and "close" in df.columns:
        df = df[df["close"] >= floor]

    return df


def _fetch_gold_fred(start, end):
    """FRED 伦敦金价 → 伪 GLD ETF 日线（2004 年前填充用）。"""
    gold = web.DataReader("GOLDAMGBD228NLBR", "fred", start, end)
    gold = gold.ffill().dropna()
    gold.columns = ["close"]
    nav = gold["close"]
    return pd.DataFrame({
        "open":  nav * 0.999,
        "high":  nav * 1.005,
        "low":   nav * 0.995,
        "close": nav,
        "volume": np.full(len(nav), 1e6),
    }, index=nav.index)


def fetch_us_data(tickers, start="1996-01-01", end="2026-06-18"):
    """拉取美股 ETF 历史数据（AKShare + FRED 混合）。

    - SPY/QQQ/GLD: AKShare 东方财富（真实 ETF）
    - SHY/IEF/TLT/BIL: FRED 国债收益率合成
    - GLD 2004 年前缺口: FRED 伦敦金价填充
    """
    result = {}

    # 1. AKShare 拉取股票 ETF
    for ticker in ["SPY", "QQQ", "GLD"]:
        if ticker not in tickers:
            continue
        try:
            df = _fetch_akshare_etf(ticker, start, end)
            if len(df) > 0:
                result[ticker] = df
        except Exception as e:
            print(f"  [{ticker}] AKShare 失败: {e}")

    # 2. GLD 数据起始晚于请求起始 → FRED 金价填充缺口
    if "GLD" in result:
        gld_start = result["GLD"].index[0]
        requested_start = pd.Timestamp(start)
        if gld_start > requested_start:
            try:
                gold_fred = _fetch_gold_fred(start, str(gld_start.date()))
                # 拼接: FRED 金价 + GLD ETF
                gold_fred_close = gold_fred["close"]
                # 对齐单位：GLD 起点 ~44，FRED 金价 ~400，等比缩放
                ratio = result["GLD"]["close"].iloc[0] / gold_fred_close.iloc[-1]
                gold_fred_scaled = gold_fred * ratio
                result["GLD"] = pd.concat([gold_fred_scaled, result["GLD"]]).sort_index()
            except Exception:
                pass  # FRED 失败不阻塞

    # 3. FRED 债券合成
    try:
        bonds = _fetch_fred_bond(start, end)
        for ticker in ["SHY", "IEF", "TLT", "BIL"]:
            if ticker in bonds and ticker in tickers:
                result[ticker] = bonds[ticker]
    except Exception as e:
        print(f"  FRED 债券合成失败: {e}")

    # 4. 债券日期对齐：FRED ffill 会填充周末/假日，截断到股票交易日
    stock_dates = set()
    for t in ["SPY", "QQQ", "GLD"]:
        if t in result:
            stock_dates.update(result[t].index)
    if stock_dates:
        for t in ["SHY", "IEF", "TLT", "BIL"]:
            if t in result:
                df = result[t]
                result[t] = df[df.index.isin(stock_dates)]

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
    aligned = align_dates_union(prices)
    return run_backtest(aligned, params=params, execution_lag=1)

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
    parser.add_argument("--start", default="1996-01-01")
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
