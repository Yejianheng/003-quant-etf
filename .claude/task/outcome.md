# 执行结果

> 执行时间：2026-06-18 | 方向来源：.claude/task/direction.md

## 任务：用生产参数 (0.15) 重跑全量历史数据，替换 system_audit.md

### 步骤 1：确认生产参数 ✅

`DEFAULT_PARAMS['target_vol_beta'] = 0.15`, `vol_tolerance = 0.0225` — 已是生产值。

### 步骤 2：生成三参数逐年对比表 ✅

`output/yearly_comparison_3betas.csv` — 三 beta 并排（0.08/0.10/0.15）收益+回撤+沪深300+等权基准，2014-2026，T+1 执行。

### 步骤 3：更新 system_audit.md §3 ✅

- §3.1 全期绩效：更新为 T+1 数据（Sharpe 1.06, MaxDD -13.6%）
- §3.2 逐年表现：三参数并排对比表
- §3.3 四 regime：统一 beta=0.15, T+1 执行
- §3.4 极端行情：统一 beta=0.15, T+1 执行
- §3.5 最差/最好月：统一 beta=0.15, T+1 执行
- 每张表标注参数版本和执行延迟

### 步骤 5：HTML 报告 ✅

- `nav_2026.html` 已重新生成
- `output/four_tables_report.html` 已重新生成

### 关键变化

T+0 → T+1 执行延迟导致数据整体下移（Sharpe 1.23→1.06, 年化 13.1%→11.1%），但策略仍跑赢三基准。T+1 为真实可执行版本。

### 验收核对

- [x] 逐年 CSV 已生成，标注 beta=0.15
- [x] system_audit.md §3 全部数据统一为 beta=0.15
- [x] 每张表标注参数版本
- [x] nav_2026.html + four_tables_report.html 已更新

---

## 提交

```
git add attribution/system_audit.md .claude/task/outcome.md
git commit -m "v190-20260618-28: 数据 — system_audit §3 逐年/regime 统一为 beta=0.15 生产参数"
```
