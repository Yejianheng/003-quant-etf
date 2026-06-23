# [2026-06-23] 新增：新鲜度门禁 — 数据不齐禁止生成图表
# [2026-06-22] 修复：权重还原纯等权，现金列二元判断（空仓=100%，持仓=0）
# [2026-06-18] 修改：新增等权基准 + 60/40 基准线（图表 + 表格列）
# [2026-06-18] 修改：新增逆回购可视化（背景带 + 净值虚线 + 表格统计行）
# [2026-06-16] 修改：去 A/B 参考线，只保留 50/50 生产策略 + 5 ETF 基准
# [2026-06-16] 修复：移除手动 50/50 平均逻辑，主策略直接取 B（生产 50/50，避免二次平均成 75/25）
# [2026-06-12] 修改：新增 A(无sf)/B(sf+0.08)/50-50 三策略对比
# [2026-06-11] 修改：T+1 表格数据前移 + 操作列含权重变化（箭头格式）+ 表头改「今日调仓」
# [2026-06-11] 修改：净值归一化除以首日 + 底部分页增加页码跳转
# [2026-06-11] 修改：表格重做为持仓权重 + tooltip 移除自定义 callback 修复36行重复
# [2026-06-11] 修改：输出路径改项目根 + 鼠标悬停6线净值 + 数据表格 + 日期搜索
# [2026-06-11] 新增：2026 净值对比图表脚本 — 纯防御策略 vs 5 ETF 买入持有
"""
2026 净值对比图表生成脚本：拉取 5 ETF 数据 → 跑 50/50 生产策略回测 → 生成 HTML 净值对比图。

用法：python scripts/nav_chart.py
输出：nav_2026.html
"""
import os
import sys
import json

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.backtest_engine import run_backtest
from src.signal_generator import DEFAULT_PARAMS, DEFENSE_NAMES
from src.etf_universe import ETF_UNIVERSE
from src.data_pipeline import load_from_parquet, check_freshness
from scripts.update_data import update_single_etf

START_DATE = "2026-01-01"
PAGE_SIZE = 20
REPO_ANNUAL_RATE = 0.02

COLORS = {
    "50/50 组合": "#dc3912",
    "沪深300": "#3366cc",
    "创业板": "#e06666",
    "纳指": "#6aa84f",
    "黄金": "#bf9000",
    "国债ETF": "#674ea7",
    "逆回购净值": "#999999",
    "5 ETF 等权": "#888888",
    "60/40 股债": "#8B4513",
}


def update_all_etfs(data_dir: str = "data") -> None:
    """
    更新全部 5 只防御 ETF 的 parquet 文件。
    任一 parquet 缺失 → FileNotFoundError。
    """
    for name in DEFENSE_NAMES:
        code = ETF_UNIVERSE[name]
        path = os.path.join(data_dir, f"{code}.parquet")
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"parquet 文件缺失: {path}，请先运行 scripts/update_data.py"
            )
        update_single_etf(code, data_dir)


def load_prices(data_dir: str = "data") -> dict[str, pd.DataFrame]:
    """
    从 parquet 加载 5 只防御 ETF 的 OHLCV 数据。
    任一 parquet 缺失 → FileNotFoundError。
    """
    prices = {}
    for name in DEFENSE_NAMES:
        code = ETF_UNIVERSE[name]
        path = os.path.join(data_dir, f"{code}.parquet")
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"parquet 文件缺失: {path}，请先运行 scripts/update_data.py"
            )
        prices[name] = load_from_parquet(path)
    return prices


def truncate_to_start(series: pd.Series, start_date: str) -> pd.Series:
    """截断 series 到 start_date 及之后，归一化到起点 1.0。"""
    mask = series.index >= pd.Timestamp(start_date)
    truncated = series[mask]
    if len(truncated) == 0:
        raise ValueError(f"无 {start_date} 及之后的数据")
    return truncated / truncated.iloc[0]


def compute_etf_navs(
    prices: dict[str, pd.DataFrame], start_date: str
) -> dict[str, pd.Series]:
    """计算每只 ETF 从 start_date 起的买入持有归一化净值。"""
    navs = {}
    for name in DEFENSE_NAMES:
        if name not in prices:
            continue
        close = prices[name]["close"]
        navs[name] = truncate_to_start(close, start_date)
    return navs


