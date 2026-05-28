# [2026-05-28] 修改：run_backtest 传递 defense_ratio；parameter_scan 支持 checkpoint 持久化
# [2026-05-27] 新增：回测引擎 — 日循环驱动 + 参数扫描入口

import csv
import itertools
import os
import numpy as np
import pandas as pd

from src.signal_generator import generate_signal
from src.portfolio_manager import allocate_capital
from src.recorder import init_recorder, record_daily, get_records_df
from src.benchmark import compute_benchmark, compute_single_benchmark


def run_backtest(
    prices: dict[str, pd.DataFrame],
    initial_capital: float = 1_000_000,
    params: dict | None = None,
    min_days: int = 120,
) -> dict:
    """运行完整回测。

    prices: {标的名: OHLCV DataFrame}，所有 DataFrame 需对齐到同一日期范围。
    initial_capital: 初始资金。
    params: 传给 generate_signal 的参数。
    min_days: 最少需要的数据天数（trend_window + corr_window + sma_window 缓冲）。

    返回绩效指标 dict，含 records_df 和 benchmark_nav。
    """
    # 1. 日期范围：所有标的 index 的交集
    date_sets = [set(df.index) for df in prices.values()]
    common_dates = sorted(set.intersection(*date_sets))
    dates = pd.DatetimeIndex(common_dates)

    if len(dates) <= min_days:
        raise ValueError(
            f"共同交易日不足：需要 > {min_days} 天，实际 {len(dates)} 天"
        )

    # 2. 初始状态
    nav = float(initial_capital)
    positions: dict[str, float] = {}
    repo_cash = float(initial_capital)
    recorder = init_recorder()

    nav_values = np.full(len(dates), float(initial_capital))
    nav_series = pd.Series(nav_values, index=dates, dtype=float)

    # 3. 日循环
    for t in range(min_days, len(dates)):
        today = dates[t]

        # 估值：昨日持仓按今日收盘价重估
        if positions:
            nav = sum(
                positions.get(name, 0.0) * prices[name].loc[today, "close"]
                for name in positions
            )
            nav += repo_cash

        # 更新 nav_series
        nav_series.iloc[t] = nav

        # 可见数据 + 信号 + 分配
        visible_prices = {name: df.loc[:today] for name, df in prices.items()}
        signal = generate_signal(visible_prices, nav_series.iloc[: t + 1], params)
        defense_ratio = (params or {}).get("defense_ratio", 0.70)
        alloc = allocate_capital(signal, nav, defense_ratio=defense_ratio)

        # 调仓：目标金额 → 股数（今日收盘价成交）
        positions = {}
        for name, target_dollar in alloc["positions"].items():
            price = prices[name].loc[today, "close"]
            if price > 0:
                positions[name] = target_dollar / price
        repo_cash = alloc["repo_amount"]

        # 日记录
        record_daily(
            recorder, str(today.date()), nav, signal, alloc["positions"]
        )

    # 4. 绩效指标
    records_df = get_records_df(recorder)
    final_nav = float(records_df["nav"].iloc[-1]) if len(records_df) > 0 else float(initial_capital)
    total_return = (final_nav - initial_capital) / initial_capital

    # 日收益率 → 年化指标
    daily_nav = records_df["nav"].values
    daily_returns = np.diff(daily_nav) / daily_nav[:-1]
    n_trading_days = len(records_df)

    if n_trading_days >= 2:
        annual_return = (final_nav / initial_capital) ** (252 / n_trading_days) - 1
        annual_volatility = float(np.std(daily_returns, ddof=1) * np.sqrt(252))
        sharpe_ratio = annual_return / annual_volatility if annual_volatility > 0 else 0.0
    else:
        annual_return = 0.0
        annual_volatility = 0.0
        sharpe_ratio = 0.0

    # 回撤
    running_max = np.maximum.accumulate(daily_nav)
    drawdowns = (daily_nav - running_max) / running_max
    max_drawdown = float(np.min(drawdowns)) if len(drawdowns) > 0 else 0.0

    calmar_ratio = annual_return / abs(max_drawdown) if abs(max_drawdown) > 0 else 0.0

    # 5. 基准
    benchmark_nav = compute_benchmark(prices)
    final_benchmark_nav = float(benchmark_nav.iloc[-1])
    benchmark_return = final_benchmark_nav - 1.0

    benchmark_300 = compute_single_benchmark(prices, "沪深300")
    benchmark_chinext = compute_single_benchmark(prices, "创业板")
    benchmark_nasdaq = compute_single_benchmark(prices, "纳指")

    return {
        "records_df": records_df,
        "benchmark_nav": benchmark_nav,
        "benchmark_300": benchmark_300,
        "benchmark_chinext": benchmark_chinext,
        "benchmark_nasdaq": benchmark_nasdaq,
        "final_nav": final_nav,
        "final_benchmark_nav": final_benchmark_nav,
        "total_return": total_return,
        "benchmark_return": benchmark_return,
        "annual_return": annual_return,
        "annual_volatility": annual_volatility,
        "sharpe_ratio": sharpe_ratio,
        "max_drawdown": max_drawdown,
        "calmar_ratio": calmar_ratio,
    }


