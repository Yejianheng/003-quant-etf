# [2026-06-22] 修复：T+1 模式 record_daily 传入 exec_alloc["positions"]
# [2026-06-18] 修改：参数化 repo_rate/defense_names/benchmark_specs，支持跨市场回测 @claude-override-approved
# [2026-06-18] 修改：新增 slippage_bps_map per-ETF 价差参数 + benchmark_6040 返回值
# [2026-05-30] 修复：parameter_scan scalar_metrics 排除 _recorder/benchmark_* 序列，避免 CSV 字段超限
# [2026-05-30] 修复：repo_cash 改为残差计算（现金守恒）+ 首日直接执行避免空仓期 — T+1 现金泄漏
# [2026-05-30] 新增：execution_lag 参数（0=当日成交，1=T+1成交）— Look-Ahead Bias 验证
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

REPO_ANNUAL_RATE_DEFAULT = 0.02


def union_dates(prices: dict[str, pd.DataFrame], min_etf_count: int | None = None) -> pd.DatetimeIndex:
    """返回所有 ETF 日期 index 的并集（非交集），按升序排列。

    min_etf_count: 若指定，只保留至少 min_etf_count 只 ETF 有数据的交易日。
    """
    date_sets = [set(df.index) for df in prices.values() if len(df) > 0]
    if not date_sets:
        return pd.DatetimeIndex([])
    all_dates = sorted(set.union(*date_sets))
    if min_etf_count is not None and min_etf_count > 1:
        filtered = []
        for d in all_dates:
            count = sum(1 for ds in date_sets if d in ds)
            if count >= min_etf_count:
                filtered.append(d)
        return pd.DatetimeIndex(filtered)
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


