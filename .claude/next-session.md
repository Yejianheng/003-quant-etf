# 下一会话

> 顾问每次会话结束前更新。新会话顾问读取此文件恢复上下文。

## 当前阶段

策略审计与基准完善已完成。7 项缺口关 5 项，策略参数 v0.15 封存发布。进入维护观察期。

## 本次结论

1. **缺口关闭**：G1（等权基准）、G2（60/40 基准）、G4（per-ETF 价差）、G5（换手率统计）、G7（不完整日防御）全部修复。
2. **参数终选**：target_vol_beta = 0.15（生产），0.08（保守备份）。理由：年化 +1.4pp vs 0.08，回撤 -13.1% 距 20% 硬约束有 7pp 安全垫。
3. **策略定性**：α≈0，择时系数≈0，偏度≈-0.05。纯风险预算器，不做方向预测。
4. **熔断确认**：(0.0, 60, 5) 恰好最优组合，三维扫描无悬崖退化。
5. **宏观无用**：股债相关性 R²=0.32（CN 10Y 主导），宏观指标不进决策链。
6. **双 tag 封存**：`v0.15-release`（生产）、`v0.08-canonical`（备份），覆盖全部决策空间。

## 已完成

- [x] 四张表收益归因系统（`attribution/` 目录，7 模块 + 7 测试文件）
- [x] `four_tables_report.html` 首次生成（R²=0.46, α≈0, 偏度≈-0.05）
- [x] 缺口审计 7 项关 5 项（`attribution/gap_audit.md`）
- [x] 逆回购可视化（`nav_chart.py` repo 背景带 + 净值线）
- [x] 数据管线不完整日修复（`trim_isolated_dates()` + `min_active_etfs`）
- [x] target_vol_beta 重扫描（0.04→0.22，选定 0.15 生产）
- [x] 基准对比表（策略 vs 等权 vs 60/40）
- [x] `attribution/system_audit.md` 系统审计文件（9 节完整技术文档）
- [x] 熔断三维鲁棒性扫描（corr_threshold × window × sma_window）
- [x] 股债相关性宏观分解（R²=0.32，CN 10Y 唯一主导）
- [x] 双 tag 封存发布（`v0.15-release` + `v0.08-canonical`）

## 待处理

- [ ] G3（全天候基准）：需先定义资产池和权重方案，搁置
- [ ] G6（2008 压力测试）：五只 ETF 全部 2011+ 上市，需合成数据，搁置
- [ ] 方向性讨论后续：`方向性讨论.md` 中的开放议题

## 重要上下文

### 策略核心参数（生产环境）

```
target_vol_beta = 0.15    # 生产（v0.15-release）
target_vol_beta = 0.08    # 保守备份（v0.08-canonical）
trend_window = 40
ewma_lambda = 0.94
defense_ratio = 1.00
corr_threshold = 0.0
drawdown = [0.08, 0.12, 0.18]
vol_tolerance = 0.012
```

### 基准对比（当前数据 3128 天）

| | 策略 (0.15) | 策略 (0.08) | 5 ETF 等权 | 60/40 |
|------|:--:|:--:|:--:|:--:|
| 年化 | 13.1% | 11.7% | 11.9% | 5.6% |
| 回撤 | -13.1% | -11.0% | -22.2% | -29.0% |
| Sharpe | 1.23 | 1.28 | 0.92 | 0.42 |

### 核心文件

- `attribution/system_audit.md` — 系统审计文件（新窗口必读）
- `attribution/gap_audit.md` — 缺口审计（7 关 5，2 搁置）
- `attribution/report.py` — HTML 报表，`generate_four_tables_report()`
- `scripts/four_tables.py` — 归因入口
- `scripts/nav_chart.py` — 2026 净值图表（含 repo 可视化）
- `output/four_tables_report.html` — 最新报表
- `output/nav_2026.html` — 2026 净值图表
- `src/data_pipeline.py` — 含 `trim_isolated_dates()`（v190-15）
- `src/backtest_engine.py` — 含 `min_active_etfs` 参数（v190-15）

### 三类已知表现模式

1. **慢牛最差**：2017 策略 +1.1% vs 沪深300 +20.7%，74% 空仓。趋势强度在慢牛中反复穿越零轴，反复剔除-重新入场，是策略的天然盲区。
2. **liquidate 从未触发**：12 年内 18% 线一次未破。halve@12% 足以在触发前控住。回撤参数是"睡得好"保险，不是频繁执行的操作。
3. **熔断唯一悬崖**：corr_threshold 从 0.0 → 0.05 回撤即跳至 -17.3%（逼近 liquidate 18%）。正向偏离是唯一需要警惕的方向，负向偏离不危险（多空仓几天而已）。
