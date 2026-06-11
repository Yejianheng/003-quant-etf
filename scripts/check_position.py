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
)
from src.signal_generator import generate_signal, DEFAULT_PARAMS, DEFENSE_NAMES
from src.etf_universe import ETF_UNIVERSE
from scripts.nav_chart import main as update_chart

DATA_DIR = "data"
OUTPUT_PATH = "nav_2026.html"


def main() -> None:
    data_dir = DATA_DIR
    output_path = OUTPUT_PATH

    # 1. 更新 5 ETF parquet
    codes = list(ETF_UNIVERSE.values())
    for code in codes:
        update_single_etf(code, data_dir)

    # 2. 加载数据
    prices = load_prices(data_dir)
    if not prices:
        print("错误：data/ 目录无 parquet 文件", file=sys.stderr)
        sys.exit(1)

    # 3. 构造组合净值 + 生成信号
    state = _load_state(data_dir)
    portfolio_value = _build_portfolio_value(prices, state)
    signal = generate_signal(prices, portfolio_value)

    # 4. 比较上一次信号
    prev_signal = None
    if state:
        prev_signal = _previous_signal_from_state(state)

    # 5. 输出持仓报告
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

    print("【操作指令】")
    actions = _compare_signals(signal, prev_signal)
    for action in actions:
        print(f"  {action}")
    print()

    # 6. 风控状态
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

    # 7. 更新图表
    update_chart(data_dir=data_dir, output_path=output_path)
    print(f"图表已更新 → {output_path}")


if __name__ == "__main__":
    main()
