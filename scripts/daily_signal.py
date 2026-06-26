# [2026-06-25] 新增：间隔回放 _replay_gap + 期间回顾报告段
# [2026-05-30] 新增：每日信号脚本 — 收盘后运行，输出中文信号报告
"""
每日信号脚本：读 data/ parquet → 算信号 → 输出中文报告 → 保存状态文件。

用法：python scripts/daily_signal.py
"""
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.data_pipeline import load_from_parquet
from src.etf_universe import ETF_UNIVERSE
from src.signal_generator import generate_signal, DEFAULT_PARAMS
from src.trend_strength import trend_strength

CODE_TO_NAME = {v: k for k, v in ETF_UNIVERSE.items()}
DEFENSE_CODES = list(ETF_UNIVERSE.values())  # ["510300", "159915", "513100", "518880", "511010"]
MIN_TRADING_DAYS = 120
STATE_FILENAME = "position_state.json"


# ---- 数据加载 ----

def load_prices(data_dir: str = "data") -> dict[str, pd.DataFrame]:
    """加载 data_dir 下所有 ETF parquet 文件，返回 {中文名: OHLCV DataFrame}。缺失文件跳过不报错。"""
    prices = {}
    data_path = Path(data_dir)
    if not data_path.exists():
        return prices
    for parquet_file in data_path.glob("*.parquet"):
        code = parquet_file.stem
        name = CODE_TO_NAME.get(code)
        if name is None:
            continue
        try:
            df = load_from_parquet(str(parquet_file))
            if "close" in df.columns:
                prices[name] = df
        except Exception:
            continue
    return prices


# ---- 间隔回放 ----

def _replay_gap(prices: dict[str, pd.DataFrame],
                state: dict | None) -> dict:
    """逐日回放 state.last_date 到最新数据日之间的趋势信号。

    返回:
    {
        "gap_trading_days": int,
        "last_date": str,
        "today": str,
        "daily_active": [{date, active}],
        "changes": [{date, event, etf}],
    }
    无 state 或 gap=0 时 gap_trading_days=0, changes=[]。
    """
    if state is None:
        return {"gap_trading_days": 0, "last_date": "", "today": "",
                "daily_active": [], "changes": []}

    last_date_str = state.get("last_date", "")
    if not last_date_str:
        return {"gap_trading_days": 0, "last_date": "", "today": "",
                "daily_active": [], "changes": []}
    last_date = pd.Timestamp(last_date_str)

    # 求所有 ETF 共同交易日
    common = None
    for df in prices.values():
        if common is None:
            common = set(df.index)
        else:
            common &= set(df.index)
    if not common:
        return {"gap_trading_days": 0, "last_date": last_date_str, "today": "",
                "daily_active": [], "changes": []}

    sorted_dates = sorted(common)
    today = sorted_dates[-1]
    gap_dates = [d for d in sorted_dates if d > last_date]

    if not gap_dates:
        return {"gap_trading_days": 0, "last_date": last_date_str,
                "today": str(today.date()), "daily_active": [], "changes": []}

    # 上限 60 个交易日
    if len(gap_dates) > 60:
        gap_dates = gap_dates[:60]

    trend_window = DEFAULT_PARAMS.get("trend_window", 40)
    daily_active = []
    changes = []
    prev_active = set(state.get("last_active", []))

    for d in gap_dates:
        active = set()
        for name, df in prices.items():
            subset = df[df.index <= d]
            if len(subset) < trend_window:
                continue
            ts = trend_strength(subset["close"], window=trend_window)
            if ts > 0:
                active.add(name)

        daily_active.append({"date": str(d.date()), "active": list(active)})

        removed = prev_active - active
        added = active - prev_active
        for etf in sorted(removed):
            changes.append({"date": str(d.date()), "event": "removed", "etf": etf})
        for etf in sorted(added):
            changes.append({"date": str(d.date()), "event": "added", "etf": etf})

        prev_active = active

    return {
        "gap_trading_days": len(gap_dates),
        "last_date": last_date_str,
        "today": str(today.date()),
        "daily_active": daily_active,
        "changes": changes,
    }