def compute_equal_weight_nav(
    prices: dict[str, pd.DataFrame], start_date: str
) -> pd.Series:
    """5 ETF 等权买入持有（1/N=20%，无再平衡）。起始净值 1.0。"""
    common_dates = None
    etf_returns = {}
    for name in DEFENSE_NAMES:
        if name not in prices:
            continue
        close = prices[name]["close"]
        mask = close.index >= pd.Timestamp(start_date)
        if mask.sum() < 2:
            continue
        norm = close[mask] / close[mask].iloc[0]
        etf_returns[name] = norm
        if common_dates is None:
            common_dates = set(norm.index)
        else:
            common_dates = common_dates.intersection(set(norm.index))
    if not etf_returns:
        raise ValueError("无可用 ETF 数据计算等权基准")
    common_dates = sorted(common_dates)
    nav = pd.Series(0.0, index=pd.DatetimeIndex(common_dates), dtype=float)
    weight = 1.0 / len(etf_returns)
    for name, ret in etf_returns.items():
        nav += weight * ret.loc[common_dates]
    return nav


def compute_6040_nav(
    prices: dict[str, pd.DataFrame], start_date: str
) -> pd.Series:
    """60/40 股债月度再平衡（沪深300 60% + 国债ETF 40%）。起始净值 1.0。"""
    if "沪深300" not in prices or "国债ETF" not in prices:
        raise ValueError("缺少沪深300 或 国债ETF 数据，无法计算 60/40 基准")
    stock_close = prices["沪深300"]["close"]
    bond_close = prices["国债ETF"]["close"]
    common = stock_close.index.intersection(bond_close.index)
    common = common[common >= pd.Timestamp(start_date)]
    if len(common) < 2:
        raise ValueError(f"60/40 基准：{start_date} 之后共同交易日不足")
    start_dt = common[0]
    stock_units = 0.6 / stock_close.loc[start_dt]
    bond_units = 0.4 / bond_close.loc[start_dt]
    navs = []
    dates_list = []
    current_month = start_dt.month
    for i, d in enumerate(common):
        s_val = stock_units * stock_close.loc[d]
        b_val = bond_units * bond_close.loc[d]
        nav_val = s_val + b_val
        navs.append(nav_val)
        dates_list.append(d)
        if d.month != current_month:
            current_month = d.month
            stock_units = 0.6 * nav_val / stock_close.loc[d]
            bond_units = 0.4 * nav_val / bond_close.loc[d]
    return pd.Series(navs, index=pd.DatetimeIndex(dates_list), dtype=float)


def _compute_turnover_stats(
    positions_detail: list[dict], prices: dict[str, pd.DataFrame]
) -> dict:
    """从日持仓明细计算换手率与交易成本。

    positions_detail: recorder["positions_detail"]，每条含 date + 各 ETF 持仓市值。
    prices: ETF OHLCV 数据（用于 per-ETF 价差估算）。
    返回 turnover_stats dict。
    """
    if len(positions_detail) < 2:
        return {"annual_turnover_rate": 0.0, "total_cost": 0.0, "cost_pct": 0.0}

    # per-ETF 价差（bp）— 与 slippage_scan.py 同逻辑
    spreads = {}
    for name, df in prices.items():
        if "volume" not in df.columns or len(df) < 20:
            spreads[name] = 15.0
        else:
            avg_volume = float(df["volume"].tail(252).mean())
            avg_close = float(df["close"].tail(252).mean())
            avg_turnover = avg_volume * avg_close
            if avg_turnover > 1e9:
                spreads[name] = 3.0
            elif avg_turnover > 2e8:
                spreads[name] = 8.0
            else:
                spreads[name] = 15.0

    COMMISSION_RATE = 0.00025  # 万2.5

    etf_names = [k for k in positions_detail[0] if k != "date"]
    total_turnover = 0.0
    total_commission = 0.0
    total_slippage = 0.0
    total_position_value = 0.0
    n_days = len(positions_detail)

    for i in range(1, n_days):
        prev = positions_detail[i - 1]
        curr = positions_detail[i]
        daily_position_value = 0.0
        for name in etf_names:
            prev_val = float(prev.get(name, 0.0) or 0.0)
            curr_val = float(curr.get(name, 0.0) or 0.0)
            turnover = abs(curr_val - prev_val)
            total_turnover += turnover
            daily_position_value += curr_val
            # 成本：佣金 + 滑点
            if turnover > 0:
                total_commission += turnover * COMMISSION_RATE
                total_slippage += turnover * (spreads.get(name, 8.0) / 10000.0)
        total_position_value += daily_position_value

    avg_position_value = total_position_value / (n_days - 1) if n_days > 1 else 1.0
    total_cost = total_commission + total_slippage

    return {
        "total_turnover": round(total_turnover, 2),
        "avg_position_value": round(avg_position_value, 2),
        "annual_turnover_rate": round(total_turnover / avg_position_value * 100, 1) if avg_position_value > 0 else 0.0,
        "total_commission": round(total_commission, 2),
        "total_slippage": round(total_slippage, 2),
        "total_cost": round(total_cost, 2),
        "cost_pct": round(total_cost / avg_position_value * 100, 4) if avg_position_value > 0 else 0.0,
    }


