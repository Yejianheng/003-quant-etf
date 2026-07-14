# outcome.md — execution_lag=1 执行价修正

> 2026-07-13 | 回测引擎修复

## audit 报告

- **审计模型**：Qwen3-Max（异构，与当前推理模型不同厂商）
- **结果**：PASS
- **审计意见**：未发现安全或架构违规，允许执行写入

## 改动概要

**问题**：`backtest_engine.py` 在 `execution_lag=1` 时，用**收盘价**重估旧持仓后执行信号，导致过时持仓吃全天跌幅。

**fix**：
1. `execution_lag=1` 时，执行顺序改为 **执行(open) → 估值(close) → 信号**
2. 执行价从 `close` 改为 `open`
3. 现金守恒改用 `old_value_at_open`（旧持仓在开盘价下的市值），而非 `prev_nav`
4. `execution_lag=0` 路径不变

## 涉及文件

| 文件 | 操作 | 保护区 |
|------|------|--------|
| `src/backtest_engine.py` | 修改（~20行） | ✅ protected-files.json:12 |

## 验证计划

1. 跑全量测试（`pytest tests/ -v`）
2. 重新生成 nav_2026.html
3. 检查 07-13 Δ% 应从 -1.22% 变为约 -0.28%