def parameter_scan(
    prices: dict[str, pd.DataFrame],
    param_grid: dict[str, list],
    initial_capital: float = 1_000_000,
    min_days: int = 120,
    checkpoint_path: str | None = None,
) -> list[dict]:
    """参数扫描入口。

    param_grid: {"trend_window": [40, 60, 80], "target_vol_beta": [0.08, 0.10, 0.12], ...}
    checkpoint_path: 可选 CSV 路径，每完成一个组合追加写入，支持断点续扫。

    对每个参数组合调用 run_backtest，返回按 Sharpe 降序排列的结果列表。
    每个元素 = {**params_combo, **绩效指标}（不含 records_df / benchmark_nav）。
    """
    keys = list(param_grid.keys())
    value_lists = list(param_grid.values())
    combinations = list(itertools.product(*value_lists))

    # 断点续扫：读取已完成组合
    completed: set[tuple] = set()
    if checkpoint_path and os.path.exists(checkpoint_path):
        with open(checkpoint_path, "r", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                completed.add(tuple(row[k] for k in keys))

    results: list[dict] = []
    header_written = bool(completed)  # 已有文件 → 表头已存在
    for combo in combinations:
        params = dict(zip(keys, combo))
        # 跳过已完成组合
        if checkpoint_path:
            param_tuple = tuple(str(params[k]) for k in keys)
            if param_tuple in completed:
                continue

        bt = run_backtest(
            prices,
            initial_capital=initial_capital,
            params=params,
            min_days=min_days,
        )
        scalar_metrics = {
            k: v
            for k, v in bt.items()
            if k not in ("records_df", "benchmark_nav")
        }
        results.append({**params, **scalar_metrics})

        # checkpoint 写入
        if checkpoint_path:
            row = {**{k: str(v) for k, v in params.items()}, **scalar_metrics}
            os.makedirs(os.path.dirname(checkpoint_path) or ".", exist_ok=True)
            mode = "a" if header_written else "w"
            with open(checkpoint_path, mode, newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(row.keys()))
                if not header_written:
                    writer.writeheader()
                    header_written = True
                writer.writerow(row)

    # 合并内存结果与 checkpoint 已有数据用于排序
    if checkpoint_path and os.path.exists(checkpoint_path):
        with open(checkpoint_path, "r", newline="") as f:
            all_rows = list(csv.DictReader(f))
        all_results = []
        for row in all_rows:
            entry = {}
            for k, v in row.items():
                try:
                    entry[k] = float(v)
                except (ValueError, TypeError):
                    entry[k] = v
            all_results.append(entry)
        all_results.sort(key=lambda r: float(r.get("sharpe_ratio", 0)), reverse=True)
        return all_results

    results.sort(key=lambda r: r["sharpe_ratio"], reverse=True)
    return results
