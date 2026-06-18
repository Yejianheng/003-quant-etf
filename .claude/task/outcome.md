# 执行结果

> 执行时间：2026-06-18 | 方向来源：.claude/task/direction.md

## 任务：修复数据管线跨 ETF 不完整日导致的 NAV 暴跌

### 根因

6/18 部分 ETF 有数据（黄金、国债ETF）、部分没有（沪深300、创业板、纳指）。回测引擎估值时无数据 ETF 被静默跳过，仅剩有数据 ETF + 残差 repo_cash，导致 NAV 单日 -51.8%。

### 修复

| 文件 | 改动 | 保护区 |
|------|------|--------|
| `src/backtest_engine.py` | `run_backtest()` 新增 `min_active_etfs` 参数（默认1），可用 ETF 不足时跳过当天（NAV 保持前值） | 是 |
| `src/data_pipeline.py` | 新增 `trim_isolated_dates()` 剔除跨 ETF 不一致的孤立交易日 | 否 |
| `scripts/update_data.py` | `main()` 更新完成后调用 `trim_isolated_dates()` | 否 |

### 验证

| 指标 | 修复前 | 修复后 |
|------|--------|--------|
| Sharpe | 0.233 | **1.153** |
| 年化 | 4.1% | **10.7%** |
| 回撤 | -51.9% | **-9.9%** |
| 单日 >10% 暴跌 | 1 天（6/18） | **0 天** |
| 数据对齐 | 各 ETF 日期不一致 | **5 ETF 严格对齐 3128 天** |

### 审计流程

- [x] CLI validate 通过
- [x] CLI audit 通过（Qwen3-Max 盲审）
- [x] gate 标记 + 令牌 Edit
- [x] 11/11 测试全绿

### 验收对照

- [x] 6/18 数据对齐（5 ETF 全无数据，截到 6/17）
- [x] NAV 不再因不完整日单日暴跌
- [x] 11/11 pytest 零回归
- [x] `nav_2026.html` 已更新
- [x] `four_tables_report.html` 已更新

---

请顾问窗口审查。