def _format_replay_segments(replay: dict) -> list[str]:
    """将 replay result 格式化为人类可读的"期间回顾"行列表。"""
    if not replay or replay["gap_trading_days"] == 0:
        return []

    lines = []
    changes = replay["changes"]

    if not changes:
        # 全程无变化 — 从 daily_active 或 state last_active 获取持仓
        active_set = set()
        if replay["daily_active"]:
            active_set = set(replay["daily_active"][0]["active"])
        n_etfs = len(active_set)
        names_str = "、".join(sorted(active_set)) if active_set else "空仓"
        lines.append(
            f"  {replay['last_date']} → {replay['today']}  "
            f"持续持有 {n_etfs} 只（{names_str}），无变化"
        )
    else:
        # 分段：从 last_date 到第一个 change 前一天
        # 用 daily_active 来确定每段的 active 集合
        seg_start = replay["last_date"]
        current_active = set()
        last_active_set = set()

        # 先确定初始 active（从 state 或 daily_active[0]）
        if replay["daily_active"]:
            last_active_set = set(replay["daily_active"][0]["active"])
        elif "last_active" in replay and replay["last_active"]:
            last_active_set = set(replay["last_active"])

        change_idx = 0
        for i, day in enumerate(replay["daily_active"]):
            day_active = set(day["active"])
            # 检查这一天是否有变化
            day_changes = [c for c in changes if c["date"] == day["date"]]

            if day_changes:
                # 变化前的稳定段
                if day_active != last_active_set or i == 0:
                    n_etfs = len(last_active_set)
                    names_str = "、".join(sorted(last_active_set)) if last_active_set else "空仓"
                    lines.append(
                        f"  {seg_start} → {day['date']}  "
                        f"{n_etfs} 只（{names_str}），无变化"
                    )
                # 变化事件
                for c in day_changes:
                    verb = "买入" if c["event"] == "added" else "卖出"
                    lines.append(f"  {day['date']}  {verb} {c['etf']}（趋势转{'正' if c['event'] == 'added' else '负'}）")
                seg_start = day["date"]
                last_active_set = day_active

        # 最后一段：从末次变化到今日
        if replay["daily_active"]:
            final_active = set(replay["daily_active"][-1]["active"])
            n_etfs = len(final_active)
            names_str = "、".join(sorted(final_active)) if final_active else "空仓"
            if seg_start != replay["today"]:
                lines.append(
                    f"  {seg_start} → {replay['today']}  "
                    f"{n_etfs} 只（{names_str}），无变化"
                )

    return lines


# ---- 报告格式化 ----

def _compare_signals(current: dict, previous: dict | None) -> list[str]:
    """比较当前与上一交易日信号，返回操作指令列表。"""
    if previous is None:
        if current["circuit_breaker"]["triggered"]:
            return ["全部清仓（熔断触发）"]
        return ["首次建仓"]

    # 熔断触发 → 无条件清仓
    if current["circuit_breaker"]["triggered"]:
        return ["全部清仓（熔断触发）"]

    actions = []
    prev_active = set(previous["defense"]["active"])
    curr_active = set(current["defense"]["active"])

    removed = prev_active - curr_active
    added = curr_active - prev_active

    for name in sorted(removed):
        actions.append(f"卖出 {name}")
    for name in sorted(added):
        actions.append(f"买入 {name}")

    prev_offense = set(previous["offense"]["target_weights"].keys())
    curr_offense = set(current["offense"]["target_weights"].keys())
    off_removed = prev_offense - curr_offense
    off_added = curr_offense - prev_offense
    for name in sorted(off_removed):
        actions.append(f"卖出 {name}")
    for name in sorted(off_added):
        actions.append(f"买入 {name}")

    if not actions:
        return ["无需调仓"]

    return actions


def format_signal_report(signal: dict, previous_signal: dict | None = None,
                          replay_result: dict | None = None) -> str:
    """信号 dict → 中文可读报告字符串。"""
    lines = []
    lines.append(f"日期：{signal['date']}")
    lines.append("")

    # 期间回顾（间隔回放）
    replay_lines = _format_replay_segments(replay_result) if replay_result else []
    if replay_lines:
        lines.append("【期间回顾】")
        lines.extend(replay_lines)
        lines.append("")

    # 趋势强度
    lines.append("【趋势强度】")
    ts = signal["defense"]["trend_strengths"]
    if ts:
        for name, strength in ts.items():
            lines.append(f"  {name}：{strength:.4f}")
    else:
        lines.append("  无数据")
    lines.append("")

    # 熔断
    lines.append("【相关性熔断】")
    cb = signal["circuit_breaker"]
    lines.append(f"  状态：{'触发' if cb['triggered'] else '正常'}")
    lines.append(f"  平滑相关系数：{cb['smoothed_corr']:.4f}")
    lines.append("")

    # 回撤
    lines.append("【回撤止损】")
    ds = signal["drawdown_stop"]
    lines.append(f"  当前回撤：{ds['drawdown']:.2%}")
    lines.append(f"  止损档位：{ds['level']}")
    lines.append(f"  仓位系数：{ds['position_multiplier']:.2f}")
    lines.append("")

    # 目标持仓
    lines.append("【目标持仓】")
    def_weights = signal["defense"]["target_weights"]
    if def_weights:
        for name, w in def_weights.items():
            lines.append(f"  {name}：{w:.2%}")
    else:
        lines.append("  防御层空仓")
    off_weights = signal["offense"]["target_weights"]
    if off_weights:
        lines.append("  --- 进攻层 ---")
        for name, w in off_weights.items():
            lines.append(f"  {name}：{w:.2%}")
    lines.append("")

    # 操作指令——有回放时与回放最后一天 active 做比较
    if replay_result and replay_result["changes"]:
        # 用 replay 最后一天 active 构造 previous_signal 替代
        last_active = None
        if replay_result["daily_active"]:
            last_active = replay_result["daily_active"][-1]["active"]
        if last_active is not None:
            replay_prev = {
                "defense": {"active": list(last_active)},
                "offense": {"target_weights": {}},
                "circuit_breaker": {"triggered": False},
            }
            prev_for_compare = replay_prev
        else:
            prev_for_compare = previous_signal
    else:
        prev_for_compare = previous_signal

    lines.append("【操作指令】")
    actions = _compare_signals(signal, prev_for_compare)
    for action in actions:
        lines.append(f"  {action}")

    report = "\n".join(lines)
    return report


