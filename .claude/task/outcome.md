# 执行结果

> 执行时间：2026-06-18 | 方向来源：.claude/task/direction.md

## 任务：基准完善 + 成本细化 + 图表更新

### 提交记录

| 提交 | 内容 |
|------|------|
| `v190-20260618-9` | 步骤 1：nav_chart 等权基准 + 60/40 基准线（图表 + 表格列） |
| `v190-20260618-10` | 步骤 2+4：per-ETF 价差（volume→三档 3/8/15bp）+ benchmark_6040 返回值 |
| `v190-20260618-11` | 步骤 3：nav_chart 表格底部换手率 + 交易成本统计行 |
| `v190-20260618-12` | 步骤 0：重跑 nav_chart.py + slippage_scan.py 生成最终 HTML/CSV |

### 修改文件清单

| 文件 | 操作 | 保护区 |
|------|------|--------|
| `scripts/nav_chart.py` | 修改：等权/60/40 基准线（图表+表格列）、换手统计行 | 否 |
| `scripts/slippage_scan.py` | 修改：volume→流动性三档价差、per-ETF slippage_bps_map | 否 |
| `src/backtest_engine.py` | 修改：slippage_bps_map 参数 + benchmark_6040 返回值 | 是 |
| `tests/test_nav_chart.py` | 修改：dataset 7→9、颜色 +2、表头 +2列、benchmark + turnover 测试 | 否 |

### 步骤 0 — 图表重跑验证

`nav_2026.html` 内容检查（8/8 通过）：

| 检查项 | 状态 |
|------|------|
| repoBand 背景带插件 | OK |
| 逆回购净值虚线 | OK |
| 5 ETF 等权基准线 | OK |
| 60/40 股债基准线 | OK |
| 表格等权净值列 | OK |
| 表格 60/40 净值列 | OK |
| 年化换手率统计 | OK |
| 累计交易成本统计 | OK |

`slippage_scan_results.csv` — per-ETF 价差四场景：

| 场景 | 倍数 | avg价差 | 佣金 | Sharpe | 年化 | 最大回撤 |
|------|------|---------|------|--------|------|---------|
| 理想 | ×0.0 | 0bp | 万0.0 | 0.25 | 4.7% | -56.3% |
| 乐观 | ×1.0 | 6bp | 万2.5 | 0.21 | 4.0% | -56.8% |
| 中性 | ×2.0 | 13bp | 万2.5 | 0.21 | 4.0% | -56.8% |
| 悲观 | ×3.0 | 19bp | 万5.0 | 0.18 | 3.4% | -56.9% |

### 测试结果

| 测试文件 | 结果 |
|------|------|
| `tests/test_nav_chart.py` | 7/7 通过 |
| `tests/test_backtest_engine.py` | 4/4 通过 |

### 审计流程

- [x] CLI validate 通过
- [x] CLI audit 通过（Qwen3-Max 盲审）
- [x] gate 标记 + 令牌 Edit
- [x] 11/11 测试全绿

### 验收对照

- [x] `nav_2026.html` 图表含等权、60/40 两条新基准线 + repo 背景带
- [x] 表格含等权净值、60/40 净值两列 + 底部换手/成本统计
- [x] `slippage_scan_results.csv` 已按 per-ETF 价差重跑
- [x] `run_backtest()` 返回 `benchmark_6040`
- [x] 11/11 零回归

---

请顾问窗口审查。
