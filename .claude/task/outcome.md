# 执行发现 — 仓位报告趋势方向表述错误

> 2026-07-09 | 来源：`仓位` 命令输出 | 执行者：@执行

## 现象

`scripts/check_position.py` 输出的期间回顾中，关于创业板趋势反转的方向表述与实际相反。

## 数据核实

| 日期 | 创业板收盘 | 40日 trend_strength | 趋势状态 |
|------|-----------|-------------------|---------|
| 2026-07-08 | 3.867 | **-0.1065** | 空头（inactive） |
| 2026-07-09 | 4.040 (+4.5%) | **+0.1664** | 多头（active） |

**实际：** 由空翻多（inactive → active）
**脚本输出：** 声称由多翻空（方向反了）

## 代码位置

趋势变化描述在 `scripts/daily_signal.py:185`：

```python
lines.append(f"  {day['date']}  {verb} {c['etf']}（趋势转{'正' if c['event'] == 'added' else '负'}）")
```

- `_replay_gap()` (line 105-132) 负责计算 daily_active 及变化事件（added/removed）
- `_format_replay_segments()` (line 135-200) 格式化输出

## 初步判断

事件类型判定逻辑（added=趋势转正, removed=趋势转负）本身是正确的。问题可能出在：

1. `_replay_gap()` 中 prev_active 的初始值从 state.last_active 获取，若 state 已包含了当日信号，prev_active 已是最新值，导致 added/removed 判定错位
2. 或者回放循环中 prev_active 与当日 active 比较时出现逻辑反转

## 需要顾问审查

- 趋势反转方向为何与数据相反
- 修复方案