# ---- 状态文件 ----

def _load_state(state_dir: str) -> dict | None:
    """加载持仓状态文件，不存在返回 None。"""
    state_path = os.path.join(state_dir, STATE_FILENAME)
    if not os.path.exists(state_path):
        return None
    with open(state_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_state(state_dir: str, state: dict) -> None:
    """保存持仓状态文件。"""
    os.makedirs(state_dir, exist_ok=True)
    state_path = os.path.join(state_dir, STATE_FILENAME)
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2, default=str)


def _build_portfolio_value(prices: dict[str, pd.DataFrame],
                           state: dict | None) -> pd.Series:
    """构造组合净值序列。有历史状态则合并，无则从等权防御 ETF 从头计算。"""
    # 等权防御 ETF 日收益率 → 累积净值
    defense_names = [n for n in ["沪深300", "创业板", "纳指", "黄金", "国债ETF"] if n in prices]
    if not defense_names:
        return pd.Series(dtype=float)

    # 对齐所有防御 ETF 的收盘价
    closes = {}
    for name in defense_names:
        closes[name] = prices[name]["close"]
    close_df = pd.DataFrame(closes).dropna()
    returns = close_df.pct_change().dropna()
    eq_returns = returns.mean(axis=1)
    nav = (1 + eq_returns).cumprod()
    nav.name = "nav"

    # 若有历史状态，合并到历史末端
    if state and "portfolio_values" in state and state["portfolio_values"]:
        hist = pd.Series(
            [v["value"] for v in state["portfolio_values"]],
            index=pd.DatetimeIndex([v["date"] for v in state["portfolio_values"]]),
            name="nav",
        )
        # 拼接：历史 + 新数据（去重）
        combined = pd.concat([hist, nav])
        combined = combined[~combined.index.duplicated(keep="first")]
        combined = combined.sort_index()
        return combined

    return nav


def _signal_to_state(signal: dict, portfolio_values: pd.Series) -> dict:
    """将信号和净值序列转为可持久化的 state dict。"""
    pv_list = [
        {"date": str(idx.date()), "value": float(val)}
        for idx, val in portfolio_values.items()
    ]
    return {
        "last_date": signal["date"],
        "last_active": signal["defense"]["active"],
        "last_offense_weights": signal["offense"]["target_weights"],
        "last_cb_triggered": signal["circuit_breaker"]["triggered"],
        "portfolio_values": pv_list,
    }


def _previous_signal_from_state(state: dict) -> dict:
    """从 state dict 重构上一交易日信号摘要。"""
    return {
        "defense": {"active": state.get("last_active", [])},
        "offense": {"target_weights": state.get("last_offense_weights", {})},
        "circuit_breaker": {"triggered": state.get("last_cb_triggered", False)},
    }


# ---- 主入口 ----

def main(data_dir: str = "data", state_dir: str = "data") -> str:
    """
    每日信号主流程：加载数据 → 校验 → 算信号 → 出报告 → 保存状态。
    返回报告字符串。异常时 sys.exit(1)。
    """
    # 1. 加载
    prices = load_prices(data_dir)
    if not prices:
        print("错误：data/ 目录无 parquet 文件，无法生成信号", file=sys.stderr)
        sys.exit(1)

    # 2. 校验防御层标的完整
    loaded_defense = [n for n in CODE_TO_NAME.values() if n in prices]
    if len(loaded_defense) < 5:
        missing = [n for n in CODE_TO_NAME.values() if n not in prices]
        print(f"错误：防御层 ETF 不全，缺失：{missing}", file=sys.stderr)
        sys.exit(1)

    # 3. 校验交易日数
    min_len = min(len(prices[n]) for n in loaded_defense)
    if min_len < MIN_TRADING_DAYS:
        print(f"错误：交易日不足 {MIN_TRADING_DAYS} 天（最少 {min_len} 天）", file=sys.stderr)
        sys.exit(1)

    # 4. 构造组合净值
    state = _load_state(state_dir)
    portfolio_value = _build_portfolio_value(prices, state)

    # 5. 间隔回放
    replay_result = _replay_gap(prices, state)

    # 6. 算信号
    signal = generate_signal(prices, portfolio_value)

    # 7. 比较上一次信号
    prev_signal = None
    if state:
        prev_signal = _previous_signal_from_state(state)

    # 8. 格式化报告
    report = format_signal_report(signal, prev_signal, replay_result)

    # 9. 保存状态
    _save_state(state_dir, _signal_to_state(signal, portfolio_value))

    return report


if __name__ == "__main__":
    report = main()
    print(report)
