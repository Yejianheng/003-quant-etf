# [2026-05-29] 修改：修正回测起始日（≥防御全部就位）+ 清盘恢复机制（repo 利息 + 状态追踪）
# [2026-05-29] 修改：run_backtest 日期从交集改为并集 + 动态 ETF 接入 + union_dates/get_available_etfs
# [2026-05-28] 修改：run_backtest 传递 defense_ratio；parameter_scan 支持 checkpoint 持久化
# [2026-05-27] 新增：回测引擎 — 日循环驱动 + 参数扫描入口

import csv
import itertools
import os
import numpy as np
import pandas as pd

from src.signal_generator import DEFENSE_NAMES, generate_signal
from src.portfolio_manager import allocate_capital
from src.recorder import init_recorder, record_daily, get_records_df
from src.benchmark import compute_benchmark, compute_single_benchmark

REPO_ANNUAL_RATE = 0.02


def union_dates(prices: dict[str, pd.DataFrame]) -> pd.DatetimeIndex:
    """返回所有 ETF 日期 index 的并集（非交集），按升序排列。"""
    date_sets = [set(df.index) for df in prices.values() if len(df) > 0]
    if not date_sets:
        return pd.DatetimeIndex([])
    all_dates = sorted(set.union(*date_sets))
    return pd.DatetimeIndex(all_dates)


def get_available_etfs(
    prices: dict[str, pd.DataFrame],
    date: pd.Timestamp,
    min_history: int = 120,
) -> list[str]:
    """返回指定日期有数据且历史 ≥ min_history 的 ETF 名称列表。"""
    available = []
    for name, df in prices.items():
        if len(df) == 0:
            continue
        if date not in df.index:
            continue
        # 该 ETF 在 date 之前（含）的数据天数
        hist = (df.index <= date).sum()
        if hist >= min_history:
            available.append(name)
    return available


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
    # 1. 日期范围：所有标的 index 的并集（动态 ETF 接入）
    dates = union_dates(prices)

    # 1b. 截断到防御 ETF 全部就位之后
    defense_starts = []
    for name in DEFENSE_NAMES:
        if name in prices and len(prices[name]) > 0:
            defense_starts.append(prices[name].index.min())
    if defense_starts:
        defense_start = max(defense_starts)
        dates = dates[dates >= defense_start]

    if len(dates) <= min_days:
        raise ValueError(
            f"防御全就位后交易日不足：需要 > {min_days} 天，实际 {len(dates)} 天"
        )

    # 2. 初始状态
    nav = float(initial_capital)
    positions: dict[str, float] = {}
    repo_cash = float(initial_capital)
    recorder = init_recorder()
    # 清盘恢复状态追踪
    prev_drawdown_level = "normal"
    liquidation_nav: float | None = None

    nav_values = np.full(len(dates), float(initial_capital))
    nav_series = pd.Series(nav_values, index=dates, dtype=float)

    # 3. 日循环
    for t in range(min_days, len(dates)):
        today = dates[t]

        # repo 现金日利息（年化 2% / 252）
        repo_cash *= (1.0 + REPO_ANNUAL_RATE / 252.0)

        # 估值：昨日持仓按今日收盘价重估
        if positions:
            nav = sum(
                positions.get(name, 0.0) * prices[name].loc[today, "close"]
                for name in positions
                if name in prices and today in prices[name].index
            )
            nav += repo_cash

        # 更新 nav_series
        nav_series.iloc[t] = nav

        # 动态 ETF 接入：只传入当日有数据且满足 min_history 的 ETF
        available_names = get_available_etfs(prices, today, min_history=min_days)
        visible_prices = {name: prices[name].loc[:today] for name in available_names}
        signal = generate_signal(visible_prices, nav_series.iloc[: t + 1], params)
        defense_ratio = (params or {}).get("defense_ratio", 0.70)

        # 清盘恢复机制：持续监控 drawdown，回到 halve 阈值以下则恢复
        current_level = signal["drawdown_stop"]["level"]
        current_dd = signal["drawdown_stop"]["drawdown"]
        if prev_drawdown_level == "liquidate":
            if current_level != "liquidate":
                # drawdown 已自然回落到 halve/warning/normal → 恢复
                pass  # signal 已包含正确的 level/multiplier
            elif liquidation_nav is not None and current_dd > -0.12:
                # repo 利息让 nav 回升，drawdown 已 < 12% → 强制恢复 halve
                signal["drawdown_stop"]["level"] = "halve"
                signal["drawdown_stop"]["position_multiplier"] = 0.5
                signal["execution"]["final_multiplier"] = min(
                    signal["defense"]["scaling_factor"], 0.5
                )
                signal["execution"]["funds_to_repo"] = False
        if current_level == "liquidate" and prev_drawdown_level != "liquidate":
            liquidation_nav = nav
        prev_drawdown_level = current_level

        alloc = allocate_capital(signal, nav, defense_ratio=defense_ratio)

        # 调仓：目标金额 → 股数（今日收盘价成交）
        positions = {}
        for name, target_dollar in alloc["positions"].items():
            if name not in prices or today not in prices[name].index:
                continue
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