# @claude-override-approved
def run_backtest(
    prices: dict[str, pd.DataFrame],
    initial_capital: float = 1_000_000,
    params: dict | None = None,
    min_days: int = 120,
    execution_lag: int = 0,
    slippage_bps: float = 0.0,
    commission_rate: float = 0.0,
    slippage_bps_map: dict[str, float] | None = None,
    min_active_etfs: int = 1,
) -> dict:
    """运行完整回测。

    prices: {标的名: OHLCV DataFrame}，所有 DataFrame 需对齐到同一日期范围。
    initial_capital: 初始资金。
    params: 传给 generate_signal 的参数。
    min_days: 最少需要的数据天数（trend_window + corr_window + sma_window 缓冲）。
    execution_lag: 0=信号当日成交（当前），1=T+1成交（修正 Look-Ahead Bias）。
    slippage_bps: 双边滑点（bp），买入 close*(1+s/10000)，卖出 close*(1-s/10000)。
    commission_rate: 佣金费率（如 0.00025 = 万2.5），按换手额收取。
    slippage_bps_map: per-ETF 双边滑点（bp），优先于 slippage_bps。不传则所有 ETF 使用 slippage_bps。
    min_active_etfs: 交易日最少需要的 ETF 数量，低于此数则跳过当日。默认 1。

    返回绩效指标 dict，含 records_df 和 benchmark_nav。
    """
    # 1. 日期范围：所有标的 index 的并集（动态 ETF 接入）
    dates = union_dates(prices)
    p = params or {}
    repo_rate = p.get("repo_rate", REPO_ANNUAL_RATE_DEFAULT)
    defense_names = p.get("defense_names", DEFENSE_NAMES)

    # 1b. 截断到防御 ETF 全部就位之后
    defense_starts = []
    for name in defense_names:
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
    # T+1 执行：存储上一日的 alloc，当日执行
    pending_alloc: dict | None = None

    nav_values = np.full(len(dates), float(initial_capital))
    nav_series = pd.Series(nav_values, index=dates, dtype=float)

    # 3. 日循环
    for t in range(min_days, len(dates)):
        today = dates[t]

        # repo 现金日利息（年化 repo_rate / 252）
        repo_cash *= (1.0 + repo_rate / 252.0)

        # 动态 ETF 接入：只传入当日有数据且满足 min_history 的 ETF
        available_names = get_available_etfs(prices, today, min_history=min_days)

        # 不完整交易日保护：可用 ETF 不足 → 跳过估值与调仓，NAV 保持前值
        if len(available_names) < min_active_etfs:
            nav_series.iloc[t] = nav
            record_daily(
                recorder, str(today.date()), nav,
                {"execution": {"final_multiplier": 0.0},
                 "defense": {"active": [], "scaling_factor": 0.0, "predicted_vol": 0.0},
                 "offense": {"rankings": []},
                 "circuit_breaker": {"triggered": False},
                 "drawdown_stop": {"level": "normal", "drawdown": 0.0, "position_multiplier": 1.0}},
                {},
                positions_detail={},
            )
            continue

        # execution_lag=1：先执行(open)→再估值(close)→再信号
        # execution_lag=0：原逻辑 估值(close)→信号→执行(close)
        if execution_lag == 1 and pending_alloc is not None:
            # === 执行：pending_alloc 以开盘价成交 ===
            exec_alloc = pending_alloc
            prev_positions = positions.copy()
            positions = {}
            total_commission = 0.0
            old_value_open = sum(
                prev_positions.get(n, 0.0) * prices[n].loc[today, "open"]
                for n in prev_positions
                if n in prices and today in prices[n].index
            )
            total_at_open = old_value_open + repo_cash
            # [2026-07-14] 修复：隔夜跳空导致 total_at_open < nav 时，按比例缩放目标金额避免负现金
            scale_factor = total_at_open / exec_alloc["total_capital"] if exec_alloc.get("total_capital", 0) > 0 else 0.0

            for name, target_dollar in exec_alloc["positions"].items():
                scaled_target = target_dollar * scale_factor
                if name not in prices or today not in prices[name].index:
                    continue
                price_open = prices[name].loc[today, "open"]
                if price_open <= 0:
                    continue
                per_slippage = (slippage_bps_map or {}).get(name, slippage_bps)
                current_value = prev_positions.get(name, 0.0) * price_open
                exec_price = price_open * (1.0 + per_slippage / 10000.0) if scaled_target > current_value else price_open * (1.0 - per_slippage / 10000.0)
                positions[name] = scaled_target / exec_price
                total_commission += abs(scaled_target - current_value) * commission_rate
            # 现金守恒：总可支配资金 - 新持仓开盘市值 - 佣金
            new_target_sum = sum(
                d * scale_factor for n, d in exec_alloc["positions"].items()
                if n in prices and today in prices[n].index
            )
            repo_cash = total_at_open - new_target_sum - total_commission

            # === 估值：新持仓以收盘价重估 ===
            nav = sum(
                positions.get(n, 0.0) * prices[n].loc[today, "close"]
                for n in positions if n in prices and today in prices[n].index
            ) + repo_cash

        else:
            # execution_lag=1 首日（pending_alloc=None）或 execution_lag=0
            # 统一：先估值→再信号→再执行
            if positions:
                nav = sum(
                    positions.get(n, 0.0) * prices[n].loc[today, "close"]
                    for n in positions if n in prices and today in prices[n].index
                ) + repo_cash

        # 更新 nav_series
        nav_series.iloc[t] = nav

        visible_prices = {name: prices[name].loc[:today] for name in available_names}
        signal = generate_signal(visible_prices, nav_series.iloc[: t + 1], params)
        defense_ratio = (params or {}).get("defense_ratio", 0.70)

        # 清盘恢复机制：持续监控 drawdown，回到 halve 阈值以下则恢复
        current_level = signal["drawdown_stop"]["level"]
        current_dd = signal["drawdown_stop"]["drawdown"]
        if prev_drawdown_level == "liquidate":
            if current_level != "liquidate":
                pass  # signal 已包含正确的 level/multiplier
            elif liquidation_nav is not None and current_dd > -0.12:
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

        # 执行(close)：lag=0 所有日 或 lag=1 首日引导（无 pending_alloc）
        is_bootstrap = execution_lag == 1 and pending_alloc is None
        if execution_lag == 0 or is_bootstrap:
            exec_alloc = alloc
            prev_positions = positions.copy()
            positions = {}
            total_commission = 0.0
            if exec_alloc is not None:
                for name, target_dollar in exec_alloc["positions"].items():
                    if name not in prices or today not in prices[name].index:
                        continue
                    price = prices[name].loc[today, "close"]
                    if price <= 0:
                        continue
                    per_slippage = (slippage_bps_map or {}).get(name, slippage_bps)
                    current_value = prev_positions.get(name, 0.0) * price
                    exec_price = price * (1.0 + per_slippage / 10000.0) if target_dollar > current_value else price * (1.0 - per_slippage / 10000.0)
                    positions[name] = target_dollar / exec_price
                    total_commission += abs(target_dollar - current_value) * commission_rate
            positions_value = sum(
                positions.get(n, 0.0) * prices[n].loc[today, "close"]
                for n in positions if n in prices and today in prices[n].index
            )
            repo_cash = nav - positions_value - total_commission
            # lag=1 首日引导：保存 alloc 供明日开盘执行
            if is_bootstrap:
                pending_alloc = alloc

        # lag=1 非首日：仅保存明日信号（今日已在循环顶部用 open 执行）
        if execution_lag == 1 and pending_alloc is not None and not is_bootstrap:
            pending_alloc = alloc

        exec_day = today  # record_daily 通用
        # 日记录（含持仓明细，供 Golden Dataset 使用）
        pos_detail = {name: positions.get(name, 0.0) * prices[name].loc[exec_day, "close"]
                      for name in positions
                      if name in prices and exec_day in prices[name].index}
        record_daily(
            recorder, str(today.date()), nav, signal, exec_alloc["positions"],
            positions_detail=pos_detail,
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
    benchmark_specs = p.get("benchmark_specs")
    if benchmark_specs:
        # 从 benchmark_specs 构建默认 benchmark_nav（等权各 spec）
        default_weights: dict[str, float] = {}
        n_specs = len(benchmark_specs)
        for label, spec in benchmark_specs.items():
            if spec is None:
                default_weights[label] = default_weights.get(label, 0) + 1.0 / n_specs
            elif isinstance(spec, dict):
                for name, w in spec.items():
                    default_weights[name] = default_weights.get(name, 0) + w / n_specs
        benchmark_nav = compute_benchmark(prices, default_weights)
    else:
        benchmark_nav = compute_benchmark(prices)
    final_benchmark_nav = float(benchmark_nav.iloc[-1])
    benchmark_return = final_benchmark_nav - 1.0

    result = {
        "records_df": records_df,
        "_recorder": recorder,
        "benchmark_nav": benchmark_nav,
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

    if benchmark_specs:
        for label, spec in benchmark_specs.items():
            key = f"benchmark_{label}"
            if spec is None:
                result[key] = compute_single_benchmark(prices, label)
            elif isinstance(spec, dict):
                result[key] = compute_benchmark(prices, spec)
    else:
        result["benchmark_300"] = compute_single_benchmark(prices, "沪深300")
        result["benchmark_chinext"] = compute_single_benchmark(prices, "创业板")
        result["benchmark_nasdaq"] = compute_single_benchmark(prices, "纳指")
        result["benchmark_6040"] = compute_benchmark(prices, {"沪深300": 0.60, "国债ETF": 0.40})

    return result


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
            if k not in ("records_df", "benchmark_nav", "_recorder")
            and not k.startswith("benchmark_")
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
