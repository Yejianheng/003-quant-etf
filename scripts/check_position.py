# [2026-06-25] 新增：间隔回放 + 期间回顾报告段
# [2026-06-23] 新增：新鲜度门禁 — 数据不齐禁止输出仓位
# [2026-06-11] 新增：仓位三合一脚本 — 更新数据 → 持仓报告 + 操作指令 + 更新图表
"""
仓位三合一脚本：一步完成数据更新、持仓报告、图表更新。
用法：python scripts/check_position.py
"""
import os
import sys
from datetime import date

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.update_data import update_single_etf
from scripts.daily_signal import (
    load_prices,
    _load_state,
    _previous_signal_from_state,
    _build_portfolio_value,
    _compare_signals,
    _replay_gap,
    _format_replay_segments,
    _save_state,
    _signal_to_state,
)
from src.signal_generator import generate_signal, DEFAULT_PARAMS, DEFENSE_NAMES
from src.etf_universe import ETF_UNIVERSE
from src.data_pipeline import check_freshness
from scripts.nav_chart import main as update_chart

DATA_DIR = "data"
OUTPUT_PATH = "nav_2026.html"


def main() -> None:
    data_dir = DATA_DIR
    output_path = OUTPUT_PATH

    # 1. 拉取 5 ETF 数据（不入库，待 Web 核验）
    codes = list(ETF_UNIVERSE.values())
    results = []
    for code in codes:
        results.append(update_single_etf(code, data_dir))

    # 检查待核验
    needs_verify = [r for r in results if r.get("needs_verify")]
    if needs_verify:
        print(f"\n[待核验] {len(needs_verify)} 只需要 Web 核验")
        for r in needs_verify:
            print(f"  {r['name']}({r['code']}) {r['source']} close={r['latest_close']:.3f}")
        print("---")
        print("请执行窗口 AI WebFetch 核验以上收盘价：")
        print("  https://q.stock.sohu.com/cn/{code}/lshq.shtml")
        print("核验通过后运行入库脚本，然后重新执行 仓位 命令。")
        sys.exit(0)

    # 检查失败
    failures = [r for r in results if not r["ok"]]
    if failures:
        print("\n[失败]")
        for r in failures:
            print(f"  {r['name']}({r['code']}): {r['reason']}")
        sys.exit(1)

    # 新鲜度门禁：任一 ETF 未更新到今日 → 中止
    stale = check_freshness(codes, data_dir)
    if stale:
        names = [k for k, v in ETF_UNIVERSE.items() if v in stale]
        print(f"[门禁] 以下 ETF 未更新到今日：{', '.join(names or stale)}，仓位报告已中止。请稍后重试。", file=sys.stderr)
        sys.exit(1)

    # 2. 加载数据
    prices = load_prices(data_dir)
    if not prices:
        print("错误：data/ 目录无 parquet 文件", file=sys.stderr)
        sys.exit(1)

    # 3. 间隔回放
    state = _load_state(data_dir)
    replay_result = _replay_gap(prices, state)

    # 4. 构造组合净值 + 生成信号
    portfolio_value = _build_portfolio_value(prices, state)
    signal = generate_signal(prices, portfolio_value)

    # 5. 比较上一次信号（有回放则用回放最后一天对比）
    prev_signal = None
    if state:
        prev_signal = _previous_signal_from_state(state)

    # 有回放且期间有变化 → 操作指令基于回放最后一天 active
    if replay_result and replay_result["changes"]:
        last_active = None
        if replay_result["daily_active"]:
            last_active = replay_result["daily_active"][-1]["active"]
        if last_active is not None:
            prev_signal = {
                "defense": {"active": list(last_active)},
                "offense": {"target_weights": {}},
                "circuit_breaker": {"triggered": False},
            }

    # 6. 保存 state（避免下次重复回放）
    _save_state(data_dir, _signal_to_state(signal, portfolio_value))

    # 7. 输出持仓报告
    today = date.today().strftime("%Y-%m-%d")
    target_weights = signal["defense"]["target_weights"]

    print(f"=== {today} 仓位报告 ===")
    print()

    print("【当前持仓】")
    total_w = sum(target_weights.values())
    for name in DEFENSE_NAMES:
        w = target_weights.get(name)
        if w is not None:
            print(f"  {name}    {w:.1%}")
        else:
            print(f"  {name}    —")
    cash_pct = max(0.0, 1.0 - total_w)
    print(f"  现金        {cash_pct:.1%}")
    print()

    # 期间回顾
    if replay_result and replay_result["gap_trading_days"] > 0:
        replay_lines = _format_replay_segments(replay_result)
        if replay_lines:
            print("【期间回顾】")
            for line in replay_lines:
                print(line)
            print()

    print("【操作指令】")
    actions = _compare_signals(signal, prev_signal)
    for action in actions:
        print(f"  {action}")
    print()

    # 8. 风控状态
    print("【风控状态】")
    active_count = len(signal["defense"]["active"])
    total_count = len(DEFENSE_NAMES)
    removed_names = [n for n in DEFENSE_NAMES if n not in signal["defense"]["active"]]
    removed_str = f"（{''.join(removed_names)}剔除）" if removed_names else ""
    print(f"  趋势过滤：{active_count}/{total_count} 通过{removed_str}")

    sf = signal["defense"]["scaling_factor"]
    print(f"  波动率缩放：sf={sf:.2f}")

    cb = signal["circuit_breaker"]
    print(f"  相关性熔断：{'触发' if cb['triggered'] else '正常'}（{cb['smoothed_corr']:.2f}）")

    ds = signal["drawdown_stop"]
    print(f"  回撤止损：{ds['level']}（{ds['drawdown']:.1%}）")
    print()

    # 9. 更新图表
    update_chart(data_dir=data_dir, output_path=output_path)
    print(f"图表已更新 → {output_path}")


if __name__ == "__main__":
    main()