def _nav_to_json(series: pd.Series) -> list[float]:
    """净值 Series → JSON 可序列化的 float 列表（6 位有效数字）。"""
    return [round(float(v), 6) for v in series.values]


def _dates_to_labels(index: pd.DatetimeIndex) -> list[str]:
    """DatetimeIndex → YYYY-MM-DD 字符串列表。"""
    return [str(d.date()) for d in index]


def _format_action(old_weights, new_weights, etf_names):
    """格式化调仓操作文本：卖出 品种(旧%→新%), 买入 品种(旧%→新%)"""
    sold = []
    bought = []
    for name in etf_names:
        old_w = old_weights.get(name, 0.0)
        new_w = new_weights.get(name, 0.0)
        if new_w > old_w + 0.001:
            bought.append((name, old_w, new_w))
        elif old_w > new_w + 0.001:
            sold.append((name, old_w, new_w))

    if not sold and not bought:
        return "无需调仓"

    parts = []
    if sold:
        sold_str = '、'.join(f"{name}({old_w*100:.0f}%→{new_w*100:.0f}%)" for name, old_w, new_w in sold)
        parts.append(f"卖出 {sold_str}")
    if bought:
        bought_str = '、'.join(f"{name}({old_w*100:.0f}%→{new_w*100:.0f}%)" for name, old_w, new_w in bought)
        parts.append(f"买入 {bought_str}")

    return "，".join(parts)


def _build_table_data(records_df, etf_names, ew_nav=None, nav_6040=None):
    """权重 = 今日实际持仓（前日 signal 执行而来），操作 = 明日调仓（当日 signal vs 前日 signal）。
    records_df[0] 为 2025 末锚点（不显示），records_df[1:] 为 2026 数据。"""
    first_nav = float(records_df.iloc[1]["nav"])
    rows = []

    for i, (_idx, row) in enumerate(records_df.iterrows()):
        if i == 0:
            continue  # anchor row, not displayed

        date_str = str(_idx.date()) if hasattr(_idx, "date") else str(_idx)[:10]
        date_ts = _idx if isinstance(_idx, pd.Timestamp) else pd.Timestamp(_idx)

        # --- 持仓权重 = 前日信号层等权分配（信号与执行隔离展示） ---
        signal_row = records_df.iloc[i - 1]
        cb_triggered_prev = bool(signal_row.get("circuit_breaker_triggered", False))
        defense_count_prev = int(signal_row.get("defense_count", 0))
        is_all_cash = cb_triggered_prev or defense_count_prev == 0

        active_str = signal_row.get("defense_active", "")
        active = [n.strip() for n in active_str.split(";") if n.strip()] if active_str else []
        n_active = len(active)

        weights = {}
        for name in etf_names:
            if is_all_cash:
                weights[name] = 0.0
            else:
                weights[name] = 1.0 / n_active if name in active and n_active > 0 else 0.0

        total_weight = sum(weights.values())

        # --- 操作列 = 明日将执行的调仓（当日信号 vs 前日信号） ---
        # new_weights = 当日信号等权（明日将持）；old_weights = 前日信号等权（今日实际持）
        new_weights = _defense_active_weights(row, etf_names)
        old_weights = _defense_active_weights(records_df.iloc[i - 1], etf_names)
        action = _format_action(old_weights, new_weights, etf_names)

        # --- 逆回购 ---
        repo_amount = float(row.get("repo_amount", 0.0))
        cb_triggered = bool(row.get("circuit_breaker_triggered", False))
        defense_count = int(row.get("defense_count", 0))
        is_repo_day = cb_triggered or defense_count == 0

        # --- NAV（当日实际 NAV） ---
        nav = float(row["nav"]) / first_nav
        prev_nav = float(records_df.iloc[i - 1]["nav"]) / first_nav
        delta_nav = round((nav - prev_nav) / prev_nav * 100, 2) if prev_nav != 0 else None

        # --- 基准净值 ---
        ew_val = round(float(ew_nav.loc[date_ts]) / float(ew_nav.iloc[0]), 4) if ew_nav is not None and date_ts in ew_nav.index else None
        v6040_val = round(float(nav_6040.loc[date_ts]) / float(nav_6040.iloc[0]), 4) if nav_6040 is not None and date_ts in nav_6040.index else None

        rows.append({
            "date": date_str,
            "nav": round(nav, 4),
            "ew_nav": ew_val,
            "nav_6040": v6040_val,
            "weights": [round(weights.get(n, 0.0), 4) for n in etf_names],
            "cash": round(1.0 - total_weight, 4),
            "repo_amount": 1.0 if is_all_cash else 0.0,
            "is_repo_day": is_repo_day,
            "action": action,
            "delta": delta_nav,
        })

    return rows


