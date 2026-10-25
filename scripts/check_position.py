# [2026-10-23] 修改：组合净值改用回测引擎真实净值，回撤止损不再基于五 ETF 等权伪净值
# [2026-10-15] 修复：「当前持有」改用 held_names，不再用 defense.active 冒充持仓
# [2026-09-11] 修复：操作指令基线误取当日信号致恒输出「无需调仓」（v221）
# [2026-09-11] 修改：持仓段拆为「当前持有」（T-1 信号）+「次日目标仓位」（T 信号）
# [2026-07-24] 修改：适配三源交叉验证返回，一致数据自动入库（v214）
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

from scripts.update_data import update_single_etf, _write_parquet_incremental
from scripts.daily_signal import (
    load_prices,
    _load_state,
    _previous_signal_from_state,
    _prev_active_signal,
    _build_portfolio_value,
    _compare_signals,
    _replay_gap,
    _format_replay_segments,
    _save_state,
    _signal_to_state,
    held_names,
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

    # 1. 拉取 5 ETF 数据（三源交叉验证，一致则自动入库）
    codes = list(ETF_UNIVERSE.values())
    results = []
    for code in codes:
        results.append(update_single_etf(code, data_dir))

    # 三源/两源一致 → 自动入库
    for r in results:
        if r["ok"] and not r.get("needs_verify") and "new_data" in r:
            _write_parquet_incremental(r["code"], r["new_data"], data_dir)

    # 检查待核验
    needs_verify = [r for r in results if r.get("needs_verify")]
    if needs_verify:
        print(f"\n[待核验] {len(needs_verify)} 只需要 Web 核验")
        for r in needs_verify:
            print(f"  {r['name']}({r['code']}) {r['source']} close={r['latest_close']:.3f}")
        print("---")
        print("请执行窗口 AI WebSearch 核验以上收盘价：")
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

    # 4. 构造组合净值（回测引擎真实净值）+ 生成信号
    portfolio_value = _build_portfolio_value(prices)
    signal = generate_signal(prices, portfolio_value)

    # 5. 比较上一次信号（有回放则用回放最后一天对比）
    prev_signal = None
    if state:
        prev_signal = _previous_signal_from_state(state)

    # 操作指令基线 = 当前实际持仓（T-1 收盘信号），与图表 T 日持仓口径一致
    prev_signal = _prev_active_signal(replay_result, prev_signal)

    # 6. 保存 state（避免下次重复回放）
    _save_state(data_dir, _signal_to_state(signal, portfolio_value))

    # 7. 输出持仓报告
    today = date.today().strftime("%Y-%m-%d")
    target_weights = signal["defense"]["target_weights"]

    print(f"=== {today} 仓位报告 ===")
    print()

    # 当前实际持仓 = T-1 收盘信号（当日已在开盘按该信号换仓）
    # [2026-10-15] 修复：改用 held_names —— 此前直接用 defense.active（趋势幸存名单），
    # 熔断触发或乘数归零时 active 依然非空，会报出并不存在的持仓。
    held = held_names(prev_signal)
    print("【当前持有】")
    if held:
        print(f"  持有：{'、'.join(held)}（{len(held)} 只等权）")
    else:
        print("  持有：空仓（100% 逆回购）")
    print()

    # 次日目标 = T 收盘信号，次日开盘执行
    print("【次日目标仓位】")
    final_mult = signal["execution"]["final_multiplier"]
    total_w = sum(target_weights.values())
    for name in DEFENSE_NAMES:
        w = target_weights.get(name)
        if w is not None:
            print(f"  {name}    {w * final_mult:.1%}")
        else:
            print(f"  {name}    —")
    scaled_total = total_w * final_mult
    cash_pct = max(0.0, 1.0 - scaled_total)
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
    final_mult = signal["execution"]["final_multiplier"]
    print(f"  仓位乘数：combined_mult={final_mult:.3f}")

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
