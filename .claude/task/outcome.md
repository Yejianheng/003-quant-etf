# 执行结果 — 每日信号脚本 daily_signal.py

> 执行时间: 2026-05-30 | 状态: 完成 | 验收: 待顾问审查

---

## 新增文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `scripts/daily_signal.py` | 新增 | 每日信号脚本，加载 parquet → 算信号 → 输出中文报告 |
| `tests/test_daily_signal.py` | 新增 | 14 条测试，覆盖 9 类场景 |

## 功能概要

`scripts/daily_signal.py` 提供三个公开函数 + main 入口：

- `load_prices(data_dir)` — 加载 data/ 下 ETF parquet，缺失跳过不崩溃
- `generate_signal(prices, portfolio_value)` — 复用现有引擎（`src/signal_generator`）
- `format_signal_report(signal, previous_signal)` — 信号 dict → 中文报告（含趋势强度/熔断/回撤/目标持仓/操作指令）
- `main()` — 端到端入口：校验（5 防御 ETF + 120 交易日）→ 构造组合净值 → 算信号 → 比较状态 → 出报告 → 写状态文件

状态文件 `data/position_state.json` 记录组合净值历史 + 上次持仓，用于跨日比较。

## 测试覆盖（14 passed）

| 场景 | 测试数 | 状态 |
|------|--------|------|
| 基础：5 ETF 全加载 → 完整报告 | 1 | PASSED |
| 基础：首次运行 → "首次建仓" | 2 | PASSED |
| 基础：信号不变 → "无需调仓" | 2 | PASSED |
| 基础：信号变化 → "卖出"/"买入" | 2 | PASSED |
| 边界：仅 4 ETF → exit 1 | 1 | PASSED |
| 边界：交易日 < 120 → exit 1 | 1 | PASSED |
| 边界：熔断触发 → "全部清仓" | 1 | PASSED |
| 异常：某 ETF 缺失 → 跳过其余正常 | 1 | PASSED |
| 异常：data/ 无 parquet → 报错退出 | 1 | PASSED |
| 杂项：空目录加载 / state 文件持久化 | 2 | PASSED |

## 全量回归

323 passed / 1 failed（预存 `test_loads_summary`，与本次无关）/ 3 skipped。零新增回归。

## 实跑验证

```bash
python scripts/daily_signal.py
```

输出完整中文报告：日期 2026-05-28，趋势强度（沪深300 3.57 / 创业板 4.90 / 纳指 6.36 / 黄金 -1.75 / 国债ETF 5.55），熔断正常（-0.21），回撤 -0.43%（normal），目标持仓 4 只等权 25%（黄金负趋势排除），操作指令"首次建仓"。

---

> 请顾问窗口审查。
