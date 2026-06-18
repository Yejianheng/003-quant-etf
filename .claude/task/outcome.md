# 执行结果

> 执行时间：2026-06-18 | 方向来源：.claude/task/direction.md

## 任务：ewma_lambda 全区间扫描 + 相位干涉检测

### 步骤 1：lambda 单变量扫描 ✅

λ=[0.85, 0.88, 0.90, 0.92, 0.94, 0.96, 0.98, 0.99]，T+1 执行。全区间 Sharpe 1.05-1.07（Δ<0.02），换手率恒定 68.6。λ 是系统中影响最小的参数。

### 步骤 2：lambda × trend_window 交叉扫描 ✅

3×5=15 组合。无相位干涉——λ 和 trend_window 独立作用。trend_window 主导排序（w=20 Sharpe 最高 1.14-1.16，w=50 最低 0.94-0.96），λ 仅产生 0.01-0.02 次级差异。

### 步骤 3：极端子区间验证 ✅

2015H2/2020H1/2022H1 三个危机区间。w=20 在所有危机中表现更好（更快反应）但换手率更高（2015H2: 105/yr vs 71/yr）。生产参数（w=40, λ=0.94）回撤控制最优。

### 步骤 4：更新 system_audit.md ✅

§6.7 从"遗留未测参数"替换为完整 lambda 扫描 + 交叉矩阵 + 极端区间验证。

### 结论

**RiskMetrics 0.94 确认鲁棒，无需修正。**

### 验收核对

- [x] lambda 单变量扫描完成
- [x] lambda × trend_window 矩阵完成
- [x] 极端子区间验证完成
- [x] system_audit.md §6.7 已替换
- [x] 结论：0.94 确认鲁棒

---

## 提交

```
git add attribution/system_audit.md .claude/task/outcome.md
git commit -m "v190-20260618-30: 数据 — ewma_lambda 全区间扫描，确认 0.94 鲁棒，无相位干涉"
```