def _defense_active_weights(record_row, etf_names):
    """从 record 行的 defense_active 解析等权权重。"""
    active_str = record_row.get("defense_active", "")
    active = [n.strip() for n in active_str.split(";") if n.strip()] if active_str else []
    n_active = len(active)
    return {name: 1.0 / n_active if name in active and n_active > 0 else 0.0 for name in etf_names}


def generate_html(
    strategy_nav: pd.Series,
    etf_navs: dict[str, pd.Series],
    records_df: pd.DataFrame,
    output_path: str,
    ew_nav: pd.Series | None = None,
    nav_6040: pd.Series | None = None,
    turnover_stats: dict | None = None,
) -> None:
    """生成 Chart.js HTML 净值对比图（50/50 策略 + 等权/60/40 基准 + 5 ETF + 盈亏线 + 持仓权重表 + 翻页 + 日期搜索）。"""

    labels = _dates_to_labels(strategy_nav.index)
    label_json = json.dumps(labels, ensure_ascii=False)

    # --- 逆回购数据 ---
    # repo NAV: 纯逆回购累计净值（年化 2% 每日复利）
    n_days_repo = len(strategy_nav)
    repo_nav_vals = [1.0]
    for _ in range(1, n_days_repo):
        repo_nav_vals.append(repo_nav_vals[-1] * (1.0 + REPO_ANNUAL_RATE / 252.0))

    # repo 背景带：空仓期标记（熔断 或 defense_count==0）
    aligned_df = records_df.loc[strategy_nav.index]
    repo_periods = []
    for _, row in aligned_df.iterrows():
        cb = bool(row.get("circuit_breaker_triggered", False))
        dc = int(row.get("defense_count", 0))
        repo_periods.append(1 if (cb or dc == 0) else 0)

    # repo 统计
    repo_interest_total = 0.0
    repo_days = 0
    cb_days = 0
    max_consecutive_repo = 0
    current_consecutive = 0
    for _, row in aligned_df.iterrows():
        cb = bool(row.get("circuit_breaker_triggered", False))
        dc = int(row.get("defense_count", 0))
        repo_amt = float(row.get("repo_amount", 0.0))
        repo_interest_total += repo_amt * (REPO_ANNUAL_RATE / 252.0)
        if cb or dc == 0:
            repo_days += 1
            current_consecutive += 1
            max_consecutive_repo = max(max_consecutive_repo, current_consecutive)
        else:
            current_consecutive = 0
        if cb:
            cb_days += 1
    total_days_data = len(aligned_df)
    # 归一化 repo 利息（除以首日 nav）使其与图表单位一致
    first_nav_for_stats = float(aligned_df.iloc[0]["nav"]) if len(aligned_df) > 0 else 1.0
    repo_interest_normalized = repo_interest_total / first_nav_for_stats if first_nav_for_stats != 0 else 0.0

    repo_periods_json = json.dumps(repo_periods)
    repo_stats = {
        "repo_interest": round(repo_interest_normalized, 4),
        "repo_days": repo_days,
        "total_days": total_days_data,
        "cb_days": cb_days,
        "max_consecutive_repo": max_consecutive_repo,
    }
    repo_stats_json = json.dumps(repo_stats, ensure_ascii=False)

    datasets = []

    # 50/50 组合（主策略，粗线）
    datasets.append({
        "label": "50/50 组合（生产）",
        "data": _nav_to_json(strategy_nav),
        "borderColor": COLORS["50/50 组合"],
        "backgroundColor": COLORS["50/50 组合"],
        "borderWidth": 3,
        "pointRadius": 0,
        "fill": False,
        "tension": 0,
    })

    # 逆回购净值（虚线）
    datasets.append({
        "label": "逆回购净值",
        "data": [round(v, 6) for v in repo_nav_vals],
        "borderColor": COLORS["逆回购净值"],
        "backgroundColor": COLORS["逆回购净值"],
        "borderWidth": 1.5,
        "pointRadius": 0,
        "fill": False,
        "tension": 0,
        "borderDash": [4, 4],
    })

    # 5 ETF 等权基准（灰色虚线）
    if ew_nav is not None and len(ew_nav) > 0:
        # 对齐到 strategy_nav 的日期范围
        ew_aligned = ew_nav.reindex(strategy_nav.index).ffill()
        datasets.append({
            "label": "5 ETF 等权",
            "data": _nav_to_json(ew_aligned),
            "borderColor": COLORS["5 ETF 等权"],
            "backgroundColor": COLORS["5 ETF 等权"],
            "borderWidth": 1.5,
            "pointRadius": 0,
            "fill": False,
            "tension": 0,
            "borderDash": [6, 3],
        })

    # 60/40 股债基准（棕色虚线）
    if nav_6040 is not None and len(nav_6040) > 0:
        v6040_aligned = nav_6040.reindex(strategy_nav.index).ffill()
        datasets.append({
            "label": "60/40 股债",
            "data": _nav_to_json(v6040_aligned),
            "borderColor": COLORS["60/40 股债"],
            "backgroundColor": COLORS["60/40 股债"],
            "borderWidth": 1.5,
            "pointRadius": 0,
            "fill": False,
            "tension": 0,
            "borderDash": [8, 4],
        })

    for name in DEFENSE_NAMES:
        if name not in etf_navs:
            continue
        etf_data = _nav_to_json(etf_navs[name])
        datasets.append({
            "label": name,
            "data": etf_data,
            "borderColor": COLORS[name],
            "backgroundColor": COLORS[name],
            "borderWidth": 1,
            "pointRadius": 0,
            "fill": False,
            "tension": 0,
            "borderDash": [],
        })

    datasets_json = json.dumps(datasets, ensure_ascii=False)

    table_data = _build_table_data(records_df, DEFENSE_NAMES, ew_nav=ew_nav, nav_6040=nav_6040)
    table_data_json = json.dumps(table_data, ensure_ascii=False)
    turnover_stats_json = json.dumps(turnover_stats, ensure_ascii=False) if turnover_stats else "null"
    total_pages = max(1, (len(table_data) + PAGE_SIZE - 1) // PAGE_SIZE)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>2026 净值对比 — 纯防御策略 vs 5 ETF</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js">
</script>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         max-width: 1200px; margin: 24px auto; padding: 0 16px; }}
  h2 {{ text-align: center; color: #333; }}
  .chart-container {{ position: relative; width: 100%; margin-bottom: 32px; }}
  .table-toolbar {{ display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }}
  .table-toolbar input[type="date"] {{ padding: 4px 8px; border: 1px solid #ccc;
      border-radius: 4px; font-size: 13px; }}
  .table-toolbar button {{ padding: 4px 14px; border: 1px solid #999; border-radius: 4px;
      background: #f5f5f5; cursor: pointer; font-size: 13px; }}
  .table-toolbar button:hover {{ background: #e0e0e0; }}
  .table-wrapper {{ overflow-x: auto; max-width: 100%; border: 1px solid #e0e0e0;
      border-radius: 4px; }}
  table {{ border-collapse: collapse; font-size: 13px; white-space: nowrap; width: 100%; }}
  th, td {{ padding: 5px 10px; border-right: 1px solid #e8e8e8;
      border-bottom: 1px solid #e8e8e8; text-align: right; }}
  th {{ background: #f5f5f5; position: sticky; top: 0; z-index: 2; font-weight: 600; }}
  th:first-child, td:first-child {{ position: sticky; left: 0; z-index: 1;
      text-align: left; background: #fff; font-weight: 600; }}
  th:first-child {{ z-index: 3; background: #f5f5f5; }}
  thead tr:first-child th {{ border-top: none; }}
  tbody tr:hover td {{ background: #fafafa; }}
  tbody tr:hover td:first-child {{ background: #fafafa; }}
  td.action-cell {{ text-align: left; white-space: pre-wrap; max-width: 200px; }}
  .pos {{ color: #d32f2f; }}
  .neg {{ color: #2e7d32; }}
  .pagination {{ display: flex; align-items: center; justify-content: center; gap: 16px;
      margin-top: 16px; margin-bottom: 24px; }}
  .pagination button {{ padding: 6px 18px; border: 1px solid #aaa; border-radius: 4px;
      background: #fff; cursor: pointer; font-size: 13px; }}
  .pagination button:hover {{ background: #f0f0f0; }}
  .pagination button:disabled {{ opacity: 0.35; cursor: default; }}
  .page-info {{ font-size: 13px; color: #666; min-width: 80px; text-align: center; }}
</style>
</head>
<body>
<h2>2026 净值对比 — 纯防御策略 vs 5 ETF</h2>
<div class="chart-container">
  <canvas id="navChart"></canvas>
</div>

<div class="table-toolbar">
  <label for="dateSearch" style="font-size:13px;">日期定位：</label>
  <input type="date" id="dateSearch">
  <button onclick="jumpToDate()">跳转</button>
  <span id="searchMsg" style="font-size:12px;color:#e53935;margin-left:8px;"></span>
</div>

<div class="table-wrapper">
  <table id="navTable">
    <thead>
      <tr>
        <th>日期</th>
        <th>纯防御净值</th>
        <th>等权净值</th><th>60/40净值</th>
        <th>沪深300</th><th>创业板</th><th>纳指</th><th>黄金</th><th>国债ETF</th>
        <th>现金</th><th>明日调仓</th><th>Δ%</th>
      </tr>
    </thead>
    <tbody></tbody>
  </table>
</div>

<div class="table-wrapper" style="margin-top:16px;">
  <table id="repoStatsTable">
    <thead><tr><th colspan="2">逆回购统计</th></tr></thead>
    <tbody></tbody>
  </table>
</div>

<div class="table-wrapper" style="margin-top:16px;">
  <table id="turnoverStatsTable">
    <thead><tr><th colspan="2">换手与成本</th></tr></thead>
    <tbody></tbody>
  </table>
</div>

<div class="pagination">
  <button id="prevBtn" onclick="changePage(-1)">上一页</button>
  <span class="page-info" id="pageInfo">第 1/{total_pages} 页</span>
  <span style="font-size:13px;color:#666;">到第</span>
  <input type="number" id="pageJumpInput" min="1" max="{total_pages}" value="1"
    style="width:50px;padding:4px 6px;border:1px solid #ccc;border-radius:4px;font-size:13px;text-align:center;">
  <span style="font-size:13px;color:#666;">页</span>
  <button onclick="jumpToPage()">跳转</button>
  <button id="nextBtn" onclick="changePage(1)">下一页</button>
</div>

<script>
const tableData = {table_data_json};
const PAGE_SIZE = {PAGE_SIZE};
const totalPages = {total_pages};
let currentPage = 1;

// ===== Chart =====
const labels = {label_json};
const datasets = {datasets_json};

const repoPeriods = {repo_periods_json};
const repoStats = {repo_stats_json};
const turnoverStats = {turnover_stats_json};

const breakevenPlugin = {{
  id: 'breakevenLine',
  afterDraw(chart) {{
    const {{ ctx, scales: {{ y }} }} = chart;
    const yPos = y.getPixelForValue(1.0);
    if (yPos < chart.chartArea.top || yPos > chart.chartArea.bottom) return;
    ctx.save();
    ctx.setLineDash([6, 4]);
    ctx.strokeStyle = '#999999';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(chart.chartArea.left, yPos);
    ctx.lineTo(chart.chartArea.right, yPos);
    ctx.stroke();
    ctx.restore();
  }}
}};

const repoBandPlugin = {{
  id: 'repoBand',
  beforeDraw(chart) {{
    const {{ ctx, chartArea, scales: {{ x }} }} = chart;
    if (!repoPeriods || repoPeriods.length === 0) return;
    ctx.save();
    ctx.fillStyle = 'rgba(180, 180, 180, 0.15)';
    let inBand = false;
    let bandStart = 0;
    const barW = x.getPixelForValue(1) - x.getPixelForValue(0);
    for (let i = 0; i <= repoPeriods.length; i++) {{
      const isRepo = i < repoPeriods.length && repoPeriods[i] === 1;
      if (isRepo && !inBand) {{
        inBand = true;
        bandStart = i;
      }} else if (!isRepo && inBand) {{
        inBand = false;
        const x0 = x.getPixelForValue(bandStart) - barW / 2;
        const x1 = x.getPixelForValue(i - 1) + barW / 2;
        ctx.fillRect(x0, chartArea.top, x1 - x0, chartArea.bottom - chartArea.top);
      }}
    }}
    if (inBand) {{
      const x0 = x.getPixelForValue(bandStart) - barW / 2;
      const x1 = x.getPixelForValue(repoPeriods.length - 1) + barW / 2;
      ctx.fillRect(x0, chartArea.top, x1 - x0, chartArea.bottom - chartArea.top);
    }}
    ctx.restore();
  }}
}};

new Chart(document.getElementById('navChart'), {{
  type: 'line',
  data: {{ labels, datasets }},
  options: {{
    responsive: true,
    maintainAspectRatio: true,
    interaction: {{
      mode: 'index',
      intersect: false,
    }},
    scales: {{
      x: {{
        title: {{ display: true, text: '日期' }},
        ticks: {{ maxTicksLimit: 20, maxRotation: 45 }}
      }},
      y: {{
        title: {{ display: true, text: '净值 (2026-01-01 = 1.0)' }},
        beginAtZero: false
      }}
    }},
    plugins: {{
      legend: {{
        position: 'top',
        align: 'end',
        labels: {{ usePointStyle: true, boxWidth: 20, padding: 12 }}
      }},
      tooltip: {{
        usePointStyle: true,
        boxPadding: 4
      }}
    }}
  }},
  plugins: [breakevenPlugin, repoBandPlugin]
}});

// ===== Table =====
function renderTable() {{
  const start = (currentPage - 1) * PAGE_SIZE;
  const end = Math.min(start + PAGE_SIZE, tableData.length);
  const tbody = document.querySelector('#navTable tbody');
  let html = '';
  for (let i = start; i < end; i++) {{
    const row = tableData[i];
    html += '<tr>';
    html += '<td>' + row.date + '</td>';
    html += '<td>' + row.nav.toFixed(4) + '</td>';
    html += '<td>' + (row.ew_nav != null ? row.ew_nav.toFixed(4) : '—') + '</td>';
    html += '<td>' + (row.nav_6040 != null ? row.nav_6040.toFixed(4) : '—') + '</td>';
    for (let j = 0; j < 5; j++) {{
      const w = row.weights[j];
      html += '<td>' + (w > 0 ? (w * 100).toFixed(0) + '%' : '—') + '</td>';
    }}
    html += '<td>' + (row.repo_amount > 0 ? (row.repo_amount * 100).toFixed(0) + '%' : '—') + '</td>';
    html += '<td class="action-cell">' + row.action + '</td>';
    if (row.delta === null) {{
      html += '<td>—</td>';
    }} else if (row.delta >= 0) {{
      html += '<td class="pos">+' + row.delta.toFixed(2) + '%</td>';
    }} else {{
      html += '<td class="neg">' + row.delta.toFixed(2) + '%</td>';
    }}
    html += '</tr>';
  }}
  tbody.innerHTML = html;
  document.getElementById('pageInfo').textContent =
    '第 ' + currentPage + '/' + totalPages + ' 页';
  document.getElementById('prevBtn').disabled = currentPage <= 1;
  document.getElementById('nextBtn').disabled = currentPage >= totalPages;
  document.getElementById('pageJumpInput').value = currentPage;
}}

function renderRepoStats() {{
  const tbody = document.querySelector('#repoStatsTable tbody');
  if (!tbody || !repoStats) return;
  tbody.innerHTML =
    '<tr><td>累计逆回购利息</td><td>' + repoStats.repo_interest.toFixed(4) + '</td></tr>' +
    '<tr><td>空仓天数</td><td>' + repoStats.repo_days + ' / ' + repoStats.total_days + ' 天</td></tr>' +
    '<tr><td>熔断触发天数</td><td>' + repoStats.cb_days + ' 天</td></tr>' +
    '<tr><td>最长连续空仓</td><td>' + repoStats.max_consecutive_repo + ' 天</td></tr>';
}}

function renderTurnoverStats() {{
  const tbody = document.querySelector('#turnoverStatsTable tbody');
  if (!tbody || !turnoverStats) return;
  tbody.innerHTML =
    '<tr><td>年化换手率</td><td>' + turnoverStats.annual_turnover_rate.toFixed(1) + '%</td></tr>' +
    '<tr><td>累计交易成本（佣金+滑点）</td><td>' + turnoverStats.total_cost.toFixed(2) + ' 元</td></tr>' +
    '<tr><td>成本占比（成本/平均持仓）</td><td>' + turnoverStats.cost_pct.toFixed(4) + '%</td></tr>';
}}

function changePage(delta) {{
  const newPage = currentPage + delta;
  if (newPage < 1 || newPage > totalPages) return;
  currentPage = newPage;
  renderTable();
  document.getElementById('navTable').scrollIntoView({{ behavior: 'smooth', block: 'start' }});
}}

function jumpToPage() {{
  const input = document.getElementById('pageJumpInput');
  const page = parseInt(input.value);
  if (isNaN(page) || page < 1 || page > totalPages) {{
    input.value = currentPage;
    return;
  }}
  currentPage = page;
  renderTable();
  document.getElementById('navTable').scrollIntoView({{ behavior: 'smooth', block: 'start' }});
}}

function jumpToDate() {{
  const input = document.getElementById('dateSearch');
  const msg = document.getElementById('searchMsg');
  msg.textContent = '';
  if (!input.value) {{
    msg.textContent = '请选择日期';
    return;
  }}
  let found = -1;
  for (let i = 0; i < tableData.length; i++) {{
    if (tableData[i].date >= input.value) {{
      found = i;
      break;
    }}
  }}
  if (found === -1) {{
    msg.textContent = '未找到该日期之后的数据';
    return;
  }}
  currentPage = Math.floor(found / PAGE_SIZE) + 1;
  renderTable();
  document.getElementById('navTable').scrollIntoView({{ behavior: 'smooth', block: 'start' }});
}}

renderTable();
renderRepoStats();
renderTurnoverStats();
</script>
</body>
</html>"""

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)


def main(data_dir: str = "data", output_path: str = "nav_2026.html") -> None:
    """
    主流程：
    1. 更新 5 ETF parquet
    2. 新鲜度门禁
    3. 加载全量历史数据
    4. 跑 50/50 生产策略回测
    5. 截断到 2026-01-01 + 归一化
    6. 生成 HTML
    """
    update_all_etfs(data_dir)

    # 新鲜度门禁：任一 ETF 未更新到今日 → 中止
    codes = list(ETF_UNIVERSE.values())
    stale = check_freshness(codes, data_dir)
    if stale:
        names = [k for k, v in ETF_UNIVERSE.items() if v in stale]
        raise RuntimeError(
            f"[门禁] 以下 ETF 未更新到今日：{', '.join(names or stale)}，"
            f"图表生成已中止。请稍后重试。"
        )

    prices = load_prices(data_dir)

    # 50/50 生产策略回测
    result = run_backtest(prices, params=DEFAULT_PARAMS, execution_lag=1)
    records_df = result["records_df"]
    nav_full = records_df["nav"]

    # 截断到 2026-01-01 + 归一化
    strategy_nav = truncate_to_start(nav_full, START_DATE)
    etf_navs = compute_etf_navs(prices, START_DATE)

    # 对齐日期
    strategy_dates = strategy_nav.index
    aligned_etf_navs = {}
    for name, nav in etf_navs.items():
        cd = nav.index.intersection(strategy_dates)
        if len(cd) > 0:
            aligned_etf_navs[name] = nav.loc[cd]

    # 基准净值
    ew_nav = compute_equal_weight_nav(prices, START_DATE)
    b6040_nav = compute_6040_nav(prices, START_DATE)

    # 表格数据：锚点行 + 2026 年数据
    start_dt = pd.Timestamp(START_DATE)
    before = records_df[records_df.index < start_dt]
    if len(before) > 0:
        anchor = before.iloc[-1:]
        records_2026 = pd.concat([anchor, records_df.loc[strategy_nav.index]])
    else:
        records_2026 = records_df.loc[strategy_nav.index]
    # 换手与成本统计
    positions_detail = result.get("_recorder", {}).get("positions_detail", [])
    # 截断到 2026 的 positions_detail
    pd_2026 = [d for d in positions_detail if pd.Timestamp(d["date"]) >= start_dt]
    turnover_stats = _compute_turnover_stats(pd_2026, prices)

    generate_html(strategy_nav, aligned_etf_navs, records_2026, output_path, ew_nav=ew_nav, nav_6040=b6040_nav, turnover_stats=turnover_stats)
    print(f"净值对比图已生成：{output_path}")


if __name__ == "__main__":
    main()
