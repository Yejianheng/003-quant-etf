# 执行结果

> 执行时间：2026-06-18 | 方向来源：.claude/task/direction.md

## 任务：全量参数扫描切换到 T+1 (execution_lag=1)

### 步骤 1：target_vol_beta 扫描 (T+1) ✅

beta=[0.04..0.22]，等比容忍带。T+1 Sharpe 区间 1.06-1.18，0.15 生产参数 Sharpe 1.06（T+0 为 1.23）。

### 步骤 2：corr_threshold 扫描 (T+1) ✅

threshold=[-0.10..0.15]。0.0 仍最优：Sharpe 1.06，回撤 -13.6%。>0.05 回撤跳至 -17.9%。

### 步骤 3：corr_window 扫描 (T+1) ✅

window=[20,40,60,90,120]。60 回撤最优（-13.6%），120 Sharpe 最高（1.14）但回撤恶化至 -16.2%。

### 步骤 4：corr_sma_window + 趋势窗口 + 回撤阈值 + ablation (T+1) ✅

- corr_sma: sma=3 略优（Sharpe 1.10 vs 5 的 1.06），差异在噪声范围
- trend_window: T+1 下 20 天 Sharpe 最高（1.15）但 40 天回撤控制最优（-13.6%）
- dd_threshold: 全部相同，liquidate 从未触发
- ablation: T+1 下趋势过滤 ΔSharpe +0.08（替代 CB 成为第一防线），CB ΔSharpe -0.03 但 DD 改善 +3.7pp

### 步骤 5：更新 system_audit.md ✅

- §6.1-6.5 全部替换为 T+1 数据
- 每张表标注 `(T+1 可执行)` + T+0 对比列
- §6.6 熔断评估重写为 T+1 结论
- §7.2 成本假设标注 T+1 基准
- 总结判断更新

### 验收核对

- [x] 四组扫描全部 T+1
- [x] system_audit.md §6 全部标注 T+1
- [x] 全量数据版本一致（T+1, beta=0.15）
- [x] T+1 vs T+0 对比列保留（可追溯）

### T+1 vs T+0 关键差异

| 模块 | T+0 ΔSharpe | T+1 ΔSharpe | 变化本质 |
|------|:--:|:--:|------|
| 趋势过滤 | +0.71 | +0.08 | T+1 下仍是第一防线 |
| 相关性熔断 | +0.85 | -0.03 | 信号→执行延迟削弱 CB，但回撤保护仍在 |
| 波动率缩放 | 0.00 | +0.01 | 不变 |

---

## 提交

```
git add attribution/system_audit.md .claude/task/outcome.md output/beta_scan_t1.csv output/corr_threshold_scan_t1.csv output/corr_window_scan_t1.csv
git commit -m "v190-20260618-29: 数据 — §6 全量扫描统一为 T+1 可执行基准"
```
