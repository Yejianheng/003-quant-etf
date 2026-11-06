# [2026-11-06] 修复：断层回放改消费回测引擎熔断/乘数状态，杜绝熔断持续期幽灵买卖与虚假持仓
# [2026-10-23] 修复：组合净值改用回测引擎真实策略净值（T+1 开盘执行），废弃五 ETF 等权伪净值
# [2026-09-11] 修复：操作指令基线误取当日信号致恒输出「无需调仓」，改取上一交易日信号（v221）
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

from src.backtest_engine import run_backtest
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

def _parse_active_field(value) -> list[str]:
    """解析回测记录 defense_active 字段（分号分隔的中文名）。"""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return []
    return [name.strip() for name in str(value).split(";") if name.strip()]


def _replay_gap(prices: dict[str, pd.DataFrame],
                state: dict | None,
                records_df: pd.DataFrame | None = None) -> dict:
    """逐日回放 state.last_date 到最新数据日之间的真实信号。

    传入 records_df（回测引擎逐日记录）时，持仓以引擎的
    circuit_breaker_triggered / final_multiplier / defense_active 为准 ——
    熔断或乘数归零期间持仓为空，趋势翻转不得被当成买卖。
    不传 records_df 时退回纯趋势回放（仅保留给旧测试与离线诊断）。

    返回:
    {
        "gap_trading_days": int,
        "last_date": str,
        "today": str,
        "start_held": [etf],          # 断层起点实际持仓
        "daily_active": [{date, active, held, circuit_breaker, final_multiplier}],
        "changes": [{date, event, etf, reason}],   # reason: 熔断 / 趋势
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

    # 回测引擎快照（按日期索引）——有 records 时以其为准，趋势仅作缺失兜底
    status_lookup = None
    if records_df is not None and len(records_df) > 0:
        status_lookup = {}
        for idx, row in records_df.iterrows():
            status_lookup[str(pd.Timestamp(idx).date())] = {
                "active": _parse_active_field(row.get("defense_active", "")),
                "cb": bool(row.get("circuit_breaker_triggered", False)),
                "multiplier": float(row.get("final_multiplier", 1.0)),
            }

    if status_lookup is not None:
        start_cb = bool(state.get("last_cb_triggered", False))
        start_mult = float(state.get("last_final_multiplier", 1.0))
        prev_cb = start_cb
        prev_held = (set() if (start_cb or start_mult == 0)
                     else set(state.get("last_active", [])))
    else:
        prev_cb = False
        prev_held = set(state.get("last_active", []))
    start_held = sorted(prev_held)

    for d in gap_dates:
        day_key = str(d.date())

        if status_lookup is not None:
            snap = status_lookup.get(day_key)
            if snap is not None:
                active = set(snap["active"])
                cb, multiplier = snap["cb"], snap["multiplier"]
            else:
                # 引擎记录缺失 → 退回趋势计算，按未熔断处理
                active = set()
                for name, df in prices.items():
                    subset = df[df.index <= d]
                    if len(subset) < trend_window:
                        continue
                    if trend_strength(subset["close"], window=trend_window) > 0:
                        active.add(name)
                cb, multiplier = False, 1.0

            held = set() if (cb or multiplier == 0) else set(active)
            daily_active.append({
                "date": day_key,
                "active": sorted(active),
                "held": sorted(held),
                "circuit_breaker": cb,
                "final_multiplier": multiplier,
            })
            reason = "熔断" if cb != prev_cb else "趋势"
            removed, added = prev_held - held, held - prev_held
            prev_held, prev_cb = held, cb
        else:
            active = set()
            for name, df in prices.items():
                subset = df[df.index <= d]
                if len(subset) < trend_window:
                    continue
                ts = trend_strength(subset["close"], window=trend_window)
                if ts > 0:
                    active.add(name)

            daily_active.append({"date": day_key, "active": list(active)})
            reason = "趋势"
            removed, added = prev_held - active, active - prev_held
            prev_held = active

        for etf in sorted(removed):
            changes.append({"date": day_key, "event": "removed",
                            "etf": etf, "reason": reason})
        for etf in sorted(added):
            changes.append({"date": day_key, "event": "added",
                            "etf": etf, "reason": reason})

    return {
        "gap_trading_days": len(gap_dates),
        "last_date": last_date_str,
        "today": str(today.date()),
        "start_held": start_held,
        "daily_active": daily_active,
        "changes": changes,
    }


def _entry_held(entry: dict) -> set:
    """取回放日的实际持仓：新格式用 held，旧格式退回 active。"""
    if "held" in entry:
        return set(entry["held"])
    return set(entry.get("active", []))


def _entry_is_repo(entry: dict | None) -> bool:
    """该回放日是否处于熔断空仓状态。"""
    return bool(entry and entry.get("circuit_breaker", False))


def _format_pool_line(start: str, end: str, held: set, repo: bool) -> str:
    """格式化一段无变化区间。"""
    if not held and repo:
        return f"  {start} → {end}  空仓（熔断中），无变化"
    names_str = "、".join(sorted(held)) if held else "空仓"
    return f"  {start} → {end}  {len(held)} 只（{names_str}），无变化"


def _format_replay_segments(replay: dict) -> list[str]:
    """将 replay result 格式化为人类可读的"期间回顾"行列表。

    持仓口径 = held（已含熔断/乘数折算）。熔断持续期只能报空仓，不得出现
    买入/卖出 —— 趋势翻转在熔断期间不产生任何交易。
    """
    if not replay or replay["gap_trading_days"] == 0:
        return []

    daily = replay.get("daily_active") or []
    changes = replay["changes"]

    if not changes:
        if daily:
            held, repo = _entry_held(daily[0]), _entry_is_repo(daily[0])
        else:
            held, repo = set(), False
        return [_format_pool_line(replay["last_date"], replay["today"], held, repo)]

    lines = []
    seg_start = replay["last_date"]
    if replay.get("start_held") is not None:
        last_held = set(replay["start_held"])
    elif daily:
        last_held = _entry_held(daily[0])
    else:
        last_held = set()
    last_repo = _entry_is_repo(daily[0]) if daily else False

    for i, day in enumerate(daily):
        day_changes = [c for c in changes if c["date"] == day["date"]]
        if not day_changes:
            continue

        day_held = _entry_held(day)
        day_repo = _entry_is_repo(day)

        # 变化前的稳定段
        if day_held != last_held or i == 0:
            lines.append(_format_pool_line(seg_start, day["date"], last_held, last_repo))

        cb_events = [c for c in day_changes if c.get("reason") == "熔断"]
        trend_events = [c for c in day_changes if c.get("reason") != "熔断"]

        if cb_events:
            sold = [c for c in cb_events if c["event"] == "removed"]
            bought = [c for c in cb_events if c["event"] == "added"]
            if sold:
                lines.append(f"  {day['date']}  全部清仓（熔断触发）")
            if bought:
                names = "、".join(sorted(c["etf"] for c in bought))
                lines.append(f"  {day['date']}  熔断解除，买入 {names}")

        for c in trend_events:
            verb = "买入" if c["event"] == "added" else "卖出"
            lines.append(f"  {day['date']}  {verb} {c['etf']}（趋势转{'正' if c['event'] == 'added' else '负'}）")

        seg_start = day["date"]
        last_held = day_held
        last_repo = day_repo

    # 最后一段：从末次变化到今日
    if daily and seg_start != replay["today"]:
        final = daily[-1]
        lines.append(_format_pool_line(seg_start, replay["today"],
                                       _entry_held(final), _entry_is_repo(final)))

    return lines


# ---- 报告格式化 ----

def _effective_holdings(sig: dict | None) -> set:
    """信号对应的实际持仓名单 —— 熔断或仓位乘数归零时为空仓。

    趋势 active 只是幸存名单，不等于持仓（CLAUDE.md 已记载的语义陷阱）。
    """
    if not sig:
        return set()
    if sig.get("circuit_breaker", {}).get("triggered"):
        return set()
    execution = sig.get("execution") or {}
    if execution.get("final_multiplier", 1.0) == 0:
        return set()
    return set(sig.get("defense", {}).get("active", []))


def _compare_signals(current: dict, previous: dict | None) -> list[str]:
    """比较当前与上一交易日信号，返回操作指令列表。"""
    if previous is None:
        if current["circuit_breaker"]["triggered"]:
            return ["全部清仓（熔断触发）"]
        return ["首次建仓"]

    # 熔断触发 → 清仓；但若昨日已在熔断中（早已空仓），再报一次是重复指令。
    # [2026-10-15] 修复：此前只读 current，previous 完全失效，导致熔断持续期间
    # 每天都输出「全部清仓」。与 v221 修的「恒输出无需调仓」是同一族的单边判断 bug。
    if current["circuit_breaker"]["triggered"]:
        if previous.get("circuit_breaker", {}).get("triggered"):
            return ["无需调仓（熔断持续）"]
        return ["全部清仓（熔断触发）"]

    actions = []
    prev_active = _effective_holdings(previous)
    curr_active = _effective_holdings(current)

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

    # 操作指令——基线 = 当前实际持仓（T-1 收盘信号），而非今日信号
    prev_for_compare = _prev_active_signal(replay_result, previous_signal)

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


def _build_backtest(prices: dict[str, pd.DataFrame],
                    state: dict | None = None) -> tuple[pd.Series, pd.DataFrame]:
    """跑回测引擎（T+1 开盘执行），返回 (归一化净值, 逐日记录)。

    [2026-11-06] 新增：把 records_df 一并返回，供 _replay_gap 读取逐日
    熔断/仓位乘数状态，避免断层回放只看趋势产生的幽灵交易。
    """
    result = run_backtest(prices, params=DEFAULT_PARAMS, execution_lag=1)
    records = result["records_df"]
    nav = pd.Series(records["nav"].values, index=records.index, name="nav")
    return nav / nav.iloc[0], records  # 归一到 1.0 起，回撤比例不变


def _build_portfolio_value(prices: dict[str, pd.DataFrame],
                           state: dict | None = None) -> pd.Series:
    """构造组合净值序列 — 回测引擎（T+1 开盘执行）的真实策略净值。

    [2026-10-23] 修复：此前用「五只防御 ETF 等权日收益 cumprod」冒充策略净值，
    不含趋势过滤/熔断/仓位乘数/现金，导致回撤止损严重误报（曾报 -13.4%，
    真实仅 -3.6%）。现改为直接复用回测引擎净值，与图表口径一致。

    state 参数仅为兼容旧调用保留，不参与计算：旧 state 中的 portfolio_values
    是同一等权伪净值，合并会再次污染回撤止损。
    """
    nav, _ = _build_backtest(prices)
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
        "last_final_multiplier": signal["execution"]["final_multiplier"],
        "portfolio_values": pv_list,
    }


def held_names(previous_signal: dict | None) -> list[str]:
    """由上一交易日信号推出「当前实际持有」的 ETF 名单。

    [2026-10-15] 新增：此前 check_position.py 直接用 defense.active，而 active 是
    趋势过滤幸存名单，不含熔断与仓位乘数 —— 熔断清零时 active 依然非空，
    于是报出「持有 X、Y」而实际是 100% 逆回购。这是 CLAUDE.md 已记载的
    final_multiplier 语义陷阱的另一张脸。

    实际持仓为空的条件（任一满足）：
      - 熔断触发（资金全部路由到逆回购）
      - final_multiplier == 0（回撤止损清仓）
    旧 state 无 execution 字段时退回 active，保持向后兼容。
    """
    if not previous_signal:
        return []
    if previous_signal.get("circuit_breaker", {}).get("triggered"):
        return []
    execution = previous_signal.get("execution") or {}
    if "final_multiplier" in execution and execution["final_multiplier"] == 0:
        return []
    return list(previous_signal.get("defense", {}).get("active", []))


def _prev_active_signal(replay_result: dict | None,
                        fallback: dict | None) -> dict | None:
    """返回「操作指令」的对比基线信号 —— 即当前实际持仓。

    图表口径：T 日持仓 = T-1 日收盘信号。回放 daily_active 的最后一项是 T 日信号
    （= 次日目标），故 T 日实际持仓应取 daily_active[-2]，而非 [-1]。

    规则：
      - 回放覆盖 T-1（gap >= 2）→ 用 daily_active[-2] 构造基线，忽略 fallback
      - 否则（gap <= 1，T-1 不在回放内）→ 原样返回 fallback
      - 两者皆无 → None（首次建仓）

    历史：v221 前基线误取 daily_active[-1]（= 今日信号），等于自己跟自己比，
    恒输出「无需调仓」，且只在当日发生趋势变化时发作——恰是最需要指令的日子。
    """
    daily_active = (replay_result or {}).get("daily_active") or []
    if len(daily_active) >= 2:
        entry = daily_active[-2]
        # [2026-11-06] 修复：此前硬编码 circuit_breaker.triggered=False，
        # 断层回放时丢弃 state 中真实的熔断状态，导致 held_names 用趋势名单
        # 冒充持仓、_compare_signals 重复报「全部清仓」。
        active = entry["held"] if "held" in entry else entry.get("active", [])
        baseline = {
            "defense": {"active": list(active)},
            "offense": {"target_weights": {}},
            "circuit_breaker": {"triggered": bool(entry.get("circuit_breaker", False))},
        }
        if "final_multiplier" in entry:
            baseline["execution"] = {"final_multiplier": float(entry["final_multiplier"])}
        return baseline
    return fallback


def _previous_signal_from_state(state: dict) -> dict:
    """从 state dict 重构上一交易日信号摘要。

    [2026-10-15] 补充 execution.final_multiplier：held_names 需要它判断是否空仓。
    旧 state 无该字段 → 不放入 execution，held_names 会退回 active。
    """
    previous = {
        "defense": {"active": state.get("last_active", [])},
        "offense": {"target_weights": state.get("last_offense_weights", {})},
        "circuit_breaker": {"triggered": state.get("last_cb_triggered", False)},
    }
    if "last_final_multiplier" in state:
        previous["execution"] = {"final_multiplier": state["last_final_multiplier"]}
    return previous


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

    # 4. 构造组合净值（回测引擎真实净值，不读 state 旧伪净值）
    state = _load_state(state_dir)
    portfolio_value, records = _build_backtest(prices)

    # 5. 间隔回放（以回测引擎逐日熔断/乘数状态为准）
    replay_result = _replay_gap(prices, state, records_df=records)

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
